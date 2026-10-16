"""Install every OCR component from requirements, without shell scripts."""
import argparse
import sys
from scripts.install_support import ROOT, environment, has_nvidia, pip_install, python_in, setup_engine, ensure_tesseract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=str(python_in(ROOT/'.venv')) if python_in(ROOT/'.venv').exists() else sys.executable,
                        help='64-bit Python 3.12 used to create environments')
    parser.add_argument('--device', choices=('auto', 'cpu', 'gpu'), default='auto',
                        help='auto installs CUDA engines when nvidia-smi detects NVIDIA hardware')
    args = parser.parse_args()
    target = environment(ROOT/'.venv', args.python)
    pip_install(target, '-r', str(ROOT/'requirements.txt'))
    ensure_tesseract()
    gpu = args.device == 'gpu' or (args.device == 'auto' and has_nvidia())
    if gpu:
        for engine in ('rapidocr', 'paddleocr', 'easyocr'):
            setup_engine(engine, 'gpu', args.python)
    print('\nAll CPU OCR components installed' + ('; CUDA environments installed.' if gpu else '.'))
    print('Start the app: python start.py')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Installation failed: {error}', file=sys.stderr)
        raise SystemExit(1)
