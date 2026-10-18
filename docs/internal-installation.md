# OCR Bench installation

Use Windows x64 and Python 3.10–3.13. Run:

```text
python install.py
```

Setup opens a local browser installer built with Python's standard library. Choose a sidebar page:

- **Components**: select CPU components, GPU engines, Tesseract, or Modify/Uninstall when an actual app registration exists.
- **Package source**: optionally provide an Artifactory simple-index URL, access token, username and CA certificate.
- **Environment**: review the target venv and choose the Python used for additional environments.

The installer appears as a compact card matching the workbench’s green and neutral theme. Logs are collapsed initially. Choose **Details** to expand them, then drag their top divider or use its arrow-key controls to resize. The remembered height does not automatically reopen the logs. Tesseract executable and language-path overrides are grouped under an expandable control to keep the component card compact.

## Package configuration

Provide **both** the HTTPS Artifactory PyPI simple-index URL and token. Setup saves the authenticated, percent-encoded index URL to the user pip configuration and selects that feed for this installation:

- Windows: `%APPDATA%/pip/pip.ini`.
- Linux: `$XDG_CONFIG_HOME/pip/pip.conf`, or `~/.config/pip/pip.conf`.
- macOS: the existing `~/Library/Application Support/pip/pip.conf` location, otherwise `~/.config/pip/pip.conf`.

Enter an Artifactory username when the repository requires username plus token-as-password. Leave the username blank if the repository accepts the token as its username.

**The token is stored as plain text in pip.ini.** The installer keeps it out of its command arguments and redacts it from the displayed log. The browser does not receive saved credentials back from the file. The URL, token and username form fields are cleared after setup accepts them. Standard pip commands outside this installer can use the saved configuration; for another Artifactory installer run, supply its details again.

Unrelated existing INI settings are preserved. The selected index is saved in both `[global]` and `[install]`; extra indexes and find-links in those sections are cleared. A supplied CA bundle is also saved. The update is atomic; malformed existing INI files are not overwritten. Certificate verification remains enabled.

If **both URL and token are blank**, setup selects public PyPI and official GPU wheel sources, even when saved pip configuration or environment variables name an older internal source. The saved files remain unchanged. One field without the other is rejected.

The selected source is authoritative for this installation and its pip build subprocesses. Setup uses a child environment with PIP_CONFIG_FILE set to the null device, clears inherited index/extra-index/find-links/no-index settings, and sets PIP_INDEX_URL to public PyPI or the supplied authenticated Artifactory URL. Tokens stay out of command arguments. The parent environment and saved files are not changed in public mode; optional certificates and environment constraints remain supported.

By default, public GPU setup selects CUDA 13 when the NVIDIA driver supports it, otherwise CUDA 12 (driver support for 12.8+). Override this with `--cuda cuda12` or `--cuda cuda13`, or the GPU compatibility selector. CUDA 12 uses PyTorch cu128, Paddle cu126 and ONNX Runtime >=1.21,<1.27; CUDA 13 uses cu130 vendor builds and ONNX Runtime >=1.27,<2. These family bounds follow the upstream CUDA build transition rather than an exact workstation version. The official PyTorch index is authoritative for its framework install, so a newer CPU-only PyPI wheel cannot win over a CUDA build. A detected CPU-only Torch installation in the GPU environment is re-resolved.

GPU source selection uses the current invocation’s explicit mode and does not import target pip to infer a source. Artifactory URL/token inputs select compatible versions exclusively from that feed; without them, public GPU sources are enabled. No missing private artifact triggers a public fallback. CPU packages and successful GPU installs are retained if another GPU setup fails.

Requirements use compatible major-version ranges: RapidOCR 3.x, PaddleOCR/Paddle 3.x, EasyOCR 1.7.x, Torch >=2.4,<3, torchvision >=0.19,<1 and tesserocr >=2.7,<3. Torch/torchvision are resolved together, and matching installed packages are reused. NumPy/OpenCV/Paddle/Torch still need binary-compatible wheels; an absent Python/platform wheel cannot be supplied by relaxing pins. A pip constraints file (`PIP_CONSTRAINT`) can enforce approved versions within these supported ranges.

Bootstrap requires pip >=23.3 for cross-venv installation. An older controller pip is upgraded directly before any --python command. The build backend retains its setuptools API minimum; feed content and Python/platform wheel tags still apply.

If the controller or an isolated GPU environment cannot load pip installation commands, setup runs the pip wheel bundled with Python in an isolated subprocess and force-reinstalls that wheel offline. This restores missing pip modules even when a newer installed version makes `ensurepip --upgrade` do nothing. The bootstrap performs an offline repair without changing pip.ini, tokens or the parent environment. Subsequent package operations use the selected installation source. The health check loads real install/uninstall commands, catching missing vendored files such as rich.traceback even if version metadata remains. Python must include ensurepip and its bundled wheel; otherwise setup reports a repair error. Uninstall uses the same recovery and refuses to claim success if either environment inspection or registration removal cannot be verified.

References: [ONNX Runtime CUDA families](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html), [pip configuration](https://pip.pypa.io/en/stable/topics/configuration/), [pip authentication](https://pip.pypa.io/en/stable/topics/authentication/).

## Command-line installation

Any command-line arguments run the CLI instead of the UI. To configure Artifactory, supply the URL and enter the token at the secure terminal prompt:

```text
python install.py --index-url "https://artifactory.example.com/artifactory/api/pypi/python-virtual/simple" --without-tesseract --device cpu
```

Noninteractive callers may provide `OCRBENCH_INDEX_TOKEN` and optional `OCRBENCH_INDEX_USERNAME` in the process environment. Keep tokens out of shell history.

To use public PyPI and official GPU wheels (the default):

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

GPU environments remain separate under .engines/<engine>-gpu to avoid CPU/GPU dependency conflicts. All pip invocations and build subprocesses use the source selected for this installation: public by default, Artifactory only with URL/token inputs.

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
| RapidOCR CPU | rapidocr>=3.0,<4 and onnxruntime>=1.20,<2 |
| PaddleOCR CPU | paddleocr>=3,<4, paddlepaddle>=3,<4 and PaddleX dependencies |
| EasyOCR CPU | easyocr>=1.7,<2, torch>=2.4,<3 and torchvision>=0.19,<1 |
| Tesseract bundled wheel | Compatible tesserocr>=2.7,<3 Windows x64 wheel for the selected Python version |
| Installed Tesseract | pytesseract plus an existing approved tesseract.exe |
| Auto install (personal PC) | Native Windows Tesseract and English data via WinGet, with the pytesseract wrapper |
| RapidOCR GPU | onnxruntime-gpu[cuda,cudnn]>=1.20,<2 and matching CUDA dependencies |
| EasyOCR GPU | Compatible CUDA torch>=2.4,<3 and torchvision>=0.19,<1, resolved together |
| PaddleOCR GPU | paddlepaddle-gpu>=3,<4, with a compatible CUDA build and dependencies |

CPU framework ranges also accept matching installed +cpu builds. Public PyPI does not supply tesserocr Windows wheels. Upstream directs Windows pip users to its separate [Windows wheel releases](https://github.com/simonflueckiger/tesserocr-windows_build/releases), which bundle the engine libraries. Choose a release for the required Tesseract version and match the Python/ABI/platform tags (for example, cp312-cp312-win_amd64 for CPython 3.12 x64). Work PC: have IT mirror an approved wheel into Artifactory, or supply an approved local wheel. Setup does not automatically contact GitHub or substitute an executable backend.

In Bundled mode, enter **Local wheel file**, or leave it blank to use the configured pip source. The CLI equivalent is:

```text
python install.py --device cpu --tesseract-backend tesserocr --tesserocr-wheel "C:/ApprovedPackages/tesserocr-2.10.0-cp312-cp312-win_amd64.whl" --tessdata-path "C:/OrgModels/tessdata"
```

Bundled setup verifies the binary and English model before installing the other components. Missing wheels produce a specific error with these alternatives; incompatible ABI/platform tags are rejected by pip. The same option is supported by scripts/setup_engine.py. Installing the wheel in a user-owned venv requires no administrator elevation, Conda or micromamba. Language models remain separate.

An explicitly supplied local wheel is reinstalled even if the binding version matches: upstream can package different Tesseract engine versions under the same tesserocr wheel version and filename. Configured-source installs continue to reuse matching installed packages.

To use installed Tesseract instead:

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

Paddle GPU 2.6.x cannot satisfy the PaddleOCR 3 API requirement. Supply a compatible Paddle GPU 3.x wheel for the selected Python and platform, or deselect PaddleOCR GPU while keeping PaddleOCR CPU. The installer does not silently downgrade or route a GPU request to CPU.
