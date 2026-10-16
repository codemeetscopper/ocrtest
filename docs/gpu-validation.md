# RapidOCR CUDA validation

The original run `8867f4dcfe4c` used the app's CPU-only `onnxruntime==1.31.0` build. Its available providers were Azure and CPU, so it correctly failed the requested GPU preflight.

A dedicated `.engines/rapidocr-gpu` interpreter now contains `rapidocr==3.10.0`, `onnxruntime-gpu==1.31.0`, and pip-provided CUDA 13/cuDNN 9 runtime libraries. The worker preloads these DLLs before creating ONNX sessions. CPU runs continue using the separate CPU runtime. Dependency versions are recorded in `locks/rapidocr-gpu-windows-py312.txt`.

Successful hardware run: `462465165487`, on the supplied 800×450 Pivi Pro image and the NVIDIA RTX 4060 laptop GPU. Detection, classification, and recognition all reported `CUDAExecutionProvider` first, with CPU also registered for runtime-assigned operations. All five measured frames completed with zero failures. The warm median image-to-result latency was 513.4 ms; p95 was 524.8 ms. These pilot measurements do not establish that GPU execution is faster than CPU, and provider registration does not establish that every operator ran on GPU.

The ONNX model hashes match those used in the earlier CPU benchmark. Quality remains unscored until the draft annotation is reviewed. The original failure remains in run history.

Both the dashboard and headless runner discover device-specific environments automatically. Explicit interpreter overrides remain supported, and the Environments page now separates CPU/shared and GPU overrides. CPU-only builds fail before inference with a specific setup message; runtime DLL/driver failures retain the failed stage and active provider list.

Dashboard run `73fca09632b5` also completed all five frames with zero failures after selecting GPU without entering a custom interpreter path. The stored configuration resolves to `.engines/rapidocr-gpu/Scripts/python.exe`. Seven targeted regression tests passed, including real CUDA inference, CPU-only rejection, automatic environment routing, DLL preload order, and CPU OCR regression.

Provision on another compatible Windows machine with:

```powershell
.\scripts\setup-engine.ps1 -Engine rapidocr -Device gpu -Python C:\Python312\python.exe
.\.venv\Scripts\python.exe -m ocrbench run configs/rapidocr-gpu.json
```

See the [official ONNX Runtime CUDA runtime loading guidance](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#preload-dlls).

## All GPU-capable engines

Combined dashboard run `5088fc4c52bb` completed successfully with RapidOCR, PaddleOCR, and EasyOCR on GPU. Each engine processed five measured repetitions of the supplied Pivi Pro image with zero failures. Dedicated interpreters were selected automatically, and the run records include observed devices and framework CUDA identity. A portable evidence report is saved as `all-gpu-benchmark.html`.

PaddleOCR uses PaddlePaddle GPU 3.3.1 (CUDA 13); EasyOCR uses PyTorch 2.14.1+cu130 and torchvision 0.29.1+cu130. The initial CPU-only framework failures are retained in history. PaddlePaddle's Windows native loader additionally needed its own NVIDIA pip DLL folders registered in the worker PATH and DLL search directories; cuBLAS, cuBLASLt, CUDA runtime, and cuDNN are preloaded from that environment. The system PATH and driver are unchanged.

The final suite passed **39 tests**, with real CUDA inference enabled for all three engines, CPU regression checks, CPU-build rejection, the CUDA 13 pip-library layout, environment routing, scoring, worker failures, and replay behavior. Exact GPU environment dependency snapshots are in `locks/paddleocr-gpu-windows-py312.txt` and `locks/easyocr-gpu-windows-py312.txt`.

Tesseract is a CPU-only baseline. It is disabled in GPU mode, and unsupported GPU requests are rejected by the API before a worker starts. This is a capability boundary rather than a CUDA setup failure.
