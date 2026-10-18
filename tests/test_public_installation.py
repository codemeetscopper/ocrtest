"""Public versus private source routing and explicit native auto installation."""
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

import install
from scripts import install_support as support, install_ui


class PublicInstallationTests(unittest.TestCase):
    def setUp(self):
        source = patch.object(support, '_package_source', {'mode':'public', 'index':support.PUBLIC_INDEX, 'cert':None})
        source.start()
        self.addCleanup(source.stop)

    def test_blank_details_override_saved_and_environment_sources_for_this_install(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'pip.ini'
            path.write_text('[install]\nindex-url = https://fake-token@internal.example/simple\nno-index = true\n')
            before = path.read_bytes()
            with patch.dict(os.environ, {'PIP_CONFIG_FILE':str(path),
                        'PIP_INDEX_URL':'https://old.example/simple',
                        'PIP_EXTRA_INDEX_URL':'https://extra.example/simple',
                        'PIP_FIND_LINKS':'/old/wheels','PIP_NO_INDEX':'1',
                        'OCRBENCH_INDEX_TOKEN':'','OCRBENCH_INDEX_USERNAME':''}),redirect_stdout(io.StringIO()):
                support.configure_pip()
                self.assertTrue(support.uses_public_pypi(sys.executable))
                # Ask real pip to parse the environment used by install/build children.
                code = ('import json;from pip._internal.commands import create_command;'
                        'o,_=create_command("install").parse_args([]);'
                        'print(json.dumps([o.index_url,o.extra_index_urls,o.find_links,o.no_index]))')
                actual = json.loads(subprocess.check_output([sys.executable,'-I','-c',code],
                                                            env=support.pip_environment(),text=True))
                self.assertEqual(actual,['https://pypi.org/simple',[],[],False])
            self.assertEqual(path.read_bytes(),before)

    def test_explicit_artifactory_is_authoritative_even_with_public_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'pip.ini'
            with patch.object(support,'user_pip_config_path',return_value=path), \
                 patch.dict(os.environ,{'OCRBENCH_INDEX_TOKEN':'fake-token',
                    'OCRBENCH_INDEX_USERNAME':'','PIP_INDEX_URL':'https://pypi.org/simple',
                    'PIP_EXTRA_INDEX_URL':'https://old.example/simple'}),redirect_stdout(io.StringIO()):
                support.configure_pip('https://internal.example/simple')
                self.assertFalse(support.uses_public_pypi('target'))
                env=support.pip_environment()
                self.assertEqual(env['PIP_INDEX_URL'],'https://fake-token@internal.example/simple')
                self.assertEqual(env['PIP_EXTRA_INDEX_URL'],'')
                self.assertEqual(env['PIP_CONFIG_FILE'],os.devnull)

    def test_public_gpu_uses_official_vendor_indexes(self):
        for engine, host in [('easyocr','download.pytorch.org'), ('paddleocr','www.paddlepaddle.org.cn')]:
            with self.subTest(engine=engine),patch.object(support,'uses_public_pypi',return_value=True), \
                 patch.object(support,'pip_install') as pip,patch.object(support,'torch_needs_repair',return_value=False),redirect_stdout(io.StringIO()):
                support.install_gpu_framework('target', engine)
                self.assertIn('--index-url' if engine == 'easyocr' else '--extra-index-url',pip.call_args.args)
                self.assertIn(host,pip.call_args.args[2])

    def test_private_gpu_never_adds_public_sources(self):
        for engine in ['easyocr','paddleocr']:
            with self.subTest(engine=engine),patch.object(support,'uses_public_pypi',return_value=False), \
                 patch.object(support,'pip_install') as pip,patch.object(support,'torch_needs_repair',return_value=False),redirect_stdout(io.StringIO()):
                support.install_gpu_framework('target',engine)
                self.assertFalse(any('https://' in str(v) or 'index-url' in str(v) for v in pip.call_args.args))

    def test_source_selection_does_not_import_target_pip(self):
        with patch.object(support.subprocess,'check_output',side_effect=AssertionError('No pip source probe')):
            self.assertTrue(support.uses_public_pypi('target-with-damaged-pip'))

    def test_auto_ui_ignores_hidden_existing_paths(self):
        args = install_ui.install_arguments({'backend':'auto','tesseract_path':'old.exe','tessdata_path':'old-data'})
        self.assertIn('--auto-install-tesseract',args)
        self.assertNotIn('--tesseract-path',args)
        self.assertNotIn('--tessdata-path',args)
        self.assertNotIn('tesserocr',args)

    def test_auto_cli_uses_native_backend_without_requesting_tesserocr(self):
        with patch.object(install,'configure_pip'),patch.object(install,'auto_install_tesseract') as auto, \
             patch.object(install,'app_environment',return_value='target'),patch.object(install,'pip_install') as pip, \
             patch.object(install,'install_tesserocr') as bundled,redirect_stdout(io.StringIO()):
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
