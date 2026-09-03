"""Download the Foundry release for this OS and extract `anvil` into tools/foundry/.

Usage: python scripts/get_anvil.py [version]   (default: latest stable)
"""
from __future__ import annotations

import io
import platform
import sys
import tarfile
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "tools" / "foundry"


def asset_name(version: str) -> str:
    sysname = platform.system().lower()
    arch = platform.machine().lower()
    arch = "arm64" if arch in ("arm64", "aarch64") else "amd64"
    if sysname == "windows":
        return f"foundry_{version}_win32_amd64.zip"
    if sysname == "darwin":
        return f"foundry_{version}_darwin_{arch}.tar.gz"
    return f"foundry_{version}_linux_{arch}.tar.gz"


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else None
    if not version:
        rel = requests.get("https://api.github.com/repos/foundry-rs/foundry/releases/latest", timeout=30).json()
        version = rel["tag_name"]
    name = asset_name(version)
    url = f"https://github.com/foundry-rs/foundry/releases/download/{version}/{name}"
    print(f"downloading {url} (~100 MB) ...")
    data = requests.get(url, timeout=600).content
    DEST.mkdir(parents=True, exist_ok=True)
    wanted = {"anvil.exe", "anvil", "cast.exe", "cast"}
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for m in z.namelist():
                if Path(m).name in wanted:
                    z.extract(m, DEST)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            for m in t.getmembers():
                if Path(m.name).name in wanted:
                    t.extract(m, DEST)
                    (DEST / m.name).chmod(0o755)
    print(f"done -> {DEST}")


if __name__ == "__main__":
    main()
