"""Python-only provisioning helpers; never invoke a shell or activation script."""
import configparser
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
ENGINES = ('rapidocr', 'paddleocr', 'easyocr', 'tesseract')


def user_pip_config_path():
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA') or Path.home()/'AppData/Roaming')/'pip/pip.ini'
    if sys.platform == 'darwin' and (Path.home()/'Library/Application Support/pip').is_dir():
        return Path.home()/'Library/Application Support/pip/pip.conf'
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'pip/pip.conf'


def configure_pip(index_url=None, cert=None):
    """Save supplied Artifactory credentials to user pip.ini, then use normal pip."""
    token = os.environ.get('OCRBENCH_INDEX_TOKEN', '').strip()
    username = os.environ.get('OCRBENCH_INDEX_USERNAME', '').strip()
    index_url = (index_url or '').strip()
    if index_url and not token and sys.stdin.isatty():
        token = getpass.getpass('Artifactory token (saved in user pip.ini as plain text): ').strip()
    if bool(index_url) != bool(token) or (username and not token):
        raise ValueError('Provide both the Artifactory URL and token, or leave both blank to use normal pip settings.')
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
        print('Using normal pip settings (PyPI when no package source is configured).', flush=True)
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
    if authenticated_url:
        print('Artifactory credentials are stored as plain text in this user configuration. Pip will read it normally.', flush=True)
    overrides = [name for name in ('PIP_INDEX_URL','PIP_EXTRA_INDEX_URL','PIP_FIND_LINKS','PIP_NO_INDEX','PIP_CONFIG_FILE','PIP_CERT') if os.environ.get(name)]
    if overrides:
        print('Normal pip precedence applies. These environment settings may override pip.ini: '+', '.join(overrides), flush=True)


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
    run([pip_controller(), '-m', 'pip', '--python', python, 'install', '--disable-pip-version-check', *requirements])


def uses_public_pypi(python):
    """Read the target's effective pip settings without returning credentials."""
    code = (
        'from pip._internal.commands import create_command; from urllib.parse import urlsplit; '
        'o,_=create_command("install").parse_args([]); u=urlsplit(o.index_url or ""); '
        'print(int(u.scheme=="https" and u.hostname=="pypi.org" '
        'and u.path.rstrip("/")=="/simple" and not u.username and not u.password '
        'and not o.no_index and not o.extra_index_urls and not o.find_links))'
    )
    try:
        return subprocess.check_output([str(python), '-I', '-c', code], text=True, timeout=30).strip() == '1'
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError('Could not inspect target pip settings; public GPU sources were not enabled.') from error


def install_gpu_framework(python, engine):
    """Supplement plain PyPI with vendor wheels; never bypass a configured feed."""
    frameworks = {
        'easyocr': ('https://download.pytorch.org/whl/cu130', ('torch==2.14.1+cu130', 'torchvision==0.29.1+cu130')),
        'paddleocr': ('https://www.paddlepaddle.org.cn/packages/stable/cu130/', ('paddlepaddle-gpu==3.3.1',)),
    }
    index, requirements = frameworks[engine]
    if uses_public_pypi(python):
        print(f'{engine} GPU: using PyPI plus the official CUDA wheel index: {index}', flush=True)
        pip_install(python, '--extra-index-url', index, *requirements)
    else:
        print(f'{engine} GPU: using configured pip sources only.', flush=True)
        pip_install(python, *requirements)


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
    if device == 'gpu' and engine in ('easyocr', 'paddleocr'):
        install_gpu_framework(target, engine)
    elif engine == 'easyocr':
        pip_install(target, 'torch==2.14.1', 'torchvision==0.29.1')
    pip_install(target, '-e', f'{ROOT}[{extra}]')
    if engine == 'tesseract' and tesseract_backend == 'tesserocr':
        pip_install(target, '--only-binary=tesserocr', 'tesserocr==2.10.0')
        configure_tesserocr(target, tessdata_path)
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
