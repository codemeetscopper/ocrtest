import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import install_support as installer


def running_venv(monkeypatch, tmp_path):
    directory = tmp_path/'external venv'
    python = installer.python_in(directory)
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(sys, 'prefix', str(directory))
    monkeypatch.setattr(sys, 'base_prefix', str(tmp_path/'base python'))
    monkeypatch.setattr(sys, 'executable', str(python))
    monkeypatch.setattr(installer, 'ROOT', tmp_path/'project')
    return python


def test_running_venv_wins_over_existing_project_environment(monkeypatch, tmp_path):
    python = running_venv(monkeypatch, tmp_path)
    local = installer.python_in(installer.ROOT/'.venv')
    local.parent.mkdir(parents=True)
    local.touch()
    calls = []
    monkeypatch.setattr(installer, 'validate_python', lambda target: calls.append(('validate', target)))
    monkeypatch.setattr(installer, 'pip_install', lambda *args: calls.append(('pip', *args)))
    monkeypatch.setattr(installer, 'environment', lambda *args: pytest.fail('Must not create/reuse project .venv'))
    assert installer.app_python() == python
    assert installer.app_environment('base-python') == python
    assert calls == [('validate', python), ('pip', python, 'pip>=23.3')]


def test_outside_venv_uses_project_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'prefix', sys.base_prefix)
    monkeypatch.delattr(sys, 'real_prefix', raising=False)
    monkeypatch.setattr(installer, 'ROOT', tmp_path)
    calls = []
    local = installer.python_in(tmp_path/'.venv')
    monkeypatch.setattr(installer, 'environment', lambda *args: calls.append(args) or local)
    assert installer.app_python() == local
    assert installer.app_environment('chosen-python312') == local
    assert calls == [(tmp_path/'.venv', 'chosen-python312')]


def test_unsupported_running_venv_fails_without_creating_another(monkeypatch, tmp_path):
    running_venv(monkeypatch, tmp_path)
    monkeypatch.setattr(installer.subprocess, 'check_output', lambda *args, **kwargs: '[3, 14, 64]')
    monkeypatch.setattr(installer, 'pip_install', lambda *args: pytest.fail('Unsupported venv must not be modified'))
    with pytest.raises(RuntimeError, match='Python 3.10-3.13'):
        installer.app_environment('other-python312')
    assert not (installer.ROOT/'.venv').exists()


@pytest.mark.parametrize('device', ['cpu', 'gpu'])
def test_entry_installs_app_into_running_venv_and_preserves_gpu_isolation(monkeypatch, tmp_path, device):
    import install as entry
    python = running_venv(monkeypatch, tmp_path)
    monkeypatch.setattr(entry, 'ROOT', installer.ROOT)
    monkeypatch.setattr(sys, 'argv', ['install.py', '--without-tesseract', '--device', device])
    monkeypatch.setattr(installer, 'validate_python', lambda target: None)
    monkeypatch.setattr(installer, 'environment', lambda *args: pytest.fail('Must not create project .venv'))
    calls = []
    monkeypatch.setattr(installer, 'pip_install', lambda *args: calls.append(args))
    monkeypatch.setattr(entry, 'pip_install', installer.pip_install)
    engines = []
    monkeypatch.setattr(entry, 'setup_engine', lambda *args: engines.append(args))
    entry.main()
    assert calls == [(python, 'pip>=23.3'), (python, '-r', str(entry.ROOT/'requirements.txt'))]
    assert engines == ([(engine, 'gpu', str(python)) for engine in ('rapidocr', 'paddleocr', 'easyocr')] if device == 'gpu' else [])
    assert not (entry.ROOT/'.venv').exists()


def test_launcher_prefers_running_venv(monkeypatch, tmp_path):
    import start
    python = running_venv(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, 'argv', ['start.py', '--port', '8766'])
    calls = []
    monkeypatch.setattr(start.subprocess, 'call', lambda args, **kwargs: calls.append(args) or 0)
    assert start.main() == 0
    assert calls == [[str(python), '-m', 'ocrbench', 'serve', '--port', '8766']]


def test_direct_venv_python_without_activation_reuses_it_for_install_and_launch(tmp_path):
    # Exercise real interpreter prefixes without installing packages or accessing a feed.
    directory = tmp_path/'external venv'
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(directory)], check=True)
    python = installer.python_in(directory)
    project = tmp_path/'project'
    project.mkdir()
    code = '''
import json, sys
from pathlib import Path
from scripts import install_support as support
import start
support.ROOT = Path(sys.argv[1])
installs = []
support.pip_install = lambda *args: installs.append([str(a) for a in args])
target = support.app_environment('unused-base-python')
launched = []
start.subprocess.call = lambda args, **kwargs: launched.append(args) or 0
sys.argv = ['start.py']
start.main()
print(json.dumps({'target': str(target), 'installs': installs, 'launched': launched}))
'''
    result = subprocess.check_output([str(python), '-c', code, str(project)], cwd=installer.ROOT, text=True)
    record = json.loads(result.splitlines()[-1])
    assert Path(record['target']) == python
    assert record['installs'] == [[str(python), 'pip>=23.3']]
    assert record['launched'][0][0] == str(python)
    assert not (project/'.venv').exists()
