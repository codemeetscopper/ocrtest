# Python setup and metric help validation

Validated 16 October 2026 on Windows x64 / Python 3.12.

- `python install.py --device cpu` completed successfully, including all four CPU Python engines and portable Tesseract 5.5.3.
- `python start.py` started the dashboard on port 8765.
- pip reported no broken requirements.
- Full hardware-enabled backend suite: 55 passed; the subsequently added language-data discovery test passed in targeted installer checks (7 unit tests).
- Browser preview/navigation regression suite: 4 passed.
- Actual inference from the app environment succeeded for RapidOCR, PaddleOCR, EasyOCR, and Tesseract on the supplied Pivi Pro image.
- Existing isolated CUDA environments passed all three real-image GPU tests.
- Browser checks verified four page glossaries, F1/P95 heading descriptions, native Tesseract discovery, and Python setup commands. No browser errors.
- HTML export contains the shared glossary.

All CPU Python dependencies are in requirements.txt. The complete installer additionally provisions native Tesseract and optionally isolated CUDA environments; raw pip requirements installation does not run native installers or create other virtual environments.
