from types import SimpleNamespace
from PIL import Image
from ocrbench.schema import RunConfig
import ocrbench.storage as storage


def test_camera_frames_are_temporary_and_not_in_dataset_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path/'data')
    session = tmp_path/'temporary'
    session.mkdir()
    monkeypatch.setattr(storage, '_camera_session', SimpleNamespace(name=str(session)))
    monkeypatch.setattr(storage, '_session_frames', {})
    assert RunConfig(mode='live').save_camera_frames is False
    sid, path = storage.camera_frame_path('test-000000')
    Image.new('RGB', (20, 10)).save(path)
    assert path.parent == session and sid.startswith('session-')
    assert storage.sample_path(sid) == path
    assert storage.sample_list() == []
    assert not (storage.DATA/'captures').exists()
    # A new app session cannot resolve the expired temporary frame.
    monkeypatch.setattr(storage, '_session_frames', {})
    import pytest
    with pytest.raises(FileNotFoundError):
        storage.sample_path(sid)


def test_only_explicitly_saved_camera_frames_enter_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    sid, path = storage.camera_frame_path('opted-in-000000', True)
    Image.new('RGB', (20, 10)).save(path)
    old = tmp_path/'captures/legacy-000000.png'
    Image.new('RGB', (20, 10)).save(old)
    assert [s['id'] for s in storage.sample_list()] == [sid]
    assert storage.sample_path(sid) == path
    # Legacy frames stay readable by their existing run, outside the dataset.
    assert storage.sample_path('capture-legacy-000000') == old


def test_live_acquisition_uses_temporary_storage(tmp_path, monkeypatch):
    import cv2
    import numpy as np
    import threading
    from ocrbench.sources import Stream
    session = tmp_path/'temporary'
    session.mkdir()
    monkeypatch.setattr(storage, 'DATA', tmp_path/'data')
    monkeypatch.setattr(storage, '_camera_session', SimpleNamespace(name=str(session)))
    monkeypatch.setattr(storage, '_session_frames', {})
    class Camera:
        def isOpened(self): return True
        def set(self, *args): pass
        def get(self, *args): return 20
        def getBackendName(self): return 'test camera'
        def read(self): return True, np.zeros((10, 20, 3), dtype=np.uint8)
        def release(self): pass
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *args: Camera())
    def stop_after_one(self, seconds):
        self.stopped.set()
        return True
    monkeypatch.setattr(Stream, '_wait', stop_after_one)
    stream = Stream(RunConfig(mode='live', samples=[]), [], threading.Event())
    stream.thread.join(timeout=2)
    frames = list(stream)
    assert stream.done.is_set() and stream.error is None and len(frames) == 1
    assert frames[0]['frame_storage'] == 'session'
    assert frames[0]['path'].parent == session
    assert storage.sample_path(frames[0]['sample_id']).is_file()
    assert storage.sample_list() == []
