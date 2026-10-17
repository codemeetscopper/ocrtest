"""Launch the local workbench without activating a shell environment."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    from scripts.install_support import app_python
    python = app_python()
    if not python.exists():
        parser.error('App environment missing. Run python install.py first.')
    print(f'OCR Bench: http://127.0.0.1:{args.port}', flush=True)
    try:
        return subprocess.call([str(python), '-m', 'ocrbench', 'serve', '--port', str(args.port)], cwd=root)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
