"""Locate managed or existing native OCR tools without changing system PATH."""
import os
from pathlib import Path
import shutil
from .storage import ROOT, read_json


def tesseract_backend():
    return os.environ.get('OCRBENCH_TESSERACT_BACKEND') or read_json(ROOT/'.engines/native-tools.json', {}).get('backend', 'pytesseract')


def tesserocr_data():
    settings = read_json(ROOT/'.engines/native-tools.json', {})
    explicit = os.environ.get('TESSDATA_PREFIX') or settings.get('tessdata')
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates = [ROOT/'data/models/tesseract/tessdata', ROOT/'data/models/tesseract',
                  ROOT/'.engines/tesseract-native/share/tessdata']
    return next((p for p in candidates if (p/'eng.traineddata').is_file()), None)


def tesseract_command():
    override = os.environ.get('OCRBENCH_TESSERACT') or read_json(ROOT/'.engines/native-tools.json', {}).get('tesseract')
    if override:
        return str(Path(override)) if Path(override).is_file() else None
    candidates = [shutil.which('tesseract')]
    for variable in ('ProgramFiles', 'LOCALAPPDATA'):
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable])/'Tesseract-OCR/tesseract.exe'))
    if os.environ.get('LOCALAPPDATA'):
        candidates.append(str(Path(os.environ['LOCALAPPDATA'])/'Programs/Tesseract-OCR/tesseract.exe'))
    candidates.append(str(ROOT/'.engines/tesseract-native/Library/bin/tesseract.exe'))
    return next((str(Path(p)) for p in candidates if p and Path(p).is_file()), None)


def tesseract_data(command):
    override = os.environ.get('TESSDATA_PREFIX')
    if override:
        return Path(override)
    path = Path(command).resolve()
    settings = read_json(ROOT/'.engines/native-tools.json', {})
    if settings.get('tesseract') and Path(settings['tesseract']).resolve() == path and settings.get('tessdata'):
        return Path(settings['tessdata'])
    candidates = [path.parent/'tessdata', path.parent.parent/'share/tessdata',
                  path.parent.parent.parent/'share/tessdata']
    return next((p for p in candidates if (p/'eng.traineddata').is_file()), None)
