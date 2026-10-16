"""Bounded arrival queues shared by replay and native OpenCV camera capture."""
import queue
import threading
import time
import uuid
from .storage import camera_frame_path


class Stream:
    def __init__(self, config, paths, cancel):
        self.config, self.paths, self.cancel = config, paths, cancel
        self.stopped = threading.Event()
        self.queue = queue.Queue(config.queue_size)
        self.done = threading.Event()
        self.stats = {"received": 0, "queue_drops": 0, "capture_faults": 0, "backend": None,
                      "timestamp_origin": "host perf_counter; receive after successful acquisition"}
        self.error = None
        self.thread = threading.Thread(target=self._produce, daemon=True)
        self.thread.start()

    def _wait(self, seconds):
        end = time.perf_counter()+seconds
        while time.perf_counter() < end:
            if self.cancel.is_set() or self.stopped.wait(min(0.05, end-time.perf_counter())):
                return True
        return self.cancel.is_set() or self.stopped.is_set()

    def _offer(self, frame):
        self.stats["received"] += 1
        if self.config.queue_policy == "latest":
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                    self.stats["queue_drops"] += 1
                except queue.Empty:
                    pass
            self.queue.put_nowait(frame)
        else:
            # Bounded all-frame mode drops new arrivals when capacity is exhausted;
            # never block acquisition and pretend the camera/replay slowed down.
            try:
                self.queue.put_nowait(frame)
            except queue.Full:
                self.stats["queue_drops"] += 1

    def _produce(self):
        cap = None
        try:
            start = time.perf_counter()
            if self.config.mode == "replay":
                schedule = self.config.replay_offsets_ms
                offsets = [n/1000 for n in schedule] if schedule else [i/self.config.replay_fps for i in range(len(self.paths))]
                period = (offsets[-1] if offsets else 0) + 1/self.config.replay_fps
                for repetition in range(self.config.repetitions):
                    for i, (sample_id, path) in enumerate(self.paths):
                        target = start + repetition*period + offsets[i]
                        if self._wait(max(0, target-time.perf_counter())):
                            return
                        self._offer({"sample_id": sample_id, "path": path, "received_at": time.perf_counter(),
                                     "scheduled_at": target, "frame_id": f"replay-{repetition}-{i}", "repetition": repetition})
                self.stats["backend"] = "timed replay"
            else:
                import cv2
                cap = cv2.VideoCapture(self.config.camera_index, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    raise RuntimeError("Cannot open camera. Check the index, camera permissions, and Windows driver.")
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.camera_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.camera_height)
                self.stats.update({"backend": cap.getBackendName(), "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                                   "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT), "fps": cap.get(cv2.CAP_PROP_FPS)})
                session = uuid.uuid4().hex[:10]
                start = time.perf_counter()
                i = 0
                while time.perf_counter()-start < self.config.duration_s and not self.cancel.is_set() and not self.stopped.is_set():
                    ok, image = cap.read()
                    received = time.perf_counter()
                    if not ok:
                        self.stats["capture_faults"] += 1
                        if self.stats["capture_faults"] >= 10:
                            raise RuntimeError("Camera repeatedly failed to deliver frames")
                        continue
                    # Temporary files let the isolated worker read frames and retain
                    # review history for this app session. Dataset saving is opt-in.
                    stem = f"{session}-{i:06d}"
                    sample_id, path = camera_frame_path(stem, self.config.save_camera_frames)
                    encoded, buffer = cv2.imencode(".png", image)
                    if not encoded:
                        raise RuntimeError("Failed to persist camera frame")
                    buffer.tofile(str(path))
                    self._offer({"sample_id": sample_id, "path": path, "received_at": received,
                                 "frame_id": f"{session}-{i}", "repetition": 0,
                                 "frame_storage": "dataset" if self.config.save_camera_frames else "session"})
                    i += 1
                    self._wait(max(0, 1/self.config.replay_fps - (time.perf_counter()-received)))
                self.stats["requested_sampling_fps"] = self.config.replay_fps
        except Exception as exc:
            self.error = str(exc)
        finally:
            if cap:
                cap.release()
            self.done.set()

    def __iter__(self):
        while not self.cancel.is_set() and (not self.done.is_set() or not self.queue.empty()):
            try:
                yield self.queue.get(timeout=0.1)
            except queue.Empty:
                pass

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
