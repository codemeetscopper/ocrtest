from pathlib import Path
from ocrbench.process import Worker
from ocrbench.storage import ROOT

worker = Worker({"engine": "rapidocr", "device": "cpu", "languages": ["en"], "threads": 4}, ROOT / "probe.log")
try:
    value = worker.predict(ROOT / "data/fixtures/pivi-pro.jpg", metadata=True)
    import json
    print(json.dumps(value, indent=2))
finally:
    worker.close()
