"""Resolve device-specific interpreters without replacing the CPU runtime."""
import sys
from .storage import ROOT


def discovered_interpreter(engine, device="cpu"):
    name = engine + ("-gpu" if device == "gpu" else "")
    directory = ROOT / ".engines" / name
    interpreter = directory / "Scripts" / "python.exe"
    package = "pytesseract" if engine == "tesseract" else engine
    if interpreter.exists() and (directory / "Lib" / "site-packages" / package).is_dir():
        return str(interpreter)
    return None


def resolve_interpreter(config):
    return (config.get("python_path") or discovered_interpreter(config["engine"], config.get("device", "cpu"))
            or discovered_interpreter(config["engine"]) or sys.executable)
