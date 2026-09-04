import { useEffect, useState } from "react";
import { fileUrl, postJSON } from "../api.js";
import { Alert, Hash, Icon, Meter, PlatformTag, Tag, engineLabel, fmtTime, shortHash } from "./ui.jsx";

function Card({ title, right, children }) {
  return (
    <section className="card enter">
      <div className="card__head"><h3>{title}</h3>{right}</div>
      <div className="card__body">{children}</div>
    </section>
  );
}

function ScanCard({ id, q }) {
  return (
    <Card title="01 · Face scan" right={<Tag tone="lav">{q.faces_in_image} face{q.faces_in_image === 1 ? "" : "s"}</Tag>}>
      <div className="scan">
        <div className="scan__img"><img src={fileUrl(id, q.files.annotated)} alt="" /></div>
        <div className="facecrop">
          <img src={fileUrl(id, q.files.face)} alt="" />
          <span>aligned 112</span>
          <img src={fileUrl(id, q.files.crop)} alt="" />
          <span>search crop</span>
        </div>
      </div>
      <dl className="kv" style={{ marginTop: 16 }}>
        <dt>bbox</dt><dd className="num">{q.face_bbox?.[0]}, {q.face_bbox?.[1]} · {q.face_bbox?.[2]}×{q.face_bbox?.[3]} · q {q.detector_score}</dd>
        <dt>embedding</dt><dd>{q.embedding_dim}-D · L2 <Hash value={q.embedding_sha256} label="face hash" /></dd>
        <dt>models</dt><dd>{q.model?.detector} · {q.model?.recognizer}</dd>
      </dl>
    </Card>
  );
}

function SearchCard({ s }) {
  return (
    <Card title="02 · Open-web search" right={<Tag tone="amber">{engineLabel(s.engine)}</Tag>}>
      <div className="stats">
        <div className="stat"><small>Search hits</small><b className="num">{s.unique_pages ?? s.raw_count ?? "—"}</b></div>
        <div className="stat"><small>Widened</small><b className="num">+{s.expanded ?? 0}</b></div>
        <div className="stat"><small>Candidates</small><b className="num">{s.total ?? s.candidates_total ?? "—"}</b></div>
        <div className="stat"><small>Social</small><b className="num">{s.social ?? "—"}</b></div>
        <div className="stat"><small>Entity</small><b className="small">{s.entity_name || "—"}</b></div>
      </div>
      {s.expanded_by && Object.keys(s.expanded_by).length ? (
        <div className="match__row" style={{ marginTop: 12 }}>
          {Object.entries(s.expanded_by).map(([k, v]) => (
            <Tag key={k} tone={typeof v === "number" ? (v ? "lav" : undefined) : "rose"}>{k} · {typeof v === "number" ? v : "error"}</Tag>
          ))}
        </div>
      ) : null}
      {s.candidates?.length ? (
        <div style={{ overflowX: "auto", marginTop: 14 }}>
          <table className="table">
            <thead><tr><th>#</th><th>platform</th><th>page</th><th>url</th></tr></thead>
            <tbody>
              {s.candidates.slice(0, 12).map((c, i) => (
                <tr key={c.url + i}>
                  <td className="num mono">{i + 1}</td>
                  <td><PlatformTag platform={c.platform} /></td>
                  <td className="cell-title" title={c.title}>{c.title || "—"}</td>
                  <td className="cell-url"><a href={c.url} target="_blank" rel="noreferrer">{c.url}</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}

function MatchCard({ id, q, m, thr }) {
  return (
    <Card title="03 · Match" right={<PlatformTag platform={m.platform} />}>
      <div className="match">
        <figure className="match__img"><img src={fileUrl(id, q.files.crop)} alt="" /><figcaption>Scan</figcaption></figure>
        <Meter value={Number(m.similarity)} threshold={thr} />
        <figure className="match__img"><img src={fileUrl(id, m.image_file)} alt="" /><figcaption>Post</figcaption></figure>
      </div>
      <div className="match__info">
        <div className="match__title">{m.title || m.og?.og_title || m.post_url}</div>
        <div className="match__url">{m.post_url}</div>
        {m.og?.og_description ? <p className="match__desc">{m.og.og_description}</p> : null}
        <div className="match__row">
          <a className="pill pill--outline pill--xs" href={m.post_url} target="_blank" rel="noreferrer">Open post <Icon name="external" style={{ width: 12, height: 12 }} /></a>
          <a className="pill pill--outline pill--xs" href={m.image_url} target="_blank" rel="noreferrer">Source image</a>
          {m.source ? <Tag>{m.source}</Tag> : null}
        </div>
      </div>
    </Card>
  );
}

function ScanTable({ scan, matchUrl }) {
  const thr = scan.threshold;
  return (
    <Card title="Candidates" right={<Tag tone={scan.passed ? "mint" : "amber"}>{scan.passed} / {scan.checked} ≥ {thr}</Tag>}>
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead><tr><th>cosine</th><th></th><th>platform</th><th>page</th><th>faces</th></tr></thead>
          <tbody>
            {scan.results.map((v, i) => {
              const pass = v.similarity >= thr;
              return (
                <tr key={v.url + i} className={`${pass ? "is-pass" : ""} ${v.url === matchUrl ? "is-match" : ""}`}>
                  <td><span className={`simbar num ${pass ? "is-pass" : ""}`}><span>{v.similarity >= 0 ? v.similarity.toFixed(3) : "—"}</span><i><b style={{ width: `${Math.max(0, v.similarity) * 100}%` }} /></i></span></td>
                  <td>{v.thumbnail_url ? <img className="thumb" src={v.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : null}</td>
                  <td><PlatformTag platform={v.platform} /></td>
                  <td className="cell-title" title={v.title}><a href={v.url} target="_blank" rel="noreferrer">{v.title || v.url}</a></td>
                  <td className="num mono">{v.faces_found}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Fingerprints({ h }) {
  return (
    <Card title="04 · Digest">
      <div className="fp">
        <div className="fp__row"><small>record<b>{h.record_file}</b></small><Hash value={h.record} label="record hash" /></div>
        <div className="fp__row"><small>image<b>{h.image_file}</b></small><Hash value={h.image} label="image hash" /></div>
        <div className="fp__row"><small>face<b>embedding</b></small><Hash value={h.face} label="face hash" /></div>
      </div>
    </Card>
  );
}

function Receipt({ r }) {
  const evm = r.backend === "evm";
  return (
    <Card title="05 · On-chain record" right={<Tag tone={evm ? "lav" : "amber"}>{r.chain}</Tag>}>
      <div className="receipt">
        <dl className="kv">
          {evm ? <><dt>contract</dt><dd><Hash value={r.contract} prefix={false} label="contract" /></dd></> : null}
          <dt>{evm ? "tx hash" : "block hash"}</dt><dd><Hash value={evm ? r.tx_hash : r.block_hash} prefix={false} label="tx" /></dd>
          <dt>block</dt><dd className="num mono">{Number(r.block_number).toLocaleString()}{evm ? "" : ` · nonce ${r.nonce}`}</dd>
        </dl>
        <dl className="kv">
          <dt>block hash</dt><dd className="mono">{shortHash(r.block_hash, 10)}</dd>
          <dt>time</dt><dd className="mono">{new Date(r.block_timestamp * 1000).toISOString().replace("T", " ").slice(0, 19)} UTC</dd>
          {evm ? <><dt>gas</dt><dd className="num mono">{r.gas_used}</dd><dt>submitter</dt><dd className="mono">{shortHash(r.submitter, 6)}</dd></> : null}
        </dl>
      </div>
      {r.explorer_tx ? <p style={{ marginTop: 14 }}><a className="pill pill--outline pill--xs" href={r.explorer_tx} target="_blank" rel="noreferrer">Explorer</a></p> : null}
    </Card>
  );
}

function Checks({ v }) {
  return (
    <div className="checks">
      <table className="table">
        <thead><tr><th>check</th><th>recomputed</th><th>on-chain</th><th></th></tr></thead>
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
      </table>
    </div>
  );
}

function VerifyPanel({ id, initial }) {
  const [v, setV] = useState(initial || null);
  const [tamper, setTamper] = useState(null);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { setV(initial || null); setTamper(null); setErr(null); }, [id, initial]);

  const run = async (kind) => {
    setBusy(kind); setErr(null);
    try {
      if (kind === "verify") { setV(await postJSON(`/runs/${id}/verify`)); setTamper(null); }
      else setTamper(await postJSON(`/runs/${id}/tamper`));
    } catch (e) { setErr(e.message); }
    setBusy(null);
  };

  return (
    <Card title="06 · Seal"
      right={<div className="actions">
        <button className="pill pill--outline pill--xs" onClick={() => run("verify")} disabled={!!busy}>{busy === "verify" ? <span className="spinner" /> : null} Re-verify hash</button>
        <button className="pill pill--outline pill--xs" onClick={() => run("tamper")} disabled={!!busy}>{busy === "tamper" ? <span className="spinner" /> : null} Tamper test</button>
      </div>}>
      {err ? <Alert tone="red">{err}</Alert> : null}
      {v ? (
        <>
          <div className={`verdict ${v.all_ok ? "verdict--ok" : "verdict--bad"}`}>
            <Icon name={v.all_ok ? "check" : "x"} />
            <div>{v.all_ok ? "Verified" : v.found ? "Mismatch" : "Not found on chain"}<small>{v.message}{v.anchored_at ? ` · anchored ${fmtTime(v.anchored_at)}` : ""}</small></div>
          </div>
          <dl className="kv" style={{ marginTop: 14 }}>
            <dt>digest</dt><dd><Hash value={v.record_hash} label="record hash" /></dd>
            <dt>chain</dt><dd>{v.chain?.name}{v.chain?.contract ? <> · <span className="mono">{v.chain.contract}</span></> : null}</dd>
            {v.chain_integrity ? <><dt>ledger</dt><dd className={v.chain_integrity.ok ? "ok" : "bad"}>{v.chain_integrity.message}</dd></> : null}
            {v.warning ? <><dt>warning</dt><dd className="bad">{v.warning}</dd></> : null}
          </dl>
          <Checks v={v} />
        </>
      ) : null}
      {tamper ? (
        <div style={{ marginTop: 18 }} className="enter">
          <div className={`verdict ${tamper.verify.all_ok ? "verdict--ok" : "verdict--bad"}`}>
            <Icon name={tamper.verify.all_ok ? "check" : "x"} />
            <div>{tamper.verify.all_ok ? "Tampered copy verified" : "Tampering detected"}<small>{tamper.tamper.field}: {tamper.tamper.before} → {tamper.tamper.after}</small></div>
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
  const s = r.search || st["2"]?.data;
  const scan = r.scan || (st["3"]?.data && { ...st["3"].data });
  const m = r.match || st["3"]?.data?.match;
  const h = r.hashes || st["4"]?.data;
  const rc = r.receipt || st["5"]?.data;
  const v = r.verify || st["6"]?.data;
  const thr = scan?.threshold ?? job.options?.min_similarity ?? 0.363;

  return (
    <div className="results">
      {job.status === "failed" ? <Alert tone="red">{job.error}</Alert> : null}
      {job.status === "no_match" ? (
        <Alert tone="amber">No candidate above threshold {thr}{r.best ? <>. Best {Number(r.best.similarity).toFixed(3)}: <a href={r.best.url} target="_blank" rel="noreferrer">{r.best.url}</a></> : null}</Alert>
      ) : null}
      {q ? <ScanCard id={id} q={q} /> : null}
      {s ? <SearchCard s={s} /> : null}
      {m && q ? <MatchCard id={id} q={q} m={m} thr={thr} /> : null}
      {scan?.results?.length ? <ScanTable scan={scan} matchUrl={m?.post_url} /> : null}
      {h ? <Fingerprints h={h} /> : null}
      {rc ? <Receipt r={rc} /> : null}
      {rc ? <VerifyPanel id={id} initial={v} /> : null}
    </div>
  );
}
