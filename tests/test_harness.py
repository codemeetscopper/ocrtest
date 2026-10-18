import json
import threading
import time
from pathlib import Path
import pytest
from PIL import Image
from pydantic import ValidationError
from fastapi.testclient import TestClient
from ocrbench.schema import RunConfig, Region
from ocrbench.runner import RunManager, summary
from ocrbench.process import Worker, WorkerError
from ocrbench.sources import Stream
from ocrbench.storage import ROOT

@pytest.fixture
def client(tmp_path,monkeypatch):
    import ocrbench.storage as storage
    import ocrbench.server as server
    import ocrbench.runner as runner
    import ocrbench.hostlock as hostlock
    for module in (storage,server,runner,hostlock):monkeypatch.setattr(module,'DATA',tmp_path)
    (tmp_path/'fixtures').mkdir()
    Image.new('RGB',(100,50)).save(tmp_path/'fixtures'/'test.png')
    return TestClient(server.app,headers={'X-OCRBench':'local'})

def test_invalid_config():
    with pytest.raises(ValidationError):RunConfig(repetitions=0)
    with pytest.raises(ValidationError):RunConfig(mode='live',engines=[{'engine':'rapidocr'},{'engine':'easyocr'}])
    with pytest.raises(ValidationError):RunConfig(samples=['a'],replay_offsets_ms=[1,2])
    with pytest.raises(ValidationError):Region(polygon=[[0,0],[10,10],[0,10],[10,0]])

def test_api_upload_and_bounds(client):
    import io
    raw=io.BytesIO();Image.new('RGB',(30,20)).save(raw,format='PNG')
    uploaded=client.post('/api/samples',files={'file':('test.png',raw.getvalue(),'image/png')})
    assert uploaded.status_code==200
    sid=uploaded.json()['id']
    assert client.get('/api/samples/'+sid+'/image').status_code==200
    assert client.put('/api/samples/'+sid+'/annotation',json={'regions':[{'text':'x','polygon':[[0,0],[31,0],[31,10],[0,10]]}]}).status_code==422
    assert client.post('/api/samples',files={'file':('bad.png',b'not an image')}).status_code==422
    assert client.get('/api/runs/../../README').status_code==404

def test_no_csrf_mutations(client):
    assert client.post('/api/runs',json={},headers={'X-OCRBench':''}).status_code==403


def test_metric_definitions_are_available_and_exported(client):
    definitions = client.get('/api/glossary').json()
    assert any(t['title'].startswith('CER') and '100%' in t['description'] for t in definitions)
    assert any(t['title'] == 'Confidence' and 'not calibrated' in t['description'] for t in definitions)
    from ocrbench.terms import glossary_html
    html = glossary_html()
    assert 'What do these terms mean?' in html and 'P95 latency' in html


def test_missing_native_tesseract_is_not_reported_as_ready(client, monkeypatch):
    import ocrbench.server as server
    monkeypatch.setattr(server, 'tesseract_backend', lambda: 'pytesseract')
    monkeypatch.setattr(server, 'tesseract_command', lambda: None)
    monkeypatch.setattr(server.importlib.util, 'find_spec', lambda package: object())
    engines = {e['id']:e for e in client.get('/api/system').json()['engines']}
    assert not engines['tesseract']['installed']
    assert engines['rapidocr']['installed']
    assert 'runtime required' in engines['tesseract']['status']


def test_bundled_tesseract_can_be_ready_without_an_executable(client, monkeypatch, tmp_path):
    import ocrbench.server as server
    (tmp_path/'eng.traineddata').touch()
    monkeypatch.setattr(server, 'tesseract_backend', lambda: 'tesserocr')
    monkeypatch.setattr(server, 'tesseract_command', lambda: None)
    monkeypatch.setattr(server, 'tesserocr_data', lambda: tmp_path)
    monkeypatch.setattr(server.importlib.util, 'find_spec', lambda package: object())
    system = client.get('/api/system').json()
    assert system['tesseract_backend'] == 'tesserocr'
    assert next(engine for engine in system['engines'] if engine['id'] == 'tesseract')['installed']


def test_session_frame_image_is_reviewable_without_entering_dataset(client, tmp_path, monkeypatch):
    import ocrbench.storage as storage
    from types import SimpleNamespace
    session = tmp_path/'camera-session'
    session.mkdir()
    monkeypatch.setattr(storage, '_camera_session', SimpleNamespace(name=str(session)))
    monkeypatch.setattr(storage, '_session_frames', {})
    sid, path = storage.camera_frame_path('review-000000')
    Image.new('RGB', (40, 20)).save(path)
    assert client.get('/api/samples/'+sid+'/image').status_code == 200
    assert sid not in [s['id'] for s in client.get('/api/samples').json()]

def test_history_returns_metrics_without_frame_payloads(client):
    import ocrbench.server as server
    from ocrbench.storage import save_json
    config = RunConfig().model_dump()
    candidate = {'name': '0-rapidocr-cpu', 'config': config['engines'][0],
                 'status': 'completed', 'records': [{'predictions': [{'text': 'large payload'}]}],
                 'identity': {'observed_device': 'cpu', 'models': [{'weights': 'large identity'}]},
                 'summary': {'latency_ms': {'p95': 12.5}, 'completed_fps': 80,
                             'e2e': {'f1': None}, 'cer': None, 'failures': 0},
                 'resources': {'peak_process_tree_rss_mb': 100}}
    for rid, date in [('a'*12, '2026-10-15'), ('b'*12, '2026-10-16')]:
        save_json(server.DATA/'runs'/rid/'run.json', {'id': rid, 'created_at': date,
                  'status': 'completed', 'config': config, 'candidates': [candidate]})
    save_json(server.DATA/'runs'/('c'*12)/'run.json', {'id': 'c'*12,
              'created_at': '2026-10-14', 'status': 'queued', 'config': config})
    history = client.get('/api/runs').json()
    assert [r['id'] for r in history] == ['b'*12, 'a'*12, 'c'*12]
    row = history[0]['candidates'][0]
    assert row['summary']['latency_ms']['p95'] == 12.5
    assert row['summary']['e2e']['f1'] is None
    assert row['observed_device'] == 'cpu'
    assert row['resources']['peak_process_tree_rss_mb'] == 100
    assert 'records' not in row and 'identity' not in row
    assert history[-1]['candidates'] == []


def test_failed_candidate_persisted(client):
    response=client.post('/api/runs',json={'samples':['test'],'engines':[{'engine':'rapidocr','python_path':'no-such-python.exe'}]})
    assert response.status_code==200
    rid=response.json()['id']
    for _ in range(100):
        run=client.get('/api/runs/'+rid).json()
        if run['status'] not in ('queued','running'):break
        time.sleep(.02)
    assert run['status']=='completed_with_errors'
    assert run['candidates'][0]['status']=='unavailable'
    assert client.get('/api/runs/'+rid+'/export/csv').status_code==200
    assert client.get('/api/runs/'+rid+'/export/html').status_code==200

def test_failure_accounting_and_gates():
    from ocrbench.metrics import quality
    from tests.test_metrics import ann,region
    a=ann(region('68%'))
    records=[{'status':'success','sample_id':'one','quality':quality(a,[region('68%')]),'timing':{'image_to_result_ms':10}},
             {'status':'timeout','sample_id':'one','quality':quality(a,[]),'timing':{'image_to_result_ms':1000}}]
    s=summary(records,2,RunConfig(max_p95_ms=20,min_e2e_f1=.9))
    assert s['failures']==1 and s['e2e']['recall']==.5 and s['cer']==.5
    assert s['completed_fps']==.5 and s['acceptance']=={'p95':'fail','e2e_f1':'fail'}

def test_replay_overload_is_bounded():
    stream=Stream(RunConfig(mode='replay',repetitions=10,replay_fps=120,queue_size=1),[('x',Path('image.jpg'))],threading.Event())
    stream.thread.join(timeout=2)
    assert stream.done.is_set() and stream.stats['received']==10 and stream.stats['queue_drops']==9
    frames=list(stream)
    assert len(frames)==1 and frames[0]['frame_id']=='replay-9-0'

def test_replay_stop_does_not_cancel_other_candidates():
    cancellation=threading.Event()
    stream=Stream(RunConfig(mode='replay',repetitions=100,replay_fps=1),[('x',Path('image.jpg'))],cancellation)
    stream.close()
    assert not cancellation.is_set() and stream.done.is_set()

def test_worker_timeout_cleans_up():
    import queue
    worker=object.__new__(Worker)
    worker.timeout=.01;worker.dead=threading.Event();worker.responses=queue.Queue()
    import io
    class Process:
        stdin=io.StringIO()
    worker.process=Process()
    closed=[];worker.close=lambda:closed.append(True)
    with pytest.raises(WorkerError,match='timeout') as error:worker.request({'op':'predict'})
    assert error.value.status=='timeout' and closed

def test_engine_failure_does_not_pass_absent_label(tmp_path):
    class Broken:
        def predict(self,*a,**kw):raise WorkerError('crashed','crash')
    image=tmp_path/'x.png';Image.new('RGB',(20,20)).save(image)
    import io
    record=RunManager()._record(Broken(),'x',image,{'regions':[],'labels':[{'text':'absent','present':False}]},RunConfig(),{},io.StringIO())
    assert record['application']['labels'][0]['correct'] is None
    assert record['application']['correct_query_coverage']==0

def test_coordinate_mapping_and_real_rapidocr(tmp_path):
    pytest.importorskip('rapidocr')
    worker=Worker({'engine':'rapidocr','device':'cpu','languages':['en'],'threads':2},tmp_path/'worker.log')
    try:
        result=worker.predict(ROOT/'data/fixtures/pivi-pro.jpg','upscale',metadata=True)
        assert any(p['text']=='68%' for p in result['predictions'])
        assert result['identity']['observed_device']=='cpu'
        assert all(0<=x<=800 and 0<=y<=450 for p in result['predictions'] for x,y in p['polygon'])
        assert result['identity']['models'] and all(len(m['sha256'])==64 for m in result['identity']['models'])
    finally:worker.close()

def test_fatal_worker_keeps_remaining_frames_in_denominator(client,monkeypatch):
    import ocrbench.runner as runner
    class FatalWorker:
        def __init__(self,*args):self.calls=0;self.cpu_seconds=0
        def predict(self,*args,**kwargs):
            self.calls+=1
            if self.calls>1:raise WorkerError('timed out','timeout')
            return {'identity':{},'predictions':[],'timing':{}}
        def resources(self):return {}
        def close(self):pass
    monkeypatch.setattr(runner,'Worker',FatalWorker)
    rid=client.post('/api/runs',json={'samples':['test'],'repetitions':5,'warmups':0}).json()['id']
    for _ in range(100):
        run=client.get('/api/runs/'+rid).json()
        if run['status'] not in ('queued','running'):break
        time.sleep(.02)
    c=run['candidates'][0]
    assert c['status']=='timeout' and len(c['records'])==5
    assert c['summary']['failures']==5 and c['summary']['not_attempted']==4

def test_cross_process_lock(tmp_path,monkeypatch):
    import ocrbench.hostlock as hostlock
    monkeypatch.setattr(hostlock,'DATA',tmp_path)
    handle=hostlock.acquire()
    try:
        with pytest.raises(RuntimeError):hostlock.acquire()
    finally:hostlock.release(handle)

@pytest.mark.parametrize('engine',['easyocr','paddleocr'])
def test_isolated_engine_on_supplied_image(engine,tmp_path):
    interpreter=ROOT/'.engines'/engine/'Scripts/python.exe'
    if not interpreter.exists():pytest.skip('Optional engine environment not provisioned')
    worker=Worker({'engine':engine,'device':'cpu','languages':['en'],'threads':4,'python_path':str(interpreter),'options':{}},tmp_path/(engine+'.log'),180)
    try:
        result=worker.predict(ROOT/'data/fixtures/pivi-pro.jpg',metadata=True)
        # This is an integration contract, not an accuracy acceptance test.
        # Misses and transcription errors must remain visible in benchmark data.
        assert result['predictions'] and all(isinstance(p['text'],str) and len(p['polygon'])>=3 for p in result['predictions'])
        assert result['identity']['observed_device']=='cpu'
        assert result['identity']['models']
    finally:worker.close()
