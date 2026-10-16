"""Python-only provisioning helpers; never invoke a shell or activation script."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
ENGINES = ('rapidocr', 'paddleocr', 'easyocr', 'tesseract')


def run(args, **kwargs):
    print('> ' + subprocess.list2cmdline([str(a) for a in args]), flush=True)
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def python_in(directory):
    return Path(directory) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


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


def setup_engine(engine, device, python):
    if engine not in ENGINES or device not in ('cpu', 'gpu'):
        raise ValueError('Unknown engine or device')
    if engine == 'tesseract' and device == 'gpu':
        raise ValueError('Tesseract supports CPU only.')
    extra = engine + ('-gpu' if device == 'gpu' else '')
    target = environment(ROOT/'.engines'/extra, python)
    if engine == 'easyocr':
        index = 'cu130' if device == 'gpu' else 'cpu'
        pip_install(target, 'torch==2.14.1', 'torchvision==0.29.1', '--index-url', f'https://download.pytorch.org/whl/{index}')
    if engine == 'paddleocr' and device == 'gpu':
        pip_install(target, '--no-deps', 'paddlepaddle-gpu==3.3.1', '--index-url', 'https://www.paddlepaddle.org.cn/packages/stable/cu130/')
        pip_install(target, 'paddlepaddle-gpu==3.3.1')
    pip_install(target, '-e', f'{ROOT}[{extra}]')
    if engine == 'tesseract':
        ensure_tesseract()
    print(f'{engine} {device}: {target}', flush=True)
    return target


def ensure_tesseract():
    # Reuse a working installation. Native discovery is also used by the worker.
    sys.path.insert(0, str(ROOT))
    from ocrbench.native import tesseract_command, tesseract_data
    def verify(command):
        env = os.environ.copy()
        data = tesseract_data(command)
        if data:
            env['TESSDATA_PREFIX'] = str(data)
        run([command, '--version'], env=env)
        languages = subprocess.check_output([command, '--list-langs'], text=True, env=env)
        if 'eng' not in languages.splitlines():
            raise RuntimeError('Tesseract English language data is missing.')
        return command
    command = tesseract_command()
    if command:
        return verify(command)
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('Native automatic Tesseract setup currently targets Windows x64. Install Tesseract with your OS package manager, then rerun.')
    # Portable conda-forge runtime: no admin installer, system PATH changes,
    # shell hooks, PowerShell, or Conda installation required.
    tools = ROOT/'.engines'/'tools'
    tools.mkdir(parents=True, exist_ok=True)
    mamba = tools/'micromamba.exe'
    if not mamba.exists():
        archive = tools/'micromamba.tar.bz2'
        print('Downloading portable micromamba from the official Mamba distribution…', flush=True)
        urllib.request.urlretrieve('https://micro.mamba.pm/api/micromamba/win-64/latest', archive)
        with tarfile.open(archive, 'r:bz2') as tar:
            member = tar.getmember('Library/bin/micromamba.exe')
            with tar.extractfile(member) as source, mamba.open('wb') as output:
                shutil.copyfileobj(source, output)
    prefix = ROOT/'.engines'/'tesseract-native'
    run([mamba, '--no-rc', 'create', '-y', '-r', ROOT/'.engines'/'mamba-cache', '-p', prefix,
         '-c', 'conda-forge', '--override-channels', 'tesseract>=5.5,<6'])
    command = tesseract_command()
    if not command:
        raise RuntimeError('Native Tesseract installation did not produce a discoverable executable.')
    return verify(command)
