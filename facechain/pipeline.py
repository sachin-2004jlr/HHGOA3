"""The end-to-end pipeline as a reusable function with structured progress events.

Used by both the CLI (rich console renderer) and the web API (job status JSON).

    result = run_pipeline(image_bytes=..., options=Options(), emit=callback)

`emit(step, status, title, data=None, message=None)` is called for every step
transition:  status in {"start", "done", "error"}.  Steps:

    1 face      detect + embed the input face
    2 search    reverse image search (+ optional keyword expansion)
    3 match     download every candidate, compare faces, pick the match
    4 record    evidence bundle + SHA-256 fingerprints
    5 anchor    write the fingerprints to the blockchain
    6 verify    read the record back and compare
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import config
from . import evidence as ev

Emit = Callable[..., None]


class PipelineError(RuntimeError):
    def __init__(self, step: int, message: str, code: str = "error"):
        super().__init__(message)
        self.step, self.code = step, code


class NoMatchError(PipelineError):
    def __init__(self, message: str, best: Optional[dict] = None):
        super().__init__(3, message, "no_match")
        self.best = best


@dataclass
class Options:
    min_similarity: float = config.FACE_MATCH_THRESHOLD
    max_candidates: int = config.MAX_CANDIDATES
    expand: bool = True
    chain: str = "auto"            # auto | evm | sim
    face_index: int = 0
    image_url: Optional[str] = None  # already-public URL of the face (skips upload)
    skip_chain: bool = False
    top_n: int = 25                # how many candidates to include in the result


STEP_TITLES = {
    1: "Face scan: detect and encode the face",
    2: "Reverse image search on the web and social media",
    3: "Face verification of every candidate",
    4: "Evidence record and SHA-256 fingerprints",
    5: "Anchor on the blockchain",
    6: "Read back from the chain and verify",
}


def _noop(*_a, **_k) -> None:
    pass


def run_pipeline(*, image_path: Optional[Path] = None, image_bytes: Optional[bytes] = None,
                 options: Options = Options(), emit: Emit = _noop, run_id: Optional[str] = None,
                 engine=None, source_label: str = "") -> dict:
    from .face import FaceEngine, crop_face, draw_faces, encode_jpeg
    from .search import (choose_match, expand_with_ddg, fetch_post_metadata, is_social,
                         reverse_image_search, verify_candidates)
    from .uploader import publish_image

    t_start = time.time()
    result: dict = {"run_id": None, "status": "running", "source": source_label}

    def start(step: int, **data):
        emit(step, "start", STEP_TITLES[step], data=data or None)

    def done(step: int, data: dict | None = None, message: str | None = None):
        emit(step, "done", STEP_TITLES[step], data=data, message=message)

    # ------------------------------------------------------------------ 1. face
    start(1)
    engine = engine or FaceEngine()
    if image_path is not None:
        img = engine.load_image(image_path)
    else:
        img = engine.decode_bytes(image_bytes or b"")
        if img is None:
            raise PipelineError(1, "Could not decode the uploaded image (use JPEG, PNG or WebP).", "bad_image")
    img, faces = engine.analyze(img)
    if not faces:
        raise PipelineError(1, "No face detected in the image. Use a clear, front-facing photo.", "no_face")
    idx = min(max(options.face_index, 0), len(faces) - 1)
    face = faces[idx]

    bundle = ev.EvidenceBundle(run_id=run_id)
    result["run_id"] = bundle.run_id
    result["evidence_dir"] = str(bundle.dir)
    aligned_jpg = encode_jpeg(face.aligned, 95)
    query_info = bundle.save_query(image_path, image_bytes, aligned_jpg, face.embedding)
    query_info.update({
        "face_bbox": list(face.bbox), "detector_score": round(face.score, 4), "faces_in_image": len(faces),
        "face_index": idx, "image_size": [int(img.shape[1]), int(img.shape[0])],
        "model": {"detector": "YuNet 2023mar (OpenCV zoo)", "recognizer": "SFace 2021dec (OpenCV zoo)"},
    })
    (bundle.dir / "query_annotated.jpg").write_bytes(encode_jpeg(draw_faces(img, faces)))
    crop_path = bundle.dir / "query_crop.jpg"
    crop_path.write_bytes(encode_jpeg(crop_face(img, face), 92))
    result["query"] = {**query_info, "files": {"original": "query.jpg", "annotated": "query_annotated.jpg",
                                               "crop": "query_crop.jpg", "face": "query_face.jpg"}}
    done(1, result["query"], f"{len(faces)} face(s) detected, using #{idx}")

    # ---------------------------------------------------------------- 2. search
    start(2)
    if options.image_url:
        public_url, host = options.image_url, "user-supplied"
    else:
        emit(2, "progress", STEP_TITLES[2], message="uploading face crop to a temporary public host")
        public_url, host = publish_image(crop_path, log=lambda m: emit(2, "progress", STEP_TITLES[2], message=m))
    emit(2, "progress", STEP_TITLES[2], message=f"querying Google Lens with {public_url}")
    sr = reverse_image_search(public_url)
    candidates = list(sr.candidates)
    expanded = 0
    if sr.entity_name and options.expand:
        emit(2, "progress", STEP_TITLES[2],
             message=f"Lens recognised '{sr.entity_name}' - widening with keyword image search on social platforms")
        extra = expand_with_ddg(sr.entity_name, log=lambda m: emit(2, "progress", STEP_TITLES[2], message=m))
        seen = {c.url.rstrip("/") for c in candidates}
        extra = [c for c in extra if c.url.rstrip("/") not in seen]
        candidates += extra
        expanded = len(extra)
    if not candidates:
        raise PipelineError(2, "The reverse image search returned no candidates for this face.", "no_candidates")
    social_n = sum(1 for c in candidates if is_social(c.platform))
    result["search"] = {
        "engine": sr.engine, "query_image_url": public_url, "query_image_host": host,
        "entity_name": sr.entity_name, "raw_count": sr.raw_count, "unique_pages": len(sr.candidates),
        "expanded": expanded, "total": len(candidates), "social": social_n,
        "candidates": [{"url": c.url, "title": c.title, "source": c.source, "platform": c.platform,
                        "engine": c.engine, "thumbnail_url": c.thumbnail_url, "image_url": c.image_url}
                       for c in candidates[: options.top_n]],
    }
    done(2, result["search"], f"{len(candidates)} candidate pages ({social_n} on social platforms)")

    # ------------------------------------------------------------- 3. verify faces
    start(3, total=min(len(candidates), options.max_candidates))
    cands = candidates[: options.max_candidates]
    counter = {"n": 0}

    def progress(_v):
        counter["n"] += 1
        emit(3, "progress", STEP_TITLES[3], data={"done": counter["n"], "total": len(cands)})

    verified = verify_candidates(engine, face.embedding, cands, max_n=len(cands), progress=progress)
    bundle.save_json("candidates.json", [v.to_public_dict() for v in verified])
    thr = options.min_similarity
    scan = {"threshold": thr, "checked": len(verified),
            "passed": sum(1 for v in verified if v.similarity >= thr),
            "results": [v.to_public_dict() for v in verified[: options.top_n]]}
    result["scan"] = scan
    match = choose_match(verified, thr)
    if match is None:
        best = verified[0].to_public_dict() if verified else None
        bundle.save_json("record.json", {"status": "no_match", "search": {"engine": sr.engine}, "best": best})
        result["status"] = "no_match"
        emit(3, "error", STEP_TITLES[3], data=scan,
             message=f"No candidate reached the face-match threshold {thr}"
                     + (f" (best {best['similarity']:.3f})" if best else ""))
        raise NoMatchError(f"No candidate reached the face-match threshold ({thr}).", best)

    meta = fetch_post_metadata(match.candidate.url)
    img_name, img_sha = bundle.save_match_image(match.image_bytes)
    result["match"] = {
        "post_url": match.candidate.url, "platform": match.candidate.platform, "title": match.candidate.title,
        "source": match.candidate.source, "image_url": match.fetched_url, "image_file": img_name,
        "image_sha256": img_sha, "similarity": round(match.similarity, 4), "faces_in_image": match.faces_found,
        "face_bbox": list(match.face_bbox) if match.face_bbox else None,
        "og": {k: v for k, v in meta.items() if k.startswith("og_") and v},
    }
    done(3, {**scan, "match": result["match"]},
         f"match: {match.candidate.platform} post at similarity {match.similarity:.3f}")

    # ------------------------------------------------------------ 4. record + hash
    start(4)
    record = ev.build_record(
        run_id=bundle.run_id, query=query_info, match=result["match"],
        search={"engine": sr.engine, "query_image_url": public_url, "query_image_host": host,
                "entity_name": sr.entity_name, "candidates_total": len(candidates),
                "candidates_verified": len(verified), "threshold": thr},
    )
    record_hash = bundle.write_record(record)
    result["hashes"] = {"record": record_hash, "image": img_sha, "face": query_info["embedding_sha256"],
                        "record_file": "record.json", "image_file": img_name}
    done(4, result["hashes"], "record.json written and fingerprinted")

    if options.skip_chain:
        result["status"] = "done"
        result["elapsed"] = round(time.time() - t_start, 1)
        return result

    # ------------------------------------------------------------------ 5. anchor
    start(5)
    from .chain import get_backend

    backend = get_backend(options.chain)
    emit(5, "progress", STEP_TITLES[5], message=f"sending transaction on {getattr(backend, 'chain_name', backend.name)}")
    receipt = backend.anchor(record_hash=record_hash, image_hash=img_sha, face_hash=query_info["embedding_sha256"],
                             post_url=match.candidate.url, platform=match.candidate.platform,
                             similarity=match.similarity)
    receipt["anchored_at"] = ev.now_iso()
    bundle.save_json("chain_receipt.json", receipt)
    result["receipt"] = receipt
    done(5, receipt, f"anchored in block {receipt.get('block_number')} on {receipt.get('chain')}")

    # ------------------------------------------------------------------ 6. verify
    start(6)
    from .verify import verify_bundle

    vres = verify_bundle(bundle.dir, receipt.get("backend"))
    result["verify"] = vres
    result["status"] = "done" if vres["all_ok"] else "verify_failed"
    result["elapsed"] = round(time.time() - t_start, 1)
    emit(6, "done" if vres["all_ok"] else "error", STEP_TITLES[6], data=vres, message=vres["message"])
    return result
