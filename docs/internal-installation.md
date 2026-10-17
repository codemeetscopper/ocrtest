# OCR Bench installation

Use Windows x64 and Python 3.12. Run:

```text
python install.py
```

Setup opens a local browser installer built with Python's standard library. Choose a sidebar page:

- **Components**: select CPU components, GPU engines, Tesseract, or Modify/Uninstall when an actual app registration exists.
- **Package source**: optionally provide an Artifactory simple-index URL, access token, username and CA certificate.
- **Environment**: review the target venv and choose the Python used for additional environments.

The installer appears as a modern card over an Ubuntu-inspired background. Logs are collapsed initially. Choose **Details** to expand them, then drag their top divider or use its arrow-key controls to resize. The remembered height does not automatically reopen the logs.

## Package configuration

Provide **both** the HTTPS Artifactory PyPI simple-index URL and token. Setup writes the authenticated, percent-encoded index URL to the user pip configuration before running normal pip commands:

- Windows: `%APPDATA%/pip/pip.ini`.
- Linux: `$XDG_CONFIG_HOME/pip/pip.conf`, or `~/.config/pip/pip.conf`.
- macOS: the existing `~/Library/Application Support/pip/pip.conf` location, otherwise `~/.config/pip/pip.conf`.

Enter an Artifactory username when the repository requires username plus token-as-password. Leave the username blank if the repository accepts the token as its username.

**The token is stored as plain text in pip.ini.** The installer keeps it out of its command arguments and redacts it from the displayed log. The browser does not receive saved credentials back from the file. The URL, token and username form fields are cleared after setup accepts them; later pip invocations can use the saved configuration.

Unrelated existing INI settings are preserved. The selected index is saved in both `[global]` and `[install]`; extra indexes and find-links in those sections are cleared. A supplied CA bundle is also saved. The update is atomic; malformed existing INI files are not overwritten. Certificate verification remains enabled.

If **both URL and token are blank**, setup leaves the pip configuration unchanged and runs pip normally. With no pre-existing package-source settings, pip uses PyPI. If an Artifactory source was saved previously, blank fields reuse that configuration rather than deleting it. One field without the other is rejected.

Pip's normal precedence remains in effect: environment variables and per-venv settings can override the user INI file. Setup identifies relevant environment-variable names without printing their values. It does not use a temporary PIP_INDEX_URL or disable pip config files.

For a personal PC using plain public PyPI, setup automatically adds the official [Paddle CUDA 13 index](https://www.paddlepaddle.org.cn/packages/stable/cu130/) for Paddle GPU and the official [PyTorch CUDA 13 index](https://download.pytorch.org/whl/cu130) for EasyOCR's GPU framework. These apply only to the framework installation commands; pip.ini is unchanged. The effective settings are checked separately inside each target venv, including environment and site configuration. A custom index, extra index, find-links or no-index setting disables this automatic supplementation. Artifactory installations use their configured sources exclusively and must mirror the selected CUDA wheels and dependencies; failed private installations do not fall back to public sources.

References: [pip configuration](https://pip.pypa.io/en/stable/topics/configuration/), [pip authentication](https://pip.pypa.io/en/stable/topics/authentication/).

## Command-line installation

Any command-line arguments run the CLI instead of the UI. To configure Artifactory, supply the URL and enter the token at the secure terminal prompt:

```text
python install.py --index-url "https://artifactory.example.com/artifactory/api/pypi/python-virtual/simple" --without-tesseract --device cpu
```

Noninteractive callers may provide `OCRBENCH_INDEX_TOKEN` and optional `OCRBENCH_INDEX_USERNAME` in the process environment. Keep tokens out of shell history.

To use normal saved pip settings:

```text
python install.py --without-tesseract --device cpu
python start.py
```

For all engines on a personal Windows PC, including native Tesseract:

```text
python install.py --auto-install-tesseract --device auto
```

Use `--cert "C:/OrgCertificates/corporate-ca.pem"` to save a corporate CA bundle.

## Environments and launch

When run with an existing venv's Python, app requirements are installed into that venv. No additional project .venv is created. Direct invocation of the venv's Python works without shell activation. Outside a venv, setup creates or reuses the project's .venv. The `--python` option selects the interpreter used to create additional environments; it does not replace the running app venv.

GPU environments remain separate under .engines/<engine>-gpu to avoid CPU/GPU dependency conflicts. All pip invocations read the normal configuration, including the saved Artifactory settings.

**Start Workbench** runs start.py using the installer's Python and environment. After the server is ready, choose **Open Workbench**. An occupied port 8765 is handled by choosing another local port. **Stop Workbench** stops an instance launched by this installer. Closing the installer leaves the workbench running.

## Modify, uninstall and detection

Existing installations are detected from the target environment's actual site-packages registration, not source-tree egg-info. Detection is refreshed on page reload and periodically so an external uninstall is reflected.

Modify/Repair installs or repairs selected components. Unchecking a component retains existing shared libraries.

Uninstall removes the OCR Bench app registration from the selected environment. Shared frameworks, virtual environments, the source checkout, models and run history are retained. It runs pip from a neutral temporary directory with isolated Python startup to avoid local editable metadata shadowing the installed distribution. Setup verifies registration removal and reports an error if it remains; a zero pip exit code alone is insufficient.

```text
python install.py --engines rapidocr,easyocr --without-tesseract --device cpu
python install.py --uninstall
```

## Packages and models

Every selected package and its build/transitive dependencies must exist in the effective pip source. Authentication does not supply missing artifacts.

| Component | Required package/build |
|---|---|
| RapidOCR CPU | rapidocr>=3.10,<4 and onnxruntime>=1.20,<2 |
| PaddleOCR CPU | paddleocr>=3,<4, paddlepaddle>=3,<4 and PaddleX dependencies |
| EasyOCR CPU | easyocr>=1.7,<2, torch==2.14.1 and torchvision==0.29.1 |
| Tesseract bundled wheel | Approved tesserocr==2.10.0, CPython 3.12 / Windows x64 wheel with bundled native libraries |
| Installed Tesseract | pytesseract plus an existing approved tesseract.exe |
| Auto install (personal PC) | Native Windows Tesseract and English data via WinGet, with the pytesseract wrapper |
| RapidOCR GPU | onnxruntime-gpu[cuda,cudnn]==1.31.0 and NVIDIA dependencies |
| EasyOCR GPU | torch==2.14.1+cu130 and torchvision==0.29.1+cu130 |
| PaddleOCR GPU | paddlepaddle-gpu==3.3.1, the tested Windows CUDA build and dependencies |

Public-version CPU torch pins accept matching installed +cpu builds. The bundled tesserocr Windows wheel must be provided by the selected source; ordinary public PyPI does not provide the approved Windows wheel used here. To use installed Tesseract instead:

```text
python install.py --tesseract-backend pytesseract --tesseract-path "C:/Approved Tools/Tesseract-OCR/tesseract.exe"
```

Tesseract's eng.traineddata is a separate model asset. Supply its containing folder with --tessdata-path, or stage it in data/models/tesseract/tessdata. Other engines also need approved model weights. Pip configuration controls package installation, not framework model-download hosts. Stage models/caches before offline use; EasyOCR supports download_enabled:false and model_storage_directory. PaddleOCR and RapidOCR accept explicit model paths.

**Auto install (personal PC)** explicitly enables a public native download on Windows through WinGet (`UB-Mannheim.TesseractOCR`). Windows App Installer must be installed; Windows may display an administrator prompt. An existing native installation is reused and verified. Setup checks the executable and English language data and saves the paths for the workbench, without requiring PATH refresh or the unavailable tesserocr wheel. This option hides and ignores existing executable/model form fields and uses the native install's English data. It is separate from pip/Artifactory; on a restricted work PC, use Installed Tesseract or the approved bundled wheel instead. OCR Bench uninstall retains the native Tesseract installation.

## GPU selection and partial results

Choose GPU engines independently from CPU components. For all CPU components plus RapidOCR GPU:

```text
python install.py --without-tesseract --device gpu --gpu-engines rapidocr
```

If one GPU setup fails, remaining selected GPU engines are still attempted. CPU and successful GPU setups are kept; the UI reports **Partially complete** and the CLI exits nonzero. GPU benchmark preflight still requires actual CUDA support.

Paddle GPU 2.6.x cannot satisfy this app's tested 3.3.1 requirement. Supply the correct Windows / Python 3.12 CUDA wheel in the effective repository or deselect PaddleOCR GPU while keeping PaddleOCR CPU. The installer does not silently downgrade or route a GPU request to CPU.
