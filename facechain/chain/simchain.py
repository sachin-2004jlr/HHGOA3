"""Minimal pure-Python blockchain (fallback when no EVM node is available).

Each block = {index, timestamp, prev_hash, nonce, records[], hash} where
hash = sha256(canonical_json(block without hash)). Blocks are mined with a
small proof-of-work and persisted to simchain.json. validate() re-hashes
every block and checks the prev_hash links, so any edit to a stored record
breaks the chain.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import config
from ..evidence import canonical_json, sha256_hex

DIFFICULTY = 4  # leading hex zeros


class SimChain:
    name = "sim"

    def __init__(self, path: Path | None = None):
        self.path = path or config.SIMCHAIN_FILE
        self.blocks: list[dict] = []
        if self.path.exists():
            self.blocks = json.loads(self.path.read_text(encoding="utf-8"))
        if not self.blocks:
            self.blocks = [self._mine({"index": 0, "timestamp": int(time.time()), "prev_hash": "0" * 64,
                                       "records": [{"genesis": "facechain simchain"}]})]
            self._save()

    # ------------------------------------------------------------ internals
    @staticmethod
    def _hash(block: dict) -> str:
        body = {k: v for k, v in block.items() if k != "hash"}
        return sha256_hex(canonical_json(body))

    def _mine(self, block: dict) -> dict:
        block["nonce"] = 0
        while True:
            h = self._hash(block)
            if h.startswith("0" * DIFFICULTY):
                block["hash"] = h
                return block
            block["nonce"] += 1

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.blocks, indent=2), encoding="utf-8")

    # ------------------------------------------------------------ interface
    def anchor(self, *, record_hash: str, image_hash: str, face_hash: str, post_url: str,
               platform: str, similarity: float) -> dict:
        if self.get_record(record_hash):
            raise RuntimeError("already anchored")
        rec = {"record_hash": record_hash, "image_hash": image_hash, "face_hash": face_hash,
               "post_url": post_url, "platform": platform, "similarity": round(similarity, 4)}
        prev = self.blocks[-1]
        block = self._mine({"index": prev["index"] + 1, "timestamp": int(time.time()),
                            "prev_hash": prev["hash"], "records": [rec]})
        self.blocks.append(block)
        self._save()
        return {"backend": "sim", "chain": "simchain (local file)", "file": str(self.path),
                "block_number": block["index"], "block_hash": block["hash"], "prev_hash": block["prev_hash"],
                "nonce": block["nonce"], "block_timestamp": block["timestamp"], "record_hash": record_hash}

    def get_record(self, record_hash: str) -> dict | None:
        rh = record_hash.removeprefix("0x")
        for b in self.blocks:
            for r in b["records"]:
                if r.get("record_hash", "").removeprefix("0x") == rh:
                    return {**r, "timestamp": b["timestamp"], "block_number": b["index"], "block_hash": b["hash"]}
        return None

    def validate(self) -> tuple[bool, str]:
        for i, b in enumerate(self.blocks):
            if self._hash(b) != b["hash"]:
                return False, f"block {i} hash mismatch (contents were modified)"
            if not b["hash"].startswith("0" * DIFFICULTY):
                return False, f"block {i} does not satisfy proof-of-work"
            if i > 0 and b["prev_hash"] != self.blocks[i - 1]["hash"]:
                return False, f"block {i} prev_hash does not link to block {i - 1}"
        return True, f"{len(self.blocks)} blocks valid"

    def info(self) -> dict:
        ok, msg = self.validate()
        return {"backend": "sim", "file": str(self.path), "blocks": len(self.blocks),
                "records_anchored": sum(len(b["records"]) for b in self.blocks[1:]),
                "chain_valid": ok, "validation": msg, "difficulty": DIFFICULTY}
