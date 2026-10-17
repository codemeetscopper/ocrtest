import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from scripts import install_support as installer


def test_explicit_index_removes_extra_sources_and_keeps_ca(monkeypatch, tmp_path):
    monkeypatch.setattr(installer, '_pip_env', None)
    monkeypatch.setenv('PIP_EXTRA_INDEX_URL', 'https://public.example/simple')
    monkeypatch.setenv('PIP_FIND_LINKS', 'https://public.example/wheels')
    monkeypatch.setenv('PIP_TRUSTED_HOST', 'artifactory.example')
    cert = tmp_path/'corporate.pem'
    cert.touch()
    installer.configure_pip('https://artifactory.example/api/pypi/python-virtual/simple', str(cert))
    env = installer._pip_env
    assert env['PIP_CONFIG_FILE'] == os.devnull
    assert env['PIP_INDEX_URL'] == 'https://artifactory.example/api/pypi/python-virtual/simple'
    assert 'PIP_EXTRA_INDEX_URL' not in env and 'PIP_FIND_LINKS' not in env
    assert 'PIP_TRUSTED_HOST' not in env
    assert env['PIP_CERT'] == str(cert)
    # Ask real pip which sources it would use; this performs no network request.
    code = ('import json;from pip._internal.commands import create_command;'
            'o,a=create_command("install").parse_args([]);'
            'print(json.dumps([o.index_url,o.extra_index_urls,o.find_links]))')
    result = subprocess.check_output([sys.executable,'-c',code],env=env,text=True)
    assert json.loads(result) == [env['PIP_INDEX_URL'], [], []]


def test_default_install_honours_existing_corporate_pip_config(monkeypatch):
    monkeypatch.setattr(installer, '_pip_env', {})
    installer.configure_pip()
    assert installer._pip_env is None


def test_compiled_tesserocr_module_is_discovered_in_isolated_environment(monkeypatch,tmp_path):
    import ocrbench.native as native
    import ocrbench.environments as environments
    from ocrbench.storage import save_json
    monkeypatch.setattr(native,'ROOT',tmp_path)
    monkeypatch.setattr(environments,'ROOT',tmp_path)
    monkeypatch.delenv('OCRBENCH_TESSERACT_BACKEND',raising=False)
    save_json(tmp_path/'.engines/native-tools.json',{'backend':'tesserocr'})
    directory=tmp_path/'.engines/tesseract'
    (directory/'Scripts').mkdir(parents=True)
    (directory/'Scripts/python.exe').touch()
    site=directory/'Lib/site-packages';site.mkdir(parents=True)
    (site/'tesserocr.cp312-win_amd64.pyd').touch()
    assert environments.discovered_interpreter('tesseract') == str(directory/'Scripts/python.exe')


def test_index_credentials_are_not_written_in_command_log(monkeypatch, capsys):
    monkeypatch.setattr(installer, '_pip_env', None)
    installer.configure_pip('https://user:example-secret@artifactory.example/simple')
    monkeypatch.setattr(installer,'pip_controller',lambda:sys.executable)
    monkeypatch.setattr(installer.subprocess,'run',lambda *args,**kwargs:None)
    installer.pip_install('target-python','tesserocr==2.10.0')
    assert 'example-secret' not in capsys.readouterr().out


def test_bundled_backend_verification_saves_library_and_model_settings(monkeypatch,tmp_path):
    import ocrbench.native as native
    monkeypatch.setattr(installer,'ROOT',tmp_path)
    monkeypatch.setattr(native,'ROOT',tmp_path)
    data = tmp_path/'models'
    data.mkdir()
    (data/'eng.traineddata').touch()
    calls = []
    monkeypatch.setattr(installer,'run',lambda args:calls.append(args))
    installer.configure_tesserocr('approved-python',str(data))
    assert calls[0][0] == 'approved-python'
    assert 'import sys,tesserocr' in calls[0][2]
    assert native.tesseract_backend() == 'tesserocr'
    assert native.tesserocr_data() == data


def test_default_installer_uses_tesserocr_requirements(monkeypatch,tmp_path):
    import install as entry
    monkeypatch.setattr(sys,'argv',['install.py','--device','cpu','--tessdata-path',str(tmp_path)])
    calls=[]
    monkeypatch.setattr(entry,'configure_pip',lambda *args:None)
    monkeypatch.setattr(entry,'app_environment',lambda *args:'python312')
    monkeypatch.setattr(entry,'pip_install',lambda python,*args:calls.append(args))
    monkeypatch.setattr(entry,'configure_tesserocr',lambda python,data:calls.append(('models',data)))
    monkeypatch.setattr(entry,'ensure_tesseract',lambda *args:pytest.fail('Must not require tesseract.exe'))
    entry.main()
    assert calls == [('-r',str(entry.ROOT/'requirements-tesserocr.txt')),('models',str(tmp_path))]


def fake_tesserocr(monkeypatch,tmp_path,empty=False):
    import importlib.metadata
    import ocrbench.native as native
    monkeypatch.setenv('OMP_THREAD_LIMIT',os.environ.get('OMP_THREAD_LIMIT','4'))
    data=tmp_path/'models';data.mkdir();(data/'eng.traineddata').write_bytes(b'test model')
    calls=[]
    class Line:
        def GetUTF8Text(self,level):return '68%\n'
        def BoundingBox(self,level):return (3,4,30,18)
        def Confidence(self,level):return 96.5
    class API:
        def __init__(self,**params):calls.append(params)
        def SetImage(self,image):pass
        def Recognize(self):pass
        def GetIterator(self):return None if empty else object()
        def Clear(self):calls.append('cleared')
    module=SimpleNamespace(PyTessBaseAPI=API,RIL=SimpleNamespace(TEXTLINE=2),iterate_level=lambda *a:[Line()],tesseract_version=lambda:'5.5.2')
    monkeypatch.setitem(sys.modules,'tesserocr',module)
    monkeypatch.setattr(importlib.metadata,'version',lambda package:'2.10.0')
    monkeypatch.setattr(native,'tesseract_command',lambda:pytest.fail('Bundled backend must not launch an executable'))
    return data,calls


@pytest.mark.parametrize('empty',[False,True])
def test_bundled_tesseract_produces_line_regions_without_executable(monkeypatch,tmp_path,empty):
    import numpy as np
    from ocrbench.worker import Adapter
    data,calls=fake_tesserocr(monkeypatch,tmp_path,empty)
    adapter=Adapter({'engine':'tesseract','device':'cpu','languages':['en'],'threads':2,
                     'options':{'backend':'tesserocr','tessdata_dir':str(data)}})
    result=adapter.predict(np.zeros((40,60,3),dtype=np.uint8))
    assert calls[-1] == 'cleared'
    assert adapter.metadata()['runtime']['binding'] == 'tesserocr'
    assert adapter.metadata()['models'][0]['sha256']
    if empty:
        assert result == []
    else:
        assert result[0]['text'] == '68%'
        assert result[0]['confidence'] == .965
        assert result[0]['polygon'] == [[3.,4.],[30.,4.],[30.,18.],[3.,18.]]


def test_explicit_bundled_backend_does_not_accept_cli_config(monkeypatch,tmp_path):
    from ocrbench.worker import Adapter
    data,_=fake_tesserocr(monkeypatch,tmp_path)
    with pytest.raises(ValueError,match='options.psm'):
        Adapter({'engine':'tesseract','device':'cpu','languages':['en'],'threads':2,
                 'options':{'backend':'tesserocr','tessdata_dir':str(data),'config':'--psm 6'}})
