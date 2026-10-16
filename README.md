# Automotive OCR Bench

A local Windows OCR benchmarking app with a browser workbench and a headless Python runner. It uses real inference, keeps each engine in a separate persistent process, and runs candidates sequentially. The supplied Pivi Pro image is included as a development fixture.

## Start this checkout

The app environment is `.venv`. Run from this project directory:

```powershell
.\start.ps1
```

Open **http://127.0.0.1:8765**. Alternatively:

```powershell
.\.venv\Scripts\python.exe -m ocrbench serve
```

The server binds to loopback. Images, annotations, and run records stay on this computer. Initial engine provisioning may download model files from the engine's model host; inference uses the installed local models.

## Fresh installation

Use standard 64-bit Python 3.12 as the initial Windows baseline. Other Python versions depend on each engine's available wheels. Python 3.14 is not assumed compatible with the optional engines.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[rapidocr,test]"
.\start.ps1
```

For a requirements-file installation, run `python -m pip install -r requirements.txt` from this checkout. This installs the app and the default RapidOCR CPU engine from `pyproject.toml`; `requirement.txt` is an alias. Provision the other engines and GPU runtimes separately with `scripts/setup-engine.ps1` as described below.

Keep this checkout: fixture data and the local worker source live here. This is a checkout-based application, not a standalone installer.

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

Adapters are included for RapidOCR (ONNX Runtime), PaddleOCR 3 (PaddlePaddle), EasyOCR (PyTorch), and Tesseract (pytesseract plus the native executable). Optional engine environments belong in `.engines/<engine>/`. The app detects these automatically; custom interpreter paths can be set in **Environments**. Every engine gets its own worker; none of the OCR frameworks is imported in the dashboard process.

```powershell
.\scripts\setup-engine.ps1 -Engine paddleocr -Python C:\Python312\python.exe
.\scripts\setup-engine.ps1 -Engine easyocr -Python C:\Python312\python.exe
.\scripts\setup-engine.ps1 -Engine tesseract -Python C:\Python312\python.exe
```

The setup helper uses a standard Python distribution with `ensurepip`. Tesseract additionally needs the native executable and appropriate `tessdata`; use `options.tesseract_cmd` if it is not on PATH. Tesseract uses codes such as `eng`, whereas the other engines commonly use `en`. Options are adapter-specific; headless configurations support different options and languages per candidate. The workbench's shared options apply to all selected engines.

CPU environments are the installation baseline. GPU configurations require the appropriate GPU packages, CUDA/cuDNN/driver compatibility, and an actual CUDA device. RapidOCR requires CUDA providers for every active ONNX stage; EasyOCR and PaddleOCR check the selected device. A requested GPU configuration cannot silently enter the CPU comparison. ONNX Runtime may still assign unsupported operations to CPU; provider identity is recorded as a mixed-capability CUDA route, not proof that every kernel executed on GPU. VRAM and GPU utilization currently remain `null`.

### RapidOCR GPU setup

The CPU-only `onnxruntime` package cannot run CUDA, even on a computer with an NVIDIA GPU. Use the separate device environment:

```powershell
.\scripts\setup-engine.ps1 -Engine rapidocr -Device gpu -Python C:\Python312\python.exe
.\.venv\Scripts\python.exe -m ocrbench run configs/rapidocr-gpu.json
```

This installs `onnxruntime-gpu[cuda,cudnn]==1.31.0` in `.engines/rapidocr-gpu`, including its pip-provided NVIDIA runtime libraries. It does not replace the CPU environment or install a machine-wide toolkit. The worker preloads the runtime DLLs before creating ONNX sessions, as described in the [ONNX Runtime CUDA documentation](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#preload-dlls). An appropriate NVIDIA driver is required.

The dashboard and headless runner automatically select the dedicated GPU environment when the device is GPU. **Environments** also has separate CPU/shared and GPU interpreter overrides. Refresh the dashboard after adding an environment. Each active stage must report `CUDAExecutionProvider` after a real-image preflight; package presence alone is not a successful GPU check.

### PaddleOCR and EasyOCR GPU setup

These engines need their own GPU framework builds. The CPU PaddlePaddle package and Windows PyPI's CPU PyTorch build cannot execute CUDA. Install the CUDA frameworks from their official package indexes through the helper:

```powershell
.\scripts\setup-engine.ps1 -Engine paddleocr -Device gpu -Python C:\Python312\python.exe
.\scripts\setup-engine.ps1 -Engine easyocr -Device gpu -Python C:\Python312\python.exe
.\.venv\Scripts\python.exe -m ocrbench run configs/all-gpu.json
```

The helper provisions `.engines/paddleocr-gpu` with PaddlePaddle GPU 3.3.1 from the [official CUDA 13 index](https://www.paddlepaddle.org.cn/packages/stable/cu130/), and `.engines/easyocr-gpu` with PyTorch 2.14.1 / torchvision 0.29.1 CUDA 13 builds from the [official PyTorch index](https://download.pytorch.org/whl/cu130). It then installs the matching OCR package. Install framework builds before the OCR extras so generic dependencies do not select a CPU build. CUDA-enabled frameworks and CPU frameworks belong in separate environments.

GPU runs automatically discover all three dedicated interpreters. Loading a historical failed GPU setup that used the app's known default CPU interpreter now uses automatic GPU selection. Explicit custom interpreter overrides still take precedence. Framework version, CUDA/cuDNN versions, observed device, and GPU name are recorded in successful run identity. Tesseract is a CPU-only baseline: the dashboard disables it for GPU runs and the API rejects that unsupported combination before starting a worker.

On Windows, the Paddle worker registers and preloads DLLs from its own NVIDIA pip package folders, including the newer `nvidia/cu13/bin/x86_64` layout and `nvidia/cudnn/bin`. This fixes native cuBLAS loading errors without changing the system PATH. DLL directory handles remain alive for the worker's lifetime, and the registered paths are recorded in run identity. Paddle GPU synchronization uses `paddle.device.synchronize`.

RapidOCR's default model coverage is conservatively limited by the adapter to `en`/`ch_sim` unless a recognition model path is supplied. Merely entering another language does not establish that its glyphs are supported. PaddleOCR defaults to `enable_mkldnn=false`: the provisioned Windows PaddlePaddle 3.3.1 backend failed preflight on the default oneDNN route. You can explicitly override and benchmark that setting. Custom model and weight licence review remains a deployment task. Provisioned dependency snapshots are in `locks/`.

Official adapter references: [RapidOCR usage](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/), [PaddleOCR Python API](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html), [EasyOCR API](https://jaided.ai/easyocr/documentation/), [pytesseract](https://github.com/madmaze/pytesseract).

## Headless runs and Python API

```powershell
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
