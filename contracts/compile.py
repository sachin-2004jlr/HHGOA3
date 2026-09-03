"""Compile FaceMatchRegistry.sol with py-solc-x and write ABI + bytecode to build/.

Usage:  python contracts/compile.py
The build artifact is committed so end users do not need a Solidity compiler.
"""
from __future__ import annotations

import json
from pathlib import Path

import solcx

SOLC_VERSION = "0.8.26"
HERE = Path(__file__).resolve().parent
SRC = HERE / "FaceMatchRegistry.sol"
OUT = HERE / "build" / "FaceMatchRegistry.json"


def main() -> None:
    if SOLC_VERSION not in [str(v) for v in solcx.get_installed_solc_versions()]:
        print(f"Installing solc {SOLC_VERSION} ...")
        solcx.install_solc(SOLC_VERSION)
    solcx.set_solc_version(SOLC_VERSION)

    source = SRC.read_text(encoding="utf-8")
    compiled = solcx.compile_standard(
        {
            "language": "Solidity",
            "sources": {SRC.name: {"content": source}},
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "evmVersion": "paris",
                "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object", "metadata"]}},
            },
        },
        solc_version=SOLC_VERSION,
    )
    c = compiled["contracts"][SRC.name]["FaceMatchRegistry"]
    artifact = {
        "contractName": "FaceMatchRegistry",
        "solcVersion": SOLC_VERSION,
        "abi": c["abi"],
        "bytecode": "0x" + c["evm"]["bytecode"]["object"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({len(artifact['bytecode'])//2} bytes of bytecode, {len(artifact['abi'])} ABI entries)")


if __name__ == "__main__":
    main()
