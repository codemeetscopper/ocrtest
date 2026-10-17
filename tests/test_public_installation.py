"""Public versus private source routing and explicit native auto installation."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import install
from scripts import install_support as support, install_ui


class PublicInstallationTests(unittest.TestCase):
    def test_effective_pip_settings_respect_private_and_offline_sources(self):
        # Real pip parsing, no downloads. The target process reads the temporary config.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'pip.ini'
            env = {k:v for k,v in os.environ.items() if not k.startswith('PIP_')}
            env['PIP_CONFIG_FILE'] = str(path)
            for settings, expected in [
                ('index-url = https://pypi.org/simple\n', True),
                ('index-url = https://user:fake-token@internal.example/simple\n', False),
                ('index-url = https://pypi.org/simple\nextra-index-url = https://internal.example/simple\n', False),
                ('index-url = https://pypi.org/simple\nno-index = true\n', False),
                ('index-url = https://pypi.org/simple\nfind-links = /approved/wheels\n', False),
            ]:
                path.write_text('[install]\n'+settings)
                with self.subTest(settings=settings),patch.dict(os.environ, env, clear=True):
                    self.assertEqual(support.uses_public_pypi(sys.executable), expected)
            path.write_text('[install]\nindex-url = https://pypi.org/simple\n')
            env['PIP_INDEX_URL'] = 'https://internal.example/simple'
            with patch.dict(os.environ, env, clear=True):
                self.assertFalse(support.uses_public_pypi(sys.executable))

    def test_public_gpu_uses_official_vendor_indexes(self):
        for engine, host in [('easyocr','download.pytorch.org'), ('paddleocr','www.paddlepaddle.org.cn')]:
            with self.subTest(engine=engine),patch.object(support,'uses_public_pypi',return_value=True), \
                 patch.object(support,'pip_install') as pip,redirect_stdout(io.StringIO()):
                support.install_gpu_framework('target', engine)
                self.assertIn('--extra-index-url',pip.call_args.args)
                self.assertIn(host,pip.call_args.args[2])

    def test_private_gpu_never_adds_public_sources(self):
        for engine in ['easyocr','paddleocr']:
            with self.subTest(engine=engine),patch.object(support,'uses_public_pypi',return_value=False), \
                 patch.object(support,'pip_install') as pip,redirect_stdout(io.StringIO()):
                support.install_gpu_framework('target',engine)
                self.assertFalse(any('https://' in str(v) or 'index-url' in str(v) for v in pip.call_args.args))

    def test_source_probe_failure_does_not_enable_public_sources(self):
        with patch.object(support.subprocess,'check_output',side_effect=subprocess.TimeoutExpired('python',30)), \
             self.assertRaisesRegex(RuntimeError,'public GPU sources were not enabled'):
            support.uses_public_pypi('target')

    def test_auto_ui_ignores_hidden_existing_paths(self):
        args = install_ui.install_arguments({'backend':'auto','tesseract_path':'old.exe','tessdata_path':'old-data'})
        self.assertIn('--auto-install-tesseract',args)
        self.assertNotIn('--tesseract-path',args)
        self.assertNotIn('--tessdata-path',args)
        self.assertNotIn('tesserocr',args)

    def test_auto_cli_uses_native_backend_without_requesting_tesserocr(self):
        with patch.object(install,'configure_pip'),patch.object(install,'auto_install_tesseract') as auto, \
             patch.object(install,'app_environment',return_value='target'),patch.object(install,'pip_install') as pip, \
             patch.object(install,'configure_tesserocr') as bundled,redirect_stdout(io.StringIO()):
            install.main(['--engines','tesseract','--auto-install-tesseract','--device','cpu'])
        auto.assert_called_once_with()
        bundled.assert_not_called()
        self.assertFalse(any('tesserocr' in str(v) for call in pip.call_args_list for v in call.args))

    @unittest.skipUnless(os.name == 'nt', 'WinGet auto installer is Windows only')
    def test_auto_installs_and_verifies_runtime(self):
        with patch('ocrbench.native.tesseract_command',side_effect=[None,'installed/tesseract.exe']), \
             patch.object(support.shutil,'which',return_value='winget.exe'),patch.object(support,'run') as run, \
             patch.object(support,'ensure_tesseract',return_value='verified') as verify,redirect_stdout(io.StringIO()):
            self.assertEqual(support.auto_install_tesseract(),'verified')
        self.assertIn('UB-Mannheim.TesseractOCR',run.call_args.args[0])
        self.assertNotIn('shell',run.call_args.kwargs)
        verify.assert_called_once_with('installed/tesseract.exe')

    def test_auto_reuses_and_verifies_existing_native_engine(self):
        with patch('ocrbench.native.tesseract_command',return_value='installed.exe'), \
             patch.object(support,'run') as run,patch.object(support,'ensure_tesseract') as verify,redirect_stdout(io.StringIO()):
            support.auto_install_tesseract()
        run.assert_not_called()
        verify.assert_called_once_with('installed.exe')

    @unittest.skipUnless(os.name == 'nt', 'WinGet auto installer is Windows only')
    def test_auto_reports_failed_native_installation(self):
        with patch('ocrbench.native.tesseract_command',return_value=None), \
             patch.object(support.shutil,'which',return_value='winget.exe'), \
             patch.object(support,'run',side_effect=subprocess.CalledProcessError(1,['winget'])), \
             redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'WinGet could not install'):
            support.auto_install_tesseract()


if __name__ == '__main__':
    unittest.main()
