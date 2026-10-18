"""Bundled Tesseract checks run before unrelated component installation."""
import subprocess

import pytest

import install
from scripts import install_support as support, install_ui


def test_missing_wheel_has_actionable_error_without_backend_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(support, 'tesserocr_model_data', lambda path: tmp_path)
    monkeypatch.setattr(support, 'pip_install', lambda *args: (_ for _ in ()).throw(subprocess.CalledProcessError(1, 'pip')))
    monkeypatch.setattr(support, 'configure_tesserocr', lambda *args: pytest.fail('Do not persist a failed backend'))
    with pytest.raises(RuntimeError, match='Windows wheels are distributed separately from PyPI'):
        support.install_tesserocr('target')


def test_local_wheel_install_keeps_api_range_and_verifies_models(monkeypatch, tmp_path):
    wheel = tmp_path/'tesserocr-2.8.0-cp312-cp312-win_amd64.whl'
    wheel.touch()
    calls = []
    monkeypatch.setattr(support, 'tesserocr_model_data', lambda path: tmp_path)
    monkeypatch.setattr(support, 'pip_install', lambda *args: calls.append(args))
    monkeypatch.setattr(support, 'configure_tesserocr', lambda *args: calls.append(args))
    support.install_tesserocr('target', str(tmp_path), str(wheel))
    assert calls == [('target', '--only-binary=tesserocr', '--force-reinstall', str(wheel), 'tesserocr>=2.7,<3'), ('target', str(tmp_path))]


def test_bad_local_wheel_path_does_not_contact_pip(monkeypatch, tmp_path):
    monkeypatch.setattr(support, 'tesserocr_model_data', lambda path: tmp_path)
    monkeypatch.setattr(support, 'pip_install', lambda *args: pytest.fail('Invalid local wheel must fail first'))
    with pytest.raises(ValueError, match='existing tesserocr .whl'):
        support.install_tesserocr('target', wheel=str(tmp_path/'missing.whl'))


def test_bundled_failure_stops_before_other_component_installation(monkeypatch):
    monkeypatch.setattr(install, 'configure_pip', lambda *args: None)
    monkeypatch.setattr(install, 'app_environment', lambda *args: 'target')
    monkeypatch.setattr(install, 'install_tesserocr', lambda *args: (_ for _ in ()).throw(RuntimeError('no wheel')))
    monkeypatch.setattr(install, 'pip_install', lambda *args: pytest.fail('Other packages must not be installed yet'))
    with pytest.raises(RuntimeError, match='no wheel'):
        install.main(['--device', 'cpu', '--tesseract-backend', 'tesserocr'])


def test_ui_only_passes_wheel_for_bundled_backend():
    wheel = 'C:/Approved Packages/tesserocr-2.8.0-cp312-cp312-win_amd64.whl'
    args = install_ui.install_arguments({'backend': 'tesserocr', 'tesserocr_wheel': wheel})
    assert args[args.index('--tesserocr-wheel')+1] == wheel
    for backend in ['skip', 'auto', 'pytesseract']:
        assert '--tesserocr-wheel' not in install_ui.install_arguments({'backend': backend, 'tesserocr_wheel': wheel})
    with pytest.raises(ValueError, match='not a command option'):
        install_ui.install_arguments({'backend': 'tesserocr', 'tesserocr_wheel': '--help'})


def test_cli_rejects_wheel_for_other_backend_before_installing(monkeypatch):
    monkeypatch.setattr(install, 'configure_pip', lambda *args: None)
    monkeypatch.setattr(install, 'app_environment', lambda *args: pytest.fail('Invalid options must fail first'))
    with pytest.raises(SystemExit):
        install.main(['--without-tesseract', '--tesserocr-wheel', 'unused.whl'])


def test_installer_keeps_bundled_backend_and_its_models_without_executable(monkeypatch, tmp_path):
    import ocrbench.native as native
    monkeypatch.setattr(native, 'tesseract_backend', lambda: 'tesserocr')
    monkeypatch.setattr(native, 'tesseract_command', lambda: None)
    monkeypatch.setattr(native, 'tesserocr_data', lambda: tmp_path)
    options = install_ui.defaults()
    assert options['backend'] == 'tesserocr'
    assert options['tessdata_path'] == str(tmp_path)
