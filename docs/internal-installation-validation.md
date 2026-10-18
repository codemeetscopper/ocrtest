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

## Flexible dependency resolution and compact workbench theme (2026-10-18)

Removed workstation-specific exact pins for Torch, torchvision, ONNX Runtime GPU, Paddle GPU, EasyOCR and tesserocr. Torch/torchvision now resolve together; approved older releases within supported API ranges can be used. Added a direct Pydantic 2 requirement because the app uses its v2 validator API even though some FastAPI versions also allow v1. The installer accepts Windows x64 Python 3.10–3.13, and pip >=23.3 is sufficient for cross-venv setup. Older controller pip is upgraded directly before using --python.

Public GPU setup selects CUDA 12/13 by driver support, with an explicit override. The NVIDIA detector handles both CUDA Version and the newer CUDA UMD Version banner. ONNX bounds follow its upstream 1.27 CUDA-family transition. The PyTorch vendor index is authoritative for public CUDA framework resolution; private feeds receive no added public hosts and retain their own approved builds. A CPU-only Torch installation in a GPU environment is re-resolved. Missing platform wheels and incompatible API major versions are still errors.

Validation: **147 Python tests passed, 7 skipped**, with 23 passing subtests; all eight JavaScript tests passed. The 17 compatibility cases were also rerun after the final policy edit. A real offline pip dry-run paired inert Torch 2.7.1 and torchvision 0.22.1 wheels from a local feed; this tests resolver behavior, not older binary inference. Python compilation, installer JavaScript syntax and whitespace checks passed.

An actual public-source repair with the new policy completed successfully in commonsdk and all three GPU environments. Compatible installed framework versions were retained. Real workers processed the supplied Pivi Pro image again: RapidOCR/ORT 1.31.0 returned 21 regions on CUDA, Paddle 3.3.1 returned 21 on gpu:0, EasyOCR/Torch 2.14.1+cu130 returned 28 on CUDA, and native Tesseract 5.4.0.20240606 returned 33 on CPU. The app environment's pip check reported no broken requirements. A transient test download caused by the changed NVIDIA banner was stopped before installation; corrected detection selected CUDA 13, and the final repair succeeded.

The installer now uses a compact 980px-wide, 620px-high maximum card (bounded by the viewport), dark green sidebar, workbench typography and green actions. Tesseract path overrides and logs are expandable. Browser security policy blocked access to the live preview, so visual layout verification was unavailable; no alternate browser surface or screenshot workaround was used. The updated installer is served at http://127.0.0.1:52706/. The work PC and its real Artifactory contents remain unavailable for direct testing.

## Damaged pip recovery and lifecycle verification (2026-10-18)

Reproduced the reported missing `pip._vendor.packaging.tags` in commonsdk. `ensurepip --upgrade` retained the newer damaged pip installation. Setup now runs Python's bundled wheel in an isolated subprocess and force-reinstalls pip offline before checking it again. This repair is shared by installation and uninstall. The offline bootstrap leaves user pip configuration and parent environment unchanged; subsequent installations use normal pip settings. Uninstall also rejects an initial environment-inspection failure instead of treating it as an absent installation.

A fresh temporary venv reproduced missing vendor code with newer pip metadata; the old ensurepip command left it broken, while the new recovery restored the actual import without contacting a package index. A temporary config containing dummy credentials and restrictive pip environment variables remained unchanged, with no token in output. Real temporary-venv checks covered install, uninstall, reinstall, CLI uninstall and repeated uninstall while preserving data and the environment.

Repaired the actual commonsdk pip installation. Additional application checks identified damaged NumPy/ujson binaries with missing DLL dependencies; reinstalling those same versions restored their imports. A real installation through the local installer API then completed successfully for all four CPU OCR components, including native Tesseract verification. The app registration remained installed and pip check reported no broken requirements. Uninstall verification used only disposable environments, leaving the user's app registration and saved runs intact.

Final validation: **151 Python tests passed, 7 skipped**, with 23 passing subtests. This includes real CPU inference for all four engines using the supplied Pivi Pro image, offline pip recovery and the expanded lifecycle checks. Python compilation and whitespace checks also passed.

## Bundled Tesseract Windows wheel support (2026-10-18)

Confirmed that the selected public PyPI source did not expose a matching Windows tesserocr binary. Upstream's installation documentation directs Windows pip users to its separate Windows build releases. Bundled mode now accepts a local `.whl` through the UI and `--tesserocr-wheel` in both Python installer entry points; leaving it blank uses configured pip sources. No automatic GitHub fallback or alternate backend was introduced. Setup verifies the binary and English data before installing unrelated OCR components and reports a specific missing-wheel error.

Downloaded the upstream Windows x64 CPython 3.12 wheel from the tesserocr 2.10.0 / Tesseract 5.5.2 release for this personal-PC test. Its SHA-256 matched the release API's digest (`e05d41a2b0e6f38f3a5195d05a73674d72152a775d1b8ebe481ca9306f94d27a`). The wheel is stored under the ignored `.engines/wheels/` directory. Actual CLI installation and a local installer API job both succeeded using this local wheel and the existing English model. The SDK's active backend is now tesserocr; the real worker reported Tesseract 5.5.2 and detected 34 text regions in the supplied Pivi Pro image. Engine libraries came from the wheel; no elevated native installation was run. Pip check found no broken requirements.

New checks cover configured-source failure guidance, local wheel arguments and verification, invalid wheel paths, stopping before other components on bundled failure, UI backend scoping, incompatible CLI options, and dashboard readiness without an executable. A previous test assuming that native executable mode was always active now selects that backend explicitly, so it is independent of the user's saved bundled setting. Python compilation and installer JavaScript syntax checks passed.

The full suite passed **158 tests, with 7 skipped and 23 passing subtests**. Subsequent focused checks cover reinstalling the explicitly selected local binary even when its binding version matches, and keeping the saved bundled backend/model path selected in installer defaults when no native executable exists. The real explicit-wheel reinstall also succeeded and verified Tesseract 5.5.2 again.

## Explicit public default and isolated GPU pip recovery (2026-10-18)

This source policy supersedes the earlier saved-config inference: blank Artifactory URL/token fields now select public PyPI and official CUDA wheel sources for the entire installation, even if old pip configuration or environment variables name an internal feed. Supplying both fields selects Artifactory exclusively and still saves those details to user pip.ini. Per-command child environments make this choice authoritative for pip and build subprocesses without modifying saved files in public mode. Certificates remain supported; saved Artifactory certificates are reused for an explicitly selected internal installation. Tokens stay out of command arguments and are redacted from UI output.

The supplied log showed that all three GPU environments had a missing pip vendored rich.traceback module. Source selection no longer imports target pip internals. Environment setup now separately checks that actual pip install/uninstall commands load, and repairs the target interpreter offline from its bundled wheel before installing packages. This catches failures that version metadata or a satisfied pip requirement can miss.

Validation: **161 Python tests passed, 7 skipped, with 18 passing subtests**. Both missing packaging.tags and rich.traceback were reproduced and repaired in disposable target venvs using a different controller interpreter. A real pip parser verified that stale authenticated configuration, extra indexes, find-links and no-index settings do not override public mode. Explicit Artifactory mode remained exclusive despite inherited public index settings. The 18 source/settings checks also passed under stdlib unittest, and again after certificate handling was refined. Python compilation, installer JavaScript syntax and whitespace checks passed.

Actual GPU environment verification exposed additional missing package metadata and runtime files in the existing environments. These were restored at their recorded versions from public sources, with CUDA frameworks obtained from the appropriate official vendor indexes. This was recovery of the current environments, not a reintroduction of exact version pins in installation requirements. The app environment, model caches and saved runs were preserved. Using the supplied image, RapidOCR returned 21 regions with CUDA active in all three stages, PaddleOCR returned 21 on gpu:0, and EasyOCR returned 28 on cuda. All three isolated pip command checks and dependency checks passed after recovery.

A final real installation selected all three GPU engines while its parent process deliberately supplied a stale private index and no-index settings through a temporary pip.ini and environment variables. It finished with exit code zero, public mode enabled and all three GPU setups successful. No stale index appeared in the installation output. The log and compact result are saved in the ignored `.test-installer-ui/public-gpu-install.log` and `public-gpu-install-result.json` files. No real user pip configuration was changed by this test.
