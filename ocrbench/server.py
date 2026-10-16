import csv
import html
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from .schema import RunConfig, Annotation
from .storage import ROOT, DATA, sample_list, sample_path, get_annotation, save_json, read_json, clear_camera_session
from .runner import manager
from .environments import discovered_interpreter
from .terms import glossary, glossary_html
from .native import tesseract_command

@asynccontextmanager
async def lifespan(app):
    yield
    if manager.active:
        manager.stop()
        for _ in range(50):
            if not manager.active:
                break
            await asyncio.sleep(0.1)
    if not manager.active:
        clear_camera_session()


app = FastAPI(title="Automotive OCR Bench", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def local_requests(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-ocrbench") != "local":
        return Response("Local app header required", status_code=403)
    return await call_next(request)


@app.get("/api/system")
def system():
    packages = {"rapidocr": "rapidocr", "paddleocr": "paddleocr", "easyocr": "easyocr", "tesseract": "pytesseract"}
    engines = []
    for name, package in packages.items():
        installed = importlib.util.find_spec(package) is not None
        isolated = ROOT / ".engines" / name
        isolated_installed = (isolated / "Scripts" / "python.exe").exists() and (isolated / "Lib" / "site-packages" / package).is_dir()
        engines.append({"id": name, "installed": installed or isolated_installed,
                        "status": "Isolated environment · preflight required" if isolated_installed else "App environment · preflight required" if installed else "Configure isolated environment",
                        "python_path": str(isolated / "Scripts" / "python.exe") if isolated_installed else None,
                        "gpu_python_path": discovered_interpreter(name, "gpu"),
                        "gpu": name != "tesseract", "environment": str(isolated / "Scripts" / "python.exe")})
    return {"engines": engines, "interpreter": sys.executable, "active_run": manager.active, "data_directory": str(DATA),
            "tesseract_command": tesseract_command()}


@app.get('/api/glossary')
def metric_terms():
    return glossary()


@app.get("/api/samples")
def samples():
    return sample_list()


@app.get("/api/samples/{sample_id}/image")
def image(sample_id: str):
    try:
        return FileResponse(sample_path(sample_id))
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Image not found")


@app.post("/api/samples")
async def upload(file: UploadFile = File(...)):
    raw = await file.read(20*1024*1024+1)
    if len(raw) > 20*1024*1024:
        raise HTTPException(413, "Image exceeds 20 MB")
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.width * original.height > 24_000_000:
                raise HTTPException(413, "Image exceeds 24 megapixels")
            converted = ImageOps.exif_transpose(original).convert("RGB")
            stem = uuid.uuid4().hex[:12]
            path = DATA / "uploads" / f"{stem}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            converted.save(path)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Invalid or unsupported image")
    return {"id": "upload-"+stem}


@app.put("/api/samples/{sample_id}/annotation")
def annotation(sample_id: str, value: Annotation):
    try:
        path = sample_path(sample_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Image not found")
    with Image.open(path) as im:
        width, height = im.size
    polygons = [r.polygon for r in value.regions] + [l.polygon for l in value.labels if l.polygon] + [f.polygon for f in value.fields]
    if any(x > width or y > height for polygon in polygons for x,y in polygon):
        raise HTTPException(422, "Polygon extends outside source image")
    save_json(DATA / "annotations" / f"{sample_id}.json", value.model_dump())
    return value


def load_run(run_id):
    if len(run_id) != 12 or any(c not in "0123456789abcdef" for c in run_id):
        raise HTTPException(404, "Run not found")
    value = read_json(DATA / "runs" / run_id / "run.json")
    if value is None:
        raise HTTPException(404, "Run not found")
    return value


@app.get("/api/runs")
def runs():
    values = [read_json(p) for p in (DATA / "runs").glob("*/run.json")]
    result = []
    for value in values:
        if not value:
            continue
        row = {k: value.get(k) for k in ("id", "created_at", "status", "progress", "config")}
        # History needs measured summaries, but not the potentially large frame payloads.
        row["candidates"] = [
            {"name": c["name"], "config": c["config"], "status": c["status"],
             "summary": c.get("summary"), "resources": c.get("resources"),
             "observed_device": (c.get("identity") or {}).get("observed_device"),
             "error": c.get("error")}
            for c in value.get("candidates", [])
        ]
        result.append(row)
    return sorted(result, key=lambda v: v["created_at"], reverse=True)


@app.post("/api/runs")
def start_run(config: RunConfig):
    try:
        return manager.start(config)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    return load_run(run_id)


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: str):
    load_run(run_id)
    if manager.active == run_id:
        manager.stop()
    return {"status": "cancellation_requested"}


@app.get("/api/runs/{run_id}/export/{format}")
def export(run_id: str, format: str):
    value = load_run(run_id)
    headers = {"Content-Disposition": f'attachment; filename="ocrbench-{run_id}.{format}"'}
    if format == "json":
        return Response(json.dumps(value, ensure_ascii=False, indent=2), media_type="application/json", headers=headers)
    if format == "jsonl":
        rows = [{"run_id": run_id, "config_sha256": value["config_sha256"], "candidate": c["name"], "identity": c.get("identity"), **r}
                for c in value["candidates"] for r in c["records"]]
        return Response("\n".join(json.dumps(r, ensure_ascii=False) for r in rows)+"\n", media_type="application/x-ndjson", headers=headers)
    if format == "csv":
        out = io.StringIO(newline="")
        fields = ["engine", "requested_device", "observed_device", "status", "completed", "failures", "p95_ms", "p99_ms", "completed_fps", "cer", "e2e_f1", "peak_ram_mb", "error"]
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for c in value["candidates"]:
            s = c.get("summary", {}); identity = c.get("identity") or {}
            row = {"engine": c["config"]["engine"], "requested_device": c["config"]["device"], "observed_device": identity.get("observed_device"),
                   "status": c["status"], "completed": s.get("completed"), "failures": s.get("failures"), "p95_ms": s.get("latency_ms", {}).get("p95"),
                   "p99_ms": s.get("latency_ms", {}).get("p99"), "completed_fps": s.get("completed_fps"), "cer": s.get("cer"),
                   "e2e_f1": s.get("e2e", {}).get("f1"), "peak_ram_mb": c.get("resources", {}).get("peak_process_tree_rss_mb"), "error": c.get("error")}
            # Spreadsheet formula injection protection for arbitrary engine errors.
            writer.writerow({k: "'"+v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for k,v in row.items()})
        return Response("\ufeff"+out.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)
    if format == "html":
        sections = []
        for c in value["candidates"]:
            sections.append(f"<h2>{html.escape(c['name'])} · {html.escape(c['status'])}</h2><pre>{html.escape(json.dumps({k:v for k,v in c.items() if k != 'records'}, ensure_ascii=False, indent=2))}</pre>")
            for r in c["records"]:
                sections.append(f"<details><summary>{html.escape(r['frame_id'])} · {html.escape(r['status'])}</summary><pre>{html.escape(json.dumps(r, ensure_ascii=False, indent=2))}</pre></details>")
        content = "<!doctype html><meta charset='utf-8'><title>OCR benchmark report</title><style>body{font:15px system-ui;max-width:1000px;margin:48px auto;color:#17252a}pre{white-space:pre-wrap;background:#f3f5f5;padding:20px}summary{padding:12px;cursor:pointer}</style>"
        content += f"<h1>Automotive OCR benchmark</h1><p>Run {run_id} · {html.escape(value['created_at'])}</p><p>Strict Unicode scoring. Unreviewed or partial annotations have no full-image accuracy score. Repetitions do not add independent scene diversity. No automatic engine winner.</p>"+glossary_html()+"".join(sections)
        return Response(content, media_type="text/html", headers=headers)
    raise HTTPException(404, "Supported exports: json, jsonl, csv, html")


@app.get("/api/runs/{run_id}/logs/{candidate}")
def logs(run_id: str, candidate: str):
    value = load_run(run_id)
    if candidate not in [c["name"] for c in value["candidates"]]:
        raise HTTPException(404, "Candidate not found")
    path = DATA / "runs" / run_id / f"{candidate}.log"
    return Response(path.read_text(encoding="utf-8", errors="replace")[-100_000:] if path.exists() else "", media_type="text/plain")


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="dashboard")
