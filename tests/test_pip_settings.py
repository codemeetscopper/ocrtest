"""No-network checks for the normal pip.ini configuration flow."""
import configparser
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from scripts import install_support as support
from scripts import install_lifecycle as lifecycle
from scripts import install_ui


class PipSettingsTests(unittest.TestCase):
    def setUp(self):
        source = patch.object(support, '_package_source', {'mode':'public', 'index':support.PUBLIC_INDEX, 'cert':None})
        source.start()
        self.addCleanup(source.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)/'pip/pip.ini'
        self.patch_path = patch.object(support,'user_pip_config_path',return_value=self.path)
        self.patch_path.start()
        self.addCleanup(self.patch_path.stop)
        self.environment = patch.dict(os.environ,{'OCRBENCH_INDEX_TOKEN':'','OCRBENCH_INDEX_USERNAME':''})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_blank_inputs_leave_pip_configuration_untouched(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b'[global]\r\ntimeout = 77\r\n')
        before = self.path.read_bytes()
        with redirect_stdout(io.StringIO()),patch.object(support,'run') as run:
            support.configure_pip()
        self.assertEqual(self.path.read_bytes(),before)
        run.assert_not_called()

    def test_url_and_token_are_required_together_without_partial_writes(self):
        with patch.object(support.sys.stdin,'isatty',return_value=False):
            for url,token in [('https://artifactory.example/simple',''),('', 'fake-token')]:
                with self.subTest(url=url),patch.dict(os.environ,{'OCRBENCH_INDEX_TOKEN':token}),self.assertRaises(ValueError):
                    support.configure_pip(url)
        self.assertFalse(self.path.exists())

    def test_existing_settings_preserved_and_real_pip_reads_saved_credentials(self):
        self.path.parent.mkdir()
        self.path.write_text('[global]\ntimeout = 77\nextra-index-url = https://old.example/simple\n[install]\nprogress-bar = off\n')
        cert = self.path.parent/'ca.pem'; cert.touch()
        secret = 'test-token/a@b:%'
        with patch.dict(os.environ,{'OCRBENCH_INDEX_TOKEN':secret,'OCRBENCH_INDEX_USERNAME':'user@example'}),redirect_stdout(io.StringIO()) as output:
            support.configure_pip('https://artifactory.example/simple',str(cert))
        config = configparser.ConfigParser(interpolation=None);config.read(self.path)
        expected = 'https://user%40example:'+quote(secret,safe='')+'@artifactory.example/simple'
        self.assertEqual(config['global']['index-url'],expected)
        self.assertEqual(config['global']['timeout'],'77')
        self.assertEqual(config['install']['progress-bar'],'off')
        self.assertEqual(config['install']['index-url'],expected)
        self.assertEqual(config['global']['cert'],str(cert.resolve()))
        self.assertNotIn(secret,output.getvalue())
        self.assertNotIn(quote(secret,safe=''),output.getvalue())
        # Use a temporary config and ask real pip to parse it; no network access.
        env = os.environ.copy()
        for name in list(env):
            if name.startswith('PIP_'):env.pop(name)
        env['PIP_CONFIG_FILE'] = str(self.path)
        code = ('import json;from pip._internal.commands import create_command;'
                'o,a=create_command("install").parse_args([]);'
                'print(json.dumps([o.index_url,o.extra_index_urls,o.find_links,o.cert,o.timeout]))')
        actual = json.loads(subprocess.check_output([sys.executable,'-c',code],env=env,text=True))
        self.assertEqual(actual,[expected,[],[],str(cert.resolve()),77])

    def test_pip_install_uses_the_selected_source_environment(self):
        with patch.object(support,'pip_controller',return_value='controller-python'),patch.object(support,'run') as run:
            support.pip_install('target-python','rapidocr')
        self.assertEqual(run.call_args.kwargs['env']['PIP_INDEX_URL'],'https://pypi.org/simple')
        self.assertEqual(run.call_args.kwargs['env']['PIP_CONFIG_FILE'],os.devnull)
        self.assertNotIn('--index-url',run.call_args.args[0])
        self.assertNotIn('--extra-index-url',run.call_args.args[0])

    def test_saved_pip_credentials_are_redacted_without_a_new_token(self):
        child = unittest.mock.MagicMock()
        child.stdout = io.StringIO('Looking in indexes: https://user:previous-token@artifactory.example/simple\n')
        child.wait.return_value = 0
        child.__enter__.return_value = child
        with patch.object(install_ui,'inspect_installation',return_value={'installed':True,'version':'0.1.0'}):
            state = install_ui.Installation()
            with patch.object(install_ui.subprocess,'Popen',return_value=child):
                state._run(['--device','cpu'])
        self.assertNotIn('previous-token',state.snapshot()['output'])
        self.assertIn('[REDACTED]',state.snapshot()['output'])

    def test_invalid_existing_ini_is_not_overwritten(self):
        self.path.parent.mkdir();self.path.write_text('not an INI file\n')
        with patch.dict(os.environ,{'OCRBENCH_INDEX_TOKEN':'fake'}),self.assertRaises(RuntimeError):
            support.configure_pip('https://artifactory.example/simple')
        self.assertEqual(self.path.read_text(),'not an INI file\n')

    def test_uninstall_does_not_claim_success_if_registration_remains(self):
        existing = {'installed':True,'version':'0.1.0'}
        with patch.object(lifecycle,'inspect_installation',return_value=existing),patch.object(lifecycle,'run'), \
             patch.object(lifecycle,'pip_controller',return_value=sys.executable),redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(RuntimeError):lifecycle.uninstall_app()
        self.assertNotIn('OCR Bench removed',output.getvalue())

    def test_installer_refreshes_after_an_external_uninstall(self):
        with patch.object(install_ui,'inspect_installation',side_effect=[{'installed':True,'version':'0.1.0'}, {'installed':False,'version':''}]):
            state = install_ui.Installation()
            state.refresh_inventory(force=True)
        self.assertFalse(state.snapshot()['installation']['installed'])


if __name__ == '__main__':unittest.main()
