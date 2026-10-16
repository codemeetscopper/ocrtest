import threading
import sys
import os
from types import SimpleNamespace
from pathlib import Path
import pytest
from ocrbench.process import Worker, WorkerError
from ocrbench.schema import RunConfig
from ocrbench.sources import Stream
from ocrbench.storage import ROOT


def test_rapidocr_gpu_cannot_pass_as_cpu(tmp_path):
    ort=pytest.importorskip('onnxruntime')
    pytest.importorskip('rapidocr')
    if 'CUDAExecutionProvider' in ort.get_available_providers():
        pytest.skip('CUDA installed; CPU-only fallback test does not apply')
    worker=None
    try:
        with pytest.raises(WorkerError,match='no CUDA provider'):
            worker=Worker({'engine':'rapidocr','device':'gpu','languages':['en'],'threads':2,'python_path':sys.executable},tmp_path/'gpu.log')
            worker.predict(ROOT/'data/fixtures/pivi-pro.jpg')
    finally:
        if worker:worker.close()


def test_camera_acquisition_fault_is_separate(monkeypatch):
    import cv2
    released=[]
    class MissingCamera:
        def isOpened(self):return False
        def release(self):released.append(True)
        def __bool__(self):return True
    monkeypatch.setattr(cv2,'VideoCapture',lambda *args:MissingCamera())
    stream=Stream(RunConfig(mode='live',samples=[]),[],threading.Event())
    stream.thread.join(timeout=2)
    assert stream.done.is_set() and 'Cannot open camera' in stream.error
    assert stream.stats['received']==0 and released


@pytest.mark.parametrize('engine',['rapidocr','paddleocr','easyocr'])
def test_device_specific_interpreter_selection(engine,tmp_path,monkeypatch):
    import ocrbench.environments as envs
    monkeypatch.setattr(envs,'ROOT',tmp_path)
    gpu=tmp_path/'.engines'/f'{engine}-gpu'
    (gpu/'Scripts').mkdir(parents=True)
    (gpu/'Scripts/python.exe').touch()
    (gpu/'Lib/site-packages'/engine).mkdir(parents=True)
    assert envs.resolve_interpreter({'engine':engine,'device':'gpu'})==str(gpu/'Scripts/python.exe')
    assert envs.resolve_interpreter({'engine':engine,'device':'cpu'})==sys.executable
    assert envs.resolve_interpreter({'engine':engine,'device':'gpu','python_path':'custom.exe'})=='custom.exe'


def test_gpu_dlls_preloaded_before_model_creation(monkeypatch):
    from ocrbench.worker import Adapter
    import importlib.metadata
    calls=[]
    class FakeRapid:
        def __init__(self,params):
            calls.append('model')
            assert params['EngineConfig.onnxruntime.use_cuda'] is True
    monkeypatch.setitem(sys.modules,'onnxruntime',SimpleNamespace(__version__='test',get_available_providers=lambda:['CUDAExecutionProvider'],preload_dlls=lambda:calls.append('dlls')))
    monkeypatch.setitem(sys.modules,'rapidocr',SimpleNamespace(RapidOCR=FakeRapid,EngineType=SimpleNamespace(ONNXRUNTIME='onnxruntime')))
    monkeypatch.setattr(importlib.metadata,'version',lambda name:'test')
    Adapter({'engine':'rapidocr','device':'gpu','languages':['en'],'threads':2})
    assert calls==['dlls','model']


@pytest.mark.skipif(os.environ.get('OCRBENCH_TEST_GPU')!='1',reason='Opt-in real CUDA hardware test')
def test_real_rapidocr_cuda_on_supplied_image(tmp_path):
    worker=Worker({'engine':'rapidocr','device':'gpu','languages':['en'],'threads':4},tmp_path/'real-gpu.log')
    try:
        result=worker.predict(ROOT/'data/fixtures/pivi-pro.jpg',metadata=True)
        assert len(result['identity']['providers'])==3
        assert all('CUDAExecutionProvider' in p for p in result['identity']['providers'])
        assert any(p['text']=='68%' for p in result['predictions'])
        assert 'rapidocr-gpu' in result['identity']['interpreter']
    finally:worker.close()


def test_tesseract_gpu_is_rejected_before_worker_start():
    from ocrbench.schema import EngineConfig
    from pydantic import ValidationError
    with pytest.raises(ValidationError,match='CPU only'):
        EngineConfig(engine='tesseract',device='gpu')


@pytest.mark.skipif(os.name!='nt',reason='Windows DLL loader test')
def test_paddle_cuda13_pip_library_layout(tmp_path,monkeypatch):
    import ctypes
    import ocrbench.worker as module
    root=tmp_path/'nvidia'
    cuda=root/'cu13/bin/x86_64';cudnn=root/'cudnn/bin'
    cuda.mkdir(parents=True);cudnn.mkdir(parents=True)
    for filename in ('cublas64_13.dll','cublasLt64_13.dll','cudart64_13.dll'):(cuda/filename).touch()
    (cudnn/'cudnn64_9.dll').touch()
    registered=[];loaded=[]
    monkeypatch.setattr(os,'add_dll_directory',lambda path:registered.append(path))
    monkeypatch.setattr(ctypes,'WinDLL',lambda path:loaded.append(Path(path).name))
    monkeypatch.setenv('PATH','original-path')
    monkeypatch.setattr(module,'_dll_directories',[])
    monkeypatch.setattr(module,'_cuda_libraries',[])
    directories=module.load_paddle_cuda_libraries(root)
    assert set(registered)=={str(cuda.resolve()),str(cudnn.resolve())}==set(directories)
    assert loaded==['cudart64_13.dll','cublasLt64_13.dll','cublas64_13.dll','cudnn64_9.dll']
    assert os.environ['PATH'].endswith('original-path')


@pytest.mark.parametrize('engine',['paddleocr','easyocr'])
def test_cpu_framework_cannot_pass_as_gpu(engine,tmp_path):
    interpreter=ROOT/'.engines'/engine/'Scripts/python.exe'
    if not interpreter.exists():pytest.skip('CPU environment not provisioned')
    with pytest.raises(WorkerError,match='GPU requires'):
        Worker({'engine':engine,'device':'gpu','languages':['en'],'threads':2,'python_path':str(interpreter)},tmp_path/(engine+'-cpu-rejection.log'))


@pytest.mark.skipif(os.environ.get('OCRBENCH_TEST_GPU')!='1',reason='Opt-in real CUDA hardware test')
@pytest.mark.parametrize('engine',['paddleocr','easyocr'])
def test_real_framework_cuda_on_supplied_image(engine,tmp_path):
    worker=Worker({'engine':engine,'device':'gpu','languages':['en'],'threads':4},tmp_path/(engine+'-cuda.log'),180)
    try:
        result=worker.predict(ROOT/'data/fixtures/pivi-pro.jpg',metadata=True)
        identity=result['identity']
        assert result['predictions']
        assert 'gpu' in identity['observed_device'] or 'cuda' in identity['observed_device']
        assert identity['runtime']['cuda_version'] not in (None,False,'False')
        assert identity['runtime']['gpu_name']
        assert engine+'-gpu' in identity['interpreter']
    finally:worker.close()
