"""Save a portable HTML report and a compact measured validation record."""
import json
import sys
from ocrbench.server import export
from ocrbench.storage import ROOT, DATA

run_id = sys.argv[1]
run = json.loads((DATA / "runs" / run_id / "run.json").read_text(encoding="utf-8"))
report = export(run_id, "html")
(ROOT / "docs" / "sample-benchmark.html").write_bytes(report.body)
lines = ["# Supplied-image validation", "", f"Run: `{run_id}` · {run['created_at']} · {run['status']}", "",
         "Input: supplied 800×450 Pivi Pro capture. Native Windows CPU workers, four CPU threads, one warmup, five measured repetitions per engine. Candidates executed sequentially.", "",
         "| Engine | Version | p95 image-to-result (ms) | Completed FPS | Peak worker RSS (MB) | Failures |",
         "| --- | --- | ---: | ---: | ---: | ---: |"]
for c in run["candidates"]:
    s = c.get("summary", {})
    lines.append(f"| {c['config']['engine']} | {c['identity']['library_version']} | {s['latency_ms']['p95']:.1f} | {s['completed_fps']:.2f} | {c['resources']['peak_process_tree_rss_mb']:.0f} | {s['failures']} |")
lines += ["", "PaddleOCR used the CPU compatibility setting `enable_mkldnn=false`. The original oneDNN preflight failure is retained in run history. Model families differ; this is a pipeline comparison rather than a controlled backend comparison.", "",
          "Full-image quality is unavailable because the supplied draft annotations have not been human reviewed. Raw OCR predictions and application assertions remain available. The expected economy value mismatch is retained.", "",
          "Verification: 28 automated tests passed, including actual inference in all three provisioned engine environments, Unicode scoring, source-coordinate mapping, error accounting, timeout cleanup, GPU fallback rejection on the CPU runtime, mocked camera failure, bounded replay drops, and host locking. Browser checks covered a saved-image run, overlays, annotation editor, labels, region values, history, and installed-engine detection.", "",
          "Timed replay run `b99acd0f68b3` received 20 scheduled frames, completed 6, and reported 14 queue drops with no unprocessed received frames. That overload pilot was run during other verification work and is not an isolated performance comparison.", "",
          "Live camera hardware, actual GPU execution, Tesseract's native executable, required multilingual coverage, and the external production test computer remain unverified. Five repetitions and one scene do not establish reliable tail latency or a production ranking.", "",
          "See sample-benchmark.html for portable detailed evidence, or reopen the run in the app for overlays and exports."]
(ROOT / "docs" / "validation.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
print("Saved docs/sample-benchmark.html and docs/validation.md")
