"""Inspect and remove the app registration without deleting shared environments."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from scripts.install_support import app_python, pip_controller, run

PACKAGES = ('automotive-ocr-bench', 'rapidocr', 'paddleocr', 'easyocr', 'pytesseract', 'tesserocr')


def inspect_installation(python=None):
    target = Path(python) if python else app_python()
    result = {'installed': False, 'version': '', 'packages': {}, 'target': str(target)}
    if not target.is_file():
        return result
    # Inspect the target's site-packages only. Source-tree egg-info survives pip
    # uninstall and must not be mistaken for an installed application.
    code = ('import json,sysconfig,importlib.metadata as m; '
            'print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version '
            'for d in m.distributions(path=[sysconfig.get_paths()["purelib"]]) '
            f'if d.metadata["Name"].lower().replace("_","-") in {PACKAGES!r}}}))')
    try:
        packages = json.loads(subprocess.check_output([str(target), '-I', '-c', code], text=True, timeout=20))
        result.update(packages=packages, version=packages.get('automotive-ocr-bench', ''),
                      installed=bool(packages.get('automotive-ocr-bench')))
    except (OSError, ValueError, subprocess.SubprocessError):
        result['error'] = 'Could not inspect this Python environment.'
    return result


def uninstall_app():
    target = app_python()
    if not inspect_installation(target)['installed']:
        print('OCR Bench is not installed in this environment.')
        return
    # Editable source egg-info in the project cwd can shadow the installed
    # distribution and make pip report success without removing any files.
    with tempfile.TemporaryDirectory(prefix='ocrbench-uninstall-') as working:
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        run([pip_controller(), '-I', '-m', 'pip', '--python', target, 'uninstall', '--yes', 'automotive-ocr-bench'], cwd=working, env=env)
    remaining = inspect_installation(target)
    if remaining.get('error') or remaining['installed']:
        raise RuntimeError('Uninstall could not be verified: OCR Bench is still registered, or the environment could not be inspected. Close the workbench and retry.')
    print('OCR Bench removed from this environment. Shared libraries, environments, source files, models and run history were kept.')
