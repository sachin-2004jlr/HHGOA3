"""Blockchain backends: evm (any EVM JSON-RPC: Anvil, Sepolia, ...) and sim (pure Python)."""
from __future__ import annotations

from typing import Protocol


class ChainBackend(Protocol):
    name: str

    def anchor(self, *, record_hash: str, image_hash: str, face_hash: str, post_url: str,
               platform: str, similarity: float) -> dict: ...

    def get_record(self, record_hash: str) -> dict | None: ...

    def info(self) -> dict: ...


def get_backend(kind: str | None = None):
    from .. import config

    kind = (kind or config.CHAIN_BACKEND).lower()
    if kind == "auto":
        try:
            from .evm import EvmChain

            return EvmChain()
        except Exception:  # noqa: BLE001  (no node reachable -> simulated chain)
            from .simchain import SimChain

            return SimChain()
    if kind == "sim":
        from .simchain import SimChain

        return SimChain()
    if kind == "evm":
        from .evm import EvmChain

        return EvmChain()
    raise ValueError(f"unknown chain backend: {kind} (use evm|sim)")
