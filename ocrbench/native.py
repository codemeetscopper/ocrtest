"""Locate managed or existing native OCR tools without changing system PATH."""
import os
from pathlib import Path
import shutil
from .storage import ROOT


def tesseract_command():
    candidates = [os.environ.get('OCRBENCH_TESSERACT'),
                  str(ROOT/'.engines/tesseract-native/Library/bin/tesseract.exe'),
                  shutil.which('tesseract')]
    for variable in ('ProgramFiles', 'LOCALAPPDATA'):
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable])/'Tesseract-OCR/tesseract.exe'))
    return next((str(Path(p)) for p in candidates if p and Path(p).is_file()), None)


def tesseract_data(command):
    override = os.environ.get('TESSDATA_PREFIX')
    if override:
        return Path(override)
    path = Path(command).resolve()
    candidates = [path.parent/'tessdata', path.parent.parent/'share/tessdata',
                  path.parent.parent.parent/'share/tessdata']
    return next((p for p in candidates if (p/'eng.traineddata').is_file()), None)
