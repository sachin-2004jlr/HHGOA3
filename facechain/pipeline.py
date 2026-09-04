"""The end-to-end pipeline as a reusable function with structured progress events.

Used by both the CLI (rich console renderer) and the web API (job status JSON).

    result = run_pipeline(image_bytes=..., options=Options(), emit=callback)

`emit(step, status, title, data=None, message=None)` is called for every step
transition:  status in {"start", "progress", "done", "error"}.  Steps:

    1 face      detect + embed the input face
    2 search    reverse image search with a tight face crop AND the whole photo
    3 match     face-verify every candidate; take the person's name only from
                pages whose face matched, widen the search with it, verify again
    4 record    evidence bundle + SHA-256 fingerprints
    5 anchor    write the fingerprints to the blockchain
    6 verify    read the record back and compare
"""
from __future__ import annotations

import time
from dataclasses import dataclass
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


def _cand_dict(c) -> dict:
    return {"url": c.url, "title": c.title, "source": c.source, "platform": c.platform,
            "engine": c.engine, "thumbnail_url": c.thumbnail_url, "image_url": c.image_url}


def run_pipeline(*, image_path: Optional[Path] = None, image_bytes: Optional[bytes] = None,
                 options: Options = Options(), emit: Emit = _noop, run_id: Optional[str] = None,
                 engine=None, source_label: str = "") -> dict:
    from .face import FaceEngine, crop_face, draw_faces, encode_jpeg, search_image
    from .search import (choose_match, entity_from_verified, fetch_post_metadata, is_social,
                         reverse_image_search_many, verify_candidates)
    from .uploader import publish_image

    t_start = time.time()
    result: dict = {"run_id": None, "status": "running", "source": source_label}

    def start(step: int, **data):
        emit(step, "start", STEP_TITLES[step], data=data or None)

    def done(step: int, data: dict | None = None, message: str | None = None):
        emit(step, "done", STEP_TITLES[step], data=data, message=message)

    def note(step: int, message: str):
        emit(step, "progress", STEP_TITLES[step], message=message)

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
    full_path = bundle.dir / "query_search.jpg"
    full_path.write_bytes(encode_jpeg(search_image(img), 88))
    result["query"] = {**query_info, "files": {"original": "query.jpg", "annotated": "query_annotated.jpg",
                                               "crop": "query_crop.jpg", "face": "query_face.jpg"}}
    done(1, result["query"], f"{len(faces)} face(s) detected, using #{idx}")

    # ---------------------------------------------------------------- 2. search
    start(2)
    if options.image_url:
        urls, host = [options.image_url], "user-supplied"
    else:
        note(2, "uploading the face crop and the photo to a temporary public host")
        crop_url, host = publish_image(crop_path, log=lambda m: note(2, m))
        urls = [crop_url]
        try:
            full_url, _ = publish_image(full_path, log=lambda m: note(2, m))
            urls.append(full_url)
        except Exception as e:  # noqa: BLE001  (the crop alone still works)
            note(2, f"full-photo upload skipped: {e}")
    note(2, f"querying Google Lens with {len(urls)} view(s) of the face")
    sr = reverse_image_search_many(urls)
    candidates = list(sr.candidates)
    if not candidates:
        raise PipelineError(2, "The reverse image search returned no candidates for this face.", "no_candidates")
    social_n = sum(1 for c in candidates if is_social(c.platform))
    result["search"] = {
        "engine": sr.engine, "query_image_url": urls[0], "query_image_urls": urls, "query_image_host": host,
        "entity_name": sr.entity_name, "entity_source": "lens" if sr.entity_name else None,
        "raw_count": sr.raw_count, "unique_pages": len(candidates), "expanded": 0,
        "total": len(candidates), "social": social_n,
        "candidates": [_cand_dict(c) for c in candidates[: options.top_n]],
    }
    done(2, result["search"], f"{len(candidates)} candidate pages ({social_n} on social platforms)")

    # ------------------------------------------------------------- 3. verify faces
    thr = options.min_similarity
    cands = candidates[: options.max_candidates]
    start(3, total=len(cands))
    counter = {"n": 0, "total": len(cands)}

    def progress(_v):
        counter["n"] += 1
        emit(3, "progress", STEP_TITLES[3], data={"done": counter["n"], "total": counter["total"]})

    verified = verify_candidates(engine, face.embedding, cands, max_n=len(cands), progress=progress)
    passed = sum(1 for v in verified if v.similarity >= thr)
    note(3, f"{passed} of {len(verified)} candidate faces match the scan")

    # the person's name comes from pages whose face matched; Lens' own guess is only a fallback
    entity = entity_from_verified(verified, thr)
    entity_source = "verified_titles" if entity else ("lens" if sr.entity_name else None)
    entity = entity or sr.entity_name
    expanded = 0
    expanded_by: dict = {}
    if entity and options.expand:
        from .social import expand_social, sources

        note(3, f"harvesting pictures of '{entity}' from " + ", ".join(label for label, _ in sources()))
        extra, expanded_by = expand_social(entity, log=lambda m: note(3, m))
        seen = {c.url.rstrip("/") for c in candidates}
        extra = [c for c in extra if c.url.rstrip("/") not in seen][: options.max_candidates * 2]
        if extra:
            counter["total"] += len(extra)
            verified += verify_candidates(engine, face.embedding, extra, max_n=len(extra), progress=progress)
            verified.sort(key=lambda v: v.similarity, reverse=True)
            candidates += extra
            expanded = len(extra)
    social_n = sum(1 for c in candidates if is_social(c.platform))
    result["search"].update({"entity_name": entity, "entity_source": entity_source, "expanded": expanded,
                             "expanded_by": expanded_by, "total": len(candidates), "social": social_n})

    bundle.save_json("candidates.json", [v.to_public_dict() for v in verified])
    scan = {"threshold": thr, "checked": len(verified),
            "passed": sum(1 for v in verified if v.similarity >= thr),
            "results": [v.to_public_dict() for v in verified[: options.top_n]]}
    result["scan"] = scan
    match = choose_match(verified, thr)
    if match is None:
        best = verified[0].to_public_dict() if verified else None
        bundle.save_json("record.json", {"status": "no_match", "search": {"engine": sr.engine, "entity_name": entity},
                                         "best": best})
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
    done(3, {**scan, "match": result["match"], "search": result["search"]},
         f"match: {match.candidate.platform} post at similarity {match.similarity:.3f}")

    # ------------------------------------------------------------ 4. record + hash
    start(4)
    record = ev.build_record(
        run_id=bundle.run_id, query=query_info, match=result["match"],
        search={"engine": sr.engine, "query_image_urls": urls, "query_image_host": host,
                "entity_name": entity, "entity_source": entity_source, "candidates_total": len(candidates),
                "lens_results": len(sr.candidates), "expanded": expanded, "expanded_by": expanded_by,
                "social": social_n,
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
    note(5, f"sending transaction on {getattr(backend, 'chain_name', backend.name)}")
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
