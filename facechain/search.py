"""Reverse-image search + face-verified candidate ranking.

Engines
  * Yandex reverse image search (no key). Yandex matches *faces*: for a tight face
    crop it returns pages carrying the same or a look-alike image, visually similar
    faces with their source pages, and often the recognised person.
  * Google Lens via Serper.dev or SerpApi (optional key). Lens deliberately does not
    identify people, so it only helps when the exact photo is already spread around
    the web; it is queried with every view of the face (crop + whole photo).

Every candidate image is then downloaded and its face compared with the scan
(SFace cosine similarity). Only candidates whose face actually matches survive,
so the final "post" is verified biometrically, not by search ranking.
"""
from __future__ import annotations

import html as _html
import json as _json
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


def _serpapi_query(image_url: str, search_type: str) -> dict:
    params = {"engine": "google_lens", "url": image_url, "type": search_type,
              "api_key": config.SERPAPI_KEY, "hl": "en", "country": "us"}
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=90)
    if r.status_code != 200:
        raise SearchError(f"SerpApi HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    if data.get("error"):
        raise SearchError(f"SerpApi: {data['error']}")
    return data


def _serpapi_lens(image_url: str) -> tuple[list[Candidate], Optional[str], int]:
    responses = [("visual", _serpapi_query(image_url, "all"))]

    cands: list[Candidate] = []
    name = None
    for _label, data in responses:
        for key in ("exact_matches", "visual_matches"):
            for i, m in enumerate(data.get(key) or []):
                link = m.get("link") or m.get("source_link")
                if not link:
                    continue
                cands.append(Candidate(
                    url=link, title=m.get("title", ""), source=m.get("source", ""),
                    image_url=m.get("image", ""), thumbnail_url=m.get("thumbnail", ""),
                    engine=f"serpapi/google_lens/{key}", position=m.get("position", i + 1),
                ))
        kg = data.get("knowledge_graph")
        if not name:
            if isinstance(kg, list) and kg:
                name = kg[0].get("title")
            elif isinstance(kg, dict):
                name = kg.get("title")
    return cands, name, len(cands)


def _serper_lens(image_url: str) -> tuple[list[Candidate], Optional[str], int]:
    r = requests.post("https://google.serper.dev/lens",
                      json={"url": image_url, "num": config.LENS_NUM_RESULTS},
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


# ---- Yandex ---------------------------------------------------------------------
_YANDEX = "https://yandex.com/images/search"


def _abs(u: str) -> str:
    return "https:" + u if u and u.startswith("//") else (u or "")


def _yandex_state(params: dict) -> dict:
    headers = {"User-Agent": config.USER_AGENT, "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "en-US,en;q=0.9"}
    r = requests.get(_YANDEX, params=params, headers=headers, timeout=45)
    if r.status_code != 200:
        raise SearchError(f"Yandex HTTP {r.status_code}")
    m = re.search(r'<div class="Root" id="ImagesApp-[^"]+" data-state="([^"]+)"', r.text)
    if not m:
        if "captcha" in r.text.lower():
            raise SearchError("Yandex asked for a captcha (rate limited) - try again in a minute")
        raise SearchError("Yandex returned an unexpected page")
    return _json.loads(_html.unescape(m.group(1))).get("initialState", {})


def _yandex_reverse(image_url: str) -> tuple[list[Candidate], Optional[str], int]:
    """Pages carrying the image + visually similar faces (with source pages) + recognised entity."""
    st = _yandex_state({"rpt": "imageview", "url": image_url})
    cands: list[Candidate] = []
    name = None
    objs = (st.get("cbirObjectResponses") or {}).get("objectResponses") or []
    if objs and objs[0].get("title") and str(objs[0]["title"]).isascii():
        name = objs[0]["title"]
    for i, s_ in enumerate((st.get("cbirSites") or {}).get("sites") or []):
        if not s_.get("url"):
            continue
        cands.append(Candidate(
            url=s_["url"], title=s_.get("title") or "", source=s_.get("domain") or "",
            image_url=_abs((s_.get("originalImage") or {}).get("url", "")),
            thumbnail_url=_abs((s_.get("thumb") or {}).get("url", "")), engine="yandex/sites", position=i + 1))
    try:
        sim = _yandex_state({"rpt": "imageview", "url": image_url, "cbir_page": "similar"})
        ents = ((sim.get("serpList") or {}).get("items") or {}).get("entities") or {}
        for i, e in enumerate(sorted(ents.values(), key=lambda x: x.get("pos", 0))):
            sn = e.get("snippet") or {}
            if not sn.get("url"):
                continue
            cands.append(Candidate(
                url=sn["url"], title=sn.get("title") or e.get("alt") or "", source=sn.get("domain") or "",
                image_url=e.get("origUrl") or "", thumbnail_url=_abs(e.get("image") or ""),
                engine="yandex/similar", position=i + 1))
    except SearchError:
        pass  # the sites list alone is still useful
    if not name:
        tags = [t.get("text", "") for t in ((st.get("cbirTags") or {}).get("tags") or [])]
        name = guess_entity_name([c.title for c in cands] + tags, need=3)
    return cands, name, len(cands)


_LENS = {"serpapi": _serpapi_lens, "serper": _serper_lens}


def available_engines() -> list[str]:
    """Yandex needs no key; Google Lens (Serper/SerpApi) is added when a key exists."""
    pref = config.SEARCH_ENGINE
    if pref == "yandex":
        return ["yandex"]
    engines = ["yandex"]
    if pref in ("auto", "serpapi") and config.SERPAPI_KEY:
        engines.append("serpapi")
    elif pref in ("auto", "serper") and config.SERPER_API_KEY:
        engines.append("serper")
    return engines



def _clean_url(u: str) -> str:
    u = re.sub(r"[?&]utm_[a-z]+=[^&#]*", "", u or "")
    return u.replace("?&", "?").rstrip("?").split("#")[0]


def _dedupe(cands: list[Candidate]) -> list[Candidate]:
    seen, out = set(), []
    for c in cands:
        c.url = _clean_url(c.url)
        key = c.url.rstrip("/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def reverse_image_search_many(image_urls: list[str]) -> SearchResult:
    """Query every available engine with the views of the face and merge.

    Yandex gets the tight face crop (first URL); Google Lens gets every view.
    Candidates are ordered face-first: Yandex similar faces, Yandex pages, then Lens.
    """
    engines = available_engines()
    jobs: list[tuple[str, str]] = [("yandex", image_urls[0])]
    for eng in engines:
        if eng in _LENS:
            jobs += [(eng, u) for u in image_urls]
    results: dict[str, list[tuple[list[Candidate], Optional[str], int]]] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futs = {pool.submit(_yandex_reverse if e == "yandex" else _LENS[e], u): e for e, u in jobs}
        for fut, eng in futs.items():
            try:
                results.setdefault(eng, []).append(fut.result())
            except Exception as e:  # noqa: BLE001
                errors.append(f"{eng}: {e}")
    if not results:
        raise SearchError("; ".join(errors) or "reverse image search failed")
    order = ["yandex"] + [e for e in engines if e != "yandex"]
    ordered: list[Candidate] = []
    name = None
    raw = 0
    for eng in order:
        for c, n, r in results.get(eng, []):
            ordered += sorted(c, key=lambda x: 0 if x.engine.endswith("similar") else 1)
            raw += r
            name = name or n
    cands = _dedupe(ordered)
    if not name:
        name = guess_entity_name([c.title for c in cands])
    return SearchResult(engine="+".join(e for e in order if e in results), query_image_url=image_urls[0],
                        candidates=cands, entity_name=name, raw_count=raw)



# ------------------------------------------------------------- entity guessing
_STOP = {"The", "And", "For", "With", "From", "New", "Photo", "Photos", "Image", "Images", "Video",
         "News", "Instagram", "Twitter", "Facebook", "Reddit", "TikTok", "YouTube", "Pinterest",
         "LinkedIn", "Wikipedia", "Getty", "Stock", "Free", "Best", "Top", "How", "Why", "What",
         "Who", "Is", "In", "On", "At", "Of", "To", "By", "Pictures", "Picture", "Latest", "Says",
         "Wallpaper", "Wallpapers", "Download", "Full", "Join", "Telegram", "Pin", "Ideas"}


def guess_entity_name(titles: list[str], need: Optional[int] = None) -> Optional[str]:
    """Most frequent capitalised 2-3 word sequence across result titles (>= `need` hits)."""
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
    if need is None:
        need = 2 if len(titles) < 6 else 3
    return best if n >= need else None


def entity_from_verified(verified: list["Verified"], threshold: float) -> Optional[str]:
    """Name that recurs in the titles of pages whose face actually matched the scan."""
    titles = [v.candidate.title for v in verified if v.similarity >= threshold and v.candidate.title]
    if len(titles) < 2:
        return None
    return guess_entity_name(titles, need=2)


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
                      max_n: int = 60, workers: int = 12, progress=None) -> list[Verified]:
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


# Platform tiers only add a small bonus: 1 = photo networks, 2 = video platforms, 3 = re-pin / gallery sites.
PLATFORM_TIER = {p: 1 for p in ("instagram", "x", "facebook", "threads", "reddit", "linkedin", "snapchat",
                                "vk", "weibo")}
PLATFORM_TIER.update({p: 2 for p in ("tiktok", "youtube")})
PLATFORM_TIER.update({p: 3 for p in ("pinterest", "tumblr", "flickr", "imgur", "quora", "medium")})
TIER_BONUS = {1: 0.05, 2: 0.02, 3: 0.0}
OWN_ACCOUNT_BONUS = 0.05


def _letters(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def own_account(v: Verified, entity: Optional[str]) -> bool:
    """True when the post's handle looks like the identified person's own account."""
    if not entity:
        return False
    e = _letters(entity)
    handle = _letters(v.candidate.source.split("/")[-1]) if v.candidate.source else ""
    return len(e) >= 5 and bool(handle) and (e in handle or handle in e)


def match_score(v: Verified, entity: Optional[str] = None) -> float:
    """Similarity first; a small bonus for photo networks and for the person's own account."""
    bonus = TIER_BONUS.get(PLATFORM_TIER.get(v.candidate.platform, 0), 0.0)
    return v.similarity + bonus + (OWN_ACCOUNT_BONUS if own_account(v, entity) else 0.0)


def choose_match(verified: list[Verified], threshold: float, entity: Optional[str] = None) -> Optional[Verified]:
    """Above-threshold candidates only; social-media posts before plain web pages; highest score wins."""
    passing = [v for v in verified if v.similarity >= threshold]
    if not passing:
        return None
    social = [v for v in passing if is_social(v.candidate.platform)]
    return max(social or passing, key=lambda v: match_score(v, entity))


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
