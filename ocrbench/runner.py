import hashlib
import json
import platform
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
import numpy as np
import psutil
from .metrics import quality, application, edit_distance
from .process import Worker, WorkerError
from .schema import RunConfig
from .storage import DATA, ROOT, sample_path, get_annotation, digest, save_json, read_json
from .sources import Stream
from . import hostlock


def summary(records, elapsed, config):
    successful = [r for r in records if r["status"] == "success"]
    latencies = [r["timing"]["image_to_result_ms"] for r in successful]
    scored = [r["quality"] for r in records if r.get("quality") is not None]
    scores = {}
    for name in ("detection", "e2e"):
        if scored:
            tp = sum(q[name]["tp"] for q in scored)
            expected = sum(q[name]["expected"] for q in scored)
            predicted = sum(q[name]["predicted"] for q in scored)
            from .metrics import rates
            scores[name] = rates(tp, predicted, expected)
    chars = sum(q["reference_characters"] for q in scored)
    result = {"attempts": len(records), "completed": len(successful), "failures": len(records)-len(successful),
              "not_attempted": sum(r["status"] == "not_attempted" for r in records),
              "quality_scored_attempts": len(scored), "unique_samples": len({r["sample_id"] for r in records}),
              "latency_ms": {k: float(np.percentile(latencies, n)) if latencies else None for k,n in [("median",50),("p90",90),("p95",95),("p99",99)]},
              "elapsed_s": elapsed, "completed_fps": len(successful)/elapsed if elapsed > 0 else None,
              "cer": sum(q["character_edits"] for q in scored)/chars if chars else None, **scores,
              "fps_boundary": "measurement loop wall time; includes scheduling, decoding, IPC, application logic, and persistence; excludes cold start/warmups",
              "quality_note": "Repeated frames are not independent quality samples; only reviewed complete annotations contribute"}
    gates = {}
    if config.max_p95_ms is not None:
        p95 = result["latency_ms"]["p95"]
        gates["p95"] = "unmeasured" if p95 is None else "pass" if p95 <= config.max_p95_ms and result["failures"] == 0 else "fail"
    if config.min_e2e_f1 is not None:
        score = scores.get("e2e", {}).get("f1")
        gates["e2e_f1"] = "unmeasured" if score is None or len(scored) != len(records) else "pass" if score >= config.min_e2e_f1 else "fail"
    result["acceptance"] = gates
    return result


class RunManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = None
        self.cancel = threading.Event()
        self.current_worker = None
        self.host_lock = None

    def start(self, config: RunConfig):
        for s in config.samples:
            sample_path(s)
        with self.lock:
            if self.active:
                raise RuntimeError("A benchmark is already running; candidates run sequentially on this host")
            self.host_lock = hostlock.acquire()
            run_id = uuid.uuid4().hex[:12]
            self.active = run_id
            self.cancel = threading.Event()
            path = DATA / "runs" / run_id
            path.mkdir(parents=True)
            value = {"id": run_id, "created_at": datetime.now(timezone.utc).isoformat(), "status": "queued", "config": config.model_dump(),
                     "config_sha256": hashlib.sha256(json.dumps(config.model_dump(), sort_keys=True).encode()).hexdigest(),
                     "host": {"system": platform.platform(), "cpu": platform.processor(), "logical_cores": psutil.cpu_count(),
                              "ram_gb": psutil.virtual_memory().total/1024**3, "python": platform.python_version(), "execution_profile": "native host"},
                     "candidates": [], "progress": "Waiting for worker"}
            try:
                value["code_revision"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
            except (OSError, subprocess.CalledProcessError):
                value["code_revision"] = None
            value["source_sha256"] = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT/"ocrbench").glob("*.py")))).hexdigest()
            save_json(path / "run.json", value)
            threading.Thread(target=self._run, args=(value, config, path), daemon=True).start()
            return value

    def stop(self):
        self.cancel.set()
        if self.current_worker:
            self.current_worker.close()

    def _record(self, worker, sample_id, path, annotation, config, frame, output_file):
        start = time.perf_counter()
        record = {"sample_id": sample_id, "image_sha256": digest(path), "frame_id": frame.get("frame_id", sample_id),
                  "repetition": frame.get("repetition", 0), "status": "success", "predictions": [],
                  "timestamp_origin": "host perf_counter", "host_receive_s": frame.get("received_at"),
                  "queue_ms": (start-frame["received_at"])*1000 if "received_at" in frame else None,
                  "annotation": annotation}
        if "frame_storage" in frame:
            record["frame_storage"] = frame["frame_storage"]
        try:
            if config.track == "known_crops":
                if not annotation.get("reviewed") or not annotation["regions"]:
                    raise WorkerError("Known-crop track requires reviewed text polygons", "unsupported")
                crops, predictions = [], []
                for reference in annotation["regions"]:
                    if reference.get("ignore"):
                        continue
                    xs, ys = zip(*reference["polygon"])
                    crop = [int(min(xs)), int(min(ys)), int(max(xs))+1, int(max(ys))+1]
                    result = worker.predict(path, config.preprocessing, crop)
                    raw = " ".join(p["text"] for p in result["predictions"])
                    crops.append({"reference": reference["text"], "recognized": raw, "crop": crop,
                                  "edits": edit_distance(reference["text"], raw), "timing": result["timing"]})
                    predictions.extend(result["predictions"])
                record["predictions"] = predictions
                chars = sum(len(c["reference"]) for c in crops)
                record["crop_recognition"] = {"crops": crops, "cer": sum(c["edits"] for c in crops)/chars if chars else None,
                                               "note": "OCR pipeline on axis-aligned ground-truth crops; detector remains enabled"}
                record["timing"] = {"ocr_ms": sum(c["timing"]["ocr_ms"] for c in crops)}
            else:
                result = worker.predict(path, config.preprocessing)
                record["predictions"] = result["predictions"]
                record["timing"] = result["timing"]
            record["quality"] = quality(annotation, record["predictions"], config.iou_threshold) if config.track == "full" else None
            op_start = time.perf_counter()
            record["application"] = application(annotation, record["predictions"])
            record["timing"]["application_logic_ms"] = (time.perf_counter()-op_start)*1000
        except Exception as exc:
            failed_application = application(annotation, [])
            # An engine failure cannot verify absent labels or produce a correct
            # negative assertion by returning no text.
            for label in failed_application["labels"]:
                label.update({"state": "engine_failure", "correct": None})
            failed_application.update({"false_pass_rate": None, "false_fail_rate": None,
                                       "correct_query_coverage": 0 if failed_application["labels"] else None,
                                       "unresolved_engine_failure": True})
            record.update({"status": getattr(exc, "status", "error"), "error": str(exc), "timing": {},
                           "quality": quality(annotation, [], config.iou_threshold) if config.track == "full" else None,
                           "application": failed_application})
        completed = time.perf_counter()
        record["timing"]["image_to_result_ms"] = (completed-start)*1000
        record["host_result_s"] = completed
        record["timing"]["host_receipt_to_result_ms"] = (completed-frame["received_at"])*1000 if "received_at" in frame else None
        record["timing"]["schedule_to_result_ms"] = (completed-frame["scheduled_at"])*1000 if "scheduled_at" in frame else None
        output_file.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+"\n")
        output_file.flush()
        return record

    def _run(self, value, config, folder):
        try:
            value["status"] = "running"
            # Snapshot once: edits during a run cannot change its denominator.
            annotations = {s: get_annotation(s) for s in config.samples}
            paths = [(s, sample_path(s)) for s in config.samples]
            for index, engine in enumerate(config.engines):
                if self.cancel.is_set():
                    break
                name = f"{index}-{engine.engine}-{engine.device}"
                candidate = {"name": name, "config": engine.model_dump(), "status": "initializing", "records": [],
                             "initialization_ms": None, "first_result_ms": None, "identity": None}
                value["candidates"].append(candidate)
                value["progress"] = f"Initializing {engine.engine} · {engine.device}"
                save_json(folder / "run.json", value)
                worker = stream = None
                try:
                    init_start = time.perf_counter()
                    worker = Worker(engine.model_dump(), folder / f"{name}.log", config.timeout_s)
                    self.current_worker = worker
                    candidate["initialization_ms"] = (time.perf_counter()-init_start)*1000
                    # Real first inference establishes lazy-loaded models/providers.
                    preflight = paths[0][1] if paths else sample_path("pivi-pro")
                    first = worker.predict(preflight, config.preprocessing, metadata=True)
                    candidate["first_result_ms"] = (time.perf_counter()-init_start)*1000
                    candidate["first_request"] = first
                    candidate["identity"] = first["identity"]
                    candidate["initialization_note"] = "Cold worker; model cache may be warm. First result may include lazy loading/provisioning; excluded from steady-state samples."
                    for _ in range(config.warmups):
                        if self.cancel.is_set():
                            break
                        worker.predict(preflight, config.preprocessing)
                    candidate["status"] = "running"
                    value["progress"] = f"Measuring {engine.engine}"
                    save_json(folder / "run.json", value)
                    measured_start = time.perf_counter()
                    cpu_start = worker.cpu_seconds
                    with open(folder / f"{name}.jsonl", "w", encoding="utf-8") as out:
                        fatal = None
                        if config.mode == "saved":
                            frames = ({"sample_id": s, "path": p, "repetition": rep, "frame_id": f"saved-{rep}-{s}"}
                                      for rep in range(config.repetitions) for s,p in paths)
                        else:
                            stream = Stream(config, paths, self.cancel)
                            frames = iter(stream)
                        for frame in frames:
                            if self.cancel.is_set():
                                break
                            s = frame["sample_id"]
                            selected_worker = worker
                            if fatal:
                                class FailedWorker:
                                    def predict(self, *args, **kwargs):
                                        raise WorkerError("Not attempted after fatal worker failure", "not_attempted")
                                selected_worker = FailedWorker()
                            record = self._record(selected_worker, s, frame["path"], annotations.get(s, {"regions": [], "labels": [], "fields": []}), config, frame, out)
                            candidate["records"].append(record)
                            value["progress"] = f"{engine.engine} · {len(candidate['records'])} frames completed"
                            save_json(folder / "run.json", value)
                            if record["status"] in ("timeout", "crash"):
                                fatal = WorkerError(record["error"], record["status"])
                                if config.mode != "saved":
                                    break
                    candidate["summary"] = summary(candidate["records"], time.perf_counter()-measured_start, config)
                    measured_cpu = max(0, worker.cpu_seconds-cpu_start)
                    candidate["summary"]["sampled_measurement_cpu_core_seconds"] = measured_cpu
                    candidate["summary"]["cpu_core_seconds_per_completed_frame"] = measured_cpu / candidate["summary"]["completed"] if candidate["summary"]["completed"] else None
                    if stream:
                        candidate["stream"] = stream.stats
                        candidate["stream"]["unprocessed_received"] = max(0, stream.stats["received"]-stream.stats["queue_drops"]-len(candidate["records"]))
                        if stream.error:
                            raise WorkerError(stream.error, "capture_error")
                    if fatal:
                        raise fatal
                    candidate["status"] = "cancelled" if self.cancel.is_set() else "completed"
                except Exception as exc:
                    candidate["status"] = "cancelled" if self.cancel.is_set() else getattr(exc, "status", "unavailable")
                    candidate["error"] = str(exc)
                    if candidate["records"] and "summary" not in candidate:
                        candidate["summary"] = summary(candidate["records"], time.perf_counter()-measured_start, config)
                finally:
                    if worker:
                        candidate["resources"] = worker.resources()
                        worker.close()
                    self.current_worker = None
                    if stream and not stream.done.is_set():
                        stream.close()
                    save_json(folder / "run.json", value)
            states = [c["status"] for c in value["candidates"]]
            value["status"] = "cancelled" if self.cancel.is_set() else "completed" if states and all(s == "completed" for s in states) else "completed_with_errors"
            value["progress"] = "Benchmark finished"
        except Exception as exc:
            value.update({"status": "error", "error": str(exc), "progress": "Benchmark failed"})
        finally:
            value["finished_at"] = datetime.now(timezone.utc).isoformat()
            save_json(folder / "run.json", value)
            with self.lock:
                self.active = None
                hostlock.release(self.host_lock)
                self.host_lock = None


manager = RunManager()
