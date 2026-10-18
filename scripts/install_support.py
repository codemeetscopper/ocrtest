"""Python-only provisioning helpers; never invoke a shell or activation script."""
import configparser
import getpass
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
ENGINES = ('rapidocr', 'paddleocr', 'easyocr', 'tesseract')
PUBLIC_INDEX = 'https://pypi.org/simple'
_package_source = {'mode': 'public', 'index': PUBLIC_INDEX, 'cert': None}


def pip_environment():
    """Apply this installation's explicit source choice to pip and build children."""
    env = os.environ.copy()
    for name in ('PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL', 'PIP_NO_INDEX', 'PIP_FIND_LINKS', 'PIP_TRUSTED_HOST'):
        env.pop(name, None)
    # Disable saved user/site sources without modifying them in public mode.
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_INDEX_URL=_package_source['index'],
               PIP_EXTRA_INDEX_URL='', PIP_FIND_LINKS='', PIP_NO_INDEX='0')
    if _package_source['cert']:
        env['PIP_CERT'] = _package_source['cert']
    return env


def user_pip_config_path():
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA') or Path.home()/'AppData/Roaming')/'pip/pip.ini'
    if sys.platform == 'darwin' and (Path.home()/'Library/Application Support/pip').is_dir():
        return Path.home()/'Library/Application Support/pip/pip.conf'
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'pip/pip.conf'


def configure_pip(index_url=None, cert=None):
    """Use public sources unless this invocation supplies Artifactory credentials."""
    token = os.environ.get('OCRBENCH_INDEX_TOKEN', '').strip()
    username = os.environ.get('OCRBENCH_INDEX_USERNAME', '').strip()
    index_url = (index_url or '').strip()
    if index_url and not token and sys.stdin.isatty():
        token = getpass.getpass('Artifactory token (saved in user pip.ini as plain text): ').strip()
    if bool(index_url) != bool(token) or (username and not token):
        raise ValueError('Provide both the Artifactory URL and token, or leave both blank to use public PyPI.')
    authenticated_url = None
    if index_url:
        parsed = urlsplit(index_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use an HTTPS Artifactory simple-index URL without embedded credentials or query parameters.')
        credentials = quote(username, safe='')+':'+quote(token, safe='') if username else quote(token, safe='')
        authenticated_url = urlunsplit((parsed.scheme, credentials+'@'+parsed.netloc, parsed.path, '', ''))
    cert_path = None
    if cert:
        cert_path = Path(cert).expanduser().resolve()
        if not cert_path.is_file():
            raise ValueError('--cert must be an existing corporate CA bundle.')
    if not authenticated_url and not cert_path:
        _package_source.update(mode='public', index=PUBLIC_INDEX, cert=None)
        print('Using public PyPI and official GPU wheel sources. Artifactory is enabled only when its URL and token are provided.', flush=True)
        return
    path = user_pip_config_path()
    config = configparser.ConfigParser(interpolation=None)
    try:
        if path.exists():
            with path.open(encoding='utf-8-sig') as existing:
                config.read_file(existing)
    except (configparser.Error, UnicodeError) as error:
        raise RuntimeError('Could not read the existing user pip configuration. Fix its INI format before retrying.') from None
    for section in ('global', 'install'):
        if not config.has_section(section):
            config.add_section(section)
        if authenticated_url:
            config.set(section, 'index-url', authenticated_url)
            config.set(section, 'extra-index-url', '')
            config.set(section, 'find-links', '')
            config.set(section, 'no-index', 'false')
        if cert_path:
            config.set(section, 'cert', str(cert_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='pip-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            config.write(output)
        if os.name != 'nt':
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print(f'Pip configuration saved: {path}', flush=True)
    saved_cert = config.get('install', 'cert', fallback=config.get('global', 'cert', fallback=None)) if authenticated_url else None
    _package_source.update(mode='artifactory' if authenticated_url else 'public',
                           index=authenticated_url or PUBLIC_INDEX, cert=str(cert_path) if cert_path else saved_cert)
    if authenticated_url:
        print('Artifactory credentials are stored as plain text in this user configuration. Pip will read it normally.', flush=True)
        print('This installation uses the supplied Artifactory source exclusively, including GPU packages.', flush=True)
    else:
        print('Using public PyPI and official GPU wheel sources with the supplied certificate.', flush=True)


def run(args, **kwargs):
    print('> ' + subprocess.list2cmdline([str(a) for a in args]), flush=True)
    kwargs.setdefault('cwd', ROOT)
    subprocess.run([str(a) for a in args], check=True, **kwargs)


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
    pip_install(target, 'pip>=23.3')
    return target


def validate_python(python):
    version = json.loads(subprocess.check_output([str(python), '-c',
                        'import sys,json,struct;print(json.dumps([*sys.version_info[:2],struct.calcsize("P")*8]))'], text=True))
    if version[0] != 3 or not 10 <= version[1] <= 13 or version[2] != 64:
        raise RuntimeError('Full OCR installation requires 64-bit Python 3.10-3.13. Use a supported interpreter with matching OCR wheels in your feed.')


def repair_pip(python=None):
    """Reinstall Python's bundled pip offline, even when newer metadata remains."""
    target = str(python or sys.executable)
    print(f'Pip is missing or damaged in {target}. Repairing it from Python\'s bundled wheel (offline).', flush=True)
    # Running the bundled wheel directly avoids importing the damaged installed
    # copy. ensurepip --upgrade alone skips a broken, newer pip distribution.
    code = '''
import ensurepip, os, pathlib, runpy, sys, sysconfig
directories = [pathlib.Path(ensurepip.__file__).with_name('_bundled')]
system_wheels = sysconfig.get_config_var('WHEEL_PKG_DIR')
if system_wheels:
    directories.insert(0, pathlib.Path(system_wheels))
wheels = [wheel for directory in directories for wheel in directory.glob('pip-*.whl')]
if not wheels:
    raise RuntimeError('Python has no bundled pip wheel. Repair this Python installation with ensurepip support.')
wheel = wheels[0]
for name in list(os.environ):
    if name.startswith('PIP_'):
        del os.environ[name]
os.environ['PIP_CONFIG_FILE'] = os.devnull
sys.path.insert(0, str(wheel))
sys.argv = ['pip', 'install', '--no-index', '--no-deps', '--force-reinstall',
            '--disable-pip-version-check', str(wheel)]
runpy.run_module('pip', run_name='__main__', alter_sys=True)
'''
    try:
        with tempfile.TemporaryDirectory(prefix='ocrbench-pip-repair-') as working:
            bootstrap = Path(working)/'repair_pip.py'
            bootstrap.write_text(code, encoding='utf-8')
            run([target, '-I', bootstrap])
    except subprocess.CalledProcessError as error:
        raise RuntimeError('Could not repair pip from Python\'s bundled wheel. Close other package installations and retry; if it persists, repair this Python installation.') from error


def pip_version(python):
    # --version alone can succeed even when importing an actual command fails.
    code = ('import pip; from pip._internal.commands import create_command; '
            'create_command("install"); create_command("uninstall"); print("pip "+pip.__version__)')
    return subprocess.check_output([str(python), '-I', '-c', code], text=True,
                                   stderr=subprocess.DEVNULL, env=pip_environment())


def ensure_target_pip(python):
    try:
        pip_version(python)
    except subprocess.CalledProcessError:
        repair_pip(python)
        try:
            pip_version(python)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f'Pip is still unusable after repair in {python}. Repair this Python environment before retrying.') from error


def pip_controller():
    try:
        version = pip_version(sys.executable)
    except subprocess.CalledProcessError:
        repair_pip()
        try:
            version = pip_version(sys.executable)
        except subprocess.CalledProcessError as error:
            raise RuntimeError('Pip is still unusable after repair. Repair this Python installation before retrying.') from error
    match = re.match(r'pip (\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (23, 3):
        # Upgrade the controller directly: older pip cannot accept --python yet.
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'pip>=23.3'], env=pip_environment())
    return sys.executable


def pip_install(python, *requirements):
    run([pip_controller(), '-m', 'pip', '--python', python, 'install', '--disable-pip-version-check', *requirements], env=pip_environment())


def uses_public_pypi(python):
    """Use the invocation's source choice, independent of target pip internals."""
    return _package_source['mode'] == 'public'


def cuda_family(choice='auto'):
    if choice in ('cuda12', 'cuda13'):
        return choice
    if choice != 'auto':
        raise ValueError('Unknown CUDA compatibility option')
    executable = shutil.which('nvidia-smi')
    try:
        output = subprocess.check_output([executable], text=True, timeout=15) if executable else ''
        match = re.search(r'CUDA(?: UMD)? Version:\s*(\d+)\.(\d+)', output)
        if match:
            version = tuple(map(int, match.groups()))
            if version >= (13, 0):
                return 'cuda13'
            if version < (12, 8):
                raise RuntimeError('GPU setup requires an NVIDIA driver supporting CUDA 12.8 or newer. Update the driver or install CPU support.')
    except (OSError, subprocess.SubprocessError):
        pass
    return 'cuda12'


def torch_needs_repair(python):
    code = ('import importlib.util,sys; '
            's=importlib.util.find_spec("torch"); '
            'exec("import torch; sys.exit(10 if not torch.cuda.is_available() else 0)" if s else "sys.exit(0)")')
    return subprocess.run([str(python), '-I', '-c', code], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 0


def install_gpu_framework(python, engine, cuda='auto'):
    """Use public GPU wheels by default, or the explicitly supplied Artifactory."""
    public = uses_public_pypi(python)
    family = cuda_family(cuda) if public else 'cuda12'
    frameworks = {
        'easyocr': ('https://download.pytorch.org/whl/'+('cu130' if family == 'cuda13' else 'cu128'), ('torch>=2.4,<3', 'torchvision>=0.19,<1')),
        'paddleocr': ('https://www.paddlepaddle.org.cn/packages/stable/'+('cu130' if family == 'cuda13' else 'cu126')+'/', ('paddlepaddle-gpu>=3,<4',)),
    }
    index, requirements = frameworks[engine]
    repair = []
    if engine == 'easyocr':
        # A previously installed CPU build also satisfies torch's version range.
        # Re-resolve that build from the GPU source instead of silently retaining it.
        if torch_needs_repair(python):
            repair = ['--force-reinstall']
    if public:
        print(f'{engine} GPU: using public packages and official CUDA wheel source: {index}', flush=True)
        # Torch's official index must be authoritative: a newer CPU wheel from
        # PyPI must not outrank an older, compatible CUDA wheel.
        flag = '--index-url' if engine == 'easyocr' else '--extra-index-url'
        if cuda != 'auto':
            repair = ['--force-reinstall']
        pip_install(python, flag, index, *repair, *requirements)
    else:
        print(f'{engine} GPU: using the supplied Artifactory source only.', flush=True)
        pip_install(python, *repair, *requirements)


def environment(directory, python):
    target = python_in(directory)
    if not target.exists():
        validate_python(python)
        run([python, '-m', 'venv', '--without-pip', directory])
    validate_python(target)
    ensure_target_pip(target)
    pip_install(target, 'pip>=23.3')
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


def setup_engine(engine, device, python, tesseract_path=None, tessdata_path=None, tesseract_backend='pytesseract', cuda='auto', tesserocr_wheel=None):
    if engine not in ENGINES or device not in ('cpu', 'gpu'):
        raise ValueError('Unknown engine or device')
    if engine == 'tesseract' and device == 'gpu':
        raise ValueError('Tesseract supports CPU only.')
    if engine == 'tesseract' and tesseract_backend == 'pytesseract':
        ensure_tesseract(tesseract_path, tessdata_path)
    extra = engine + ('-gpu' if device == 'gpu' else '')
    target = environment(ROOT/'.engines'/extra, python)
    if engine == 'tesseract' and tesseract_backend == 'tesserocr':
        install_tesserocr(target, tessdata_path, tesserocr_wheel)
    if device == 'gpu' and engine in ('easyocr', 'paddleocr'):
        install_gpu_framework(target, engine, cuda)
    # The ORT runtime family must match the driver. These bounds correspond to
    # upstream's CUDA 12/13 build transition, rather than one machine's version.
    requirements = ['-e', f'{ROOT}[{extra}]']
    if engine == 'rapidocr' and device == 'gpu' and uses_public_pypi(target):
        requirements.append('onnxruntime-gpu[cuda,cudnn]>=1.27,<2' if cuda_family(cuda) == 'cuda13'
                            else 'onnxruntime-gpu[cuda,cudnn]>=1.21,<1.27')
    pip_install(target, *requirements)
    print(f'{engine} {device}: {target}', flush=True)
    return target


def auto_install_tesseract():
    """Explicit personal-PC option: install native Windows Tesseract with WinGet."""
    from ocrbench.native import tesseract_command
    command = tesseract_command()
    if command:
        print('Existing Tesseract found; verifying it.', flush=True)
        return ensure_tesseract(command)
    if os.name != 'nt':
        raise RuntimeError('Tesseract Auto install currently supports Windows. Install the native engine with your OS package manager, then choose Installed Tesseract.')
    winget = shutil.which('winget')
    if not winget:
        raise RuntimeError('Tesseract Auto install needs Windows App Installer (WinGet). Install App Installer from Microsoft Store, then retry Auto install.')
    print('Installing native Tesseract with WinGet. Windows may request administrator approval.', flush=True)
    try:
        run([winget, 'install', '--id', 'UB-Mannheim.TesseractOCR', '--exact', '--source', 'winget',
             '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity'])
    except subprocess.CalledProcessError as error:
        raise RuntimeError('WinGet could not install Tesseract. Check the installer output and any Windows elevation prompt, then retry Auto install.') from error
    # The process PATH need not be refreshed: native discovery includes known install folders.
    command = tesseract_command()
    if not command:
        raise RuntimeError('WinGet finished, but tesseract.exe was not found. Choose Installed Tesseract and provide its executable path.')
    return ensure_tesseract(command)


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


def tesserocr_model_data(tessdata_path=None):
    sys.path.insert(0, str(ROOT))
    from ocrbench.native import tesserocr_data
    data = Path(tessdata_path).expanduser().resolve() if tessdata_path else tesserocr_data()
    if not data or not (data/'eng.traineddata').is_file():
        raise RuntimeError('Tesseract requires approved eng.traineddata. Supply --tessdata-path or place it in data/models/tesseract/tessdata. Model files are not downloaded automatically.')
    return data


def install_tesserocr(python, tessdata_path=None, wheel=None):
    """Require a compatible binary from configured pip sources or a local wheel."""
    data = tesserocr_model_data(tessdata_path)
    requirements = ['--only-binary=tesserocr']
    if wheel:
        path = Path(wheel).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != '.whl' or not path.name.startswith('tesserocr-'):
            raise ValueError('--tesserocr-wheel must point to an existing tesserocr .whl file.')
        # Upstream publishes different bundled Tesseract engines with the same
        # binding version and wheel name. Honor the explicitly selected binary.
        requirements.extend(['--force-reinstall', str(path)])
    requirements.append('tesserocr>=2.7,<3')
    try:
        pip_install(python, *requirements)
    except subprocess.CalledProcessError as error:
        raise RuntimeError('Could not install a compatible tesserocr binary; see the pip error above. '
                           'Windows wheels are distributed separately from PyPI. Supply a matching wheel with '
                           '--tesserocr-wheel (Bundled mode: Local wheel file), or publish it in your Artifactory feed. '
                           'On this laptop you can also choose Installed Tesseract or Auto install. '
                           'No source build or alternate backend was selected automatically.') from error
    configure_tesserocr(python, str(data))


def configure_tesserocr(python, tessdata_path=None):
    """Verify the wheel's bundled library and persist the approved model path."""
    from ocrbench.storage import save_json
    data = tesserocr_model_data(tessdata_path)
    code = ('import sys,tesserocr; '
            'api=tesserocr.PyTessBaseAPI(path=sys.argv[1],lang="eng"); '
            'print(tesserocr.tesseract_version()); api.End()')
    run([python, '-c', code, str(data)])
    save_json(ROOT/'.engines/native-tools.json', {'backend': 'tesserocr', 'tessdata': str(data)})
    print('Bundled Tesseract library verified. Restart the dashboard if it is running.', flush=True)
