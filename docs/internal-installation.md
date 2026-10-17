# Install from internal Artifactory, without micromamba

Use Windows x64 and Python 3.12. All package installations now use your pip configuration. Setup contains no public PyTorch/Paddle index overrides and does not use micromamba, Conda, shell activation, or a system Tesseract installer.

When run using an existing virtual environment's Python, `install.py` installs the app and CPU OCR requirements into that environment, even if the project already has a `.venv`. It does not create an additional project `.venv`. This also works when invoking the environment's Python directly without activation. `start.py` uses the same running environment; run it with that environment's Python too. Outside a virtual environment, setup creates or reuses the project's `.venv`, and the launcher uses it. The `--python` option selects the Python used to create environments; it does not replace the running app venv. The Python 3.12 / 64-bit requirement still applies.

GPU framework builds continue to use separate `.engines/<engine>-gpu` environments to avoid conflicting CPU/GPU dependencies. Use `--device cpu` to install only into the current app environment.

## If corporate pip is already configured

Place an approved `eng.traineddata` in a local model folder, then run:

```text
python install.py --tessdata-path "C:/OrgModels/tessdata"
python start.py
```

The default Tesseract backend is now **tesserocr**. Its approved Windows wheel contains the native Tesseract libraries; no `tesseract.exe` is needed. Setup validates the model and library and records the choice in `.engines/native-tools.json`. Restart a running app after changing that choice.

## Specify one internal package source explicitly

Replace the example URL with your IT-provided **PyPI simple-index** URL:

```text
python install.py --index-url "https://artifactory.example.com/artifactory/api/pypi/python-virtual/simple" --tessdata-path "C:/OrgModels/tessdata"
```

With `--index-url`, setup uses only that index: it ignores inherited pip configuration files and removes extra-index/find-links environment settings for its child processes. This prevents a configured public fallback. The URL is held in the child-process environment, not saved in project files or printed by the installer's command logger.

For a corporate CA bundle:

```text
python install.py --index-url "https://artifactory.example.com/artifactory/api/pypi/python-virtual/simple" --cert "C:/OrgCertificates/corporate-ca.pem" --tessdata-path "C:/OrgModels/tessdata"
```

`--cert` sets pip's CA bundle while preserving certificate verification. Because explicit-index mode ignores pip configuration files, supply the CA with `--cert` or `PIP_CERT` if it was previously configured only in pip.ini. Use your organisation's approved keyring/netrc authentication, or existing pip authentication without the explicit-index flag. Do not put credentials in this checkout or send them in chat. `PIP_KEYRING_PROVIDER` and certificate-related environment settings are inherited.

## Persistent pip configuration instead

IT can configure `%APPDATA%/pip/pip.ini` on Windows. A credential-free example is in `config/pip.ini.example`. An organisation-managed configuration takes precedence over this example; use IT's settings. The installer honours existing pip settings when `--index-url` is omitted. Environment variables can override pip.ini, so check that extra package sources are not configured if all packages must come from one feed.

## Required repository contents

Mirror the application's normal dependencies and build dependencies (`setuptools`, pip), plus:

| Component | Required package/build |
|---|---|
| RapidOCR CPU | `rapidocr>=3.10,<4`, `onnxruntime>=1.20,<2` |
| PaddleOCR CPU | `paddleocr>=3,<4`, `paddlepaddle>=3,<4`, their PaddleX dependencies |
| EasyOCR CPU | `easyocr>=1.7,<2`, `torch==2.14.1+cpu`, `torchvision==0.29.1+cpu` |
| Tesseract wheel | `tesserocr==2.10.0`, CPython 3.12 / Windows x64 wheel bundling Tesseract 5.5.2 and its DLLs |
| Legacy executable wrapper | `pytesseract>=0.3.13` remains available for existing approved native installations |
| RapidOCR GPU | `onnxruntime-gpu[cuda,cudnn]==1.31.0` plus its NVIDIA runtime dependencies |
| EasyOCR GPU | `torch==2.14.1+cu130`, `torchvision==0.29.1+cu130` |
| PaddleOCR GPU | `paddlepaddle-gpu==3.3.1`, **the tested CUDA 13 Windows wheel**, plus its NVIDIA dependencies |

The approved tesserocr wheel must be mirrored into Artifactory; ordinary public PyPI does not provide the Windows build used here. Match Python version, architecture, and the bundled native library version. Setup requires a binary wheel for tesserocr and will not attempt a source build.

`--device cpu` installs CPU components only. The default `--device auto` also installs three isolated GPU environments when NVIDIA hardware is detected. `--device gpu` explicitly requests those environments. GPU frameworks remain separate from CPU builds. Runtime preflight continues to reject silent CPU fallback.

`requirements.txt` installs the CPU frameworks and Python wrappers. `requirements-tesserocr.txt` adds the bundled Tesseract wheel. Both contain package specifications only and inherit the chosen feed. For Python packages only, after corporate pip configuration:

```text
python -m pip install -r requirements-tesserocr.txt
```

Use `install.py` to create environments and validate/persist model settings.

## Models and offline operation

`eng.traineddata` is a **model asset**, not supplied by the Windows tesserocr wheel. Have IT stage it from the internal artifact store, or package the model internally and pass its extracted directory. Setup does not download it from GitHub or another public host. The folder must contain `eng.traineddata`, not another nested tessdata folder.

The other OCR engines also use model weights, which are not necessarily included in Python wheels. Stage approved weights before offline use: EasyOCR supports `model_storage_directory` and `download_enabled: false`; PaddleOCR supports explicit model directories; RapidOCR supports explicit detector/classifier/recognizer model paths. Existing caches can be reused. An internal pip index configures Python package installation, not framework-specific model download URLs.

## Backend identity and legacy support

The tesserocr backend reuses the Tesseract API inside the worker and produces text-line polygons and confidence. The legacy pytesseract backend starts the native executable for each request. Runs record the wrapper, native version, execution mode, model hashes, and options; compare matching backends when interpreting latency changes.

Tesserocr accepts `options.psm` (default 11), `options.oem` (default 3), `options.variables`, and `options.tessdata_dir`. It rejects legacy CLI `options.config` rather than silently ignoring it. English `en` is mapped to `eng`. Tesseract remains CPU-only.

To keep an existing approved executable instead:

```text
python install.py --tesseract-backend pytesseract --tesseract-path "C:/Approved Tools/Tesseract-OCR/tesseract.exe"
```

References: [pip configuration](https://pip.pypa.io/en/stable/topics/configuration/), [pip authentication](https://pip.pypa.io/en/stable/topics/authentication/), [tesserocr API](https://github.com/sirfz/tesserocr), [Windows wheel packaging](https://github.com/simonflueckiger/tesserocr-windows_build).
