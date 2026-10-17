"""Install OCR from pip. No arguments opens the local installer UI; options run the CLI."""
import argparse
import json
import os
import sys
from scripts.install_support import ROOT, app_environment, app_python, has_nvidia, pip_install, setup_engine, ensure_tesseract, configure_pip, configure_tesserocr, auto_install_tesseract


class GPUProvisioningError(RuntimeError):
    """CPU installation succeeded, but one or more requested GPU setups failed."""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from scripts.install_ui import serve
        return serve()
    parser = argparse.ArgumentParser(description=__doc__)
    default_python = app_python()
    parser.add_argument('--python', default=str(default_python) if default_python.exists() else sys.executable,
                        help='64-bit Python 3.12 used when creating environments; the running venv is reused for app packages')
    parser.add_argument('--device', choices=('auto', 'cpu', 'gpu'), default='auto',
                        help='auto installs CUDA engines when nvidia-smi detects NVIDIA hardware')
    native = parser.add_mutually_exclusive_group()
    native.add_argument('--tesseract-path', help='Existing approved tesseract executable or its folder')
    native.add_argument('--without-tesseract', action='store_true', help='Skip native Tesseract validation; the other three OCR engines remain available')
    native.add_argument('--auto-install-tesseract', action='store_true', help='Install native Windows Tesseract with WinGet (personal PC), then verify English OCR')
    parser.add_argument('--tessdata-path', help='Existing folder containing eng.traineddata')
    parser.add_argument('--tesseract-backend', choices=('tesserocr', 'pytesseract'), default='tesserocr', help='Bundled Python wheel (default) or an existing native executable')
    parser.add_argument('--index-url', help='Save Artifactory URL and token to user pip.ini; token comes from OCRBENCH_INDEX_TOKEN or a secure terminal prompt')
    parser.add_argument('--cert', help='Corporate CA bundle for HTTPS package downloads')
    parser.add_argument('--engines', help='Comma-separated components to install/repair; empty installs the dashboard only')
    parser.add_argument('--gpu-engines', help='Comma-separated engines to provision for GPU; defaults to all selected supported engines')
    parser.add_argument('--uninstall', action='store_true', help='Remove OCR Bench from this environment, keeping shared packages and saved data')
    args = parser.parse_args(argv)
    if args.uninstall:
        from scripts.install_lifecycle import uninstall_app
        return uninstall_app()
    selected = {engine.strip() for engine in args.engines.split(',') if engine.strip()} if args.engines is not None else None
    if selected is not None and selected - {'rapidocr', 'paddleocr', 'easyocr', 'tesseract'}:
        parser.error('--engines contains an unknown component')
    selected_gpu = {engine.strip() for engine in args.gpu_engines.split(',') if engine.strip()} if args.gpu_engines is not None else None
    if selected_gpu is not None:
        if selected_gpu - {'rapidocr', 'paddleocr', 'easyocr'}:
            parser.error('--gpu-engines contains an unknown or CPU-only engine')
        if selected is not None and selected_gpu - selected:
            parser.error('--gpu-engines must also be selected in --engines')
        if args.device == 'cpu' and selected_gpu:
            parser.error('--gpu-engines requires --device gpu or auto')
    skip_tesseract = args.without_tesseract or (selected is not None and 'tesseract' not in selected)
    configure_pip(args.index_url, args.cert)
    if args.without_tesseract and args.tessdata_path:
        parser.error('--tessdata-path cannot be used with --without-tesseract')
    if args.auto_install_tesseract and args.tessdata_path:
        parser.error('--auto-install-tesseract uses the installed English data; omit --tessdata-path')
    backend = 'pytesseract' if args.tesseract_path or args.auto_install_tesseract else args.tesseract_backend
    if not skip_tesseract and args.auto_install_tesseract:
        auto_install_tesseract()
    elif not skip_tesseract and backend == 'pytesseract':
        ensure_tesseract(args.tesseract_path, args.tessdata_path)
    target = app_environment(args.python)
    if selected is None:
        requirements = 'requirements-tesserocr.txt' if not skip_tesseract and backend == 'tesserocr' else 'requirements.txt'
        pip_install(target, '-r', str(ROOT/requirements))
    else:
        extras = sorted(selected - ({'tesseract'} if skip_tesseract else set()))
        if 'easyocr' in selected:
            pip_install(target, 'torch==2.14.1', 'torchvision==0.29.1')
        pip_install(target, '-e', str(ROOT) + ('['+','.join(extras)+']' if extras else ''))
        if not skip_tesseract and backend == 'tesserocr':
            pip_install(target, '--only-binary=tesserocr', 'tesserocr==2.10.0')
    if not skip_tesseract and backend == 'tesserocr':
        configure_tesserocr(target, args.tessdata_path)
    gpu = args.device == 'gpu' or (args.device == 'auto' and has_nvidia())
    gpu_engines = [engine for engine in ('rapidocr', 'paddleocr', 'easyocr')
                   if (selected is None or engine in selected) and (selected_gpu is None or engine in selected_gpu)]
    results = {'cpu': 'installed', 'gpu': {}}
    if gpu:
        for engine in gpu_engines:
            try:
                setup_engine(engine, 'gpu', args.python)
                results['gpu'][engine] = {'state': 'installed'}
            except Exception as error:
                results['gpu'][engine] = {'state': 'failed', 'error': str(error)}
                print(f'\n{engine} GPU setup failed: {error}', flush=True)
                if engine == 'paddleocr':
                    print('PaddleOCR GPU requires the approved paddlepaddle-gpu==3.3.1 Windows x64 / Python 3.12 CUDA build. '
                          'The 2.6.x builds cannot satisfy this requirement. Plain PyPI installs also use the official Paddle CUDA index; '
                          'a configured internal feed must mirror this wheel and dependencies.', flush=True)
                print('Continuing with the remaining selected GPU engines. No CPU fallback was used for GPU setup.', flush=True)
    if os.environ.get('OCRBENCH_INSTALL_UI') == '1':
        print('OCRBENCH_INSTALL_RESULT ' + json.dumps(results), flush=True)
    if any(result['state'] == 'failed' for result in results['gpu'].values()):
        print('\nCPU/app components are installed. GPU setup summary:')
        for engine, result in results['gpu'].items():
            print(f"  {engine}: {result['state']}")
        print('Start the app: python start.py')
        raise GPUProvisioningError('Some selected GPU environments failed. CPU components and successful GPU setups were kept; see the summary above.')
    print('\n' + ('Selected OCR components installed' if selected is not None else 'All OCR Python components installed') + ('; native Tesseract skipped' if skip_tesseract else '; native Tesseract verified')
          + ('; CUDA environments installed.' if gpu and gpu_engines else '.'))
    print('Start the app: python start.py')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Installation failed: {error}', file=sys.stderr)
        raise SystemExit(1)
