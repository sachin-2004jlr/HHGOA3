"""Harvest pictures of an identified person from social media.

Runs once the pipeline knows who the face is (a name read from pages whose face
matched). Every picture returned here is still face-checked afterwards.

Sources
  Apify actors (APIFY_TOKEN, free plan is enough)
    instagram   apify/instagram-scraper        profile search -> latest posts
    x           apidojo/tweet-scraper          search, tweets with images
    facebook    apify/facebook-search-scraper  -> page(s) -> apify/facebook-posts-scraper
    tiktok      clockworks/tiktok-scraper      search, video covers
    google      hooli/google-images-scraper    "<name>" on instagram / x / facebook / pinterest
  Free
    pinterest   DuckDuckGo image search restricted to pinterest.com
    keyword     DuckDuckGo image search "<name>" instagram / twitter / facebook
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import requests

from . import config
from .search import Candidate, expand_with_ddg

APIFY_RUN = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


class SocialError(RuntimeError):
    pass


def apify_items(actor: str, payload: dict, timeout: int = 150, memory: int = 1024) -> list[dict]:
    if not config.APIFY_TOKEN:
        raise SocialError("APIFY_TOKEN not set")
    r = requests.post(APIFY_RUN.format(actor=actor.replace("/", "~")),
                      params={"token": config.APIFY_TOKEN, "timeout": timeout, "memory": memory},
                      json=payload, timeout=timeout + 30)
    if r.status_code not in (200, 201):
        raise SocialError(f"{actor}: HTTP {r.status_code} {r.text[:120]}")
    data = r.json()
    return data if isinstance(data, list) else []


def _t(s: str | None, n: int = 110) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ------------------------------------------------------------------ sources
def instagram(name: str, n: int) -> list[Candidate]:
    items = apify_items("apify/instagram-scraper", {
        "search": name, "searchType": "user", "searchLimit": 2,
        "resultsType": "posts", "resultsLimit": n, "addParentData": False,
    })
    out = []
    for it in items:
        url = it.get("url")
        img = (it.get("images") or [None])[0] or it.get("displayUrl")
        if not url or not img:
            continue
        owner = it.get("ownerUsername") or ""
        out.append(Candidate(url=url, title=_t(f"@{owner} · {it.get('caption') or ''}"),
                             source=f"instagram/@{owner}", image_url=img,
                             thumbnail_url=it.get("displayUrl") or "", engine="apify/instagram"))
    return out


def x_twitter(name: str, n: int) -> list[Candidate]:
    items = apify_items("apidojo/tweet-scraper", {
        "searchTerms": [name], "maxItems": n, "onlyImage": True, "sort": "Top",
    })
    out = []
    for it in items:
        url = it.get("url") or it.get("twitterUrl")
        media = it.get("media") or []
        img = media[0] if media and isinstance(media[0], str) else None
        if not img:
            ext = ((it.get("extendedEntities") or {}).get("media") or [])
            img = ext[0].get("media_url_https") if ext else None
        if not url or not img:
            continue
        author = (it.get("author") or {}).get("userName") or ""
        out.append(Candidate(url=url, title=_t(f"@{author} · {it.get('text') or ''}"), source=f"x/@{author}",
                             image_url=img, thumbnail_url=img, engine="apify/x"))
    return out


def tiktok(name: str, n: int) -> list[Candidate]:
    items = apify_items("clockworks/tiktok-scraper", {
        "searchQueries": [name], "resultsPerPage": n, "searchSection": "/video",
    })
    out = []
    for it in items:
        url = it.get("webVideoUrl")
        vm = it.get("videoMeta") or {}
        img = vm.get("coverUrl") or vm.get("originalCoverUrl")
        if not url or not img:
            continue
        author = (it.get("authorMeta") or {}).get("name") or ""
        out.append(Candidate(url=url, title=_t(f"@{author} · {it.get('text') or ''}"), source=f"tiktok/@{author}",
                             image_url=img, thumbnail_url=img, engine="apify/tiktok"))
    return out


_FB_PERSON = ("athlete", "public figure", "artist", "musician", "actor", "politician", "author", "journalist",
              "entrepreneur", "personal blog", "sports")


def facebook(name: str, n: int) -> list[Candidate]:
    pages = apify_items("apify/facebook-search-scraper", {"categories": [name], "resultsLimit": 4}, timeout=120)
    urls = []
    for p in pages:
        u = p.get("pageUrl") or p.get("facebookUrl")
        cats = str(p.get("categories") or "").lower()
        if u and (any(k in cats for k in _FB_PERSON) or (p.get("title") or "").strip().lower() == name.lower()):
            urls.append(u)
    urls = urls[:2] or [p.get("pageUrl") or p.get("facebookUrl") for p in pages[:1] if p.get("pageUrl") or p.get("facebookUrl")]
    if not urls:
        return []
    posts = apify_items("apify/facebook-posts-scraper", {
        "startUrls": [{"url": u} for u in urls], "resultsLimit": max(5, n // len(urls)),
    })
    out = []
    for it in posts:
        url = it.get("url") or it.get("topLevelUrl")
        media = it.get("media") or []
        img = None
        for m in media:
            if isinstance(m, dict):
                img = m.get("thumbnail") or ((m.get("photo_image") or {}).get("uri")) or m.get("image")
                if img:
                    break
        if not url or not img:
            continue
        who = (it.get("user") or {}).get("name") or it.get("pageName") or ""
        out.append(Candidate(url=url, title=_t(f"{who} · {it.get('text') or ''}"), source=f"facebook/{it.get('pageName') or who}",
                             image_url=img, thumbnail_url=img, engine="apify/facebook"))
    return out


def google_images(name: str, n: int) -> list[Candidate]:
    queries = [f'"{name}" instagram', f'"{name}" x.com', f'"{name}" facebook', f'"{name}" site:pinterest.com']
    items = apify_items("hooli/google-images-scraper", {"queries": queries, "maxResultsPerQuery": max(5, n // 2)})
    out = []
    for it in items:
        url = it.get("contentUrl")
        img = it.get("imageUrl")
        if not url or not img:
            continue
        out.append(Candidate(url=url, title=_t(it.get("title")), source=it.get("origin") or "google images",
                             image_url=img, thumbnail_url=it.get("thumbnailUrl") or "", engine="apify/google-images"))
    return out


def pinterest(name: str, n: int) -> list[Candidate]:
    from ddgs import DDGS

    with DDGS() as d:
        res = d.images(f'"{name}" site:pinterest.com', max_results=n, safesearch="moderate")
    out = []
    for r in res or []:
        if not r.get("url") or not r.get("image"):
            continue
        out.append(Candidate(url=r["url"], title=_t(r.get("title")), source="pinterest.com",
                             image_url=r["image"], thumbnail_url=r.get("thumbnail") or "", engine="ddg/pinterest"))
    return out


def keyword(name: str, n: int) -> list[Candidate]:
    return expand_with_ddg(name, max_per_query=max(6, n // 2), log=lambda _m: None)


# ------------------------------------------------------------------ orchestration
def sources() -> list[tuple[str, Callable[[str, int], list[Candidate]]]]:
    free = [("pinterest", pinterest), ("keyword", keyword)]
    if not config.APIFY_TOKEN:
        return free
    # the free Apify plan allows 5 concurrent runs; facebook uses two sequential runs
    return [("instagram", instagram), ("x", x_twitter), ("facebook", facebook), ("tiktok", tiktok),
            ("google", google_images)] + free


def expand_social(name: str, per_platform: int | None = None, log=print) -> tuple[list[Candidate], dict]:
    """Run every source concurrently. Returns (candidates, {source: count or error})."""
    n = per_platform or config.SOCIAL_PER_PLATFORM
    srcs = sources()
    out: list[Candidate] = []
    report: dict = {}
    with ThreadPoolExecutor(max_workers=len(srcs)) as pool:
        futs = {pool.submit(fn, name, n): label for label, fn in srcs}
        for fut, label in futs.items():
            try:
                c = fut.result()
                out += c
                report[label] = len(c)
                log(f"{label}: {len(c)} pictures")
            except Exception as e:  # noqa: BLE001
                report[label] = f"error: {type(e).__name__}"
                log(f"{label}: {type(e).__name__}: {str(e)[:90]}")
    return out, report
