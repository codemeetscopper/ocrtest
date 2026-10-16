"""Persistent JSON-line worker. No annotations or expected answers enter this process."""
import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback

_dll_directories = []
_cuda_libraries = []


def load_paddle_cuda_libraries(nvidia_root=None):
    """Make this interpreter's pip CUDA DLLs visible to Paddle's native loader."""
    if os.name != "nt":
        return []
    import ctypes
    root = Path(nvidia_root) if nvidia_root is not None else Path(sys.prefix)/"Lib"/"site-packages"/"nvidia"
    files = sorted(root.rglob("*.dll")) if root.exists() else []
    directories = sorted({str(p.parent.resolve()) for p in files})
    if not directories:
        return []
    # New NVIDIA CUDA 13 wheels use nvidia/cu13/bin/x86_64. Paddle 3.3's
    # native LoadLibrary calls do not automatically search that pip location.
    os.environ["PATH"] = os.pathsep.join(directories + [os.environ.get("PATH", "")])
    for directory in directories:
        _dll_directories.append(os.add_dll_directory(directory))
    for prefix in ("cudart64", "cublasLt64", "cublas64", "cudnn64"):
        for path in files:
            if path.name.startswith(prefix):
                try:
                    _cuda_libraries.append(ctypes.WinDLL(str(path.resolve())))
                except OSError as exc:
                    raise ValueError(f"Cannot load Paddle CUDA library {path.name} from this environment: {exc}") from exc
    return directories


def emit(value):
    sys.__stdout__.write("OCRBENCH:" + json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    sys.__stdout__.flush()


def region(box, text, confidence):
    return {"polygon": [[float(x), float(y)] for x, y in box], "text": str(text),
            "confidence": float(confidence) if confidence is not None else None,
            "detection_confidence": None, "granularity": "line"}


class Adapter:
    def __init__(self, config):
        self.config = config
        self.engine = config["engine"]
        self.device = config.get("device", "cpu")
        self.languages = config.get("languages", ["en"])
        opts = config.get("options", {})
        cache = Path(os.environ.get("OCRBENCH_DATA", Path(__file__).resolve().parent.parent / "data")) / "models" / self.engine
        cache.mkdir(parents=True, exist_ok=True)
        self.sync = lambda: None
        self.models = []
        self.effective_options = dict(opts)
        self.model_configuration = None
        self.providers = None
        self.runtime_identity = None
        if self.engine == "rapidocr":
            if self.device == "gpu":
                import onnxruntime as ort
                if "CUDAExecutionProvider" not in ort.get_available_providers():
                    raise ValueError(
                        f"RapidOCR GPU requires onnxruntime-gpu; this interpreter has no CUDA provider: {sys.executable}. "
                        "Install the dedicated rapidocr-gpu environment or select a CUDA-enabled GPU interpreter in Environments.")
                # Load pip-provided NVIDIA DLLs before creating ONNX sessions.
                if hasattr(ort, "preload_dlls"):
                    ort.preload_dlls()
            from rapidocr import RapidOCR, EngineType
            # The installed default recognizer is Chinese + English. Other models
            # must be explicitly selected rather than silently claiming coverage.
            if set(self.languages) - {"en", "ch_sim"} and not opts.get("Rec.model_path"):
                raise ValueError("RapidOCR default supports en/ch_sim; provide Rec.model_path for other languages")
            params = {"EngineConfig.onnxruntime.intra_op_num_threads": config["threads"], **opts}
            params["EngineConfig.onnxruntime.use_cuda"] = self.device == "gpu"
            for provider in ("dml", "cann", "coreml"):
                params[f"EngineConfig.onnxruntime.use_{provider}"] = False
            for stage in ("Det", "Cls", "Rec"):
                params[f"{stage}.engine_type"] = EngineType.ONNXRUNTIME
            self.model = RapidOCR(params=params)
            import onnxruntime as ort
            self.runtime_identity = {"framework":"onnxruntime", "version":ort.__version__}
        elif self.engine == "easyocr":
            import easyocr
            import torch
            if self.device == "gpu" and not torch.cuda.is_available():
                raise ValueError(f"EasyOCR GPU requires CUDA-enabled PyTorch; {sys.executable} has torch {torch.__version__} "
                                 f"(built CUDA: {torch.version.cuda}). Select the easyocr-gpu interpreter in Environments.")
            torch.set_num_threads(config["threads"])
            self.model = easyocr.Reader(self.languages, gpu=self.device == "gpu", **{"model_storage_directory":str(cache), **opts})
            detection = self.model.detection_models[opts.get("detect_network", "craft")]
            self.models.append(str(Path(self.model.model_storage_directory) / detection["filename"]))
            for generation in self.model.recognition_models.values():
                for model in generation.values():
                    if model.get("model_script") == self.model.model_lang:
                        filename = Path(self.model.model_storage_directory) / model["filename"]
                        if filename.exists():
                            self.models.append(str(filename))
            self.model_configuration = {"detector":opts.get("detect_network", "craft"), "recognizer":opts.get("recog_network", "standard"), "model_language":self.model.model_lang}
            self.observed = str(self.model.device)
            if self.device == "gpu" and "cuda" not in self.observed:
                raise ValueError("Requested GPU but EasyOCR selected " + self.observed)
            if self.device == "gpu":
                self.sync = torch.cuda.synchronize
            self.runtime_identity = {"framework":"torch", "version":torch.__version__, "cuda_version":torch.version.cuda,
                                     "cudnn_version":torch.backends.cudnn.version(),
                                     "gpu_name":torch.cuda.get_device_name(0) if self.device == "gpu" else None}
        elif self.engine == "paddleocr":
            dll_directories = load_paddle_cuda_libraries() if self.device == "gpu" else []
            from paddleocr import PaddleOCR
            import paddle
            if len(self.languages) != 1:
                raise ValueError("One PaddleOCR language/model per configuration; create multiple configurations")
            if self.device == "gpu" and (not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() == 0):
                raise ValueError(f"PaddleOCR GPU requires paddlepaddle-gpu; {sys.executable} has paddle {paddle.__version__} "
                                 f"(CUDA compiled: {paddle.is_compiled_with_cuda()}). Select the paddleocr-gpu interpreter in Environments.")
            paddle.set_device("gpu:0" if self.device == "gpu" else "cpu")
            self.observed = paddle.get_device()
            self.model = PaddleOCR(lang=self.languages[0], device=self.observed, cpu_threads=config["threads"],
                                   **{"use_doc_orientation_classify": False, "use_doc_unwarping": False,
                                      "use_textline_orientation": False, "enable_mkldnn": False, **opts})
            self.effective_options = {"use_doc_orientation_classify":False, "use_doc_unwarping":False,
                                      "use_textline_orientation":False, "enable_mkldnn":False, **opts}
            self.model_configuration = self.model._merged_paddlex_config
            cache_home = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", Path.home()/".paddlex"))
            for submodule in self.model_configuration.get("SubModules", {}).values():
                directory = submodule.get("model_dir") or cache_home / "official_models" / str(submodule.get("model_name", ""))
                if Path(directory).is_dir():
                    self.models.extend(str(p) for p in Path(directory).glob("inference.*") if p.is_file())
            if self.device == "gpu":
                self.sync = paddle.device.synchronize
            self.runtime_identity = {"framework":"paddle", "version":paddle.__version__,
                                     "cuda_compiled":paddle.is_compiled_with_cuda(), "cuda_version":paddle.version.cuda(),
                                     "cudnn_version":paddle.version.cudnn(),
                                     "cuda_dll_directories":dll_directories,
                                     "gpu_name":paddle.device.cuda.get_device_name(0) if self.device == "gpu" else None}
        else:
            import pytesseract
            if self.device != "cpu":
                raise ValueError("Tesseract baseline supports CPU only")
            if opts.get("tesseract_cmd"):
                pytesseract.pytesseract.tesseract_cmd = opts["tesseract_cmd"]
            pytesseract.get_tesseract_version()
            self.model = pytesseract
            self.observed = "cpu"
        self.version = importlib.metadata.version({"rapidocr": "rapidocr", "easyocr": "easyocr", "paddleocr": "paddleocr", "tesseract": "pytesseract"}[self.engine])

    def predict(self, image):
        if self.engine == "rapidocr":
            result = self.model(image)
            self.providers = []
            self.models = []
            for stage, component in zip(("detection", "classification", "recognition"), (self.model.text_det, self.model.text_cls, self.model.text_rec)):
                if component is None:
                    continue
                wrapper = component.session
                session = getattr(wrapper, "session", wrapper)
                providers = session.get_providers()
                self.providers.append(providers)
                if self.device == "gpu" and "CUDAExecutionProvider" not in providers:
                    raise ValueError(f"RapidOCR {stage} stage could not load CUDA (active providers: {providers}). "
                                     "Check the worker log for missing CUDA/cuDNN DLLs or driver compatibility. CPU fallback was rejected.")
                model_path = getattr(wrapper, "model_path", None) or getattr(session, "_model_path", None)
                if model_path and Path(model_path).exists():
                    self.models.append(str(model_path))
            self.observed = "cuda:0 (ONNX; CPU ops may be assigned by runtime)" if self.device == "gpu" else "cpu"
            if result.boxes is None:
                return []
            return [region(b,t,s) for b,t,s in zip(result.boxes, result.txts, result.scores)]
        if self.engine == "easyocr":
            return [region(b,t,s) for b,t,s in self.model.readtext(image)]
        if self.engine == "paddleocr":
            result = list(self.model.predict(image))[0]
            return [region(b,t,s) for b,t,s in zip(result["rec_polys"], result["rec_texts"], result["rec_scores"])]
        from PIL import Image
        # pytesseract accepts RGB; OpenCV arrays from our pipeline are BGR.
        import cv2
        data = self.model.image_to_data(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)),
                   lang="+".join(self.languages), config=self.config.get("options", {}).get("config", "--psm 11"),
                   output_type=self.model.Output.DICT)
        # Combine word boxes into line boxes to match the benchmark granularity.
        groups = {}
        for i, text in enumerate(data["text"]):
            if not text.strip() or float(data["conf"][i]) < 0:
                continue
            key = tuple(data[k][i] for k in ("page_num", "block_num", "par_num", "line_num"))
            groups.setdefault(key, []).append(i)
        out = []
        for items in groups.values():
            x = min(data["left"][i] for i in items); y = min(data["top"][i] for i in items)
            r = max(data["left"][i]+data["width"][i] for i in items); b = max(data["top"][i]+data["height"][i] for i in items)
            prediction = region([[x,y],[r,y],[r,b],[x,b]], " ".join(data["text"][i] for i in items), None)
            prediction["word_confidences"] = [float(data["conf"][i])/100 for i in items]
            out.append(prediction)
        return out

    def metadata(self):
        files = []
        # Hash explicitly supplied weights and discovered cached model paths.
        for value in sorted(set(self.models + [str(v) for k,v in self.config.get("options", {}).items() if "model" in k and "path" in k])):
            p = Path(value)
            if p.is_file():
                files.append({"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size})
        return {"library": self.engine, "library_version": self.version, "requested_device": self.device,
                "observed_device": getattr(self, "observed", None), "providers": self.providers,
                "languages": self.languages, "models": files, "options": self.config.get("options", {}),
                "effective_options": self.effective_options,
                "runtime": self.runtime_identity,
                "model_configuration": json.loads(json.dumps(self.model_configuration, default=str)),
                "precision": "engine default; not a controlled precision comparison",
                "synchronization": "explicit CUDA synchronization" if self.device == "gpu" and self.engine in ("easyocr", "paddleocr") else "completed host outputs",
                "runtime_python": sys.version, "interpreter": sys.executable}


def prepare(path, profile, crop=None):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Cannot decode image")
    x = y = 0
    if crop:
        x,y,r,b = [int(v) for v in crop]
        image = image[y:b,x:r]
        if image.size == 0:
            raise ValueError("Empty crop")
    scale = 1
    if profile == "upscale":
        scale = 2
        image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    elif profile == "contrast":
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lab[:,:,0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(lab[:,:,0])
        image = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    elif profile == "sharpen":
        image = cv2.addWeighted(image, 1.7, cv2.GaussianBlur(image, (0,0), 1.2), -0.7, 0)
    return image, x,y,scale


def main():
    adapter = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if request["op"] == "init":
                    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
                        os.environ[key] = str(request["config"].get("threads", 4))
                    start = time.perf_counter()
                    adapter = Adapter(request["config"])
                    value = {"ok": True, "initialization_ms": (time.perf_counter()-start)*1000}
                elif request["op"] == "close":
                    emit({"ok": True})
                    break
                else:
                    start = time.perf_counter()
                    image, x,y,scale = prepare(request["path"], request.get("preprocessing", "raw"), request.get("crop"))
                    prepared = time.perf_counter()
                    adapter.sync()
                    infer_start = time.perf_counter()
                    predictions = adapter.predict(image)
                    adapter.sync()
                    infer_end = time.perf_counter()
                    for p in predictions:
                        p["polygon"] = [[px/scale+x, py/scale+y] for px,py in p["polygon"]]
                    value = {"ok": True, "predictions": predictions,
                             "timing": {"prepare_ms": (prepared-start)*1000, "ocr_ms": (infer_end-infer_start)*1000,
                                        "worker_pipeline_ms": (time.perf_counter()-start)*1000}}
                    if request.get("metadata"):
                        value["identity"] = adapter.metadata()
            emit(value)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit({"ok": False, "error": str(exc), "error_type": type(exc).__name__})


if __name__ == "__main__":
    main()
