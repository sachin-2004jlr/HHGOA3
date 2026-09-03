"""Re-verification of an evidence bundle against the chain (structured result)."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Optional

from . import config
from . import evidence as ev


def _x(h: str) -> str:
    return h if h.startswith("0x") else "0x" + h


def verify_bundle(path: Path | str, chain_kind: Optional[str] = None) -> dict:
    """Recompute every hash from the files on disk and compare with the on-chain record."""
    path = Path(path)
    b = ev.LoadedBundle(path)
    rec, receipt = b.record, b.receipt or {}
    recomputed = b.recomputed()
    m, q = rec.get("match", {}), rec.get("query", {})
    checks: list[dict] = []

    def check(name: str, local: str, remote: str, ok: bool, kind: str = "local"):
        checks.append({"name": name, "local": local, "remote": remote, "ok": bool(ok), "kind": kind})

    # local consistency: files on disk vs what record.json claims
    if "image_sha256" in recomputed:
        check("post image file vs record.json", recomputed["image_sha256"], m.get("image_sha256", ""),
              recomputed["image_sha256"] == m.get("image_sha256"))
    if "embedding_sha256" in recomputed:
        check("face embedding file vs record.json", recomputed["embedding_sha256"], q.get("embedding_sha256", ""),
              recomputed["embedding_sha256"] == q.get("embedding_sha256"))
    if "query_image_sha256" in recomputed:
        check("scanned image file vs record.json", recomputed["query_image_sha256"], q.get("image_sha256", ""),
              recomputed["query_image_sha256"] == q.get("image_sha256"))

    out: dict = {
        "evidence": str(path), "run_id": rec.get("run_id"), "record_hash": _x(recomputed["record_sha256"]),
        "recomputed": recomputed, "checks": checks, "found": False, "onchain": None, "chain": None,
        "chain_integrity": None, "all_ok": False, "message": "", "verified_at": ev.now_iso(),
    }

    kind = chain_kind or receipt.get("backend") or config.CHAIN_BACKEND
    try:
        if kind == "evm":
            from .chain.evm import EvmChain

            backend = EvmChain(contract_address=receipt.get("contract") or None)
            out["chain"] = {"backend": "evm", "name": backend.chain_name, "chain_id": backend.chain_id,
                            "contract": backend.address, "rpc_url": backend.rpc_url,
                            "explorer_contract": backend.explorer_address(backend.address) if backend.address else None}
            if receipt.get("chain_id") and receipt["chain_id"] != backend.chain_id:
                out["warning"] = (f"receipt is from chain {receipt['chain_id']} but RPC_URL points to "
                                  f"chain {backend.chain_id}")
        else:
            from .chain import get_backend

            backend = get_backend(kind)
            out["chain"] = {"backend": backend.name, "name": "simchain (local file)",
                            "file": str(getattr(backend, "path", ""))}
    except Exception as e:  # noqa: BLE001
        out["message"] = f"chain unreachable: {e}"
        return out

    rh = recomputed["record_sha256"]
    onchain = backend.get_record(rh)
    out["found"] = onchain is not None
    if onchain:
        out["onchain"] = onchain
        check("record hash", _x(rh), _x(onchain["record_hash"]),
              onchain["record_hash"].removeprefix("0x") == rh, "chain")
        if "image_sha256" in recomputed:
            check("post image hash (recomputed from file)", _x(recomputed["image_sha256"]), _x(onchain["image_hash"]),
                  onchain["image_hash"].removeprefix("0x") == recomputed["image_sha256"], "chain")
        if "embedding_sha256" in recomputed:
            check("face embedding hash (recomputed)", _x(recomputed["embedding_sha256"]), _x(onchain["face_hash"]),
                  onchain["face_hash"].removeprefix("0x") == recomputed["embedding_sha256"], "chain")
        check("post url", m.get("post_url", ""), onchain["post_url"], m.get("post_url") == onchain["post_url"], "chain")
        check("platform", m.get("platform", ""), onchain["platform"], m.get("platform") == onchain["platform"], "chain")
        check("similarity", f"{float(m.get('similarity', 0)):.4f}", f"{onchain['similarity']:.4f}",
              abs(float(m.get("similarity", 0)) - onchain["similarity"]) < 0.0001, "chain")
        out["anchored_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(onchain["timestamp"]))

    if hasattr(backend, "validate"):
        ok_chain, msg = backend.validate()
        out["chain_integrity"] = {"ok": ok_chain, "message": msg}
    else:
        ok_chain = True

    out["all_ok"] = out["found"] and ok_chain and all(c["ok"] for c in checks)
    if out["all_ok"]:
        out["message"] = "VERIFIED: the evidence is byte-for-byte identical to what was anchored on chain."
    elif not out["found"]:
        out["message"] = "NOT FOUND: no on-chain record matches this evidence (modified, or never anchored)."
    else:
        out["message"] = "MISMATCH: the on-chain record differs from the evidence on disk."
    return out


def tamper_copy(path: Path | str) -> dict:
    """Copy an evidence bundle and change one field of record.json (for the tamper demo)."""
    src = Path(path)
    dst = src.with_name(src.name + "-tampered")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    rec_path = dst / "record.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    before = rec.get("match", {}).get("post_url", "")
    after = before.rstrip("/") + "/?edited=1"
    rec.setdefault("match", {})["post_url"] = after
    rec_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"dir": str(dst), "field": "match.post_url", "before": before, "after": after}
