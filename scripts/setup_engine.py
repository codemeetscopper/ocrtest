"""Provision one isolated OCR environment using Python."""
import argparse
import sys
from install_support import ENGINES, setup_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=ENGINES, required=True)
    parser.add_argument('--python', default=sys.executable, help='64-bit Python 3.12')
    parser.add_argument('--device', choices=('cpu', 'gpu'), default='cpu')
    args = parser.parse_args()
    setup_engine(args.engine, args.device, args.python)


if __name__ == '__main__':
    main()
