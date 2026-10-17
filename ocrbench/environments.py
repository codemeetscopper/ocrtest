"""Resolve device-specific interpreters without replacing the CPU runtime."""
import sys
from .storage import ROOT


def discovered_interpreter(engine, device="cpu"):
    name = engine + ("-gpu" if device == "gpu" else "")
    directory = ROOT / ".engines" / name
    interpreter = directory / "Scripts" / "python.exe"
    if engine == 'tesseract':
        from .native import tesseract_backend
        package = tesseract_backend()
    else:
        package = engine
    site = directory / 'Lib' / 'site-packages'
    present = (site/package).is_dir() or any(site.glob(package+'*.pyd'))
    if interpreter.exists() and present:
        return str(interpreter)
    return None


def resolve_interpreter(config):
    return (config.get("python_path") or discovered_interpreter(config["engine"], config.get("device", "cpu"))
            or discovered_interpreter(config["engine"]) or sys.executable)
