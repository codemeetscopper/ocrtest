"""Provision one isolated OCR environment using Python."""
import argparse
import sys
from install_support import ENGINES, setup_engine, configure_pip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=ENGINES, required=True)
    parser.add_argument('--python', default=sys.executable, help='64-bit Python 3.12')
    parser.add_argument('--device', choices=('cpu', 'gpu'), default='cpu')
    parser.add_argument('--tesseract-path', help='Existing approved Tesseract executable or folder')
    parser.add_argument('--tessdata-path', help='Existing folder containing eng.traineddata')
    parser.add_argument('--tesseract-backend', choices=('tesserocr', 'pytesseract'), default='tesserocr')
    parser.add_argument('--index-url', help='Internal PyPI simple-index URL; otherwise honour corporate pip defaults')
    parser.add_argument('--cert', help='Corporate CA bundle')
    args = parser.parse_args()
    configure_pip(args.index_url, args.cert)
    if args.engine != 'tesseract' and (args.tesseract_path or args.tessdata_path):
        parser.error('Tesseract paths apply only to --engine tesseract')
    backend = 'pytesseract' if args.tesseract_path else args.tesseract_backend
    setup_engine(args.engine, args.device, args.python, args.tesseract_path, args.tessdata_path, backend)


if __name__ == '__main__':
    main()
