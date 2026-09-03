"""Command-line interface.

    python -m facechain run --image samples/elon_musk.jpg     # full pipeline
    python -m facechain run --webcam                          # live face scan
    python -m facechain verify --evidence evidence/<run_id>   # re-verify vs chain
    python -m facechain tamper-demo --evidence evidence/<run_id>
    python -m facechain deploy | chain-info | face --image X
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, config

console = Console(highlight=False, emoji=False)


def step(n: int, title: str) -> None:
    console.rule(f"[bold cyan]STEP {n}[/]  [bold]{title}[/]", style="cyan")


def kv_table(rows: list[tuple[str, str]], title: str | None = None) -> Table:
    t = Table(show_header=False, box=box.SIMPLE, title=title, title_justify="left", padding=(0, 1))
    t.add_column(style="bold dim", no_wrap=True)
    t.add_column(overflow="fold")
    for k, v in rows:
        t.add_row(k, str(v))
    return t


def short(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def fmt_hash(h: str) -> str:
    h = h if h.startswith("0x") else "0x" + h
    return h


# =============================================================================== run
def cmd_run(args: argparse.Namespace) -> int:
    from . import evidence as ev
    from .face import FaceEngine, crop_face, draw_faces, encode_jpeg
    from .search import (choose_match, expand_with_ddg, fetch_post_metadata, is_social,
                         reverse_image_search, verify_candidates)
    from .uploader import publish_image

    t0 = time.time()
    console.print(Panel.fit(
        f"[bold]facechain v{__version__}[/]\nface scan  ->  reverse image search  ->  face-verified social post  ->  blockchain anchor",
        border_style="cyan"))

    # ---------------------------------------------------------------- 1. face scan
    step(1, "Face scan: detect + encode the input face")
    engine = FaceEngine()
    src_path: Path | None = None
    if args.webcam:
        frame = engine.capture_webcam(args.camera)
        img_bytes = encode_jpeg(frame, 95)
        img = frame
    else:
        src_path = Path(args.image)
        if not src_path.exists():
            console.print(f"[red]image not found:[/] {src_path}")
            return 2
        img = engine.load_image(src_path)
        img_bytes = None

    img, faces = engine.analyze(img)
    if not faces:
        console.print("[red]No face detected in the input image.[/]")
        return 2
    idx = min(args.face_index, len(faces) - 1)
    face = faces[idx]
    bundle = ev.EvidenceBundle()
    aligned_jpg = encode_jpeg(face.aligned, 95)
    query_info = bundle.save_query(src_path, img_bytes, aligned_jpg, face.embedding)
    query_info["face_bbox"] = list(face.bbox)
    query_info["detector_score"] = round(face.score, 4)
    query_info["faces_in_image"] = len(faces)
    query_info["model"] = {"detector": "YuNet 2023mar (OpenCV zoo)", "recognizer": "SFace 2021dec (OpenCV zoo)"}
    (bundle.dir / "query_annotated.jpg").write_bytes(encode_jpeg(draw_faces(img, faces)))
    crop = crop_face(img, face)
    crop_path = bundle.dir / "query_crop.jpg"
    crop_path.write_bytes(encode_jpeg(crop, 92))

    console.print(kv_table([
        ("input", str(src_path) if src_path else "webcam capture"),
        ("faces detected", f"{len(faces)}  (using #{idx}, the largest)"),
        ("bbox (x,y,w,h)", f"{face.bbox}   score={face.score:.3f}"),
        ("embedding", f"SFace 128-d, L2-normalised   sha256={query_info['embedding_sha256'][:16]}..."),
        ("evidence dir", str(bundle.dir)),
    ]))

    # ---------------------------------------------------------------- 2. search
    step(2, "Web / social media search (reverse image search)")
    if args.image_url:
        public_url, host = args.image_url, "user-supplied"
    else:
        with console.status("[cyan]uploading face crop to a temporary public host ..."):
            public_url, host = publish_image(crop_path, log=lambda m: console.print(f"[dim]{m}[/]"))
    console.print(f"[dim]query image URL ({host}):[/] {public_url}")

    with console.status("[cyan]querying Google Lens (reverse image search) ..."):
        result = reverse_image_search(public_url)
    console.print(f"engine=[bold]{result.engine}[/]  raw results=[bold]{result.raw_count}[/]  "
                  f"unique pages=[bold]{len(result.candidates)}[/]  "
                  f"recognised entity=[bold]{result.entity_name or '-'}[/]")

    candidates = list(result.candidates)
    if result.entity_name and not args.no_expand:
        with console.status(f"[cyan]expanding with keyword image search for '{result.entity_name}' on social platforms ..."):
            extra = expand_with_ddg(result.entity_name, log=lambda m: console.print(f"[dim]{m}[/]"))
        seen = {c.url.rstrip('/') for c in candidates}
        extra = [c for c in extra if c.url.rstrip('/') not in seen]
        candidates += extra
        console.print(f"[dim]+{len(extra)} extra candidates from DuckDuckGo image search[/]")

    if not candidates:
        console.print("[red]Search returned no candidates.[/]")
        return 3

    social_n = sum(1 for c in candidates if is_social(c.platform))
    t = Table(title=f"Top candidates from search ({len(candidates)} total, {social_n} on social platforms)",
              box=box.SIMPLE_HEAD, title_justify="left")
    t.add_column("#", justify="right", style="dim")
    t.add_column("platform", style="magenta")
    t.add_column("title", overflow="fold", max_width=48)
    t.add_column("url", overflow="fold", style="dim", max_width=60)
    for i, c in enumerate(candidates[:12]):
        t.add_row(str(i + 1), c.platform, short(c.title, 48), short(c.url, 60))
    console.print(t)

    # ---------------------------------------------------------------- 3. verify faces
    step(3, "Face verification of every candidate image")
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

    cands = candidates[: args.max_candidates]
    with Progress(TextColumn("[cyan]{task.description}"), BarColumn(), TextColumn("{task.completed}/{task.total}"),
                  TimeElapsedColumn(), console=console) as prog:
        task = prog.add_task("downloading + matching", total=len(cands))
        verified = verify_candidates(engine, face.embedding, cands, max_n=len(cands),
                                     progress=lambda v: prog.advance(task))

    bundle.save_json("candidates.json", [v.to_public_dict() for v in verified])
    thr = args.min_similarity
    t = Table(title=f"Face similarity (SFace cosine, threshold {thr})", box=box.SIMPLE_HEAD, title_justify="left")
    t.add_column("sim", justify="right")
    t.add_column("platform", style="magenta")
    t.add_column("faces", justify="right", style="dim")
    t.add_column("title", overflow="fold", max_width=44)
    t.add_column("url", overflow="fold", style="dim", max_width=58)
    for v in verified[:15]:
        color = "green" if v.similarity >= thr else ("yellow" if v.similarity > 0.25 else "red")
        t.add_row(f"[{color}]{v.similarity:+.3f}[/]", v.candidate.platform, str(v.faces_found),
                  short(v.candidate.title, 44), short(v.candidate.url, 58))
    console.print(t)

    match = choose_match(verified, thr)
    if match is None:
        best = verified[0] if verified else None
        console.print(Panel(
            f"[red bold]No candidate passed the face-match threshold ({thr}).[/]\n"
            + (f"Best was {best.similarity:.3f} on {best.candidate.url}\n" if best else "")
            + "Try another photo (frontal, well lit), a lower --min-similarity, or --max-candidates 100.",
            border_style="red"))
        bundle.save_json("record.json", {"status": "no_match", "search": {"engine": result.engine}})
        return 4

    meta = fetch_post_metadata(match.candidate.url)
    img_name, img_sha = bundle.save_match_image(match.image_bytes)
    console.print(Panel(
        f"[bold green]MATCH[/]  similarity=[bold]{match.similarity:.3f}[/]  platform=[magenta bold]{match.candidate.platform}[/]\n"
        f"[bold]{match.candidate.title}[/]\n{match.candidate.url}\n"
        f"[dim]image: {match.fetched_url}\n"
        f"og:title: {meta.get('og_title') or '-'}\n"
        f"saved as {img_name} sha256={img_sha[:16]}...[/]",
        title="Discovered social-media post", border_style="green"))

    # ---------------------------------------------------------------- 4. record + hash
    step(4, "Build the evidence record and fingerprint it (SHA-256)")
    record = ev.build_record(
        run_id=bundle.run_id,
        query=query_info,
        match={
            "post_url": match.candidate.url, "platform": match.candidate.platform,
            "title": match.candidate.title, "source": match.candidate.source,
            "image_url": match.fetched_url, "image_file": img_name, "image_sha256": img_sha,
            "similarity": round(match.similarity, 4), "faces_in_image": match.faces_found,
            "face_bbox": list(match.face_bbox) if match.face_bbox else None,
            "og": {k: v for k, v in meta.items() if k.startswith("og_") and v},
        },
        search={
            "engine": result.engine, "query_image_url": public_url, "query_image_host": host,
            "entity_name": result.entity_name, "candidates_total": len(candidates),
            "candidates_verified": len(verified), "threshold": thr,
        },
    )
    record_hash = bundle.write_record(record)
    console.print(kv_table([
        ("record.json", str(bundle.dir / "record.json")),
        ("record_hash", "sha256(canonical record.json) = " + fmt_hash(record_hash)),
        ("image_hash", "sha256(" + img_name + ") = " + fmt_hash(img_sha)),
        ("face_hash", "sha256(query embedding) = " + fmt_hash(query_info["embedding_sha256"])),
    ]))

    if args.skip_chain:
        console.print("[yellow]--skip-chain given: not anchoring.[/]")
        return 0

    # ---------------------------------------------------------------- 5. anchor
    step(5, "Blockchain: anchor the fingerprint in FaceMatchRegistry")
    from .chain import get_backend

    backend = get_backend(args.chain)
    with console.status(f"[cyan]sending transaction via {backend.name} backend ..."):
        receipt = backend.anchor(record_hash=record_hash, image_hash=img_sha,
                                 face_hash=query_info["embedding_sha256"], post_url=match.candidate.url,
                                 platform=match.candidate.platform, similarity=match.similarity)
    receipt["anchored_at"] = ev.now_iso()
    bundle.save_json("chain_receipt.json", receipt)
    rows = [(k, str(v)) for k, v in receipt.items() if v is not None and k != "backend"]
    console.print(kv_table(rows, title=f"on-chain receipt ({backend.name})"))

    # ---------------------------------------------------------------- 6. re-verify
    step(6, "Re-verify: read the record back from the chain and compare")
    ok = _verify_bundle(bundle.dir, args.chain, quiet=False)
    console.print(Panel(
        f"evidence: [bold]{bundle.dir}[/]\n"
        f"re-run verification any time with:\n"
        f"  [bold cyan]python -m facechain verify --evidence {bundle.dir.relative_to(config.ROOT) if bundle.dir.is_relative_to(config.ROOT) else bundle.dir}[/]\n"
        f"[dim]total time {time.time() - t0:.1f}s[/]",
        title="[green bold]PIPELINE COMPLETE[/]" if ok else "[red bold]PIPELINE FINISHED WITH VERIFICATION ERRORS[/]",
        border_style="green" if ok else "red"))
    return 0 if ok else 5


# ============================================================================ verify
def _verify_bundle(path: Path, chain_kind: str | None, quiet: bool = False) -> bool:
    from . import evidence as ev
    from .chain import get_backend

    b = ev.LoadedBundle(path)
    rec = b.record
    recomputed = b.recomputed()
    checks: list[tuple[str, str, str, bool]] = []  # name, local, remote, ok

    # local consistency: files on disk vs what record.json claims
    m, q = rec.get("match", {}), rec.get("query", {})
    if "image_sha256" in recomputed:
        checks.append(("match image file vs record.json", recomputed["image_sha256"][:20] + "...",
                       m.get("image_sha256", "")[:20] + "...", recomputed["image_sha256"] == m.get("image_sha256")))
    if "embedding_sha256" in recomputed:
        checks.append(("query embedding file vs record.json", recomputed["embedding_sha256"][:20] + "...",
                       q.get("embedding_sha256", "")[:20] + "...", recomputed["embedding_sha256"] == q.get("embedding_sha256")))
    if "query_image_sha256" in recomputed:
        checks.append(("query image file vs record.json", recomputed["query_image_sha256"][:20] + "...",
                       q.get("image_sha256", "")[:20] + "...", recomputed["query_image_sha256"] == q.get("image_sha256")))

    # chain lookup
    receipt = b.receipt or {}
    kind = chain_kind or receipt.get("backend") or config.CHAIN_BACKEND
    if kind == "evm":
        from .chain.evm import EvmChain

        backend = EvmChain(contract_address=receipt.get("contract") or None)
        if receipt.get("chain_id") and receipt["chain_id"] != backend.chain_id:
            console.print(f"[yellow]warning: receipt is from chain {receipt['chain_id']} but RPC_URL points to "
                          f"chain {backend.chain_id}[/]")
    else:
        backend = get_backend(kind)

    rh = recomputed["record_sha256"]
    onchain = backend.get_record(rh)
    console.print(kv_table([
        ("evidence", str(path)),
        ("recomputed record hash", fmt_hash(rh)),
        ("chain", f"{getattr(backend, 'chain_name', backend.name)}"
                  + (f"  contract {backend.address}" if getattr(backend, 'address', None) else "")),
        ("lookup", "[green]record FOUND on chain[/]" if onchain else "[red]record NOT FOUND on chain[/]"),
    ], title="verification"))

    found = onchain is not None
    if found:
        checks.append(("record hash", fmt_hash(rh)[:22] + "...", fmt_hash(onchain["record_hash"])[:22] + "...",
                       onchain["record_hash"].removeprefix("0x") == rh))
        if "image_sha256" in recomputed:
            checks.append(("image hash (recomputed from file)", fmt_hash(recomputed["image_sha256"])[:22] + "...",
                           fmt_hash(onchain["image_hash"])[:22] + "...",
                           onchain["image_hash"].removeprefix("0x") == recomputed["image_sha256"]))
        if "embedding_sha256" in recomputed:
            checks.append(("face embedding hash (recomputed)", fmt_hash(recomputed["embedding_sha256"])[:22] + "...",
                           fmt_hash(onchain["face_hash"])[:22] + "...",
                           onchain["face_hash"].removeprefix("0x") == recomputed["embedding_sha256"]))
        checks.append(("post url", short(m.get("post_url", ""), 40), short(onchain["post_url"], 40),
                       m.get("post_url") == onchain["post_url"]))
        checks.append(("platform", m.get("platform", ""), onchain["platform"], m.get("platform") == onchain["platform"]))
        checks.append(("similarity", f"{m.get('similarity', 0):.4f}", f"{onchain['similarity']:.4f}",
                       abs(float(m.get("similarity", 0)) - onchain["similarity"]) < 0.0001))
        ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(onchain["timestamp"]))
        extra = f"anchored at block time {ts}"
        if onchain.get("submitter"):
            extra += f" by {onchain['submitter']}"
        if onchain.get("block_number") is not None:
            extra += f" in block {onchain['block_number']}"
        console.print(f"[dim]{extra}[/]")

    t = Table(box=box.SIMPLE_HEAD, title="field-by-field comparison", title_justify="left")
    t.add_column("check")
    t.add_column("local (recomputed now)", overflow="fold")
    t.add_column("on-chain / recorded", overflow="fold")
    t.add_column("result", justify="center")
    for name, a, c, ok in checks:
        t.add_row(name, a, c, "[green]OK[/]" if ok else "[red bold]MISMATCH[/]")
    console.print(t)

    if kind == "sim" and hasattr(backend, "validate"):
        ok_chain, msg = backend.validate()
        console.print(f"chain integrity: {'[green]' if ok_chain else '[red]'}{msg}[/]")
        found = found and ok_chain

    all_ok = found and all(ok for *_, ok in checks)
    if not quiet:
        console.print(Panel(
            "[bold green]VERIFIED[/] - the evidence bundle is byte-for-byte identical to what was anchored on chain."
            if all_ok else
            "[bold red]VERIFICATION FAILED[/] - the evidence differs from the on-chain record (or was never anchored).",
            border_style="green" if all_ok else "red"))
    return all_ok


def cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.evidence)
    if not path.exists():
        console.print(f"[red]no such evidence dir:[/] {path}")
        return 2
    return 0 if _verify_bundle(path, args.chain) else 1


def cmd_tamper_demo(args: argparse.Namespace) -> int:
    """Copy the bundle, edit one field of record.json, show that verification fails."""
    src = Path(args.evidence)
    dst = src.with_name(src.name + "-tampered")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    rec_path = dst / "record.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    before = rec["match"]["post_url"]
    rec["match"]["post_url"] = before.rstrip("/") + "/?edited=1"
    rec_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(Panel(f"copied bundle to [bold]{dst}[/] and changed match.post_url\n"
                        f"  from  {before}\n  to    {rec['match']['post_url']}\n"
                        f"Now re-running verification on the tampered copy ...", title="tamper demo",
                        border_style="yellow"))
    ok = _verify_bundle(dst, args.chain)
    if ok:
        console.print("[red]unexpected: tampered bundle verified![/]")
        return 1
    console.print("[green]Tampering detected as expected: the modified record hashes to a value the chain never saw.[/]")
    return 0


# ======================================================================= chain utils
def cmd_deploy(args: argparse.Namespace) -> int:
    from .chain.evm import EvmChain

    c = EvmChain()
    if c.contract_deployed() and not args.force:
        console.print(f"[yellow]FaceMatchRegistry already deployed on {c.chain_name} at {c.address}[/] (use --force to redeploy)")
        return 0
    with console.status(f"[cyan]deploying FaceMatchRegistry to {c.chain_name} ..."):
        info = c.deploy()
    console.print(kv_table([(k, str(v)) for k, v in info.items()], title="deployment"))
    console.print(f"[dim]saved to {config.DEPLOYMENTS_FILE}[/]")
    return 0


def cmd_chain_info(args: argparse.Namespace) -> int:
    from .chain import get_backend

    b = get_backend(args.chain)
    console.print(kv_table([(k, str(v)) for k, v in b.info().items()], title=f"chain info ({b.name})"))
    return 0


def cmd_face(args: argparse.Namespace) -> int:
    from .face import FaceEngine, draw_faces, encode_jpeg

    engine = FaceEngine()
    img = engine.load_image(args.image)
    img, faces = engine.analyze(img)
    console.print(f"faces detected: {len(faces)}")
    for i, f in enumerate(faces):
        console.print(f"  #{i} bbox={f.bbox} score={f.score:.3f} emb[:4]={[round(float(x), 3) for x in f.embedding[:4]]}")
    out = Path(args.image).with_name(Path(args.image).stem + "_faces.jpg")
    out.write_bytes(encode_jpeg(draw_faces(img, faces)))
    console.print(f"annotated image -> {out}")
    if args.compare:
        img2, faces2 = engine.analyze(engine.load_image(args.compare))
        if faces2 and faces:
            console.print(f"similarity({Path(args.image).name}, {Path(args.compare).name}) = "
                          f"{engine.similarity(faces[0].embedding, faces2[0].embedding):.4f}")
    return 0


# ============================================================================= main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="facechain", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"facechain {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def chain_opt(sp):
        sp.add_argument("--chain", choices=["evm", "sim"], default=None,
                        help="blockchain backend (default: CHAIN_BACKEND env or evm)")

    r = sub.add_parser("run", help="full pipeline: face scan -> search -> anchor -> verify")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", help="path to a photo containing the face")
    g.add_argument("--webcam", action="store_true", help="capture the face from the webcam")
    r.add_argument("--camera", type=int, default=0, help="webcam device index")
    r.add_argument("--image-url", help="skip the temp upload and use this already-public image URL for the search")
    r.add_argument("--face-index", type=int, default=0, help="which detected face to use (0 = largest)")
    r.add_argument("--min-similarity", type=float, default=config.FACE_MATCH_THRESHOLD,
                   help="SFace cosine threshold for accepting a candidate (default 0.363)")
    r.add_argument("--max-candidates", type=int, default=config.MAX_CANDIDATES)
    r.add_argument("--no-expand", action="store_true", help="do not widen the search with keyword image search")
    r.add_argument("--skip-chain", action="store_true", help="stop after building the evidence record")
    chain_opt(r)
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("verify", help="recompute hashes from an evidence folder and compare with the chain")
    v.add_argument("--evidence", required=True)
    chain_opt(v)
    v.set_defaults(func=cmd_verify)

    td = sub.add_parser("tamper-demo", help="modify a copy of the evidence and show verification failing")
    td.add_argument("--evidence", required=True)
    chain_opt(td)
    td.set_defaults(func=cmd_tamper_demo)

    d = sub.add_parser("deploy", help="deploy FaceMatchRegistry to the configured EVM chain")
    d.add_argument("--force", action="store_true")
    d.set_defaults(func=cmd_deploy)

    ci = sub.add_parser("chain-info", help="show chain / contract status")
    chain_opt(ci)
    ci.set_defaults(func=cmd_chain_info)

    f = sub.add_parser("face", help="debug: detect + embed faces in an image")
    f.add_argument("--image", required=True)
    f.add_argument("--compare", help="second image; prints similarity between the two largest faces")
    f.set_defaults(func=cmd_face)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]cancelled[/]")
        return 130
    except Exception as e:  # noqa: BLE001
        console.print(f"[red bold]error:[/] {type(e).__name__}: {e}")
        if "--debug" in sys.argv:
            raise
        return 1
