"""EVM backend: deploy / anchor / read the FaceMatchRegistry contract via web3.py.

Works with any EVM JSON-RPC endpoint:
  * Anvil (Foundry) local dev chain   -> chain id 31337, default RPC http://127.0.0.1:8545
  * Ethereum Sepolia testnet           -> chain id 11155111 (set RPC_URL + funded PRIVATE_KEY)
  * Polygon Amoy, Base Sepolia, ...    -> anything web3 can talk to
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError

from .. import config

EXPLORERS = {
    1: "https://etherscan.io",
    11155111: "https://sepolia.etherscan.io",
    17000: "https://holesky.etherscan.io",
    560048: "https://hoodi.etherscan.io",
    137: "https://polygonscan.com",
    80002: "https://amoy.polygonscan.com",
    8453: "https://basescan.org",
    84532: "https://sepolia.basescan.org",
    42161: "https://arbiscan.io",
    421614: "https://sepolia.arbiscan.io",
    10: "https://optimistic.etherscan.io",
    11155420: "https://sepolia-optimism.etherscan.io",
}
CHAIN_NAMES = {
    1: "Ethereum Mainnet", 11155111: "Ethereum Sepolia", 17000: "Ethereum Holesky",
    560048: "Ethereum Hoodi", 137: "Polygon", 80002: "Polygon Amoy", 8453: "Base",
    84532: "Base Sepolia", 42161: "Arbitrum One", 421614: "Arbitrum Sepolia",
    10: "OP Mainnet", 11155420: "OP Sepolia", 31337: "Anvil (local)", 1337: "Local dev chain",
}


def _b32(hex_str: str) -> bytes:
    h = hex_str[2:] if hex_str.startswith("0x") else hex_str
    b = bytes.fromhex(h)
    if len(b) != 32:
        raise ValueError("expected 32-byte hash")
    return b


def _hex(v) -> str:
    if isinstance(v, (bytes, bytearray)):
        return "0x" + bytes(v).hex()
    s = str(v)
    return s if s.startswith("0x") else "0x" + s


class EvmChain:
    name = "evm"

    def __init__(self, rpc_url: str | None = None, private_key: str | None = None,
                 contract_address: str | None = None, artifact: Path | None = None):
        self.rpc_url = rpc_url or config.RPC_URL
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 60}))
        if not self.w3.is_connected():
            raise ConnectionError(
                f"Cannot reach RPC at {self.rpc_url}. Start Anvil (scripts/start_anvil) or set RPC_URL."
            )
        self.chain_id = self.w3.eth.chain_id
        self.account = Account.from_key(private_key or config.PRIVATE_KEY)
        if self.is_local:
            self._ensure_local_funds()
        art = json.loads((artifact or config.CONTRACT_ARTIFACT).read_text(encoding="utf-8"))
        self.abi, self.bytecode = art["abi"], art["bytecode"]
        self.address = contract_address or config.CONTRACT_ADDRESS or self._saved_address()
        self.contract = (
            self.w3.eth.contract(address=Web3.to_checksum_address(self.address), abi=self.abi)
            if self.address else None
        )

    # ------------------------------------------------------------ helpers
    @property
    def chain_name(self) -> str:
        return CHAIN_NAMES.get(self.chain_id, f"chain {self.chain_id}")

    @property
    def is_local(self) -> bool:
        return self.chain_id in (31337, 1337) or "127.0.0.1" in self.rpc_url or "localhost" in self.rpc_url

    def _ensure_local_funds(self) -> None:
        """On a local dev chain (Anvil/Hardhat) make sure the signer can pay gas.

        The signer may be a freshly generated testnet wallet with no balance here; dev
        chains expose a cheat-code RPC to set balances, and if that is unavailable we
        fall back to Anvil's well-known pre-funded account #0.
        """
        if self.w3.eth.get_balance(self.account.address) > Web3.to_wei(0.01, "ether"):
            return
        amount = hex(Web3.to_wei(100, "ether"))
        for method in ("anvil_setBalance", "hardhat_setBalance"):
            try:
                self.w3.provider.make_request(method, [self.account.address, amount])
                if self.w3.eth.get_balance(self.account.address) > 0:
                    return
            except Exception:  # noqa: BLE001
                continue
        self.account = Account.from_key(config.ANVIL_DEV_KEY)

    def explorer_tx(self, tx_hash: str) -> str | None:
        base = EXPLORERS.get(self.chain_id)
        return f"{base}/tx/{tx_hash}" if base else None

    def explorer_address(self, addr: str) -> str | None:
        base = EXPLORERS.get(self.chain_id)
        return f"{base}/address/{addr}" if base else None

    def _deployments(self) -> dict:
        p = config.DEPLOYMENTS_FILE
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _saved_address(self) -> str | None:
        return (self._deployments().get(str(self.chain_id)) or {}).get("address")

    def contract_deployed(self) -> bool:
        if not self.address:
            return False
        code = self.w3.eth.get_code(Web3.to_checksum_address(self.address))
        return len(code) > 2

    def _send(self, fn_tx) -> dict:
        tx = fn_tx.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "chainId": self.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        if receipt.get("status") != 1:
            raise RuntimeError(f"transaction reverted: {_hex(tx_hash)}")
        return receipt

    # ------------------------------------------------------------ actions
    def deploy(self) -> dict:
        factory = self.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        receipt = self._send(factory.constructor())
        self.address = receipt["contractAddress"]
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        deps = self._deployments()
        deps[str(self.chain_id)] = {
            "chain": self.chain_name, "address": self.address,
            "txHash": _hex(receipt["transactionHash"]),
            "block": int(receipt["blockNumber"]), "deployer": self.account.address, "rpc": self.rpc_url,
            "deployedAt": int(time.time()),
            "explorer": self.explorer_address(self.address),
        }
        config.DEPLOYMENTS_FILE.write_text(json.dumps(deps, indent=2), encoding="utf-8")
        return deps[str(self.chain_id)]

    def ensure_deployed(self, log=print) -> str:
        if self.contract_deployed():
            return self.address
        if not self.is_local:
            where = f"at {self.address}" if self.address else "recorded"
            raise RuntimeError(
                f"No FaceMatchRegistry {where} on {self.chain_name}. Run `python -m facechain deploy` first."
            )
        log(f"[chain] no registry on {self.chain_name} yet - deploying ...")
        info = self.deploy()
        log(f"[chain] deployed FaceMatchRegistry at {info['address']} (block {info['block']})")
        return self.address

    def anchor(self, *, record_hash: str, image_hash: str, face_hash: str, post_url: str,
               platform: str, similarity: float) -> dict:
        self.ensure_deployed()
        bps = max(0, min(10000, int(round(similarity * 10000))))
        fn = self.contract.functions.anchor(_b32(record_hash), _b32(image_hash), _b32(face_hash),
                                            post_url, platform, bps)
        try:
            receipt = self._send(fn)
        except ContractLogicError as e:
            if "0x30d23813" in str(e):  # AlreadyAnchored(bytes32) selector
                raise RuntimeError("contract rejected anchor(): this exact record hash is already anchored") from e
            raise RuntimeError(f"contract rejected anchor(): {e}") from e
        tx_hex = _hex(receipt["transactionHash"])
        block = self.w3.eth.get_block(receipt["blockNumber"])
        return {
            "backend": "evm", "chain_id": self.chain_id, "chain": self.chain_name, "rpc_url": self.rpc_url,
            "contract": self.address, "tx_hash": tx_hex, "block_number": int(receipt["blockNumber"]),
            "block_hash": _hex(block["hash"]), "block_timestamp": int(block["timestamp"]),
            "gas_used": int(receipt["gasUsed"]), "submitter": self.account.address,
            "record_hash": _hex(record_hash),
            "explorer_tx": self.explorer_tx(tx_hex), "explorer_contract": self.explorer_address(self.address),
        }

    def get_record(self, record_hash: str) -> dict | None:
        if not self.contract or not self.contract_deployed():
            return None
        r = self.contract.functions.getRecord(_b32(record_hash)).call()
        # Struct order: recordHash, imageHash, faceHash, postUrl, platform, similarityBps, timestamp, submitter
        if int(r[6]) == 0:
            return None
        return {
            "record_hash": _hex(r[0]), "image_hash": _hex(r[1]), "face_hash": _hex(r[2]),
            "post_url": r[3], "platform": r[4], "similarity": int(r[5]) / 10000,
            "timestamp": int(r[6]), "submitter": r[7],
        }

    def count(self) -> int:
        return int(self.contract.functions.count().call()) if self.contract and self.contract_deployed() else 0

    def info(self) -> dict:
        bal = self.w3.eth.get_balance(self.account.address)
        return {
            "backend": "evm", "rpc_url": self.rpc_url, "chain_id": self.chain_id, "chain": self.chain_name,
            "latest_block": self.w3.eth.block_number, "account": self.account.address,
            "balance_eth": float(Web3.from_wei(bal, "ether")),
            "contract": self.address, "contract_deployed": self.contract_deployed(),
            "records_anchored": self.count(),
            "explorer_contract": self.explorer_address(self.address) if self.address else None,
        }
