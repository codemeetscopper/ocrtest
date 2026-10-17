# Internal-feed setup validation — 17 October 2026

The installer now accepts an internal PyPI simple-index URL and optional corporate CA bundle. Explicit-index mode disables inherited pip configuration files and extra package sources. GPU framework installation uses the same selected feed. No micromamba or Conda commands are used.

Validation completed:

- Full Python regression suite before the final compiled-extension discovery test: 67 passed, 3 skipped (optional GPU tests).
- Final internal-installation tests: 9 passed, including a real pip configuration parser check, inherited-source removal, credential-safe installer command logging, Windows compiled-extension discovery, and mocked tesserocr adapter behavior.
- Final combined installer regression: 25 passed, including real inference using the existing CPU installations of all four engines on the supplied image.
- Browser preview unit tests: 4 passed; JavaScript syntax and Python compilation checks passed.

The private Artifactory endpoint and an approved Windows tesserocr wheel were not available for installation testing. The user requested a placeholder URL. Native tesserocr inference and end-to-end installation from the private feed therefore remain unverified; adapter tests use a mocked native API. Existing OCR integration tests use already installed components. No public package source was used to substitute for the private feed.

## Existing virtual environment reuse

The app installer and launcher now prefer the running virtual environment, detected from the interpreter's prefixes rather than activation environment variables. Outside a venv, the existing project `.venv` creation/reuse behavior remains. GPU environments remain isolated.

Targeted installer regressions: **28 passed, 4 existing OCR inference tests deselected**. Coverage includes active-venv precedence over an existing project `.venv`, CPU/GPU installer targets, unsupported-Python rejection, launcher selection, and a subprocess test using a real external venv without activation. The subprocess test installs no packages and confirms no additional project `.venv` is created.

## Public-version torch pins and browser installer

CPU/app pins no longer require a `+cpu` build suffix. Both `torch==2.14.1` and `torchvision==0.29.1` accept the matching unsuffixed or locally labelled versions. CUDA pins remain unchanged. No-argument installation now serves a standard-library browser UI and requires an explicit click to start installation; CLI options retain direct installation.

The new dependency-light regression suite has **14 passing tests**. It covers argument routing, Tesseract option mapping, active target detection, HTTP request validation, single-install protection, output streaming, success/failure states, and subprocess interpreter selection. A real pip dry-run resolves an inert local test wheel with the new version pin and rejects the old suffixed pin, without network access or installing anything. Version-specifier checks cover retaining installed `+cpu` builds. The browser UI was opened with the `commonsdk` Python and its target and option validation were verified. No full installation from a private package index was performed.

## Ubuntu-inspired layout, resizable logs, and workbench launch

The installer now has an aubergine desktop background, orange actions, a section sidebar, and a horizontal terminal-style log window along the bottom. Its top divider supports pointer dragging and keyboard adjustment, and retains its height in browser storage. Browser checks changed the height from 210 to 250 with arrow keys, to 310 by dragging, and back to 210, then confirmed persistence after reload.

## Borderless maintenance and token authentication

The sidebar now follows right-panel focus, selections, navigation and scrolling, including the package section at the bottom of the scroll range. The outer frame, rounded window border and shadow were removed. Browser checks verified the Package source, Environment and Components highlights, token controls, detection of the existing commonsdk installation, and the Uninstall preview. No uninstall was performed on the user's environment.

Tests cover token URL encoding, child-environment-only credential transport, token redaction from raw/encoded output, selected-component modification, guarded uninstall, and stopping only the process owned by the installer. A real offline test installs an inert OCR Bench test wheel into a temporary venv, uninstalls it using the maintenance code, and confirms the environment and unrelated data remain. Detection scans target site-packages so leftover source-tree egg-info is not reported as an installed app. Authentication was verified with fake tokens; no private Artifactory endpoint or real token was available for an end-to-end authenticated download.

Final validation: **26 installer tests passed**. JavaScript syntax, Python compilation, and whitespace checks also passed. The browser was left in Modify / repair mode, with the user's installation unchanged.

## Independent GPU provisioning and partial completion

The supplied log shows CPU/app installation succeeded and RapidOCR GPU installed, then Paddle GPU provisioning failed because the configured source exposed 2.6.x rather than the required 3.3.1 build. EasyOCR GPU was never reached. GPU selection is now independent of CPU component selection through `--gpu-engines` and the UI's GPU engine checkboxes. All requested GPU setups are attempted, failures remain failures, and CPU/successful GPU installations are retained. The UI understands a partial result, while CLI exit status remains nonzero for failed requested GPU setups.

**30 installer tests passed**, including excluding Paddle GPU while retaining Paddle CPU, continuing to EasyOCR after a simulated Paddle failure, validating GPU choices, and displaying a structured partial result. No missing private-feed artifacts were downloaded or substituted. Python compilation and JavaScript syntax checks passed.

## Current setup flow: saved pip.ini, verified uninstall and distinct pages

This update supersedes the earlier per-process index/token behavior. Supplying both Artifactory URL and token now saves the authenticated index to the user pip configuration before normal pip calls. Blank inputs preserve existing settings. Tokens are stored as plain text in that INI file at the user's request; no test wrote real credentials or modified the user's real pip configuration. A real pip parser verified a temporary INI containing dummy percent-encoded credentials, certificate and preserved unrelated settings. All seven new pip-settings tests passed, alongside the 30 installer regressions.

Uninstall now runs from a neutral temporary cwd with isolated Python startup and without inherited PYTHONPATH/PYTHONHOME, then checks the actual target registration before reporting success. The offline temporary-venv test uses the same app version as the source checkout (0.1.0), verifies a fresh environment is not installed, and verifies install/uninstall without deleting shared data or the venv. Tests also cover refusing to report success when registration remains and refreshing installer detection after an external uninstall.

The UI now has separate Components, Package source and Environment panels, an Ubuntu-inspired background around the content card, and Details-controlled logs collapsed on initial load. Log expansion is never triggered by installation progress alone. JavaScript syntax and Python compilation are checked separately; browser verification covers page routing and Details expansion/collapse.

Final checks: the 30 installer regression cases passed with the user's commonsdk Python as the controller, including the same-version editable install/uninstall scenario. Eight pip-settings checks also passed, including a real pip configuration-parser check and redaction of saved-config URL credentials when no new token is supplied. Temporary test paths were used for every config write and uninstall. The user's current commonsdk app registration was left intact; the existing-installation badge is therefore accurate until that installation is removed.

**19 installer regression tests passed**, including the new protected launch endpoint, current-Python subprocess arguments, startup log collection, readiness transitions, launch failure, duplicate launch, installation overlap, and occupied-port handling. Python compilation and whitespace checks passed. The actual Start Workbench button launched `start.py` successfully; the app at `http://127.0.0.1:8765/api/system` reported interpreter `D:/Projects/sdks/commonsdk/Scripts/python.exe`. The installer displayed Workbench ready and its Open Workbench link. Closing the installer leaves workbench output redirected to a temporary log file so the running app is independent of the installer terminal.

## Personal PC sources and native Tesseract Auto install (2026-10-17)

Plain public PyPI now supplements GPU framework installs with the official CUDA 13 Paddle/PyTorch indexes. Target-venv pip settings are inspected first. Private indexes, configured extra indexes, find-links and offline settings do not receive automatic public sources. Nine new checks cover real pip configuration parsing (including environment precedence), public/private GPU routing, failing source inspection, Auto install UI/CLI mapping, native runtime reuse, WinGet execution/verification and native install failure. All **47 installer checks passed**: 30 installer UI/lifecycle checks, eight pip-settings checks and nine public-install checks. Python compilation, JavaScript syntax and whitespace checks also passed.

An actual full install was completed through the browser installer on this unrestricted Windows laptop, using the existing commonsdk environment and no Artifactory credentials. WinGet installed native Tesseract 5.4.0.20240606 with English data; its executable/data paths and pytesseract backend were saved. All three isolated GPU environments installed successfully, and the installer reported success with exit code zero. User pip.ini remained absent; public GPU indexes were command-local. No micromamba or activation scripts were used.

The supplied Pivi Pro image was then processed through the app's real workers:

| Engine | Observed runtime | Detected regions |
|---|---|---:|
| Tesseract | Native 5.4.0.20240606, pytesseract, CPU | 33 |
| RapidOCR | ONNX Runtime 1.31.0; CUDA provider active in detection, classification and recognition | 21 |
| PaddleOCR | Paddle 3.3.1, CUDA 13.0, gpu:0 | 21 |
| EasyOCR | PyTorch 2.14.1+cu130, CUDA 13.0, cuda | 28 |

GPU tests used the NVIDIA GeForce RTX 4060 Laptop GPU. Region counts demonstrate working inference, not accuracy scores. Browser checks verified the Auto install selection, hidden executable/model fields in that mode, all three GPU success results, collapsed Details and re-enabled controls after completion. No real internal Artifactory endpoint/token was available; private-source isolation was verified with temporary configurations and fake credentials.
