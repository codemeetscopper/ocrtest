"""Recover broken pip without downloading a bootstrap executable or wheel."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import install_support as support
from scripts import install_lifecycle as lifecycle


def test_controller_repairs_broken_pip_before_installing(monkeypatch):
    calls = []
    responses = iter([subprocess.CalledProcessError(1, 'pip'), 'pip 25.0 from pip (python 3.12)'])

    def probe(*args, **kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(support.subprocess, 'check_output', probe)
    monkeypatch.setattr(support, 'repair_pip', lambda: calls.append('repair'))
    assert support.pip_controller() == sys.executable
    assert calls == ['repair']


def test_failed_repair_stops_before_dependency_install(monkeypatch):
    monkeypatch.setattr(support.subprocess, 'check_output', lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, 'pip')))
    monkeypatch.setattr(support, 'repair_pip', lambda: None)
    monkeypatch.setattr(support, 'run', lambda *a, **k: pytest.fail('Must not run dependency installation'))
    with pytest.raises(RuntimeError, match='still unusable after repair'):
        support.pip_install('target', 'rapidocr')


def test_uninstall_inspection_failure_is_an_error(monkeypatch):
    monkeypatch.setattr(lifecycle, 'inspect_installation', lambda target: {'installed': False, 'error': 'unavailable'})
    monkeypatch.setattr(lifecycle, 'run', lambda *a, **k: pytest.fail('Must not uninstall an uninspectable environment'))
    with pytest.raises(RuntimeError, match='could not inspect'):
        lifecycle.uninstall_app()


@pytest.mark.parametrize('missing', ['packaging/tags.py', 'rich/traceback.py'])
def test_real_offline_repair_of_newer_pip_with_missing_vendor_file(tmp_path, missing):
    directory = tmp_path/'broken venv'
    subprocess.run([sys.executable, '-m', 'venv', str(directory)], check=True, capture_output=True)
    python = support.python_in(directory)
    site = Path(subprocess.check_output([str(python), '-I', '-c', 'import sysconfig;print(sysconfig.get_paths()["purelib"])'], text=True).strip())
    vendor_file = site/'pip/_vendor'/missing
    assert vendor_file.is_file()
    vendor_file.unlink()
    metadata = next(site.glob('pip-*.dist-info/METADATA'))
    text = metadata.read_text(encoding='utf-8')
    text = '\n'.join('Version: 99.0' if line.startswith('Version: ') else line for line in text.splitlines())+'\n'
    metadata.write_text(text, encoding='utf-8')
    broken = subprocess.run([str(python), '-I', '-c', 'from pip._internal.commands import create_command;create_command("install")'], capture_output=True, text=True)
    assert broken.returncode != 0 and vendor_file.stem in broken.stderr
    # Reproduce the previous failed recovery: newer metadata defeats ensurepip.
    subprocess.run([str(python), '-m', 'ensurepip', '--upgrade'], check=True, capture_output=True)
    assert not vendor_file.exists()

    config = tmp_path/'pip.ini'
    config.write_text('[global]\nindex-url = https://fake-token@unreachable.invalid/simple\n', encoding='utf-8')
    before = config.read_bytes()
    env = os.environ.copy()
    env.update(PIP_CONFIG_FILE=str(config), PIP_NO_INDEX='1', PIP_REQUIRE_HASHES='1')
    # Repair another interpreter, just as GPU setup repairs its isolated venv.
    code = 'import sys;from scripts.install_support import ensure_target_pip;ensure_target_pip(sys.argv[1])'
    repaired = subprocess.run([sys.executable, '-c', code, str(python)], cwd=support.ROOT, env=env, capture_output=True, text=True)
    assert repaired.returncode == 0, repaired.stdout+repaired.stderr
    assert vendor_file.is_file()
    assert config.read_bytes() == before
    assert 'fake-token' not in repaired.stdout+repaired.stderr
    subprocess.run([str(python), '-m', 'pip', '--version'], check=True, capture_output=True, env=env)
    # A real vendored import catches the original failure, rather than only metadata.
    subprocess.run([str(python), '-I', '-c', 'from pip._vendor.packaging.tags import sys_tags;assert next(sys_tags())'], check=True, capture_output=True)
