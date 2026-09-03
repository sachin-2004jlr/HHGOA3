"""Reverse-image search + face-verified candidate ranking.

Step 1  A reverse-image engine (Google Lens via SerpApi or Serper.dev) is
        queried with a public URL of the scanned face. It returns pages on the
        open web / social media whose images look like the query.
Step 2  (optional) If the engine recognised the person (knowledge graph or a
        name that recurs across result titles) we widen the net with a
        keyword image search restricted to social platforms (DuckDuckGo, free).
Step 3  Every candidate image is downloaded and the face in it is compared
        against the scanned face with SFace cosine similarity. Only
        candidates whose face actually matches are kept, so the final "post"
        is verified biometrically and not just by search-engine ranking.
"""
from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlparse

import numpy as np
import requests

from . import config
from .face import FaceEngine

_HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "image/*,*/*;q=0.8"}


# --------------------------------------------------------------------------- data
@dataclass
class Candidate:
    url: str
    title: str = ""
    source: str = ""
    image_url: str = ""
    thumbnail_url: str = ""
    engine: str = ""
    position: int = 0
    platform: str = field(default="web")

    def __post_init__(self):
        self.platform = classify_platform(self.url)


@dataclass
class Verified:
    candidate: Candidate
    similarity: float
    faces_found: int
    fetched_url: str            # which image URL we actually downloaded
    image_bytes: bytes = field(repr=False, default=b"")
    face_bbox: Optional[tuple[int, int, int, int]] = None

    def to_public_dict(self) -> dict:
        d = asdict(self.candidate)
        d.update(similarity=round(self.similarity, 4), faces_found=self.faces_found,
                 fetched_url=self.fetched_url, face_bbox=self.face_bbox)
        return d


@dataclass
class SearchResult:
    engine: str
    query_image_url: str
    candidates: list[Candidate]
    entity_name: Optional[str] = None
    raw_count: int = 0


# ------------------------------------------------------------------ platform utils
def classify_platform(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return "web"
    host = host.split(":")[0]
    parts = host.split(".")
    for i in range(len(parts) - 1):
        dom = ".".join(parts[i:])
        if dom in config.SOCIAL_PLATFORMS:
            return config.SOCIAL_PLATFORMS[dom]
    return "web"


def is_social(platform: str) -> bool:
    return platform != "web"


# ------------------------------------------------------------------ engines
class SearchError(RuntimeError):
    pass


def _serpapi_lens(image_url: str) -> tuple[list[Candidate], Optional[str], int]:
    params = {"engine": "google_lens", "url": image_url, "api_key": config.SERPAPI_KEY,
              "hl": "en", "country": "us"}
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=90)
    if r.status_code != 200:
        raise SearchError(f"SerpApi HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    if data.get("error"):
        raise SearchError(f"SerpApi: {data['error']}")

    cands: list[Candidate] = []
    for key in ("exact_matches", "visual_matches"):
        for i, m in enumerate(data.get(key) or []):
            link = m.get("link") or m.get("source_link")
            if not link:
                continue
            cands.append(Candidate(
                url=link, title=m.get("title", ""), source=m.get("source", ""),
                image_url=m.get("image", ""), thumbnail_url=m.get("thumbnail", ""),
                engine="serpapi/google_lens", position=m.get("position", i + 1),
            ))
    name = None
    kg = data.get("knowledge_graph")
    if isinstance(kg, list) and kg:
        name = kg[0].get("title")
    elif isinstance(kg, dict):
        name = kg.get("title")
    return cands, name, len(cands)


def _serper_lens(image_url: str) -> tuple[list[Candidate], Optional[str], int]:
    r = requests.post("https://google.serper.dev/lens", json={"url": image_url},
                      headers={"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"},
                      timeout=90)
    if r.status_code != 200:
        raise SearchError(f"Serper HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    cands: list[Candidate] = []
    for i, m in enumerate(data.get("organic") or []):
        link = m.get("link")
        if not link:
            continue
        cands.append(Candidate(
            url=link, title=m.get("title", ""), source=m.get("source", ""),
            image_url=m.get("imageUrl", ""),
            thumbnail_url=m.get("thumbnailUrl", "") or m.get("thumbnail", ""),
            engine="serper/google_lens", position=m.get("position", i + 1),
        ))
    kg = data.get("knowledgeGraph") or {}
    name = kg.get("title") if isinstance(kg, dict) else None
    return cands, name, len(cands)


def pick_engine() -> str:
    pref = config.SEARCH_ENGINE
    if pref == "serpapi" or (pref == "auto" and config.SERPAPI_KEY):
        if not config.SERPAPI_KEY:
            raise SearchError("SEARCH_ENGINE=serpapi but SERPAPI_KEY is not set")
        return "serpapi"
    if pref == "serper" or (pref == "auto" and config.SERPER_API_KEY):
        if not config.SERPER_API_KEY:
            raise SearchError("SEARCH_ENGINE=serper but SERPER_API_KEY is not set")
        return "serper"
    raise SearchError(
        "No reverse-image search key configured. Set SERPAPI_KEY (https://serpapi.com, free tier) "
        "or SERPER_API_KEY (https://serper.dev, free credits) in .env"
    )


def reverse_image_search(image_url: str) -> SearchResult:
    engine = pick_engine()
    fn = _serpapi_lens if engine == "serpapi" else _serper_lens
    cands, name, raw = fn(image_url)
    cands = _dedupe(cands)
    if not name:
        name = guess_entity_name([c.title for c in cands])
    return SearchResult(engine=engine, query_image_url=image_url, candidates=cands,
                        entity_name=name, raw_count=raw)


def _dedupe(cands: list[Candidate]) -> list[Candidate]:
    seen, out = set(), []
    for c in cands:
        key = c.url.split("#")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


_STOP = {"The", "And", "For", "With", "From", "New", "Photo", "Photos", "Image", "Images", "Video",
         "News", "Instagram", "Twitter", "Facebook", "Reddit", "TikTok", "YouTube", "Pinterest",
         "LinkedIn", "Wikipedia", "Getty", "Stock", "Free", "Best", "Top", "How", "Why", "What",
         "Who", "Is", "In", "On", "At", "Of", "To", "By", "Pictures", "Picture", "Latest", "Says"}


def guess_entity_name(titles: list[str]) -> Optional[str]:
    """Most frequent capitalised 2-3 word sequence across result titles (>= 3 hits)."""
    counter: Counter[str] = Counter()
    for t in titles:
        words = re.findall(r"[A-Z][a-zA-Z'\-]+", t or "")
        seen_in_title = set()
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                seq = words[i:i + n]
                if any(w in _STOP for w in seq):
                    continue
                key = " ".join(seq)
                if key not in seen_in_title:
                    seen_in_title.add(key)
                    counter[key] += 1
    if not counter:
        return None
    best, n = counter.most_common(1)[0]
    return best if n >= 3 else None


# ------------------------------------------------------------- expansion (DDG)
def expand_with_ddg(name: str, max_per_query: int = 12, log=print) -> list[Candidate]:
    """Free keyword image search on social platforms for a recognised name."""
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    queries = [f'"{name}" instagram', f'"{name}" twitter', f'"{name}" facebook']
    out: list[Candidate] = []
    try:
        with DDGS() as ddg:
            for q in queries:
                try:
                    res = ddg.images(q, max_results=max_per_query, safesearch="moderate")
                except Exception as e:  # noqa: BLE001
                    log(f"[expand] ddg '{q}' failed: {type(e).__name__}")
                    continue
                for i, r in enumerate(res or []):
                    url = r.get("url") or ""
                    if not url:
                        continue
                    out.append(Candidate(url=url, title=r.get("title", ""),
                                         source=r.get("source", "duckduckgo"),
                                         image_url=r.get("image", ""), thumbnail_url=r.get("thumbnail", ""),
                                         engine="ddg/images", position=i + 1))
    except Exception as e:  # noqa: BLE001
        log(f"[expand] ddg unavailable: {type(e).__name__}")
    return out


# ------------------------------------------------------------- verification
def _download(url: str, max_bytes: int = 8_000_000) -> Optional[bytes]:
    if not url or not url.startswith("http"):
        return None
    try:
        r = requests.get(url, headers=_HEADERS, timeout=config.HTTP_TIMEOUT, stream=True)
        if r.status_code != 200:
            return None
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf) > max_bytes:
                break
        return bytes(buf)
    except requests.RequestException:
        return None


def _verify_one(engine: FaceEngine, query_vec: np.ndarray, cand: Candidate) -> Optional[Verified]:
    for url in (cand.image_url, cand.thumbnail_url):
        data = _download(url)
        img = engine.decode_bytes(data) if data else None
        if img is None:
            continue
        img, faces = engine.analyze(img, max_faces=8)
        if not faces:
            return Verified(cand, -1.0, 0, url, data)
        best, best_face = -1.0, None
        for f in faces:
            s = engine.similarity(query_vec, f.embedding)
            if s > best:
                best, best_face = s, f
        return Verified(cand, best, len(faces), url, data, best_face.bbox if best_face else None)
    return None


def verify_candidates(engine: FaceEngine, query_vec: np.ndarray, cands: list[Candidate],
                      max_n: int = 60, workers: int = 8, progress=None) -> list[Verified]:
    """Download + face-compare candidates concurrently. Returns all that decoded."""
    cands = cands[:max_n]
    out: list[Verified] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_verify_one, engine, query_vec, c): c for c in cands}
        for fut in as_completed(futs):
            try:
                v = fut.result()
            except Exception:  # noqa: BLE001
                v = None
            if v is not None:
                out.append(v)
            if progress:
                progress(v)
    out.sort(key=lambda v: v.similarity, reverse=True)
    return out


def choose_match(verified: list[Verified], threshold: float) -> Optional[Verified]:
    """Best social-media match above threshold; else best web match above threshold."""
    passing = [v for v in verified if v.similarity >= threshold]
    if not passing:
        return None
    social = [v for v in passing if is_social(v.candidate.platform)]
    pool = social or passing
    return max(pool, key=lambda v: v.similarity)


# ------------------------------------------------------------- post metadata
def fetch_post_metadata(url: str) -> dict:
    """Best-effort Open Graph metadata of the discovered post (many sites block bots)."""
    meta = {"url": url, "fetched": False}
    try:
        r = requests.get(url, headers={"User-Agent": config.USER_AGENT, "Accept": "text/html"},
                         timeout=config.HTTP_TIMEOUT, allow_redirects=True)
        meta["status_code"] = r.status_code
        meta["final_url"] = r.url
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            return meta
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(r.text[:600_000], "html.parser")

        def og(prop):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            return (tag.get("content") or "").strip() if tag else ""

        meta.update(
            fetched=True,
            og_title=og("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else ""),
            og_description=og("og:description") or og("description"),
            og_image=og("og:image"),
            og_site_name=og("og:site_name"),
            og_type=og("og:type"),
        )
    except Exception as e:  # noqa: BLE001
        meta["error"] = f"{type(e).__name__}: {e}"[:200]
    return meta
