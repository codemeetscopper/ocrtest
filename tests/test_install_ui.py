"""Installer checks runnable before app dependencies exist: python -m unittest discover -s tests -p test_install_ui.py."""
from contextlib import contextmanager, redirect_stdout
import http.client
import io
import os
import json
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote
import zipfile

import install
from scripts import install_support, install_ui
from scripts import install_lifecycle


@contextmanager
def server_for(state=None):
    server = install_ui.create_server(installation=state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def request(server, method, path, values=None, token=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    body = json.dumps(values) if values is not None else None
    headers = dict(headers or {})
    if token:
        headers['X-OCRBench-Installer'] = token
    if body:
        headers['Content-Type'] = 'application/json'
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        content = response.read()
        return response.status, content
    finally:
        connection.close()


class InstallUITests(unittest.TestCase):
    def test_gpu_failure_keeps_successes_and_attempts_remaining_engines(self):
        output = io.StringIO()
        def setup(engine, *args):
            if engine == 'paddleocr':
                raise subprocess.CalledProcessError(1,['pip','install','paddlepaddle-gpu==3.3.1'])
            return 'gpu-python'
        with patch.object(install,'configure_pip'),patch.object(install,'app_environment',return_value='python312'), \
             patch.object(install,'pip_install'),patch.object(install,'setup_engine',side_effect=setup) as gpu, \
             patch.dict(os.environ,{'OCRBENCH_INSTALL_UI':'1'}),redirect_stdout(output):
            with self.assertRaises(install.GPUProvisioningError):
                install.main(['--device','gpu','--without-tesseract'])
        self.assertEqual([call.args[0] for call in gpu.call_args_list],['rapidocr','paddleocr','easyocr'])
        text = output.getvalue()
        report = json.loads(next(line.removeprefix('OCRBENCH_INSTALL_RESULT ') for line in text.splitlines() if line.startswith('OCRBENCH_INSTALL_RESULT ')))
        self.assertEqual(report['cpu'],'installed')
        self.assertEqual(report['gpu']['paddleocr']['state'],'failed')
        self.assertEqual(report['gpu']['easyocr']['state'],'installed')
        self.assertIn('CPU/app components are installed',text)
        self.assertIn('2.6.x builds cannot satisfy',text)

    def test_gpu_selection_keeps_paddle_cpu_without_requesting_paddle_gpu(self):
        with patch.object(install,'configure_pip'),patch.object(install,'app_environment',return_value='python312'), \
             patch.object(install,'pip_install') as pip,patch.object(install,'setup_engine') as gpu,patch('builtins.print'):
            install.main(['--engines','rapidocr,paddleocr,easyocr','--gpu-engines','rapidocr',
                          '--device','gpu','--without-tesseract'])
        self.assertIn('paddleocr',pip.call_args.args[-1])
        self.assertEqual([call.args[0] for call in gpu.call_args_list],['rapidocr'])

    def test_ui_gpu_choice_validation(self):
        args = install_ui.install_arguments({'device':'gpu','backend':'skip',
                                            'engines':['rapidocr','paddleocr'],'gpu_engines':['rapidocr']})
        self.assertEqual(args[args.index('--gpu-engines')+1],'rapidocr')
        for values in [{'gpu_engines':'rapidocr'}, {'gpu_engines':['tesseract']},
                       {'engines':['rapidocr'],'gpu_engines':['paddleocr'],'device':'gpu'},
                       {'device':'cpu','gpu_engines':['rapidocr']}]:
            with self.subTest(values=values),self.assertRaises(ValueError):
                install_ui.install_arguments(values)

    def test_partial_gpu_result_remains_usable_and_is_not_reported_as_success(self):
        report = {'cpu':'installed','gpu':{'rapidocr':{'state':'installed'},'paddleocr':{'state':'failed','error':'missing wheel'}}}
        child = unittest.mock.MagicMock()
        child.stdout = io.StringIO('CPU installed\nOCRBENCH_INSTALL_RESULT '+json.dumps(report)+'\nGPU setup incomplete\n')
        child.wait.return_value = 1
        child.__enter__.return_value = child
        state = install_ui.Installation()
        with patch.object(install_ui.subprocess,'Popen',return_value=child):
            state._run(['--device','gpu'])
        result = state.snapshot()
        self.assertEqual(result['state'],'partial')
        self.assertEqual(result['setup_results'],report)
        self.assertNotIn('OCRBENCH_INSTALL_RESULT',result['output'])
        self.assertEqual(result['returncode'],1)

    def test_token_authentication_is_saved_in_user_pip_ini(self):
        import configparser
        secret = 'example-token/a@b:123'
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary)/'pip.ini'
            with patch.dict(os.environ, {'OCRBENCH_INDEX_TOKEN':secret,'OCRBENCH_INDEX_USERNAME':'user@example'}), \
                 patch.object(install_support,'user_pip_config_path',return_value=config_path),patch('builtins.print'):
                install_support.configure_pip('https://artifactory.example/simple')
                config = configparser.ConfigParser(interpolation=None)
                config.read(config_path)
                self.assertEqual(config['global']['index-url'],'https://user%40example:'+quote(secret,safe='')+'@artifactory.example/simple')
                self.assertEqual(config['install']['index-url'],config['global']['index-url'])
                with self.assertRaises(ValueError):
                    install_support.configure_pip('http://artifactory.example/simple')

    def test_ui_token_is_never_a_command_argument_or_status_value(self):
        secret = 'example-token/a@b:123'
        inventory = {'installed': True, 'version': '1', 'packages': {}}
        with patch.object(install_ui, 'inspect_installation', return_value=inventory):
            state = install_ui.Installation()
            with patch.object(install_ui.threading, 'Thread') as thread:
                state.start({'action':'modify', 'backend':'skip', 'auth_mode':'token',
                             'index_url':'https://artifactory.example/simple', 'access_token':secret})
                args, auth = thread.call_args.kwargs['args']
                self.assertNotIn(secret, str(args))
                self.assertEqual(auth['OCRBENCH_INDEX_TOKEN'], secret)
                self.assertNotIn(secret, json.dumps(state.snapshot()))
            child = unittest.mock.MagicMock()
            child.stdout = io.StringIO('token '+secret+' encoded '+quote(secret,safe='')+'\n')
            child.wait.return_value = 0
            child.__enter__.return_value = child
            with patch.object(install_ui.subprocess, 'Popen', return_value=child) as launch:
                state._run(args, auth)
            self.assertEqual(launch.call_args.kwargs['env']['OCRBENCH_INDEX_TOKEN'], secret)
            self.assertNotIn(secret, state.snapshot()['output'])
            self.assertNotIn(quote(secret,safe=''), state.snapshot()['output'])
            self.assertIn('[REDACTED]', state.snapshot()['output'])

    def test_uninstall_action_is_scoped_and_blocks_running_workbench(self):
        with patch.object(install_ui, 'inspect_installation', return_value={'installed':True,'version':'1','packages':{}}):
            state = install_ui.Installation()
        state.app_state = 'running'
        with self.assertRaises(RuntimeError):
            state.start({'action':'uninstall'})
        state.app_state = 'idle'
        with patch.object(install_ui.threading, 'Thread') as thread:
            state.start({'action':'uninstall'})
            self.assertEqual(thread.call_args.kwargs['args'], (['--uninstall'], {}))
        self.assertEqual(state.snapshot()['operation'], 'uninstall')

    def test_cli_uninstall_never_creates_or_installs_environment(self):
        with patch.object(install_lifecycle, 'uninstall_app') as remove, \
             patch.object(install, 'app_environment') as environment, patch.object(install, 'pip_install') as pip:
            install.main(['--uninstall'])
        remove.assert_called_once_with()
        environment.assert_not_called()
        pip.assert_not_called()

    def test_stop_targets_only_the_process_owned_by_installer(self):
        state = install_ui.Installation()
        with self.assertRaises(RuntimeError):
            state.stop_workbench()
        child = unittest.mock.MagicMock()
        child.pid = 123456789
        child.poll.return_value = None
        state.app_process = child
        with patch.object(install_ui.subprocess,'run') as stop, patch.object(install_ui.os,'killpg',create=True) as kill:
            state.stop_workbench()
            if os.name == 'nt':
                self.assertEqual(stop.call_args.args[0],['taskkill','/PID','123456789','/T','/F'])
            else:
                kill.assert_called_once()
        self.assertEqual(state.app_state,'stopping')

    def test_modify_selected_engine_installs_only_its_extra_and_gpu_environment(self):
        with patch.object(install, 'configure_pip'), patch.object(install, 'app_environment',return_value='python312'), \
             patch.object(install,'pip_install') as pip, patch.object(install,'setup_engine') as gpu, patch('builtins.print'):
            install.main(['--engines','rapidocr','--without-tesseract','--device','gpu','--python','base312'])
        pip.assert_called_once_with('python312','-e',str(install.ROOT)+'[rapidocr]')
        gpu.assert_called_once_with('rapidocr','gpu','base312')

    def test_real_uninstall_removes_only_app_from_temporary_venv(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            subprocess.run([sys.executable,'-m','venv','--without-pip',str(directory/'venv')],check=True,capture_output=True)
            python = install_support.python_in(directory/'venv')
            self.assertFalse(install_lifecycle.inspect_installation(python)['installed'])
            info = 'automotive_ocr_bench-0.1.0.dist-info'
            wheel = directory/'automotive_ocr_bench-0.1.0-py3-none-any.whl'
            files = {'_ocrbench_uninstall_fixture.py':'# inert installation test\n',
                     info+'/METADATA':'Metadata-Version: 2.1\nName: automotive-ocr-bench\nVersion: 0.1.0\n',
                     info+'/WHEEL':'Wheel-Version: 1.0\nGenerator: installer-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
            files[info+'/RECORD'] = ''.join(name+',,\n' for name in [*files,info+'/RECORD'])
            with zipfile.ZipFile(wheel,'w') as archive:
                for name,value in files.items():archive.writestr(name,value)
            subprocess.run([sys.executable,'-m','pip','--python',str(python),'install','--no-index','--no-deps',str(wheel)],check=True,capture_output=True)
            self.assertTrue(install_lifecycle.inspect_installation(python)['installed'])
            marker = directory/'shared-library-and-saved-data.txt'
            marker.write_text('preserve')
            commands = []
            def run(args, **kwargs):
                commands.append([str(a) for a in args])
                subprocess.run(commands[-1],check=True,capture_output=True,**kwargs)
            with patch.object(install_lifecycle,'app_python',return_value=python), \
                 patch.object(install_lifecycle,'pip_controller',return_value=sys.executable), \
                 patch.object(install_lifecycle,'run',side_effect=run),patch('builtins.print'):
                install_lifecycle.uninstall_app()
            self.assertEqual(commands[0][-3:],['uninstall','--yes','automotive-ocr-bench'])
            self.assertFalse(install_lifecycle.inspect_installation(python)['installed'])
            self.assertTrue(python.is_file())
            self.assertEqual(marker.read_text(),'preserve')

    def test_no_arguments_open_ui_without_installing(self):
        with patch.object(install_ui, 'serve') as serve, patch.object(install, 'pip_install') as pip:
            install.main([])
        serve.assert_called_once_with()
        pip.assert_not_called()

    def test_explicit_arguments_keep_cli_installation(self):
        with patch.object(install_ui, 'serve') as serve, patch.object(install, 'configure_pip'), \
             patch.object(install, 'app_environment', return_value=Path('active-python')), \
             patch.object(install, 'pip_install') as pip, patch('builtins.print'):
            install.main(['--device', 'cpu', '--without-tesseract'])
        serve.assert_not_called()
        pip.assert_called_once_with(Path('active-python'), '-r', str(install.ROOT/'requirements.txt'))

    def test_options_preserve_spaces_and_use_no_shell(self):
        values = {'device': 'cpu', 'backend': 'pytesseract', 'tesseract_path': 'C:/Approved Tools/tesseract.exe',
                  'index_url': 'https://artifactory.example/simple', 'access_token':'test-token', 'cert': 'C:/Approved CA/ca.pem'}
        args = install_ui.install_arguments(values)
        self.assertIn('C:/Approved Tools/tesseract.exe', args)
        self.assertIn('--index-url', args)
        self.assertNotIn('--without-tesseract', args)
        self.assertNotIn('--tessdata-path', args)

    def test_skip_ignores_hidden_tesseract_fields(self):
        args = install_ui.install_arguments({'backend': 'skip', 'tesseract_path': 'old.exe', 'tessdata_path': 'old/models'})
        self.assertIn('--without-tesseract', args)
        self.assertNotIn('--tesseract-path', args)
        self.assertNotIn('--tessdata-path', args)

    def test_bundled_backend_does_not_pass_hidden_executable(self):
        args = install_ui.install_arguments({'backend': 'tesserocr', 'tesseract_path': 'old.exe', 'tessdata_path': 'models'})
        self.assertIn('tesserocr', args)
        self.assertNotIn('--tesseract-path', args)
        self.assertIn('--tessdata-path', args)

    def test_invalid_options_and_credential_urls_rejected(self):
        for value in [{'device': 'bad'}, {'backend': 'bad'}, {'unknown': 'option'}, {'cert': 1}, [],
                      {'python': '--help'}, {'index_url': 'https://user:secret@example/simple'},
                      {'index_url': 'https://example/simple?token=secret'}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                install_ui.install_arguments(value)

    def test_defaults_preserve_active_environment_and_normal_tesseract(self):
        with patch.object(install_ui, 'active_python', return_value=Path(sys.executable)), \
             patch.object(install_ui, 'app_python', return_value=Path(sys.executable)), \
             patch('ocrbench.native.tesseract_command', return_value='native/tesseract.exe'), \
             patch('ocrbench.native.tesseract_backend', return_value='pytesseract'), \
             patch('ocrbench.native.tesseract_data', return_value=Path('models')):
            config = install_ui.defaults()
        self.assertTrue(config['active'])
        self.assertEqual(config['target'], sys.executable)
        self.assertEqual(config['backend'], 'pytesseract')

    def test_http_page_status_and_start_protection(self):
        with server_for() as server:
            status, page = request(server, 'GET', '/')
            self.assertEqual(status, 200)
            self.assertIn(b'Install components', page)
            self.assertIn(b'Installation output', page)
            status, body = request(server, 'GET', '/api/config')
            self.assertEqual(status, 200)
            token = json.loads(body)['token']
            status, body = request(server, 'POST', '/api/install', {'backend': 'skip'})
            self.assertEqual(status, 403)
            status, _ = request(server, 'GET', '/api/config', headers={'Host': 'other.example'})
            self.assertEqual(status, 403)
            status, _ = request(server, 'POST', '/api/install', {'device': 'bad'}, token)
            self.assertEqual(status, 400)
            self.assertEqual(server.installation.snapshot()['state'], 'idle')

    def test_http_triggers_current_python_and_streams_success(self):
        child = unittest.mock.MagicMock()
        child.stdout = io.StringIO('Installing components\nComplete\n')
        child.wait.return_value = 0
        child.__enter__.return_value = child
        with patch.object(install_ui.subprocess, 'Popen', return_value=child) as launch, server_for() as server:
            status, _ = request(server, 'POST', '/api/install', {'backend': 'skip'}, server.installation.token)
            self.assertEqual(status, 202)
            for _ in range(100):
                snapshot = server.installation.snapshot()
                if snapshot['state'] != 'running':
                    break
                time.sleep(.01)
            self.assertEqual(snapshot['state'], 'succeeded')
            self.assertIn('Installing components', snapshot['output'])
            command = next(call for call in launch.call_args_list if str(install_ui.ROOT/'install.py') in call.args[0])
            args, kwargs = command
            self.assertEqual(args[0][0], sys.executable)
            self.assertIn('--without-tesseract', args[0])
            self.assertNotIn('shell', kwargs)
            self.assertEqual(kwargs['env']['PYTHONUNBUFFERED'], '1')

    def test_failure_and_duplicate_start_are_visible(self):
        state = install_ui.Installation()
        state.state = 'running'
        with server_for(state) as server:
            status, _ = request(server, 'POST', '/api/install', {'backend': 'skip'}, state.token)
            self.assertEqual(status, 409)
        with patch.object(install_ui.subprocess, 'Popen', side_effect=OSError('example failure')):
            state._run(['--device', 'cpu'])
        self.assertEqual(state.snapshot()['state'], 'failed')
        self.assertIn('example failure', state.snapshot()['output'])

    def test_nonzero_child_exit_is_failed(self):
        child = unittest.mock.MagicMock()
        child.stdout = io.StringIO('No matching distribution found\n')
        child.wait.return_value = 1
        child.__enter__.return_value = child
        state = install_ui.Installation()
        with patch.object(install_ui.subprocess, 'Popen', return_value=child):
            state._run(['--device', 'cpu'])
        self.assertEqual(state.snapshot()['state'], 'failed')
        self.assertEqual(state.snapshot()['returncode'], 1)

    def test_launch_api_requires_token_and_blocks_install_overlap(self):
        with server_for() as server:
            token = server.installation.token
            status, _ = request(server, 'POST', '/api/launch', {})
            self.assertEqual(status, 403)
            status, _ = request(server, 'POST', '/api/launch', {'python': 'other-python'}, token)
            self.assertEqual(status, 400)
            server.installation.state = 'running'
            status, _ = request(server, 'POST', '/api/launch', {}, token)
            self.assertEqual(status, 409)

    def test_launch_endpoint_starts_once_and_reports_url(self):
        launched = threading.Event()
        with server_for() as server, patch.object(server.installation, '_launch', side_effect=lambda port: launched.set()) as launch:
            status, body = request(server, 'POST', '/api/launch', {}, server.installation.token)
            self.assertEqual(status, 202)
            record = json.loads(body)
            self.assertEqual(record['app_state'], 'starting')
            self.assertTrue(record['app_url'].startswith('http://127.0.0.1:'))
            self.assertTrue(launched.wait(1))
            launch.assert_called_once()
            status, _ = request(server, 'POST', '/api/launch', {}, server.installation.token)
            self.assertEqual(status, 409)

    def test_workbench_launch_uses_current_python_and_collects_output(self):
        state = install_ui.Installation()
        state.app_state = 'starting'
        process = unittest.mock.MagicMock()
        process.poll.side_effect = [None, 0, 0]
        def child(*args, **kwargs):
            kwargs['stdout'].write(b'Workbench listening\n')
            kwargs['stdout'].flush()
            return process
        snapshots = []
        with patch.object(install_ui.subprocess, 'Popen', side_effect=child) as launch, \
             patch.object(state, '_ready', return_value=True), \
             patch.object(install_ui.time, 'sleep', side_effect=lambda delay: snapshots.append(state.snapshot())):
            state._launch(8765)
        args, kwargs = launch.call_args
        self.assertEqual(args[0], [sys.executable, '-u', str(install_ui.ROOT/'start.py'), '--port', '8765'])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(snapshots[0]['app_state'], 'running')
        self.assertIn('Workbench listening', state.snapshot()['app_output'])
        self.assertEqual(state.snapshot()['app_state'], 'stopped')

    def test_workbench_start_failure_is_visible(self):
        state = install_ui.Installation()
        with patch.object(install_ui.subprocess, 'Popen', side_effect=OSError('Cannot run Python')):
            state._launch(8765)
        self.assertEqual(state.snapshot()['app_state'], 'failed')
        self.assertIn('Cannot run Python', state.snapshot()['app_output'])
        process = unittest.mock.MagicMock()
        process.poll.return_value = 1
        with patch.object(install_ui.subprocess, 'Popen', return_value=process):
            state._launch(8765)
        self.assertEqual(state.snapshot()['app_state'], 'failed')
        self.assertIn('code 1', state.snapshot()['app_output'])

    def test_workbench_uses_another_port_when_default_is_occupied(self):
        with socket.socket() as listener:
            try:
                listener.bind(('127.0.0.1', 8765))
                listener.listen()
            except OSError:
                pass  # An already running app occupies it instead.
            state = install_ui.Installation()
            with patch.object(install_ui.threading, 'Thread'):
                state.launch()
            self.assertNotEqual(state.app_url, 'http://127.0.0.1:8765/')

    def test_cpu_engine_does_not_require_local_build_suffix(self):
        with patch.object(install_support, 'environment', return_value='python312'), \
             patch.object(install_support, 'pip_install') as pip, patch('builtins.print'):
            install_support.setup_engine('easyocr', 'cpu', 'base-python')
        self.assertEqual(pip.call_args_list[0].args, ('python312', 'torch==2.14.1', 'torchvision==0.29.1'))

    def test_torch_pins_accept_internal_and_existing_cpu_builds(self):
        from packaging.requirements import Requirement
        requirements = (install.ROOT/'requirements.txt').read_text().splitlines()
        for name, version in [('torch', '2.14.1'), ('torchvision', '0.29.1')]:
            req = Requirement(next(line for line in requirements if line.startswith(name+'==')))
            self.assertIn(version, req.specifier)
            self.assertIn(version+'+cpu', req.specifier)
            self.assertNotIn('1.0.0', req.specifier)

    def test_real_pip_resolves_public_build_without_network(self):
        # A minimal inert local wheel exercises pip's resolver without installing torch.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            wheel = directory/'torch-2.14.1-py3-none-any.whl'
            info = 'torch-2.14.1.dist-info'
            with zipfile.ZipFile(wheel, 'w') as archive:
                archive.writestr(info+'/METADATA', 'Metadata-Version: 2.1\nName: torch\nVersion: 2.14.1\n')
                archive.writestr(info+'/WHEEL', 'Wheel-Version: 1.0\nGenerator: installer-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
                archive.writestr(info+'/RECORD', '')
            command = [sys.executable, '-m', 'pip', 'install', '--dry-run', '--ignore-installed', '--no-index', '--no-deps', '--find-links', temporary]
            new = subprocess.run([*command, 'torch==2.14.1'], capture_output=True, text=True)
            self.assertEqual(new.returncode, 0, new.stderr)
            old = subprocess.run([*command, 'torch==2.14.1+cpu'], capture_output=True, text=True)
            self.assertNotEqual(old.returncode, 0)


if __name__ == '__main__':
    unittest.main()
