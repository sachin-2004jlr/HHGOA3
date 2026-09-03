import { useEffect, useState } from "react";
import { fileUrl, postJSON } from "../api.js";
import { Alert, Empty, Hash, Icon, Meter, Pill, PlatformPill, fmtTime, shortHash } from "./ui.jsx";

function Card({ icon, title, right, children, className = "" }) {
  return (
    <section className={`card enter ${className}`}>
      <div className="card__head"><h3><Icon name={icon} /> {title}</h3>{right}</div>
      <div className="card__body">{children}</div>
    </section>
  );
}

function ScanCard({ id, q }) {
  return (
    <Card icon="face" title="Step 1 · Face scan" right={<Pill tone="teal">{q.faces_in_image} face{q.faces_in_image === 1 ? "" : "s"} detected</Pill>}>
      <div className="scan">
        <div className="scan__img"><img src={fileUrl(id, q.files.annotated)} alt="input with detected faces" /></div>
        <div className="facecrop">
          <img src={fileUrl(id, q.files.face)} alt="aligned face crop" />
          <span>aligned 112×112 crop</span>
          <img src={fileUrl(id, q.files.crop)} alt="search crop" />
          <span>sent to the search</span>
        </div>
      </div>
      <dl className="kv" style={{ marginTop: 14 }}>
        <dt>bounding box</dt><dd className="num">x {q.face_bbox?.[0]}, y {q.face_bbox?.[1]}, {q.face_bbox?.[2]}×{q.face_bbox?.[3]} px · detector score {q.detector_score}</dd>
        <dt>embedding</dt><dd>SFace, {q.embedding_dim}-d, L2-normalised <Hash value={q.embedding_sha256} label="face hash" /></dd>
        <dt>models</dt><dd>{q.model?.detector} · {q.model?.recognizer}</dd>
      </dl>
    </Card>
  );
}

function SearchCard({ s }) {
  return (
    <Card icon="search" title="Step 2 · Web and social media search" right={<Pill tone="amber">{s.engine}</Pill>}>
      <div className="stats">
        <div className="stat"><small>Lens results</small><b className="num">{s.unique_pages ?? s.raw_count ?? "-"}</b></div>
        <div className="stat"><small>Widened by</small><b className="num">+{s.expanded ?? 0}</b></div>
        <div className="stat"><small>Total candidates</small><b className="num">{s.total ?? s.candidates_total ?? "-"}</b></div>
        <div className="stat"><small>On social platforms</small><b className="num">{s.social ?? "-"}</b></div>
        <div className="stat"><small>Recognised entity</small><b className="small">{s.entity_name || "not recognised"}</b></div>
      </div>
      {s.query_image_url ? <p className="hint">query image ({s.query_image_host}): <a href={s.query_image_url} target="_blank" rel="noreferrer">{s.query_image_url}</a></p> : null}
      {s.candidates?.length ? (
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table className="table">
            <thead><tr><th>#</th><th>platform</th><th>page</th><th>url</th></tr></thead>
            <tbody>
              {s.candidates.slice(0, 12).map((c, i) => (
                <tr key={c.url + i}>
                  <td className="num">{i + 1}</td>
                  <td><PlatformPill platform={c.platform} /></td>
                  <td className="cell-title" title={c.title}>{c.title || "-"}</td>
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
    <Card icon="shield" title="Step 3 · Face-verified match" right={<PlatformPill platform={m.platform} />} className="card--match">
      <div className="match">
        <figure className="match__img" style={{ margin: 0 }}>
          <img src={fileUrl(id, q.files.crop)} alt="scanned face" />
          <figcaption>your scan</figcaption>
        </figure>
        <Meter value={Number(m.similarity)} threshold={thr} />
        <figure className="match__img" style={{ margin: 0 }}>
          <img src={fileUrl(id, m.image_file)} alt="image from the matched post" />
          <figcaption>found post</figcaption>
        </figure>
      </div>
      <div className="match__info">
        <div className="match__title">{m.title || m.og?.og_title || m.post_url}</div>
        <div className="match__url">{m.post_url}</div>
        {m.og?.og_description ? <p className="match__desc">{m.og.og_description}</p> : null}
        <div className="match__row">
          <a className="btn btn--sm" href={m.post_url} target="_blank" rel="noreferrer"><Icon name="external" /> Open post</a>
          <a className="btn btn--sm btn--ghost" href={m.image_url} target="_blank" rel="noreferrer"><Icon name="image" /> Source image</a>
          {m.source ? <Pill>{m.source}</Pill> : null}
          <Pill>{m.faces_in_image} face{m.faces_in_image === 1 ? "" : "s"} in image</Pill>
        </div>
      </div>
    </Card>
  );
}

function ScanTable({ scan, matchUrl }) {
  const thr = scan.threshold;
  return (
    <Card icon="layers" title="Candidates checked" right={<Pill tone={scan.passed ? "green" : "amber"}>{scan.passed} of {scan.checked} passed ≥ {thr}</Pill>}>
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead><tr><th>similarity</th><th></th><th>platform</th><th>page</th><th>faces</th></tr></thead>
          <tbody>
            {scan.results.map((v, i) => {
              const pass = v.similarity >= thr;
              return (
                <tr key={v.url + i} className={`${pass ? "is-pass" : ""} ${v.url === matchUrl ? "is-match" : ""}`}>
                  <td><span className={`simbar num ${pass ? "is-pass" : ""}`}><span>{v.similarity >= 0 ? v.similarity.toFixed(3) : "no face"}</span><i><b style={{ width: `${Math.max(0, v.similarity) * 100}%` }} /></i></span></td>
                  <td>{v.thumbnail_url ? <img className="thumb" src={v.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : null}</td>
                  <td><PlatformPill platform={v.platform} /></td>
                  <td className="cell-title" title={v.title}><a href={v.url} target="_blank" rel="noreferrer">{v.title || v.url}</a></td>
                  <td className="num">{v.faces_found}</td>
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
    <Card icon="hash" title="Step 4 · Fingerprints (SHA-256)">
      <div className="fp">
        <div className="fp__row"><small><b>recordHash</b>canonical record.json</small><Hash value={h.record} label="record hash" /></div>
        <div className="fp__row"><small><b>imageHash</b>{h.image_file} bytes</small><Hash value={h.image} label="image hash" /></div>
        <div className="fp__row"><small><b>faceHash</b>query embedding vector</small><Hash value={h.face} label="face hash" /></div>
      </div>
    </Card>
  );
}

function Receipt({ r }) {
  const evm = r.backend === "evm";
  return (
    <Card icon="chain" title="Step 5 · On-chain receipt" right={<Pill tone={evm ? "indigo" : "amber"}>{r.chain}</Pill>}>
      <div className="receipt">
        <dl className="kv">
          {evm ? <><dt>contract</dt><dd><Hash value={r.contract} prefix={false} label="contract" /></dd></> : null}
          <dt>{evm ? "transaction" : "block hash"}</dt><dd><Hash value={evm ? r.tx_hash : r.block_hash} prefix={false} label="tx" /></dd>
          <dt>block</dt><dd className="num">#{r.block_number}{evm ? "" : ` · nonce ${r.nonce}`}</dd>
        </dl>
        <dl className="kv">
          <dt>block hash</dt><dd className="mono">{shortHash(r.block_hash, 12)}</dd>
          <dt>timestamp</dt><dd>{fmtTime(new Date(r.block_timestamp * 1000).toISOString())}</dd>
          {evm ? <><dt>gas used</dt><dd className="num">{r.gas_used}</dd><dt>submitter</dt><dd className="mono">{shortHash(r.submitter, 8)}</dd></> : <><dt>ledger</dt><dd className="mono">{r.file}</dd></>}
        </dl>
      </div>
      {r.explorer_tx ? <p style={{ marginTop: 12 }}><a className="btn btn--sm" href={r.explorer_tx} target="_blank" rel="noreferrer"><Icon name="external" /> View on block explorer</a></p> : null}
    </Card>
  );
}

function Checks({ v }) {
  return (
    <div className="checks">
      <table className="table">
        <thead><tr><th>check</th><th>local (recomputed now)</th><th>on-chain / recorded</th><th>result</th></tr></thead>
        <tbody>
          {v.checks.map((c, i) => (
            <tr key={i}>
              <td>{c.name}{c.kind === "chain" ? <Pill tone="indigo" className="pill--sm" >chain</Pill> : null}</td>
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
    <Card icon="shield" title="Step 6 · Verification against the chain"
      right={<div className="actions">
        <button className="btn btn--sm" onClick={() => run("verify")} disabled={!!busy}>{busy === "verify" ? <span className="spinner" /> : <Icon name="refresh" />} Re-verify now</button>
        <button className="btn btn--sm btn--danger" onClick={() => run("tamper")} disabled={!!busy}>{busy === "tamper" ? <span className="spinner" /> : <Icon name="alert" />} Tamper test</button>
      </div>}>
      {err ? <Alert tone="red">{err}</Alert> : null}
      {v ? (
        <>
          <div className={`verdict ${v.all_ok ? "verdict--ok" : "verdict--bad"}`}>
            <Icon name={v.all_ok ? "check" : "x"} />
            <div>{v.all_ok ? "VERIFIED" : v.found ? "MISMATCH" : "NOT FOUND ON CHAIN"}<small>{v.message}{v.anchored_at ? ` Anchored ${fmtTime(v.anchored_at)}.` : ""}</small></div>
          </div>
          <dl className="kv" style={{ marginTop: 12 }}>
            <dt>record hash</dt><dd><Hash value={v.record_hash} label="record hash" /></dd>
            <dt>chain</dt><dd>{v.chain?.name}{v.chain?.contract ? <> · <span className="mono">{v.chain.contract}</span></> : null}</dd>
            {v.chain_integrity ? <><dt>ledger integrity</dt><dd className={v.chain_integrity.ok ? "ok" : "bad"}>{v.chain_integrity.message}</dd></> : null}
            {v.warning ? <><dt>warning</dt><dd className="bad">{v.warning}</dd></> : null}
          </dl>
          <Checks v={v} />
        </>
      ) : <p className="hint">Not verified yet. Click Re-verify to recompute the hashes from the evidence files and look the record up on the chain.</p>}

      {tamper ? (
        <div style={{ marginTop: 18 }} className="enter">
          <Alert tone="amber" icon="alert">
            Tamper test: copied the evidence and changed <code>{tamper.tamper.field}</code> from <code>{tamper.tamper.before}</code> to <code>{tamper.tamper.after}</code>, then verified the copy.
          </Alert>
          <div className={`verdict ${tamper.verify.all_ok ? "verdict--ok" : "verdict--bad"}`} style={{ marginTop: 10 }}>
            <Icon name={tamper.verify.all_ok ? "check" : "x"} />
            <div>{tamper.verify.all_ok ? "UNEXPECTED: tampered copy verified" : "TAMPERING DETECTED"}<small>{tamper.verify.message}</small></div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

export default function Results({ job }) {
  if (!job) {
    return (
      <section className="card">
        <Empty icon="face" title="Nothing scanned yet">Upload a photo or capture one with the webcam. Each step of the pipeline appears here as it completes.</Empty>
      </section>
    );
  }
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
        <Alert tone="amber">
          <b>No candidate reached the face-match threshold ({thr}).</b> {r.best ? <>Best was {Number(r.best.similarity).toFixed(3)} on <a href={r.best.url} target="_blank" rel="noreferrer">{r.best.url}</a>. </> : null}
          Try a clearer, front-facing photo, or lower the threshold in Advanced options.
        </Alert>
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
