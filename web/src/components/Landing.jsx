import { useEffect, useState } from "react";
import { fileUrl, getJSON, postJSON } from "../api.js";
import { chainLine, shortHash } from "./ui.jsx";

const TICKER = ["FACE DETECT", "EMBED 128-D", "REVERSE IMAGE SEARCH", "MATCH CONFIDENCE", "SHA-256 FINGERPRINT", "ON-CHAIN ANCHOR", "RE-VERIFY"];

const STEPS = [
  { n: "01", tag: "INPUT", title: "Face scan",
    body: "A single frame is enough. Detection crops the subject, aligns landmarks and reduces the face to one normalized 128-dimension vector — the only thing that leaves this step.",
    code: "detect(frame) → align() → embed() → vec[128]" },
  { n: "02", tag: "SEARCH", title: "Open-web match",
    body: "That vector drives a live reverse-image and handle search across public sources. Candidates are scored by cosine similarity; only matches over threshold are accepted.",
    code: "search(crop) → candidates[] → score → accept > 0.363" },
  { n: "03", tag: "SEAL", title: "Chain anchor",
    body: "The accepted post — image bytes, URL, platform, score — is hashed and the digest committed on chain. Re-hash any time to prove nothing moved.",
    code: "sha256(payload) → anchor(tx) → verify(digest)" },
];

const STACK = [
  { k: "DETECT / EMBED", v: "OpenCV SFace", d: "YuNet detection, SFace embeddings, 128-D, CPU." },
  { k: "DISCOVERY", v: "Google Lens", d: "Reverse image search plus social keyword widening, face-verified candidates." },
  { k: "INTEGRITY", v: "SHA-256", d: "Canonical payload hashing over image, URL and metadata." },
  { k: "LEDGER", v: "EVM chain", d: "Solidity anchor contract; testnet, mainnet or local node." },
];

function fmtT(sec) {
  const s = Math.max(0, Number(sec) || 0);
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${(s - m * 60).toFixed(2).padStart(5, "0")}`;
}

function buildLog(run) {
  const r = run?.result || {};
  const q = r.query, s = r.search, m = r.match, rc = r.receipt, v = r.verify;
  const lines = [];
  let t = 0;
  if (q) { t += 0.12; lines.push({ t: fmtT(t), msg: `face detected · ${q.faces_in_image} subject${q.faces_in_image === 1 ? "" : "s"} · bbox ${q.face_bbox?.[2]}×${q.face_bbox?.[3]} · quality ${q.detector_score}` }); }
  if (q) { t += 0.36; lines.push({ t: fmtT(t), msg: `embedding computed · ${q.embedding_dim}-D vector · L2 normalized` }); }
  if (s) { t += 2.2; lines.push({ t: fmtT(t), msg: `reverse image search · ${s.engine} · ${s.candidates_total ?? s.total} candidates` }); }
  if (m) { t += 0.4; lines.push({ t: fmtT(t), msg: `best match accepted · cosine ${Number(m.similarity).toFixed(2)} above threshold ${s?.threshold ?? 0.363}` }); }
  if (rc) { t += 1.5; lines.push({ t: fmtT(t), msg: `digest sha256(record) written to chain · block ${rc.block_number}` }); }
  if (rc) { t += 3.3; lines.push({ t: fmtT(t), msg: rc.tx_hash ? `tx confirmed · ${shortHash(rc.tx_hash, 6)} · record immutable` : `block sealed · ${shortHash(rc.block_hash, 6)} · record immutable` }); }
  if (v && !v.all_ok) lines.push({ t: "verify", msg: v.message, bad: true });
  return lines;
}

export default function Landing({ go, status, header }) {
  const { chain, offline } = status;
  const [run, setRun] = useState(null);
  const [log, setLog] = useState([]);
  const [sealed, setSealed] = useState(null); // null unknown, true verified, false pending
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const hist = await getJSON("/runs");
        const last = hist.find((h) => h.status === "done" && h.tx_hash) || hist.find((h) => h.status === "done");
        if (!last) return;
        const j = await getJSON(`/runs/${last.id}`);
        if (cancelled) return;
        setRun(j);
        setLog(buildLog(j));
        setSealed(!!j.result?.receipt);
      } catch { /* backend offline */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const reverify = async () => {
    if (!run || busy) return;
    setBusy(true); setSealed(false);
    try {
      const v = await postJSON(`/runs/${run.id}/verify`);
      setSealed(v.all_ok);
      setLog((l) => [...l, { t: "re-check", msg: v.all_ok ? "evidence re-hashed · digest identical · seal intact" : v.message, bad: !v.all_ok }]);
    } catch (e) {
      setLog((l) => [...l, { t: "re-check", msg: e.message, bad: true }]);
    }
    setBusy(false);
  };

  const r = run?.result || {};
  const m = r.match, rc = r.receipt, h = r.hashes;
  const status_ = !run ? "NO RUN" : sealed == null ? "—" : sealed ? "VERIFIED" : "PENDING";
  const statusColor = sealed ? "#9dffc4" : "#ffd27a";
  const blockLine = rc ? `${Number(rc.block_number).toLocaleString()} · ${new Date(rc.block_timestamp * 1000).toISOString().replace("T", " ").slice(0, 19)} UTC` : "";

  return (
    <div style={{ position: "relative", width: "100%", overflow: "hidden", background: "var(--bg)" }}>
      <section className="hero">
        <div className="noise" aria-hidden="true" />
        <div className="hero__glow" aria-hidden="true" />
        <div className="grain" aria-hidden="true" />
        {header}
        <div className="hero__stage">
          <h1 className="hero__word">VERIFACE</h1>
          <div className="hero__subject">
            <img src="/hero.webp" alt="" />
            <div className="hero__scan" aria-hidden="true" />
          </div>
          <div className="hero__copy">
            <b>Proof, carried by light.</b>
            <p>One face becomes one vector. The vector finds its own traces across the open web. What it finds is sealed to a chain that cannot be talked out of it.</p>
          </div>
          <div className="hero__meta">
            <div className="flicker">128-D EMBEDDING · LIVE</div>
            <div className="dim">v1.0 / end-to-end</div>
          </div>
        </div>
        <div className="ticker" aria-hidden="true">
          <div className="ticker__track">
            {[0, 1].map((k) => (
              <div key={k}>{TICKER.map((w, i) => <span key={i}>{w}<span style={{ marginLeft: 40 }}>·</span></span>)}</div>
            ))}
          </div>
        </div>
      </section>

      <section id="pipeline" className="sec-pipeline">
        <div className="wrap">
          <div className="sec-head">
            <h2>THREE MOVES,<br />ONE PROOF</h2>
            <p>Every run is a straight line: a face becomes math, the math finds a real post, the post becomes a record no one owns.</p>
          </div>
          <div className="moves">
            {STEPS.map((s) => (
              <article className="move" key={s.n}>
                <div className="move__tag">{s.tag}</div>
                <div className="move__n">{s.n}</div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                <code>{s.code}</code>
                <div className="move__line" aria-hidden="true" />
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="ledger" className="sec-ledger">
        <div className="ledger">
          <div>
            <div className="label">LIVE RUN · #{run ? run.id : "—"}</div>
            <h2>Watch a match get sealed.</h2>
            <p>The discovered post is hashed with its URL, platform and capture time. That digest is written once. Re-verification re-hashes the evidence and compares — a single changed byte breaks the seal.</p>
            <div className="ledger__actions">
              <button className="pill pill--lav" onClick={() => go("console")}>Run pipeline</button>
              <button className="pill pill--outline" onClick={reverify} disabled={!run || busy}>{busy ? <span className="spinner" /> : null} Re-verify hash</button>
            </div>
            <div className="loglines">
              {log.map((l, i) => <div key={i} className={`logline ${l.bad ? "is-bad" : ""}`}><span>{l.t}</span><span>{l.msg}</span></div>)}
            </div>
          </div>

          <div className="ledger__cards">
            <div className="vcard">
              <div className="vcard__head"><span>MATCHED POST</span><span className="mint">{m ? `COSINE ${Number(m.similarity).toFixed(2)}` : ""}</span></div>
              <div className="vcard__body post">
                <div className="post__thumb">{m ? <img src={fileUrl(run.id, m.image_file)} alt="" /> : null}</div>
                <div style={{ minWidth: 0 }}>
                  {m ? (
                    <>
                      <div className="post__handle">{m.source || m.platform}</div>
                      <div className="post__url">{m.post_url}</div>
                      <p className="post__caption">{m.og?.og_description || m.title}</p>
                    </>
                  ) : <div className="label" style={{ paddingTop: 48 }}>NO RUN YET</div>}
                </div>
              </div>
            </div>

            <div className="record">
              <div className="record__head">
                <span>ON-CHAIN RECORD</span>
                <span className="record__status" style={{ color: statusColor }}><span className="led" />{status_}</span>
              </div>
              <div className="record__rows">
                <div><div className="record__k">DIGEST</div><div className="record__v">{h ? "0x" + h.record : "—"}</div></div>
                <div><div className="record__k">{rc?.tx_hash ? "TX HASH" : "BLOCK HASH"}</div><div className="record__v">{rc ? (rc.tx_hash || rc.block_hash) : "—"}</div></div>
                <div><div className="record__k">BLOCK</div><div className="record__v">{blockLine || "—"}</div></div>
                <div><div className="record__k">ANCHORED FIELDS</div><div className="record__v">record_sha256 · image_sha256 · face_sha256 · post_url · platform · similarity</div></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="stack" className="sec-stack">
        <div className="stack">
          {STACK.map((k) => (
            <div key={k.k}>
              <div className="stack__k">{k.k}</div>
              <div className="stack__v">{k.v}</div>
              <div className="stack__d">{k.d}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="sec-close">
        <div className="noise noise--close" aria-hidden="true" />
        <div className="sec-close__glow" aria-hidden="true" />
        <div className="close__inner">
          <div className="label">FACE → SIGNAL → SEAL</div>
          <h2>Identity you can<br />audit.</h2>
          <p>Point it at a single frame. Get back where that face already lives on the open web, and a chain receipt anyone can check without asking you for permission.</p>
          <button className="pill pill--white" onClick={() => go("console")}>Start a scan <span className="chev" /></button>
        </div>
        <footer className="foot">
          <span>VERIFACE · END-TO-END VERIFICATION PIPELINE</span>
          <span>{chainLine(chain, offline, true)}</span>
        </footer>
      </section>
    </div>
  );
}
