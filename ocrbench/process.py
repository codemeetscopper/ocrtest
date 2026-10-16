import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
import psutil
from .storage import ROOT
from .environments import resolve_interpreter


class WorkerError(RuntimeError):
    def __init__(self, message, status="error"):
        super().__init__(message)
        self.status = status


class Worker:
    def __init__(self, config, log_path, timeout=120):
        self.timeout = timeout
        self.log = open(log_path, "a", encoding="utf-8")
        interpreter = resolve_interpreter(config)
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.started = time.perf_counter()
        self.process = subprocess.Popen([interpreter, "-m", "ocrbench.worker"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, text=True, encoding="utf-8", env=env, cwd=ROOT, creationflags=flags)
        self.responses = queue.Queue()
        self.dead = threading.Event()
        self.peak_rss = 0
        self.resource_samples = 0
        self.monitor_stop = threading.Event()
        self.cpu_seconds = 0
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._monitor, daemon=True).start()
        try:
            self.init = self.request({"op": "init", "config": config})
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                if line.startswith("OCRBENCH:"):
                    try:
                        self.responses.put(json.loads(line[9:]))
                    except ValueError:
                        self.responses.put({"ok": False, "error": "Malformed worker JSON", "status": "invalid_output"})
                else:
                    if not self.log.closed:
                        self.log.write(line)
        finally:
            self.dead.set()
            self.responses.put({"ok": False, "error": "Worker exited", "status": "crash"})

    def _monitor(self):
        while not self.monitor_stop.is_set():
            try:
                root = psutil.Process(self.process.pid)
                processes = [root] + root.children(recursive=True)
                rss, cpu = 0, 0
                for p in processes:
                    rss += p.memory_info().rss
                    t = p.cpu_times()
                    cpu += t.user+t.system
                self.peak_rss = max(self.peak_rss, rss)
                self.cpu_seconds = max(self.cpu_seconds, cpu)
                self.resource_samples += 1
            except psutil.Error:
                pass
            self.monitor_stop.wait(0.05)

    def request(self, payload):
        if self.dead.is_set():
            raise WorkerError("Worker no longer running", "crash")
        start = time.perf_counter()
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise WorkerError(str(exc), "crash") from exc
        try:
            reply = self.responses.get(timeout=self.timeout)
        except queue.Empty:
            self.close()
            raise WorkerError(f"Worker exceeded {self.timeout:g}s timeout", "timeout")
        if not reply.get("ok"):
            raise WorkerError(reply.get("error", "Worker failure"), reply.get("status", "error"))
        reply["roundtrip_ms"] = (time.perf_counter()-start)*1000
        return reply

    def predict(self, path, preprocessing="raw", crop=None, metadata=False):
        value = self.request({"op": "predict", "path": str(path), "preprocessing": preprocessing, "crop": crop, "metadata": metadata})
        from .schema import Region
        try:
            for p in value["predictions"]:
                Region(text=p["text"], polygon=p["polygon"])
                score = p.get("confidence")
                if score is not None and not 0 <= score <= 1:
                    raise ValueError("Confidence outside [0,1]")
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkerError(f"Invalid prediction: {exc}", "invalid_output") from exc
        return value

    def resources(self):
        return {"peak_process_tree_rss_mb": self.peak_rss/1024**2 if self.resource_samples else None,
                "cpu_core_seconds": self.cpu_seconds if self.resource_samples else None, "gpu_utilization": None, "vram_mb": None,
                "scope": "worker process tree; summed RSS can double count shared memory; lifetime including initialization",
                "sample_interval_ms": 50, "samples": self.resource_samples}

    def close(self):
        self.monitor_stop.set()
        if self.process.poll() is None:
            try:
                root = psutil.Process(self.process.pid)
                children = root.children(recursive=True)
                for p in reversed(children):
                    try:
                        p.kill()
                    except psutil.Error:
                        pass
                root.kill()
            except psutil.Error:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if not self.log.closed:
            self.log.close()
