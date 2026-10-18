"""Compatibility policies and real pip resolution against a small older feed."""
import json
import subprocess
import sys
import zipfile
try:
    import tomllib
except ImportError:
    from pip._vendor import tomli as tomllib

import pytest
from packaging.requirements import Requirement
from scripts import install_support as support, install_ui


@pytest.mark.parametrize('minor',[10,11,12,13])
def test_supported_python_minors_are_not_locked_to_312(monkeypatch,minor):
    monkeypatch.setattr(support.subprocess,'check_output',lambda *a,**k:json.dumps([3,minor,64]))
    support.validate_python('target')


@pytest.mark.parametrize('driver,expected',[('13.3','cuda13'),('13.0','cuda13'),('12.8','cuda12')])
@pytest.mark.parametrize('label',['CUDA Version: ','CUDA UMD Version: '])
def test_auto_cuda_matches_driver(monkeypatch,driver,expected,label):
    monkeypatch.setattr(support.shutil,'which',lambda name:'nvidia-smi')
    monkeypatch.setattr(support.subprocess,'check_output',lambda *a,**k:label+driver)
    assert support.cuda_family() == expected


def test_old_driver_has_an_actionable_error(monkeypatch):
    monkeypatch.setattr(support.shutil,'which',lambda name:'nvidia-smi')
    monkeypatch.setattr(support.subprocess,'check_output',lambda *a,**k:'CUDA Version: 12.6')
    with pytest.raises(RuntimeError,match='Update the driver or install CPU'):
        support.cuda_family()


def test_private_gpu_sources_do_not_assume_cuda13_or_add_public_hosts(monkeypatch):
    calls=[]
    monkeypatch.setattr(support,'uses_public_pypi',lambda python:False)
    monkeypatch.setattr(support,'cuda_family',lambda *a:pytest.fail('Private feed owns its GPU builds'))
    monkeypatch.setattr(support,'torch_needs_repair',lambda python:False)
    monkeypatch.setattr(support,'pip_install',lambda *a:calls.append(a))
    for engine in ['easyocr','paddleocr']:
        support.install_gpu_framework('target',engine)
    assert all('https://' not in str(arg) and '==' not in str(arg) for call in calls for arg in call)


def test_cpu_torch_in_gpu_environment_is_re_resolved(monkeypatch):
    calls=[]
    monkeypatch.setattr(support,'uses_public_pypi',lambda python:True)
    monkeypatch.setattr(support,'torch_needs_repair',lambda python:True)
    monkeypatch.setattr(support,'pip_install',lambda *a:calls.append(a))
    support.install_gpu_framework('target','easyocr','cuda12')
    assert '--force-reinstall' in calls[0] and '--index-url' in calls[0]
    assert 'https://download.pytorch.org/whl/cu128' in calls[0]


def test_available_older_engine_versions_are_within_supported_ranges():
    project=tomllib.loads((support.ROOT/'pyproject.toml').read_text())
    # FastAPI can accept Pydantic 1, but this app uses the v2 validator API.
    pydantic=next(Requirement(item) for item in project['project']['dependencies'] if item.startswith('pydantic'))
    assert '2.7.0' in pydantic.specifier and '1.10.0' not in pydantic.specifier
    extras=project['project']['optional-dependencies']
    versions={'rapidocr':'3.0.0','onnxruntime':'1.20.1','onnxruntime-gpu':'1.20.2',
              'easyocr':'1.7.1','torch':'2.7.1','torchvision':'0.22.1',
              'paddleocr':'3.1.0','paddlepaddle':'3.0.0','pytesseract':'0.3.13'}
    for name in ['rapidocr','rapidocr-gpu','easyocr','easyocr-gpu','paddleocr','paddleocr-gpu','tesseract']:
        for text in extras[name]:
            req=Requirement(text)
            assert versions[req.name] in req.specifier, text
            assert not any(spec.operator in ('==','===') for spec in req.specifier)
    req=Requirement(next(line for line in (support.ROOT/'requirements-tesserocr.txt').read_text().splitlines() if line.startswith('tesserocr')))
    assert '2.8.0' in req.specifier


def test_real_pip_pairs_older_torch_and_vision_from_a_local_feed(tmp_path):
    for name,version,dependency in [('torch','2.7.1',''),('torchvision','0.22.1','Requires-Dist: torch==2.7.1\n')]:
        info=f'{name}-{version}.dist-info'
        with zipfile.ZipFile(tmp_path/f'{name}-{version}-py3-none-any.whl','w') as wheel:
            wheel.writestr(info+'/METADATA',f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n'+dependency)
            wheel.writestr(info+'/WHEEL','Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
            wheel.writestr(info+'/RECORD','')
    report=tmp_path/'report.json'
    subprocess.run([sys.executable,'-m','pip','install','--dry-run','--ignore-installed','--no-index',
                    '--find-links',str(tmp_path),'--report',str(report),'torch>=2.4,<3','torchvision>=0.19,<1'],
                   check=True,capture_output=True,text=True)
    resolved={item['metadata']['name']:item['metadata']['version'] for item in json.loads(report.read_text())['install']}
    assert resolved == {'torch':'2.7.1','torchvision':'0.22.1'}


def test_ui_routes_cuda_selection_and_rejects_unknown_values():
    assert '--cuda' in install_ui.install_arguments({'backend':'skip','device':'gpu','cuda':'cuda12'})
    with pytest.raises(ValueError,match='CUDA compatibility'):
        install_ui.install_arguments({'cuda':'cuda99'})


def test_old_controller_pip_is_upgraded_before_using_python_flag(monkeypatch):
    calls=[]
    monkeypatch.setattr(support.subprocess,'check_output',lambda *a,**k:'pip 22.0 from pip (python 3.10)')
    monkeypatch.setattr(support,'run',lambda *a,**k:calls.append(a[0]))
    assert support.pip_controller() == sys.executable
    assert calls == [[sys.executable,'-m','pip','install','--disable-pip-version-check','pip>=23.3']]
