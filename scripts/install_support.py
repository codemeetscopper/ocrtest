"""Python-only provisioning helpers; never invoke a shell or activation script."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
ENGINES = ('rapidocr', 'paddleocr', 'easyocr', 'tesseract')
_pip_env = None


def configure_pip(index_url=None, cert=None):
    """Use corporate pip defaults, or one explicit index with no extra sources."""
    global _pip_env
    _pip_env = None
    if index_url or cert:
        env = os.environ.copy()
        if index_url:
            parsed = urlsplit(index_url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                raise ValueError('--index-url must be a valid HTTP(S) PyPI simple-index URL.')
            if parsed.query or parsed.fragment:
                raise ValueError('Use a simple-index URL without query parameters/fragments and approved pip authentication.')
            env['PIP_CONFIG_FILE'] = os.devnull
            env['PIP_INDEX_URL'] = index_url
            for key in ('PIP_EXTRA_INDEX_URL', 'PIP_FIND_LINKS', 'PIP_NO_INDEX', 'PIP_TRUSTED_HOST'):
                env.pop(key, None)
        if cert:
            path = Path(cert).expanduser().resolve()
            if not path.is_file():
                raise ValueError('--cert must be an existing corporate CA bundle.')
            env['PIP_CERT'] = str(path)
        env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
        _pip_env = env


def run(args, **kwargs):
    print('> ' + subprocess.list2cmdline([str(a) for a in args]), flush=True)
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def python_in(directory):
    return Path(directory) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def active_python():
    """Detect the running venv, including direct invocation without activation."""
    if sys.prefix != sys.base_prefix or hasattr(sys, 'real_prefix'):
        return Path(sys.executable)
    return None


def app_python():
    """Prefer the running venv over a project-local environment."""
    return active_python() or python_in(ROOT/'.venv')


def app_environment(python):
    """Install into the running venv, creating a local one only when needed."""
    target = active_python()
    if target is None:
        return environment(ROOT/'.venv', python)
    validate_python(target)
    print(f'Using current virtual environment: {sys.prefix}', flush=True)
    pip_install(target, 'pip>=25')
    return target


def validate_python(python):
    version = json.loads(subprocess.check_output([str(python), '-c',
                        'import sys,json,struct;print(json.dumps([*sys.version_info[:2],struct.calcsize("P")*8]))'], text=True))
    if version != [3, 12, 64]:
        raise RuntimeError('Full OCR installation requires 64-bit Python 3.12. Pass --python C:/Python312/python.exe.')


def pip_controller():
    if subprocess.run([sys.executable, '-m', 'pip', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run([sys.executable, '-m', 'ensurepip', '--upgrade'])
    return sys.executable


def pip_install(python, *requirements):
    run([pip_controller(), '-m', 'pip', '--python', python, 'install', '--disable-pip-version-check', *requirements],
        **({'env': _pip_env} if _pip_env is not None else {}))


def environment(directory, python):
    target = python_in(directory)
    if not target.exists():
        validate_python(python)
        run([python, '-m', 'venv', '--without-pip', directory])
    validate_python(target)
    pip_install(target, 'pip>=25')
    return target


def has_nvidia():
    executable = shutil.which('nvidia-smi')
    if not executable:
        return False
    try:
        return bool(subprocess.check_output([executable, '--query-gpu=name', '--format=csv,noheader'],
                                           text=True, timeout=15).strip())
    except (OSError, subprocess.SubprocessError):
        return False


def setup_engine(engine, device, python, tesseract_path=None, tessdata_path=None, tesseract_backend='pytesseract'):
    if engine not in ENGINES or device not in ('cpu', 'gpu'):
        raise ValueError('Unknown engine or device')
    if engine == 'tesseract' and device == 'gpu':
        raise ValueError('Tesseract supports CPU only.')
    if engine == 'tesseract' and tesseract_backend == 'pytesseract':
        ensure_tesseract(tesseract_path, tessdata_path)
    extra = engine + ('-gpu' if device == 'gpu' else '')
    target = environment(ROOT/'.engines'/extra, python)
    if engine == 'easyocr':
        build = 'cu130' if device == 'gpu' else 'cpu'
        pip_install(target, f'torch==2.14.1+{build}', f'torchvision==0.29.1+{build}')
    if engine == 'paddleocr' and device == 'gpu':
        pip_install(target, 'paddlepaddle-gpu==3.3.1')
    pip_install(target, '-e', f'{ROOT}[{extra}]')
    if engine == 'tesseract' and tesseract_backend == 'tesserocr':
        pip_install(target, '--only-binary=tesserocr', 'tesserocr==2.10.0')
        configure_tesserocr(target, tessdata_path)
    print(f'{engine} {device}: {target}', flush=True)
    return target


def ensure_tesseract(tesseract_path=None, tessdata_path=None):
    """Validate an existing approved runtime; never download another manager."""
    sys.path.insert(0, str(ROOT))
    from ocrbench.native import tesseract_command, tesseract_data
    from ocrbench.storage import save_json
    explicit_data = Path(tessdata_path).expanduser().resolve() if tessdata_path else None
    if explicit_data and not (explicit_data/'eng.traineddata').is_file():
        raise RuntimeError('--tessdata-path must contain eng.traineddata.')
    def verify(command):
        env = os.environ.copy()
        data = explicit_data or tesseract_data(command)
        if data:
            env['TESSDATA_PREFIX'] = str(data)
        run([command, '--version'], env=env)
        languages = subprocess.check_output([command, '--list-langs'], text=True, env=env)
        if 'eng' not in languages.splitlines():
            raise RuntimeError('Tesseract English language data is missing.')
        if tesseract_path or explicit_data:
            settings = {'backend': 'pytesseract', 'tesseract': str(Path(command).resolve())}
            if data:
                settings['tessdata'] = str(data)
            save_json(ROOT/'.engines/native-tools.json', settings)
            print('Tesseract paths saved. Restart the dashboard if it is running.', flush=True)
        return command
    if tesseract_path:
        command = Path(tesseract_path).expanduser().resolve()
        if command.is_dir():
            command /= 'tesseract.exe' if os.name == 'nt' else 'tesseract'
        if not command.is_file():
            raise RuntimeError(f'Tesseract executable not found: {command}')
        return verify(str(command))
    command = tesseract_command()
    if command:
        return verify(command)
    raise RuntimeError('No existing Tesseract runtime found. Use an organisation-approved installation: '
                       'python install.py --tesseract-path "C:/Program Files/Tesseract-OCR/tesseract.exe" '
                       '(and --tessdata-path if needed), or use --without-tesseract to install the other three engines. '
                       'Setup does not download or run a native package manager.')


def configure_tesserocr(python, tessdata_path=None):
    """Verify the wheel's bundled library and persist the approved model path."""
    sys.path.insert(0, str(ROOT))
    from ocrbench.native import tesserocr_data
    from ocrbench.storage import save_json
    data = Path(tessdata_path).expanduser().resolve() if tessdata_path else tesserocr_data()
    if not data or not (data/'eng.traineddata').is_file():
        raise RuntimeError('Tesseract requires approved eng.traineddata. Supply --tessdata-path or place it in data/models/tesseract/tessdata. Model files are not downloaded automatically.')
    code = ('import sys,tesserocr; '
            'api=tesserocr.PyTessBaseAPI(path=sys.argv[1],lang="eng"); '
            'print(tesserocr.tesseract_version()); api.End()')
    run([python, '-c', code, str(data)])
    save_json(ROOT/'.engines/native-tools.json', {'backend': 'tesserocr', 'tessdata': str(data)})
    print('Bundled Tesseract library verified. Restart the dashboard if it is running.', flush=True)
