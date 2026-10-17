# Automotive OCR Bench

A local Windows OCR benchmarking app with a browser workbench and a headless Python runner. It uses real inference, keeps each engine in a separate persistent process, and runs candidates sequentially. The supplied Pivi Pro image is included as a development fixture.

## Install from your internal pip feed (Python only)

Use **Windows x64 / Python 3.12**. See the complete [Artifactory installation guide](docs/internal-installation.md), including the package/build inventory, authentication, certificates, and offline model setup.

If IT has already configured pip for your internal repository:

~~~text
python install.py --tessdata-path "C:/OrgModels/tessdata"
python start.py
~~~

Or supply your PyPI simple-index URL explicitly:

~~~text
python install.py --index-url "https://artifactory.example.com/artifactory/api/pypi/python-virtual/simple" --tessdata-path "C:/OrgModels/tessdata"
~~~

Replace the URL with your own repository. Explicit-index mode uses only that feed and ignores inherited configuration files/extra indexes/find-links for installer subprocesses. Supply --cert with a corporate CA bundle if needed; otherwise use your approved pip/keyring/netrc authentication. No credentials are stored in the checkout. Without --index-url, normal corporate pip configuration is honoured. A credential-free configuration example is in config/pip.ini.example.

The complete installer installs all four CPU Python engines/frameworks and defaults to the **tesserocr wheel**, which contains the native Tesseract library. It does not require micromamba, Conda, PowerShell activation, or tesseract.exe. Your internal feed must include the approved Python 3.12 / Windows x64 tesserocr 2.10.0 wheel with bundled Tesseract 5.5.2. The eng.traineddata model is a separate approved asset supplied using --tessdata-path; setup does not download models from public hosts.

requirements.txt installs the CPU Python components, including the legacy pytesseract wrapper. requirements-tesserocr.txt additionally installs the bundled library wheel. Both contain no public package-index directives. When run from an existing venv, the installer installs into that venv and start.py uses it too. Otherwise setup creates/reuses the project's .venv. Setup validates/persists the selected backend and model directory. Restart a running app after setup.

~~~text
python install.py --python C:/Python312/python.exe --tessdata-path "C:/OrgModels/tessdata"
python install.py --device cpu --tessdata-path "C:/OrgModels/tessdata"
python install.py --device gpu --tessdata-path "C:/OrgModels/tessdata"
python start.py --port 8766
~~~

The default --device auto adds isolated CUDA environments when NVIDIA hardware is detected. CPU and CUDA framework builds must both be mirrored to the internal feed. Setup no longer switches to public PyTorch/Paddle indexes. Use --without-tesseract if needed, or --tesseract-backend pytesseract --tesseract-path with an existing approved executable. Tesseract remains CPU-only.

All other engines also need approved model weights. Stage caches or configure explicit model paths before offline use; a pip index configures Python packages, not framework-specific model download URLs. Details and EasyOCR's download_enabled setting are in the installation guide.

The bootstrap Python needs pip or ensurepip. Setup creates environments without activation scripts and fails with a nonzero exit code if a required artifact is missing. Open **http://127.0.0.1:8765** after launching. Keep this checkout because fixture data and worker sources live here.

## Workbench workflow

1. Use the supplied capture or import PNG, JPEG, or WebP images. Imports apply EXIF orientation and store lossless PNG pixels; the resulting image is the coordinate reference.
2. Open **Review annotations**. Drag rectangles to add text regions and edit the exact text. The **Full JSON** editor also supports polygons, per-region languages, ignored regions, expected labels, and named extraction fields.
3. Mark human review and completeness only after checking the ground truth. Full-image accuracy is unavailable for draft or partial annotations. The supplied annotations are deliberately **unreviewed drafts**.
4. Select engines, device, preparation, warmups, and repetitions. Advanced configuration exposes language codes, thread count, timeout, IoU threshold, optional quality/latency gates, and engine options.
5. Run the benchmark. Inspect text polygons, original strings, confidence, expected-label checks, raw region values, and parser errors. An annotation edit affects a new run; existing runs keep their original annotation snapshot.
6. Export comparison CSV, complete JSON, raw JSONL, or a standalone HTML evidence report. Reopen a run or load its configuration from **Run history**.

**Run history** shows one row per engine/run with p95 latency, throughput, F1, CER, memory, and failure counts. Sort by a column, filter by engine/device, or check runs and choose **Compare selected** to keep their rows together. Source samples, preparation, track, warmups, repetitions, language, and thread count remain visible for comparison context; open results for model identity and annotation snapshots. Missing quality scores remain unavailable. The Source image overlay displays detected text and recognition confidence beside each green region; turn off **Text & confidence** for a clearer image.

During a live run, the source card becomes **Camera stream** and follows newly processed camera frames automatically. Each decoded frame is displayed with its own detection boxes and confidence labels, respecting the overlay toggles. Preview refreshes check for results every 250 ms; visible frame rate follows OCR completion and the configured camera sampling rate. Uncheck **Follow latest camera frame**, or choose a result frame, to inspect an earlier capture; re-enable following to return to the latest result. After stopping, use **Previous / Next** or the result-frame selector to review any processed frame. Following switches off when the run finishes. Live runs reopen on their last processed frame.

The supplied fixture includes positive PHONE/MEDIA queries, an absent NAVIGATION query, and driving score, phone name, and economy value fields. These are draft application assertions, not production acceptance criteria.

## Engines and isolation

The installer supplies all four engines through the configured pip feed, with Tesseract using the approved tesserocr wheel by default. The legacy executable backend remains available. All CPU Python components are available in the app environment. Existing isolated environments under .engines/<engine>/ are discovered and reused. Custom interpreters remain configurable in **Environments**. Each candidate runs in its own worker process. GPU builds always live in separate .engines/<engine>-gpu/ environments.

To provision or repair one isolated engine:

~~~text
python scripts/setup_engine.py --engine paddleocr --python C:/Python312/python.exe
python scripts/setup_engine.py --engine easyocr --python C:/Python312/python.exe
python scripts/setup_engine.py --engine tesseract --python C:/Python312/python.exe
python scripts/setup_engine.py --engine rapidocr --device gpu --python C:/Python312/python.exe
python scripts/setup_engine.py --engine paddleocr --device gpu --python C:/Python312/python.exe
python scripts/setup_engine.py --engine easyocr --device gpu --python C:/Python312/python.exe
~~~

CUDA setup resolves the approved ONNX Runtime 1.31.0 CUDA/cuDNN extras, PaddlePaddle GPU 3.3.1 CUDA 13 wheel, and PyTorch 2.14.1+cu130 / torchvision 0.29.1+cu130 builds from your configured internal pip feed. GPU interpreters are discovered automatically. A compatible NVIDIA driver and real CUDA device are required. Real-image preflight rejects silent CPU fallback. ONNX may assign unsupported operations to CPU, which its observed-device identity explicitly describes. GPU utilization and VRAM telemetry remain unavailable.

The Paddle worker registers and preloads DLLs from its own pip NVIDIA folders, including nvidia/cu13/bin/x86_64 and nvidia/cudnn/bin, without editing system PATH. GPU synchronization uses paddle.device.synchronize. CPU Paddle defaults to enable_mkldnn=false because the tested Windows oneDNN route failed; overrides remain configurable.

Tesseract supports tesserocr (persistent in-process library) and pytesseract (native subprocess per request); runtime identity records that distinction. Compare matching bindings when judging timing. Tesseract uses language codes such as eng; the adapter accepts en for English. RapidOCR's default model is conservatively limited to en/ch_sim unless a recognition model is supplied. Language coverage and combinations remain engine-specific. Workbench options apply to every selected engine; headless configurations allow per-engine options. Custom model licensing/provenance remains a deployment check.

Use **? Terms & metrics** on any page, expand **What do these terms mean?**, or hover/focus a marked table heading. HTML exports include the same definitions. F1 balances precision/recall for exactly matching text and overlapping regions; higher is better. CER is character edits/reference characters; lower is better and it can exceed 100%. P95 is the 95th percentile of successful warm-call durations in milliseconds; lower is faster. Completed FPS is successful frames per measurement-loop wall second; higher is better. Peak RAM is sampled worker-tree resident memory in MB. Confidence is an engine score, not verified accuracy or a calibrated probability shared by engines. A dash means unavailable, never zero or a pass. The full glossary also covers units, arrows, missing values, IoU, cold start, warmups, queues, and application checks.

Official references: [ONNX CUDA](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html), [PaddleOCR installation](https://www.paddleocr.ai/main/en/version3.x/installation.html), [PyTorch packages](https://download.pytorch.org/whl/cu130), [pytesseract](https://github.com/madmaze/pytesseract).

## Headless runs and Python API

```text
.\.venv\Scripts\python.exe -m ocrbench run configs/sample.json
.\.venv\Scripts\python.exe -m ocrbench run configs/compare.json
.\.venv\Scripts\python.exe -m ocrbench run configs/replay.json
.\.venv\Scripts\python.exe -m ocrbench run configs/live.json
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp
node --test tests/live-preview.test.cjs
```

`configs/compare.json` references the isolated PaddleOCR and EasyOCR environments. Provision models before timing production experiments. Cold first results are recorded separately and may include a first-use download. Warmups and first-result calls are excluded from the steady-state summary. Initialization failures are retained as unavailable candidates, and worker errors, invalid outputs, crashes, and timeouts are retained in evidence.

The Python entry points are `ocrbench.schema.RunConfig`, `ocrbench.runner.RunManager`, `ocrbench.metrics.quality`, and `ocrbench.metrics.application`. The HTTP API is documented at **/docs**; mutation requests need the `X-OCRBench: local` header. This header protects local browser writes from ordinary cross-origin forms. The server has no remote authentication and should remain bound to loopback.

## Saved images, replay, and camera capture

Saved-image runs use the same frames across candidates. Replay uses a constant arrival rate by default; headless configs can supply an ordered `replay_offsets_ms` array corresponding to `samples`, repeated with the configured cycle gap. Use captured sample IDs from the dataset API to replay a recorded camera session and supply its observed receive offsets.

Live capture uses OpenCV's Windows DirectShow backend and one OCR candidate. It records the actual backend, negotiated dimensions and reported camera FPS. Frames are sampled at the requested app cadence. By default, lossless PNGs stay in temporary session storage outside the dataset, allowing frame review until the app exits or restarts. Enable **Save camera frames to dataset** before starting a run (headless: `save_camera_frames: true`) to keep them in `data/captures` and the dataset. Run metrics and recognized text remain in run history either way; an expired temporary image is clearly marked unavailable. This sampled cadence is distinct from sensor FPS. Acquisition uses host receive timestamps, not exposure timestamps. The app records queue delay, host-receipt-to-result age, queue drops, and capture faults. Live frames without reviewed labels have timing evidence only.

Both queue policies are bounded. `latest` drops the oldest waiting frame; `all` is FIFO and drops new arrivals on overflow. Neither is a production policy decision. Replay retains scheduled timestamps as well as receive timestamps. Camera vendor SDKs, exposure/focus control, hard acquisition deadlines, and blocked-driver recovery need the target camera's integration. The app has no automatic recapture/deblur policy. Only explicitly saved camera captures appear in the dataset. Legacy automatically saved captures are excluded from the dataset view but retained on disk for their existing run reports. Temporary session frames are cleaned up on normal app shutdown. Sustained experiments require adequate temporary disk space.

## Measurement contract

- **Initialization:** subprocess startup plus adapter construction. **First result:** from startup to the first completed prediction, including lazy loading/provisioning where applicable.
- **Warm OCR:** decode/preparation and OCR stages are separate. **Image-to-result:** includes image hashing, decoding, explicit preparation, IPC, returned source-coordinate predictions, application logic, and quality evaluation. It excludes final JSON persistence. Quality scoring may add CPU cost when annotations are enabled; use identical annotation policies for comparisons.
- **FPS:** completed original frames divided by measured loop wall time, including result persistence and arrival scheduling. It is not the inverse of median OCR latency. Known-crop runs count one original image as one frame and expose per-crop timing separately.
- **Resources:** sampled peak worker-process-tree RSS at a nominal 50 ms cadence, and lifetime sampled CPU core-seconds including initialization. Shared RSS may be counted more than once; short peaks can be missed. The dashboard's own memory is excluded. Unsupported GPU telemetry is unavailable.
- **Quality:** maximum-cardinality one-to-one polygon matching above a configured IoU threshold, then overlap tie-breaking. Strict case, punctuation, spaces, and Unicode. Unmatched predictions count as character insertions; missed reference text counts as deletions. CER can exceed 100%. Empty references use negative-input metrics instead of a fabricated CER.
- **Scoring detail:** detection and joint exact-text F1, aggregate CER, grapheme-aware error diagnostics, matched IoU, full-screen correctness, and per-language counts. WER remains unavailable because a language-specific tokenizer has not been configured. Ignored polygons suppress substantially overlapping predictions. Split/merged predictions remain observable under the declared granularity; no engine-specific merging is applied.
- **Application operations:** labels use exact text (optionally Unicode casefold) and optional source-region membership by polygon centroid. Field extraction reuses the full-image result and preserves raw strings. Numeric parsing is strict and uses the configured decimal separator. A worker failure cannot pass an absent-label assertion.
- **Known-crop track:** runs each engine's OCR pipeline on axis-aligned ground-truth crops. It reports crop transcription separately. This is not a pure recognizer-only benchmark: the detector remains active. Do not compare its F1 with full-image F1.
- **Reproducibility:** config/source/image hashes, host profile, installed library identity, effective adapter settings, raw records, annotation snapshots, logs, and discovered model hashes. Model provenance covers RapidOCR ONNX files, selected cached EasyOCR weights, PaddleOCR pipeline configuration/cached inference files, and explicitly supplied weight paths. Confirm custom model provenance when using alternative layouts. A data-directory lock prevents dashboard and headless runs from competing with each other; different data directories or external workloads still require host-level coordination.

No weighted score or automatic winner is generated. Quality/latency gates are optional and remain unconfigured by default. Tail latency from five repetitions is only a pilot estimate. One image cannot establish multilingual quality, robustness, a production engine ranking, or performance on the external test computer.

## Files and scope

`ocrbench/` contains the server, workers, sources, evaluator, and static UI. `data/fixtures/` contains the supplied image and draft annotation. `data/annotations/` contains reviewed edits. `data/runs/<id>/` holds the configuration, reports, raw JSONL, and worker logs. `docs/benchmark-plan.md` preserves the supplied reference plan. Set `OCRBENCH_DATA` to an alternative dataset/run directory if needed (copy fixtures there).

Implemented scope is the first local benchmark workbench, saved/replay/live foundations, four initial adapters, the four HMI operations, explicit preparation profiles, strict scoring, evidence, and reporting. The plan's later research tracks (docTR/OpenOCR/MMOCR/TrOCR), model optimization/calibration, confidence intervals, production acceptance limits, vendor camera SDKs, and final multilingual test collection are not claimed complete. Exact scripts, symbols, hardware limits, and unreadable-input production behavior remain configurable or unresolved as in the reference plan.
