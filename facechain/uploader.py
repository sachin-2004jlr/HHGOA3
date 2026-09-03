"""Publish the query image to a temporary public URL.

Reverse-image engines (Google Lens etc.) need a URL they can fetch. We upload
the face image to a short-lived anonymous host (expires in about 1 hour) and
verify the link serves an image before handing it to the search engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import requests

from . import config

_HEADERS = {"User-Agent": config.USER_AGENT}


def _tmpfiles(path: Path) -> str:
    with path.open("rb") as fh:
        r = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": fh},
                          headers=_HEADERS, timeout=config.HTTP_TIMEOUT * 2)
    r.raise_for_status()
    url = r.json()["data"]["url"]  # https://tmpfiles.org/123/x.jpg  (HTML page)
    return url.replace("https://tmpfiles.org/", "https://tmpfiles.org/dl/", 1)


def _litterbox(path: Path) -> str:
    with path.open("rb") as fh:
        r = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "1h"},
            files={"fileToUpload": fh}, headers=_HEADERS, timeout=config.HTTP_TIMEOUT * 2,
        )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"litterbox: {url[:100]}")
    return url


def _0x0(path: Path) -> str:
    with path.open("rb") as fh:
        r = requests.post("https://0x0.st", files={"file": fh},
                          data={"expires": "1"},  # hours
                          headers={"User-Agent": "facechain/0.1 (research pipeline)"},
                          timeout=config.HTTP_TIMEOUT * 2)
    r.raise_for_status()
    return r.text.strip()


def _uguu(path: Path) -> str:
    with path.open("rb") as fh:
        r = requests.post("https://uguu.se/upload", files={"files[]": fh},
                          headers=_HEADERS, timeout=config.HTTP_TIMEOUT * 2)
    r.raise_for_status()
    return r.json()["files"][0]["url"]


HOSTS: list[tuple[str, Callable[[Path], str]]] = [
    ("uguu.se", _uguu),              # direct image link, expires in ~3h
    ("tmpfiles.org", _tmpfiles),     # expires in 1h
    ("litterbox.catbox.moe", _litterbox),
    ("0x0.st", _0x0),
]


def _serves_image(url: str) -> bool:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=config.HTTP_TIMEOUT, stream=True)
        ctype = r.headers.get("content-type", "")
        head = r.raw.read(16)
        r.close()
        return r.status_code == 200 and (
            ctype.startswith("image/") or head[:3] == b"\xff\xd8\xff" or head[:4] == b"\x89PNG"
        )
    except requests.RequestException:
        return False


def publish_image(path: str | Path, log=print) -> tuple[str, str]:
    """Upload and return (public_url, host_name). Tries hosts in order."""
    path = Path(path)
    errors = []
    for name, fn in HOSTS:
        try:
            url = fn(path)
            if _serves_image(url):
                return url, name
            errors.append(f"{name}: link did not serve an image ({url})")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
        log(f"[upload] {name} failed, trying next host ...")
    raise RuntimeError("All temporary image hosts failed:\n  " + "\n  ".join(errors))
