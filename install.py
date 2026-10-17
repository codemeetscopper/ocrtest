"""Install OCR from the configured pip feed, using bundled or external Tesseract."""
import argparse
import sys
from scripts.install_support import ROOT, app_environment, app_python, has_nvidia, pip_install, setup_engine, ensure_tesseract, configure_pip, configure_tesserocr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_python = app_python()
    parser.add_argument('--python', default=str(default_python) if default_python.exists() else sys.executable,
                        help='64-bit Python 3.12 used when creating environments; the running venv is reused for app packages')
    parser.add_argument('--device', choices=('auto', 'cpu', 'gpu'), default='auto',
                        help='auto installs CUDA engines when nvidia-smi detects NVIDIA hardware')
    native = parser.add_mutually_exclusive_group()
    native.add_argument('--tesseract-path', help='Existing approved tesseract executable or its folder')
    native.add_argument('--without-tesseract', action='store_true', help='Skip native Tesseract validation; the other three OCR engines remain available')
    parser.add_argument('--tessdata-path', help='Existing folder containing eng.traineddata')
    parser.add_argument('--tesseract-backend', choices=('tesserocr', 'pytesseract'), default='tesserocr', help='Bundled Python wheel (default) or an existing native executable')
    parser.add_argument('--index-url', help='Internal Artifactory PyPI simple-index URL; otherwise use existing pip configuration')
    parser.add_argument('--cert', help='Corporate CA bundle for HTTPS package downloads')
    args = parser.parse_args()
    configure_pip(args.index_url, args.cert)
    if args.without_tesseract and args.tessdata_path:
        parser.error('--tessdata-path cannot be used with --without-tesseract')
    backend = 'pytesseract' if args.tesseract_path else args.tesseract_backend
    if not args.without_tesseract and backend == 'pytesseract':
        ensure_tesseract(args.tesseract_path, args.tessdata_path)
    target = app_environment(args.python)
    requirements = 'requirements-tesserocr.txt' if not args.without_tesseract and backend == 'tesserocr' else 'requirements.txt'
    pip_install(target, '-r', str(ROOT/requirements))
    if not args.without_tesseract and backend == 'tesserocr':
        configure_tesserocr(target, args.tessdata_path)
    gpu = args.device == 'gpu' or (args.device == 'auto' and has_nvidia())
    if gpu:
        for engine in ('rapidocr', 'paddleocr', 'easyocr'):
            setup_engine(engine, 'gpu', args.python)
    print('\nAll OCR Python components installed' + ('; native Tesseract skipped' if args.without_tesseract else '; native Tesseract verified')
          + ('; CUDA environments installed.' if gpu else '.'))
    print('Start the app: python start.py')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Installation failed: {error}', file=sys.stderr)
        raise SystemExit(1)
