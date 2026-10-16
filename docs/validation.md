# Supplied-image validation

Run: `6c37f5f77d16` · 2026-10-16T12:48:09.101046+00:00 · completed

Input: supplied 800×450 Pivi Pro capture. Native Windows CPU workers, four CPU threads, one warmup, five measured repetitions per engine. Candidates executed sequentially.

| Engine | Version | p95 image-to-result (ms) | Completed FPS | Peak worker RSS (MB) | Failures |
| --- | --- | ---: | ---: | ---: | ---: |
| rapidocr | 3.10.0 | 511.5 | 2.09 | 297 | 0 |
| paddleocr | 3.7.0 | 8285.5 | 0.12 | 723 | 0 |
| easyocr | 1.7.2 | 1630.6 | 0.63 | 843 | 0 |

PaddleOCR used the CPU compatibility setting `enable_mkldnn=false`. The original oneDNN preflight failure is retained in run history. Model families differ; this is a pipeline comparison rather than a controlled backend comparison.

Full-image quality is unavailable because the supplied draft annotations have not been human reviewed. Raw OCR predictions and application assertions remain available. The expected economy value mismatch is retained.

Verification: 28 automated tests passed, including actual inference in all three provisioned engine environments, Unicode scoring, source-coordinate mapping, error accounting, timeout cleanup, GPU fallback rejection on the CPU runtime, mocked camera failure, bounded replay drops, and host locking. Browser checks covered a saved-image run, overlays, annotation editor, labels, region values, history, and installed-engine detection.

Timed replay run `b99acd0f68b3` received 20 scheduled frames, completed 6, and reported 14 queue drops with no unprocessed received frames. That overload pilot was run during other verification work and is not an isolated performance comparison.

Actual RapidOCR CUDA execution was subsequently validated on this computer; see gpu-validation.md. Live camera hardware, Tesseract's native executable, required multilingual coverage, and the external production test computer remain unverified. Five repetitions and one scene do not establish reliable tail latency or a production ranking.

See sample-benchmark.html for portable detailed evidence, or reopen the run in the app for overlays and exports.
