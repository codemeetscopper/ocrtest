import hashlib
import json
import os
import threading
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("OCRBENCH_DATA", ROOT / "data")).resolve()
LOCK = threading.RLock()
_camera_session = None
_session_frames = {}


def clear_camera_session():
    global _camera_session
    with LOCK:
        _session_frames.clear()
        if _camera_session is not None:
            _camera_session.cleanup()
            _camera_session = None


def camera_frame_path(stem, save_to_dataset=False):
    """Keep default captures outside the dataset, only for this app session."""
    global _camera_session
    with LOCK:
        if save_to_dataset:
            path = DATA / "captures" / f"{stem}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            save_json(path.with_suffix('.dataset.json'), {"included": True})
            return f"capture-{stem}", path
        if _camera_session is None:
            _camera_session = tempfile.TemporaryDirectory(prefix="ocrbench-camera-")
        sample_id = f"session-{stem}"
        path = Path(_camera_session.name) / f"{stem}.png"
        _session_frames[sample_id] = path
        return sample_id, path


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, value):
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)


def read_json(path, default=None):
    with LOCK:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def sample_list():
    samples = []
    from PIL import Image
    for folder, prefix in [("fixtures", ""), ("uploads", "upload-"), ("captures", "capture-")]:
        for p in sorted((DATA / folder).glob("*")):
            if p.suffix.lower() not in (".jpg", ".png", ".jpeg", ".webp"):
                continue
            if folder == "captures" and not read_json(p.with_suffix('.dataset.json'), {}).get('included'):
                continue
            with Image.open(p) as image:
                width, height = image.size
            sample_id = prefix + p.stem
            annotation = get_annotation(sample_id)
            samples.append({"id": sample_id, "name": "Pivi Pro · supplied image" if sample_id == "pivi-pro" else p.name,
                            "width": width, "height": height, "sha256": digest(p),
                            "capture_group": "supplied-pivi-pro" if sample_id == "pivi-pro" else p.stem,
                            "split": "development", "annotation": annotation,
                            "url": f"/api/samples/{sample_id}/image"})
    return samples


def sample_path(sample_id):
    # Never accept arbitrary filesystem paths from HTTP clients.
    if not sample_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in sample_id):
        raise ValueError("Invalid sample identifier")
    if sample_id.startswith('session-'):
        with LOCK:
            path = _session_frames.get(sample_id)
        if path is not None and path.exists():
            return path
        raise FileNotFoundError(sample_id)
    folder, stem = ("uploads", sample_id[7:]) if sample_id.startswith("upload-") else ("captures", sample_id[8:]) if sample_id.startswith("capture-") else ("fixtures", sample_id)
    for suffix in (".jpg", ".png", ".jpeg", ".webp"):
        p = DATA / folder / (stem + suffix)
        if p.exists():
            return p
    raise FileNotFoundError(sample_id)


def get_annotation(sample_id):
    default = read_json(DATA / "fixtures" / f"{sample_id}.json", {"reviewed": False, "complete": False, "granularity": "line", "regions": [], "labels": [], "fields": [], "notes": ""})
    return read_json(DATA / "annotations" / f"{sample_id}.json", default)
