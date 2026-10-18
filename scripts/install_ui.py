"""Dependency-free loopback installer UI; subprocesses use the launching Python."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import os
import re
from pathlib import Path
import secrets
import signal
import subprocess
import socket
import sys
import threading
import tempfile
import time
from urllib.parse import quote, urlsplit
import webbrowser

from scripts.install_support import ROOT, active_python, app_python, user_pip_config_path
from scripts.install_lifecycle import inspect_installation

PAGE = Path(__file__).with_name('installer.html')


def defaults():
    from ocrbench.native import tesseract_backend, tesseract_command, tesseract_data, tesserocr_data
    command = tesseract_command()
    backend = tesseract_backend()
    data = tesserocr_data() if backend == 'tesserocr' or not command else tesseract_data(command)
    target = app_python()
    return {
        'target': str(target), 'active': active_python() is not None,
        'python': str(target) if target.exists() else sys.executable,
        'backend': backend if backend == 'tesserocr' or command else 'skip',
        'tesseract_path': command or '', 'tessdata_path': str(data) if data else '',
        'pip_config_path': str(user_pip_config_path()),
    }


def install_arguments(values):
    if not isinstance(values, dict):
        raise ValueError('Expected installation options.')
    allowed = {'device', 'backend', 'python', 'index_url', 'cert', 'tesseract_path', 'tessdata_path', 'tesserocr_wheel', 'engines', 'gpu_engines', 'auth_mode', 'token_user', 'access_token', 'cuda'}
    if values.keys() - allowed or any(not isinstance(v, str) for k,v in values.items() if k not in ('engines','gpu_engines')):
        raise ValueError('Invalid installation options.')
    if 'engines' in values:
        engines = values['engines']
        if not isinstance(engines, list) or any(e not in ('rapidocr', 'paddleocr', 'easyocr', 'tesseract') for e in engines):
            raise ValueError('Choose valid OCR components.')
    if 'gpu_engines' in values:
        engines = values['gpu_engines']
        if not isinstance(engines, list) or any(e not in ('rapidocr', 'paddleocr', 'easyocr') for e in engines):
            raise ValueError('Choose valid GPU engines.')
        if 'engines' in values and set(engines) - set(values['engines']):
            raise ValueError('GPU engines must also be selected in OCR components.')
        if values.get('device', 'cpu') == 'cpu' and engines:
            raise ValueError('Choose GPU processing support for selected GPU engines.')
    index = values.get('index_url', '').strip()
    access_token = values.get('access_token', '').strip()
    if bool(index) != bool(access_token) or (values.get('token_user', '').strip() and not access_token):
        raise ValueError('Provide both the Artifactory URL and token, or leave both blank to use public PyPI.')
    if access_token:
        parsed = urlsplit(values.get('index_url', '').strip())
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('Artifactory requires an HTTPS simple-index URL.')
    device = values.get('device', 'cpu')
    backend = values.get('backend', 'pytesseract')
    if device not in ('cpu', 'auto', 'gpu') or backend not in ('skip', 'pytesseract', 'tesserocr', 'auto'):
        raise ValueError('Choose a valid device and Tesseract backend.')
    args = ['--device', device]
    cuda = values.get('cuda', 'auto')
    if cuda not in ('auto', 'cuda12', 'cuda13'):
        raise ValueError('Choose a valid CUDA compatibility option.')
    if cuda != 'auto':
        args.extend(['--cuda', cuda])
    if 'engines' in values:
        args.extend(['--engines', ','.join(dict.fromkeys(values['engines']))])
    if 'gpu_engines' in values:
        args.extend(['--gpu-engines', ','.join(dict.fromkeys(values['gpu_engines']))])
    for field, flag in [('python', '--python'), ('index_url', '--index-url'), ('cert', '--cert')]:
        value = values.get(field, '').strip()
        if value:
            if value.startswith('-'):
                raise ValueError(f'{field} must be a path or URL, not a command option.')
            if field == 'index_url':
                url = urlsplit(value)
                if url.scheme not in ('http', 'https') or not url.hostname or url.query or url.fragment:
                    raise ValueError('Use an HTTP(S) PyPI simple-index URL without query parameters.')
                if url.username or url.password:
                    raise ValueError('Use approved pip authentication; omit credentials from the URL.')
            args.extend([flag, value])
    if backend == 'skip':
        args.append('--without-tesseract')
    elif backend == 'auto':
        args.append('--auto-install-tesseract')
    else:
        args.extend(['--tesseract-backend', backend])
        fields = [('tessdata_path', '--tessdata-path')]
        if backend == 'tesserocr':
            fields.append(('tesserocr_wheel', '--tesserocr-wheel'))
        if backend == 'pytesseract':
            fields.append(('tesseract_path', '--tesseract-path'))
        for field, flag in fields:
            value = values.get(field, '').strip()
            if value:
                if value.startswith('-'):
                    raise ValueError(f'{field} must be a path, not a command option.')
                args.extend([flag, value])
    return args


class Installation:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.state = 'idle'
        self.output = ''
        self.returncode = None
        self.app_state = 'idle'
        self.app_output = ''
        self.app_url = ''
        self.app_process = None
        self.operation = 'install'
        self.installation = inspect_installation()
        self.last_inventory_check = time.monotonic()
        self.setup_results = None

    def refresh_inventory(self, force=False):
        with self.lock:
            now = time.monotonic()
            if self.state == 'running' or (not force and now - self.last_inventory_check < 5):
                return
            self.last_inventory_check = now
        inventory = inspect_installation()
        with self.lock:
            self.installation = inventory

    def snapshot(self):
        with self.lock:
            return {'state': self.state, 'output': self.output, 'returncode': self.returncode,
                    'app_state': self.app_state, 'app_output': self.app_output, 'app_url': self.app_url,
                    'operation': self.operation, 'installation': self.installation, 'setup_results': self.setup_results}

    def stop_workbench(self):
        with self.lock:
            process = self.app_process
            if process is None or process.poll() is not None:
                raise RuntimeError('No workbench launched by this installer is running.')
            self.app_state = 'stopping'
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=True,
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except (OSError, subprocess.SubprocessError) as error:
            with self.lock:
                self.app_state = 'running' if process.poll() is None else 'stopped'
            raise RuntimeError('Could not stop the workbench. Close it and try again.') from error

    def launch(self):
        with self.lock:
            if self.state == 'running':
                raise RuntimeError('Wait for installation to finish before starting the workbench.')
            if self.app_state in ('starting', 'running', 'stopping'):
                raise RuntimeError('The workbench is already starting or running.')
            # Prefer the usual port; choose a free one if another app already uses it.
            with socket.socket() as listener:
                try:
                    listener.bind(('127.0.0.1', 8765))
                except OSError:
                    listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            self.app_state, self.app_output, self.app_process = 'starting', '', None
            self.app_url = f'http://127.0.0.1:{port}/'
        threading.Thread(target=self._launch, args=(port,), daemon=True).start()

    @staticmethod
    def _ready(port):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=.5)
        try:
            connection.request('GET', '/')
            return connection.getresponse().status == 200
        except (OSError, http.client.HTTPException):
            return False
        finally:
            connection.close()

    def _launch(self, port):
        log_path = None
        try:
            env = os.environ.copy()
            env.update(PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
            # A file keeps the workbench's stdout usable after the installer closes.
            with tempfile.NamedTemporaryFile(prefix='ocrbench-start-', suffix='.log', delete=False) as log:
                log_path = Path(log.name)
                process = subprocess.Popen([sys.executable, '-u', str(ROOT/'start.py'), '--port', str(port)],
                                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                           **({'start_new_session': True} if os.name != 'nt' else {}))
            with self.lock:
                self.app_process = process
            with log_path.open('r', encoding='utf-8', errors='replace') as output:
                while True:
                    content = output.read()
                    with self.lock:
                        self.app_output = (self.app_output + content)[-100_000:]
                        starting = self.app_state == 'starting'
                    code = process.poll()
                    if code is not None:
                        with self.lock:
                            self.app_output = (self.app_output + output.read())[-100_000:]
                            self.app_output += f'\nWorkbench exited with code {code}.\n'
                            self.app_state = 'stopped' if code == 0 or self.app_state == 'stopping' else 'failed'
                        break
                    if starting and self._ready(port):
                        with self.lock:
                            self.app_state = 'running'
                    time.sleep(.25)
        except Exception as error:
            with self.lock:
                self.app_state = 'failed'
                self.app_output += f'Could not start workbench: {error}\n'
        finally:
            if log_path and (self.app_process is None or self.app_process.poll() is not None):
                log_path.unlink(missing_ok=True)

    def start(self, values):
        if not isinstance(values, dict):
            raise ValueError('Expected installation options.')
        values = dict(values)
        operation = values.pop('action', 'install')
        if operation not in ('install', 'modify', 'uninstall'):
            raise ValueError('Choose Install, Modify, or Uninstall.')
        auth = {}
        if operation == 'uninstall':
            if values:
                raise ValueError('Uninstall takes no package or authentication options.')
            if not self.installation['installed']:
                raise RuntimeError('No OCR Bench installation was found in this environment.')
            args = ['--uninstall']
        else:
            args = install_arguments(values)
            if values.get('access_token', '').strip():
                auth = {'OCRBENCH_INDEX_TOKEN': values['access_token'].strip(),
                        'OCRBENCH_INDEX_USERNAME': values.get('token_user', '').strip()}
        with self.lock:
            if self.state == 'running':
                raise RuntimeError('An installation is already running.')
            if operation == 'uninstall' and self.app_state in ('starting', 'running', 'stopping'):
                raise RuntimeError('Stop the workbench before uninstalling it.')
            self.operation = operation
            self.setup_results = None
            self.state, self.output, self.returncode = 'running', '', None
        threading.Thread(target=self._run, args=(args, auth), daemon=True).start()

    def _run(self, args, auth=None):
        code = 1
        secret = (auth or {}).get('OCRBENCH_INDEX_TOKEN', '')
        def redact(value):
            for password in (secret, quote(secret, safe='')):
                if password:
                    value = value.replace(password, '[REDACTED]')
            # Also cover credentials loaded from pip.ini on later runs where
            # the form is blank and no token is present in this job's payload.
            return re.sub(r'(https?://)[^/\s@]+@',r'\1[REDACTED]@',value,flags=re.IGNORECASE)
        try:
            env = os.environ.copy()
            env.pop('OCRBENCH_INDEX_TOKEN', None)
            env.pop('OCRBENCH_INDEX_USERNAME', None)
            env.update(auth or {})
            env.update(PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', OCRBENCH_INSTALL_UI='1')
            # No shell, activation, or environment switching; preserve the launching venv.
            with subprocess.Popen([sys.executable, '-u', str(ROOT/'install.py'), *args],
                                  cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace') as process:
                for line in process.stdout:
                    if line.startswith('OCRBENCH_INSTALL_RESULT '):
                        try:
                            result = json.loads(redact(line.removeprefix('OCRBENCH_INSTALL_RESULT ')))
                            if isinstance(result, dict) and result.get('cpu') == 'installed' and isinstance(result.get('gpu'), dict):
                                with self.lock:
                                    self.setup_results = result
                                continue
                        except ValueError:
                            pass
                    with self.lock:
                        self.output = (self.output + redact(line))[-200_000:]
                code = process.wait()
        except Exception as error:
            with self.lock:
                self.output += redact(f'Could not run installer: {error}\n')
        finally:
            inventory = inspect_installation()
            with self.lock:
                self.installation = inventory
                self.returncode = code
                self.state = 'succeeded' if code == 0 else 'partial' if self.setup_results and self.setup_results.get('cpu') == 'installed' else 'failed'


def create_server(port=0, installation=None):
    installation = installation or Installation()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, payload, kind='application/json; charset=utf-8'):
            body = json.dumps(payload).encode('utf-8') if kind.startswith('application/json') else payload
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            return self.headers.get('Host') == expected

        def do_GET(self):
            if not self.local_request():
                return self.respond(403, {'error': 'Local installer only.'})
            if self.path == '/':
                return self.respond(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
            if self.path == '/api/config':
                installation.refresh_inventory(force=True)
                return self.respond(200, {**defaults(), 'installation': installation.installation, 'token': installation.token})
            if self.path == '/api/status':
                installation.refresh_inventory()
                return self.respond(200, installation.snapshot())
            self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.local_request() or not secrets.compare_digest(self.headers.get('X-OCRBench-Installer', ''), installation.token):
                return self.respond(403, {'error': 'Reload the local installer page and try again.'})
            if self.path not in ('/api/install', '/api/launch', '/api/stop'):
                return self.respond(404, {'error': 'Not found.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16_384:
                    raise ValueError('Invalid request size.')
                values = json.loads(self.rfile.read(length))
                if self.path in ('/api/launch', '/api/stop'):
                    if values != {}:
                        raise ValueError('Workbench launch takes no options.')
                    if self.path == '/api/launch':
                        installation.launch()
                    else:
                        installation.stop_workbench()
                else:
                    installation.start(values)
            except (ValueError, TypeError) as error:
                return self.respond(400, {'error': str(error)})
            except RuntimeError as error:
                return self.respond(409, {'error': str(error)})
            self.respond(202, installation.snapshot())

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.installation = installation
    return server


def serve():
    server = create_server()
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'OCR Bench installer: {url}', flush=True)
    print('Open this URL if the browser does not open. Press Ctrl+C to close the installer.', flush=True)
    try:
        webbrowser.open(url)
    except webbrowser.Error:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
