import { useEffect, useState } from "react";
import { fileUrl, postJSON } from "../api.js";
import { Alert, Hash, Icon, Meter, PlatformTag, Tag, engineLabel, fmtTime } from "./ui.jsx";

function Card({ title, right, children }) {
  return (
    <section className="card enter">
      <div className="card__head"><h3>{title}</h3>{right}</div>
      <div className="card__body">{children}</div>
    </section>
  );
}

function FaceCard({ id, q }) {
  return (
    <Card title="01 · Face scan" right={<Tag tone="lav">{q.faces_in_image} face{q.faces_in_image === 1 ? "" : "s"} detected</Tag>}>
      <div className="scan">
        <div className="scan__img"><img src={fileUrl(id, q.files.annotated)} alt="" /></div>
        <div className="facecrop">
          <img src={fileUrl(id, q.files.face)} alt="" />
          <span>aligned face</span>
        </div>
      </div>
      <dl className="kv" style={{ marginTop: 16 }}>
        <dt>encoding</dt><dd>{q.model?.recognizer} · {q.embedding_dim}-D vector <Hash value={q.embedding_sha256} label="face hash" /></dd>
      </dl>
    </Card>
  );
}

function PostCard({ id, q, s, m, scan, thr }) {
  return (
    <Card title="02 · Matching social media post" right={<PlatformTag platform={m.platform} />}>
      <div className="match">
        <figure className="match__img"><img src={fileUrl(id, q.files.crop)} alt="" /><figcaption>Scan</figcaption></figure>
        <Meter value={Number(m.similarity)} threshold={thr} />
        <figure className="match__img"><img src={fileUrl(id, m.image_file)} alt="" /><figcaption>Post</figcaption></figure>
      </div>
      <div className="match__info">
        <div className="match__title">{m.title || m.og?.og_title || m.post_url}</div>
        <div className="match__url">{m.post_url}</div>
        <div className="match__row">
          <a className="pill pill--outline pill--xs" href={m.post_url} target="_blank" rel="noreferrer">Open post <Icon name="external" style={{ width: 12, height: 12 }} /></a>
          {m.source ? <Tag>{m.source}</Tag> : null}
        </div>
      </div>
      {s ? (
        <div className="stats" style={{ marginTop: 18 }}>
          <div className="stat"><small>Search</small><b className="small">{engineLabel(s.engine)}</b></div>
          <div className="stat"><small>Identified as</small><b className="small">{s.entity_name || "—"}</b></div>
          <div className="stat"><small>Candidates checked</small><b className="num">{scan?.checked ?? s.total ?? "—"}</b></div>
          <div className="stat"><small>Faces matched</small><b className="num">{scan?.passed ?? "—"}</b></div>
        </div>
      ) : null}
    </Card>
  );
}

function Checks({ v }) {
  return (
    <div className="checks"><table className="table">
      <thead><tr><th>check</th><th>recomputed now</th><th>on-chain</th><th></th></tr></thead>
      <tbody>
        {v.checks.map((c, i) => (
          <tr key={i}>
            <td>{c.name}</td>
            <td className="cell-url" title={c.local}>{c.local}</td>
            <td className="cell-url" title={c.remote}>{c.remote}</td>
            <td>{c.ok ? <span className="ok">OK</span> : <span className="bad">MISMATCH</span>}</td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}

function ChainCard({ id, h, r, initial }) {
  const [v, setV] = useState(initial || null);
  const [tamper, setTamper] = useState(null);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { setV(initial || null); setTamper(null); setErr(null); }, [id, initial]);
  const evm = r.backend === "evm";

  const run = async (kind) => {
    setBusy(kind); setErr(null);
    try {
      if (kind === "verify") { setV(await postJSON(`/runs/${id}/verify`)); setTamper(null); }
      else setTamper(await postJSON(`/runs/${id}/tamper`));
    } catch (e) { setErr(e.message); }
    setBusy(null);
  };

  return (
    <Card title="03 · Blockchain record" right={<Tag tone={evm ? "lav" : "amber"}>{r.chain}</Tag>}>
      <div className="fp">
        <div className="fp__row"><small>record digest<b>sha256(record.json)</b></small><Hash value={h.record} label="record hash" /></div>
        <div className="fp__row"><small>post image<b>sha256({h.image_file})</b></small><Hash value={h.image} label="image hash" /></div>
        <div className="fp__row"><small>face vector<b>sha256(embedding)</b></small><Hash value={h.face} label="face hash" /></div>
      </div>
      <div className="receipt" style={{ marginTop: 18 }}>
        <dl className="kv">
          {evm ? <><dt>contract</dt><dd><Hash value={r.contract} prefix={false} label="contract" /></dd></> : null}
          <dt>{evm ? "tx hash" : "block hash"}</dt><dd><Hash value={evm ? r.tx_hash : r.block_hash} prefix={false} label="tx" /></dd>
        </dl>
        <dl className="kv">
          <dt>block</dt><dd className="num mono">{Number(r.block_number).toLocaleString()}</dd>
          <dt>time</dt><dd className="mono">{new Date(r.block_timestamp * 1000).toISOString().replace("T", " ").slice(0, 19)} UTC</dd>
          {r.explorer_tx ? <><dt>explorer</dt><dd><a href={r.explorer_tx} target="_blank" rel="noreferrer">{r.explorer_tx}</a></dd></> : null}
        </dl>
      </div>

      <div className="actions" style={{ marginTop: 18 }}>
        <button className="pill pill--lav pill--xs" onClick={() => run("verify")} disabled={!!busy}>{busy === "verify" ? <span className="spinner" /> : null} Re-verify against chain</button>
        <button className="pill pill--outline pill--xs" onClick={() => run("tamper")} disabled={!!busy}>{busy === "tamper" ? <span className="spinner" /> : null} Tamper test</button>
      </div>
      {err ? <div style={{ marginTop: 12 }}><Alert tone="red">{err}</Alert></div> : null}
      {v ? (
        <div style={{ marginTop: 14 }}>
          <div className={`verdict ${v.all_ok ? "verdict--ok" : "verdict--bad"}`}>
            <Icon name={v.all_ok ? "check" : "x"} />
            <div>{v.all_ok ? "Verified" : v.found ? "Mismatch" : "Not found on chain"}<small>{v.message}{v.anchored_at ? ` · anchored ${fmtTime(v.anchored_at)}` : ""}</small></div>
          </div>
          <Checks v={v} />
        </div>
      ) : null}
      {tamper ? (
        <div style={{ marginTop: 14 }} className="enter">
          <div className={`verdict ${tamper.verify.all_ok ? "verdict--ok" : "verdict--bad"}`}>
            <Icon name={tamper.verify.all_ok ? "check" : "x"} />
            <div>{tamper.verify.all_ok ? "Tampered copy verified" : "Tampering detected"}<small>{tamper.tamper.field} changed to {tamper.tamper.after.slice(-24)} · {tamper.verify.message}</small></div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

export default function Results({ job }) {
  if (!job) return <section className="card"><div className="empty">No scan yet</div></section>;
  const r = job.result || {};
  const st = job.steps || {};
  const id = job.id;
  const q = r.query || st["1"]?.data;
  const s = r.search || st["3"]?.data?.search || st["2"]?.data;
  const scan = r.scan || st["3"]?.data;
  const m = r.match || st["3"]?.data?.match;
  const h = r.hashes || st["4"]?.data;
  const rc = r.receipt || st["5"]?.data;
  const v = r.verify || st["6"]?.data;
  const thr = scan?.threshold ?? job.options?.min_similarity ?? 0.363;

  return (
    <div className="results">
      {job.status === "failed" ? <Alert tone="red">{job.error}</Alert> : null}
      {job.status === "no_match" ? (
        <Alert tone="amber">No matching post: no candidate reached the face-match threshold {thr}{r.best ? <>. Closest {Number(r.best.similarity).toFixed(3)}: <a href={r.best.url} target="_blank" rel="noreferrer">{r.best.url}</a></> : null}</Alert>
      ) : null}
      {q ? <FaceCard id={id} q={q} /> : null}
      {m && q ? <PostCard id={id} q={q} s={s} m={m} scan={scan} thr={thr} /> : null}
      {h && rc ? <ChainCard id={id} h={h} r={rc} initial={v} /> : null}
    </div>
  );
}
