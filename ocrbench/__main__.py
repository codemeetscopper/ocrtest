import argparse
import json
import time
from .schema import RunConfig


def main():
    parser = argparse.ArgumentParser(description="Automotive OCR benchmark workbench")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="Start the local dashboard")
    serve.add_argument("--port", type=int, default=8765)
    bench = sub.add_parser("run", help="Run a saved JSON configuration headlessly")
    bench.add_argument("config")
    args = parser.parse_args()
    if args.command == "run":
        from .runner import manager
        from .storage import DATA, read_json
        config = RunConfig.model_validate_json(open(args.config, encoding="utf-8").read())
        run = manager.start(config)
        print(f"Run {run['id']} started", flush=True)
        try:
            while manager.active:
                time.sleep(0.2)
        except KeyboardInterrupt:
            manager.stop()
            while manager.active:
                time.sleep(0.2)
        result = read_json(DATA / "runs" / run["id"] / "run.json")
        print(json.dumps({"id": result["id"], "status": result["status"], "candidates": [{k:v for k,v in c.items() if k != "records" and k != "first_request"} for c in result["candidates"]]}, indent=2))
        raise SystemExit(0 if result["status"] == "completed" else 1)
    else:
        import uvicorn
        uvicorn.run("ocrbench.server:app", host="127.0.0.1", port=getattr(args, "port", 8765))


if __name__ == "__main__":
    main()
