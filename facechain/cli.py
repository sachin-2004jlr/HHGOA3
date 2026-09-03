"""Command-line interface (the web UI in web/ is the primary front end).

    python -m facechain run --image photo.jpg        # full pipeline
    python -m facechain run --webcam                 # live face scan
    python -m facechain verify --evidence evidence/<run_id>
    python -m facechain tamper-demo --evidence evidence/<run_id>
    python -m facechain deploy | chain-info | face --image X
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, config

console = Console(highlight=False, emoji=False)


def kv_table(rows, title=None) -> Table:
    t = Table(show_header=False, box=box.SIMPLE, title=title, title_justify="left", padding=(0, 1))
    t.add_column(style="bold dim", no_wrap=True)
    t.add_column(overflow="fold")
    for k, v in rows:
        t.add_row(str(k), str(v))
    return t


def short(s: str, n: int = 70) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 3] + "..."


# =============================================================================== run
def cmd_run(args: argparse.Namespace) -> int:
    from .pipeline import NoMatchError, Options, PipelineError, run_pipeline

    console.print(Panel.fit(f"[bold]facechain v{__version__}[/]\nface scan -> reverse image search -> "
                            f"face-verified social post -> blockchain anchor", border_style="cyan"))
    image_path, image_bytes = None, None
    if args.webcam:
        from .face import FaceEngine, encode_jpeg

        image_bytes = encode_jpeg(FaceEngine().capture_webcam(args.camera), 95)
    else:
        image_path = Path(args.image)
        if not image_path.exists():
            console.print(f"[red]image not found:[/] {image_path}")
            return 2

    def emit(step, status, title, data=None, message=None):
        if status == "start":
            console.rule(f"[bold cyan]STEP {step}[/]  [bold]{title}[/]", style="cyan")
        elif status == "progress":
            if data and "total" in data:
                console.print(f"  [dim]{data['done']}/{data['total']} candidates checked[/]", end="\r")
            elif message:
                console.print(f"  [dim]{message}[/]")
        elif status == "done":
            if message:
                console.print(f"  [green]{message}[/]")
            _render_step(step, data)
        elif status == "error":
            console.print(f"  [red]{message}[/]")

    opts = Options(min_similarity=args.min_similarity, max_candidates=args.max_candidates,
                   expand=not args.no_expand, chain=args.chain or "auto", face_index=args.face_index,
                   image_url=args.image_url, skip_chain=args.skip_chain)
    try:
        result = run_pipeline(image_path=image_path, image_bytes=image_bytes, options=opts, emit=emit,
                              source_label=str(image_path) if image_path else "webcam")
    except NoMatchError as e:
        console.print(Panel(f"[red bold]{e}[/]\nTry a clearer photo, --min-similarity 0.30 or --max-candidates 100.",
                            border_style="red"))
        return 4
    except PipelineError as e:
        console.print(Panel(f"[red bold]step {e.step} failed:[/] {e}", border_style="red"))
        return 3

    ok = result["status"] == "done"
    console.print(Panel(
        f"evidence: [bold]{result['evidence_dir']}[/]\nre-verify any time with:\n"
        f"  [bold cyan]python -m facechain verify --evidence evidence/{result['run_id']}[/]\n"
        f"[dim]total time {result.get('elapsed', 0)}s[/]",
        title="[green bold]PIPELINE COMPLETE[/]" if ok else "[red bold]FINISHED WITH ERRORS[/]",
        border_style="green" if ok else "red"))
    return 0 if ok else 5


def _render_step(step: int, d: dict | None) -> None:
    if not d:
        return
    if step == 1:
        console.print(kv_table([("faces", f"{d['faces_in_image']} (using #{d['face_index']})"),
                                ("bbox", f"{tuple(d['face_bbox'])} score={d['detector_score']}"),
                                ("embedding sha256", d["embedding_sha256"])]))
    elif step == 2:
        console.print(f"  engine={d['engine']} lens results={d['unique_pages']} expanded=+{d['expanded']} "
                      f"total={d['total']} social={d['social']} entity={d['entity_name'] or '-'}")
        t = Table(box=box.SIMPLE_HEAD)
        t.add_column("platform", style="magenta")
        t.add_column("title", max_width=48, overflow="fold")
        t.add_column("url", max_width=60, overflow="fold", style="dim")
        for c in d["candidates"][:10]:
            t.add_row(c["platform"], short(c["title"], 48), short(c["url"], 60))
        console.print(t)
    elif step == 3:
        t = Table(title=f"face similarity (threshold {d['threshold']})", box=box.SIMPLE_HEAD, title_justify="left")
        t.add_column("sim", justify="right")
        t.add_column("platform", style="magenta")
        t.add_column("title", max_width=44, overflow="fold")
        t.add_column("url", max_width=58, overflow="fold", style="dim")
        for v in d["results"][:12]:
            color = "green" if v["similarity"] >= d["threshold"] else "red"
            t.add_row(f"[{color}]{v['similarity']:+.3f}[/]", v["platform"], short(v["title"], 44), short(v["url"], 58))
        console.print(t)
        m = d.get("match")
        if m:
            console.print(Panel(f"[bold green]MATCH[/] similarity={m['similarity']} platform=[magenta]{m['platform']}[/]\n"
                                f"[bold]{m['title']}[/]\n{m['post_url']}", title="Discovered social-media post",
                                border_style="green"))
    elif step == 4:
        console.print(kv_table([("record_hash", "0x" + d["record"]), ("image_hash", "0x" + d["image"]),
                                ("face_hash", "0x" + d["face"])]))
    elif step == 5:
        console.print(kv_table([(k, v) for k, v in d.items() if v is not None and k != "backend"],
                               title="on-chain receipt"))
    elif step == 6:
        _render_verify(d)


def _render_verify(v: dict) -> None:
    chain = v.get("chain") or {}
    console.print(kv_table([("evidence", v["evidence"]), ("record hash", v["record_hash"]),
                            ("chain", f"{chain.get('name', '?')} {chain.get('contract') or ''}"),
                            ("lookup", "[green]record FOUND on chain[/]" if v["found"] else "[red]NOT FOUND[/]")]))
    t = Table(box=box.SIMPLE_HEAD, title="field-by-field comparison", title_justify="left")
    t.add_column("check")
    t.add_column("local (recomputed now)", overflow="fold", max_width=30)
    t.add_column("on-chain / recorded", overflow="fold", max_width=30)
    t.add_column("result", justify="center")
    for c in v["checks"]:
        t.add_row(c["name"], short(c["local"], 28), short(c["remote"], 28),
                  "[green]OK[/]" if c["ok"] else "[red bold]MISMATCH[/]")
    console.print(t)
    if v.get("chain_integrity"):
        ci = v["chain_integrity"]
        console.print(f"chain integrity: {'[green]' if ci['ok'] else '[red]'}{ci['message']}[/]")
    console.print(Panel(v["message"], border_style="green" if v["all_ok"] else "red"))


# ============================================================================ verify
def cmd_verify(args: argparse.Namespace) -> int:
    from .verify import verify_bundle

    path = Path(args.evidence)
    if not path.exists():
        console.print(f"[red]no such evidence dir:[/] {path}")
        return 2
    v = verify_bundle(path, args.chain)
    _render_verify(v)
    return 0 if v["all_ok"] else 1


def cmd_tamper_demo(args: argparse.Namespace) -> int:
    from .verify import tamper_copy, verify_bundle

    info = tamper_copy(args.evidence)
    console.print(Panel(f"copied bundle to [bold]{info['dir']}[/] and changed {info['field']}\n"
                        f"  from  {info['before']}\n  to    {info['after']}", title="tamper demo", border_style="yellow"))
    v = verify_bundle(info["dir"], args.chain)
    _render_verify(v)
    if v["all_ok"]:
        console.print("[red]unexpected: tampered bundle verified![/]")
        return 1
    console.print("[green]Tampering detected: the modified record hashes to a value the chain never saw.[/]")
    return 0


# ======================================================================= chain utils
def cmd_deploy(args: argparse.Namespace) -> int:
    from .chain.evm import EvmChain

    c = EvmChain()
    if c.contract_deployed() and not args.force:
        console.print(f"[yellow]already deployed on {c.chain_name} at {c.address}[/] (use --force to redeploy)")
        return 0
    with console.status(f"[cyan]deploying FaceMatchRegistry to {c.chain_name} ..."):
        info = c.deploy()
    console.print(kv_table(list(info.items()), title="deployment"))
    return 0


def cmd_chain_info(args: argparse.Namespace) -> int:
    from .chain import get_backend

    b = get_backend(args.chain or "auto")
    console.print(kv_table(list(b.info().items()), title=f"chain info ({b.name})"))
    return 0


def cmd_face(args: argparse.Namespace) -> int:
    from .face import FaceEngine, draw_faces, encode_jpeg

    engine = FaceEngine()
    img, faces = engine.analyze(engine.load_image(args.image))
    console.print(f"faces detected: {len(faces)}")
    for i, f in enumerate(faces):
        console.print(f"  #{i} bbox={f.bbox} score={f.score:.3f}")
    out = Path(args.image).with_name(Path(args.image).stem + "_faces.jpg")
    out.write_bytes(encode_jpeg(draw_faces(img, faces)))
    console.print(f"annotated image -> {out}")
    if args.compare:
        _, faces2 = engine.analyze(engine.load_image(args.compare))
        if faces2 and faces:
            console.print(f"similarity = {engine.similarity(faces[0].embedding, faces2[0].embedding):.4f}")
    return 0


# ============================================================================= main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="facechain", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"facechain {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def chain_opt(sp):
        sp.add_argument("--chain", choices=["auto", "evm", "sim"], default=None,
                        help="blockchain backend (default auto: EVM node if reachable, else simulated chain)")

    r = sub.add_parser("run", help="full pipeline: face scan -> search -> anchor -> verify")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", help="path to a photo containing the face")
    g.add_argument("--webcam", action="store_true", help="capture the face from the webcam")
    r.add_argument("--camera", type=int, default=0)
    r.add_argument("--image-url", help="skip the temp upload and use this already-public image URL")
    r.add_argument("--face-index", type=int, default=0, help="which detected face to use (0 = largest)")
    r.add_argument("--min-similarity", type=float, default=config.FACE_MATCH_THRESHOLD)
    r.add_argument("--max-candidates", type=int, default=config.MAX_CANDIDATES)
    r.add_argument("--no-expand", action="store_true", help="do not widen the search with keyword image search")
    r.add_argument("--skip-chain", action="store_true")
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
    f.add_argument("--compare")
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
