import json
from pathlib import Path
import pytest
import importlib.util
import sys
from scripts import install_support as installer


def test_unsupported_python_fails_before_environment_creation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(installer.subprocess, 'check_output', lambda *a, **k: json.dumps([3, 14, 64]))
    monkeypatch.setattr(installer, 'run', lambda args: calls.append(args))
    with pytest.raises(RuntimeError, match='Python 3.12'):
        installer.environment(tmp_path/'new env', Path('Python 314/python.exe'))
    assert calls == []


@pytest.mark.parametrize('engine,framework', [('easyocr', 'torch==2.14.1'), ('paddleocr', 'paddlepaddle-gpu==3.3.1')])
def test_gpu_framework_installed_before_ocr_extra(monkeypatch, tmp_path, engine, framework):
    target = tmp_path/'GPU env'/'python.exe'
    calls = []
    monkeypatch.setattr(installer, 'ROOT', tmp_path)
    monkeypatch.setattr(installer, 'environment', lambda directory, python: target)
    monkeypatch.setattr(installer, 'pip_install', lambda python, *args: calls.append((python, args)))
    installer.setup_engine(engine, 'gpu', 'python312')
    assert calls[0][0] == target and framework in calls[0][1]
    assert calls[-1][1] == ('-e', f'{tmp_path}[{engine}-gpu]')
    assert all('paddlepaddle==3.3.1' not in args for _, args in calls)


def test_cpu_only_engine_rejected_before_installation(monkeypatch):
    monkeypatch.setattr(installer, 'environment', lambda *a: pytest.fail('must not create an environment'))
    with pytest.raises(ValueError, match='CPU only'):
        installer.setup_engine('tesseract', 'gpu', 'python312')


def test_managed_tesseract_discovered_without_system_path(monkeypatch, tmp_path):
    import ocrbench.native as native
    monkeypatch.setattr(native, 'ROOT', tmp_path)
    monkeypatch.setattr(native.shutil, 'which', lambda name: None)
    monkeypatch.delenv('OCRBENCH_TESSERACT', raising=False)
    target = tmp_path/'.engines/tesseract-native/Library/bin/tesseract.exe'
    target.parent.mkdir(parents=True)
    target.touch()
    assert native.tesseract_command() == str(target)


def test_tesseract_explicit_override_has_priority(monkeypatch, tmp_path):
    import ocrbench.native as native
    target = tmp_path/'custom executable.exe'
    target.touch()
    monkeypatch.setenv('OCRBENCH_TESSERACT', str(target))
    assert native.tesseract_command() == str(target)


def test_portable_tesseract_language_data_discovery(monkeypatch, tmp_path):
    from ocrbench.native import tesseract_data
    monkeypatch.delenv('TESSDATA_PREFIX', raising=False)
    executable = tmp_path/'Library/bin/tesseract.exe'
    data = tmp_path/'share/tessdata'
    data.mkdir(parents=True)
    (data/'eng.traineddata').touch()
    assert tesseract_data(executable) == data


@pytest.mark.parametrize('engine,package', [('rapidocr','rapidocr'),('paddleocr','paddleocr'),('easyocr','easyocr'),('tesseract','pytesseract')])
def test_requirements_engines_work_in_app_environment(engine, package, tmp_path):
    if importlib.util.find_spec(package) is None:
        pytest.skip('Full requirements installation not present')
    if engine == 'tesseract':
        from ocrbench.native import tesseract_command
        if not tesseract_command():
            pytest.skip('Native runtime not installed')
    from ocrbench.storage import ROOT
    from ocrbench.process import Worker
    worker = Worker({'engine': engine, 'device': 'cpu', 'languages': ['en'], 'threads': 4,
                     'python_path': sys.executable, 'options': {}}, tmp_path/f'{engine}.log', 180)
    try:
        result = worker.predict(ROOT/'data/fixtures/pivi-pro.jpg', metadata=True)
        assert result['predictions']
        assert result['identity']['observed_device'] == 'cpu'
        assert Path(result['identity']['interpreter']) == Path(sys.executable)
        if engine == 'tesseract':
            assert result['identity']['models']
            assert result['identity']['languages'] == ['eng']
            assert result['identity']['runtime']['tessdata']
    finally:
        worker.close()
