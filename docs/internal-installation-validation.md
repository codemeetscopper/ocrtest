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
