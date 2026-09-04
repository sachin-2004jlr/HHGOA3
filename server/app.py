"""FastAPI backend for the facechain web app.

    python -m uvicorn server.app:app --port 8010

Endpoints (all JSON unless noted):
    GET  /api/health                      liveness + version
    GET  /api/chain                       which blockchain backend is active, contract, record count
    POST /api/runs                        multipart: image=<file>, optional min_similarity, max_candidates,
                                          expand, chain  -> {id}  (job runs in the background)
    GET  /api/runs                        history of previous runs (from memory + evidence folders)
    GET  /api/runs/{id}                   live job state: status, steps, log, result
    GET  /api/runs/{id}/files/{name}      evidence files (images, record.json, receipt)
    POST /api/runs/{id}/verify            re-verify the evidence bundle against the chain
    POST /api/runs/{id}/tamper            tamper a copy of the evidence and verify it (expected to fail)
    DELETE /api/runs/{id}                 delete an evidence bundle
If web/dist exists (npm run build) it is served at / so the app works from a single port.
"""
from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from facechain import __version__, config  # noqa: E402
from facechain import evidence as ev  # noqa: E402
from facechain.pipeline import NoMatchError, Options, PipelineError, run_pipeline  # noqa: E402
from facechain.verify import tamper_copy, verify_bundle  # noqa: E402

app = FastAPI(title="facechain", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# One pipeline at a time: the face models are CPU bound and chain transactions must keep nonce order.
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_engine = None
_engine_lock = threading.Lock()

ALLOWED_FILES = {"query.jpg", "query_annotated.jpg", "query_crop.jpg", "query_search.jpg", "query_face.jpg", "record.json",
                 "candidates.json", "chain_receipt.json", "query_embedding.json"}
MAX_UPLOAD = 15 * 1024 * 1024


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            from facechain.face import FaceEngine

            _engine = FaceEngine()
        return _engine


# --------------------------------------------------------------------------- jobs
def _new_job(run_id: str, source: str, options: dict) -> dict:
    job = {
        "id": run_id, "status": "queued", "source": source, "options": options,
        "created_at": ev.now_iso(), "started_at": None, "finished_at": None, "elapsed": None,
        "steps": {str(i): {"status": "pending", "title": None, "started": None, "finished": None,
                           "duration": None, "data": None, "message": None} for i in range(1, 7)},
        "log": [], "result": None, "error": None,
    }
    with _jobs_lock:
        _jobs[run_id] = job
    return job


def _run_job(job: dict, image_bytes: bytes, opts: Options) -> None:
    job["status"], job["started_at"] = "running", ev.now_iso()
    t0 = time.time()

    def emit(step, status, title, data=None, message=None):
        s = job["steps"][str(step)]
        s["title"] = title
        now = time.time()
        if status == "start":
            s.update(status="running", started=now, message=None, progress=None)
        elif status == "progress":
            if data:
                s["progress"] = data
            if message:
                s["message"] = message
        elif status in ("done", "error"):
            s.update(status=status, finished=now, duration=round(now - (s["started"] or now), 2), message=message)
            if data is not None:
                s["data"] = data
        if message or status in ("start", "done", "error"):
            job["log"].append({"t": round(now - t0, 2), "step": step, "status": status,
                               "message": message or ("started" if status == "start" else status)})

    try:
        result = run_pipeline(image_bytes=image_bytes, options=opts, emit=emit, run_id=job["id"],
                              engine=get_engine(), source_label=job["source"])
        job["result"] = result
        job["status"] = result.get("status", "done")
    except NoMatchError as e:
        job["status"], job["error"] = "no_match", str(e)
        job["result"] = {"run_id": job["id"], "status": "no_match", "best": e.best}
    except PipelineError as e:
        job["status"], job["error"] = "failed", str(e)
        job["steps"][str(e.step)].update(status="error", finished=time.time(), message=str(e))
        job["log"].append({"t": round(time.time() - t0, 2), "step": e.step, "status": "error", "message": str(e)})
    except Exception as e:  # noqa: BLE001
        job["status"], job["error"] = "failed", f"{type(e).__name__}: {e}"
        running = [k for k, s in job["steps"].items() if s["status"] == "running"]
        for k in running:
            job["steps"][k].update(status="error", finished=time.time(), message=job["error"])
        job["log"].append({"t": round(time.time() - t0, 2), "step": int(running[0]) if running else 0,
                           "status": "error", "message": job["error"]})
    finally:
        job["finished_at"] = ev.now_iso()
        job["elapsed"] = round(time.time() - t0, 1)


def _evidence_dir(run_id: str) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(400, "bad run id")
    return config.EVIDENCE_DIR / run_id


def _history_from_disk() -> list[dict]:
    items = []
    if not config.EVIDENCE_DIR.exists():
        return items
    for d in sorted(config.EVIDENCE_DIR.iterdir(), reverse=True):
        rec_path = d / "record.json"
        if not d.is_dir() or not rec_path.exists() or d.name.endswith("-tampered"):
            continue
        try:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        receipt_path = d / "chain_receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else None
        match = rec.get("match") or {}
        items.append({
            "id": d.name, "created_at": rec.get("created_at"), "status": rec.get("status", "done" if receipt else "unanchored"),
            "platform": match.get("platform"), "post_url": match.get("post_url"), "title": match.get("title"),
            "similarity": match.get("similarity"), "record_hash": ev.record_hash(rec) if "match" in rec else None,
            "chain": (receipt or {}).get("chain"), "tx_hash": (receipt or {}).get("tx_hash"),
            "block_number": (receipt or {}).get("block_number"), "image_file": match.get("image_file"),
        })
    return items


# ---------------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "search_engine": _search_engine_name(),
            "time": ev.now_iso()}


def _search_engine_name() -> Optional[str]:
    from facechain.search import available_engines

    return "+".join(available_engines())


@app.get("/api/chain")
def chain_info():
    from facechain.chain import get_backend

    try:
        b = get_backend("auto")
        info = b.info()
        info["ok"] = True
        return info
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@app.post("/api/runs")
async def create_run(image: UploadFile = File(...), min_similarity: float = Form(config.FACE_MATCH_THRESHOLD),
                     max_candidates: int = Form(config.MAX_CANDIDATES), expand: bool = Form(True),
                     chain: str = Form("auto"), source: str = Form("upload")):
    data = await image.read()
    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image larger than 15 MB")
    if chain not in ("auto", "evm", "sim"):
        raise HTTPException(400, "chain must be auto, evm or sim")
    opts = Options(min_similarity=max(0.0, min(1.0, min_similarity)), max_candidates=max(5, min(150, max_candidates)),
                   expand=expand, chain=chain)
    run_id = ev.new_run_id()
    with _jobs_lock:
        while run_id in _jobs or (config.EVIDENCE_DIR / run_id).exists():
            time.sleep(1)
            run_id = ev.new_run_id()
    job = _new_job(run_id, source, {"min_similarity": opts.min_similarity, "max_candidates": opts.max_candidates,
                                    "expand": opts.expand, "chain": opts.chain, "filename": image.filename})
    job["queue_position"] = sum(1 for j in _jobs.values() if j["status"] in ("queued", "running")) - 1
    _executor.submit(_run_job, job, data, opts)
    return {"id": run_id, "status": job["status"]}


@app.get("/api/runs")
def list_runs():
    disk = {h["id"]: h for h in _history_from_disk()}
    with _jobs_lock:
        live = [j for j in _jobs.values() if j["status"] in ("queued", "running")]
    for j in live:
        disk[j["id"]] = {"id": j["id"], "created_at": j["created_at"], "status": j["status"]}
    return sorted(disk.values(), key=lambda h: h["id"], reverse=True)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    with _jobs_lock:
        job = _jobs.get(run_id)
    if job:
        return job
    d = _evidence_dir(run_id)
    if not (d / "record.json").exists():
        raise HTTPException(404, "unknown run")
    rec = json.loads((d / "record.json").read_text(encoding="utf-8"))
    receipt_path = d / "chain_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else None
    cands_path = d / "candidates.json"
    cands = json.loads(cands_path.read_text(encoding="utf-8")) if cands_path.exists() else []
    match = rec.get("match")
    result = {
        "run_id": run_id, "status": rec.get("status", "done" if receipt else "unanchored"), "evidence_dir": str(d),
        "query": {**rec.get("query", {}), "files": {"original": "query.jpg", "annotated": "query_annotated.jpg",
                                                    "crop": "query_crop.jpg", "face": "query_face.jpg"}},
        "search": {**rec.get("search", {}), "unique_pages": rec.get("search", {}).get("lens_results"),
                   "total": rec.get("search", {}).get("candidates_total"), "candidates": []},
        "scan": {"threshold": rec.get("search", {}).get("threshold"), "checked": len(cands),
                 "passed": sum(1 for c in cands if c.get("similarity", -1) >= rec.get("search", {}).get("threshold", 1)),
                 "results": cands[:25]},
        "match": match, "receipt": receipt, "restored": True,
    }
    if match:
        result["hashes"] = {"record": ev.record_hash(rec), "image": match.get("image_sha256"),
                            "face": rec.get("query", {}).get("embedding_sha256"), "record_file": "record.json",
                            "image_file": match.get("image_file")}
    return {"id": run_id, "status": result["status"], "restored": True, "created_at": rec.get("created_at"),
            "steps": {}, "log": [], "result": result, "error": None}


@app.get("/api/runs/{run_id}/files/{name}")
def get_file(run_id: str, name: str):
    d = _evidence_dir(run_id)
    if not (name in ALLOWED_FILES or name.startswith("match_image.")):
        raise HTTPException(404, "no such file")
    p = d / name
    if not p.exists():
        raise HTTPException(404, "no such file")
    return FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/runs/{run_id}/verify")
def verify_run(run_id: str, chain: Optional[str] = None):
    d = _evidence_dir(run_id)
    if not (d / "record.json").exists():
        raise HTTPException(404, "unknown run")
    return verify_bundle(d, chain)


@app.post("/api/runs/{run_id}/tamper")
def tamper_run(run_id: str):
    d = _evidence_dir(run_id)
    if not (d / "record.json").exists():
        raise HTTPException(404, "unknown run")
    info = tamper_copy(d)
    v = verify_bundle(info["dir"])
    shutil.rmtree(info["dir"], ignore_errors=True)
    return {"tamper": info, "verify": v}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    d = _evidence_dir(run_id)
    with _jobs_lock:
        job = _jobs.get(run_id)
        if job and job["status"] in ("queued", "running"):
            raise HTTPException(409, "run is still in progress")
        _jobs.pop(run_id, None)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return {"deleted": run_id}


# ----------------------------------------------------------- production static files
DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = DIST / path
        if path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def index():
        return JSONResponse({"facechain": __version__, "hint": "run `npm run dev` for the web UI, or see /docs"})
