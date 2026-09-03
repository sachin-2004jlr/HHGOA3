"""Evidence bundle: what gets hashed, how, and how it is stored on disk.

A run produces evidence/<run_id>/ with
    query.jpg            original input image (copy)
    query_face.jpg       aligned 112x112 crop used for the embedding
    query_embedding.json 128-d SFace vector
    match_image.<ext>    the image downloaded from the matched post
    candidates.json      every candidate considered + its similarity (transparency)
    record.json          the canonical record whose SHA-256 goes on-chain
    chain_receipt.json   tx hash / block / contract (written after anchoring)

record_hash = sha256(canonical_json(record))     -> anchored on chain
image_hash  = sha256(match_image bytes)          -> anchored on chain
face_hash   = sha256(canonical_json(embedding))  -> anchored on chain
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from . import config

RECORD_VERSION = "facechain/1"


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON encoding: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def embedding_hash(vec: np.ndarray) -> str:
    rounded = [round(float(x), 6) for x in np.asarray(vec).reshape(-1)]
    return sha256_hex(canonical_json(rounded))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ext_for(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "bin"


class EvidenceBundle:
    def __init__(self, run_id: str | None = None, base: Path | None = None):
        self.run_id = run_id or new_run_id()
        self.dir = (base or config.EVIDENCE_DIR) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- writing
    def save_query(self, src_path: Path | None, image_bytes: bytes | None, aligned_jpg: bytes,
                   embedding: np.ndarray) -> dict:
        if src_path is not None:
            shutil.copyfile(src_path, self.dir / "query.jpg")
            qbytes = (self.dir / "query.jpg").read_bytes()
        else:
            qbytes = image_bytes or b""
            (self.dir / "query.jpg").write_bytes(qbytes)
        (self.dir / "query_face.jpg").write_bytes(aligned_jpg)
        emb = [round(float(x), 6) for x in embedding.reshape(-1)]
        (self.dir / "query_embedding.json").write_text(json.dumps(emb), encoding="utf-8")
        return {"image_sha256": sha256_hex(qbytes), "face_crop_sha256": sha256_hex(aligned_jpg),
                "embedding_sha256": embedding_hash(embedding), "embedding_dim": len(emb)}

    def save_match_image(self, data: bytes) -> tuple[str, str]:
        ext = _ext_for(data)
        name = f"match_image.{ext}"
        (self.dir / name).write_bytes(data)
        return name, sha256_hex(data)

    def save_json(self, name: str, obj: Any) -> None:
        (self.dir / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_record(self, record: dict) -> str:
        """Persist the canonical record and return its SHA-256 (hex, no 0x)."""
        self.save_json("record.json", record)
        return record_hash(record)

    # ------------------------------------------------------------- reading
    @staticmethod
    def load(path: Path) -> "LoadedBundle":
        return LoadedBundle(Path(path))


def record_hash(record: dict) -> str:
    return sha256_hex(canonical_json(record))


def build_record(*, query: dict, match: dict, search: dict, run_id: str) -> dict:
    """The canonical record. Field order does not matter (sorted at hashing)."""
    return {
        "version": RECORD_VERSION,
        "run_id": run_id,
        "created_at": now_iso(),
        "query": query,        # image_sha256, face_crop_sha256, embedding_sha256, embedding_dim, face_bbox
        "match": match,        # post_url, platform, title, source, image_url, image_sha256, similarity, ...
        "search": search,      # engine, query_image_url, entity_name, candidates_total, candidates_verified
    }


class LoadedBundle:
    """Read an evidence folder back and recompute every hash from the raw files."""

    def __init__(self, path: Path):
        self.dir = path
        if not (path / "record.json").exists():
            raise FileNotFoundError(f"{path} has no record.json")
        self.record: dict = json.loads((path / "record.json").read_text(encoding="utf-8"))
        rc = path / "chain_receipt.json"
        self.receipt: dict | None = json.loads(rc.read_text(encoding="utf-8")) if rc.exists() else None

    @property
    def record_hash(self) -> str:
        return record_hash(self.record)

    def recomputed(self) -> dict:
        """Hashes recomputed from the files on disk (not from record.json)."""
        out: dict = {"record_sha256": self.record_hash}
        img_name = self.record.get("match", {}).get("image_file")
        if img_name and (self.dir / img_name).exists():
            out["image_sha256"] = sha256_hex((self.dir / img_name).read_bytes())
        emb = self.dir / "query_embedding.json"
        if emb.exists():
            vec = np.array(json.loads(emb.read_text(encoding="utf-8")), dtype=np.float64)
            out["embedding_sha256"] = embedding_hash(vec)
        q = self.dir / "query.jpg"
        if q.exists():
            out["query_image_sha256"] = sha256_hex(q.read_bytes())
        return out
