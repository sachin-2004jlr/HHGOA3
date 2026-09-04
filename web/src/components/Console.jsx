import { useCallback, useEffect, useRef, useState } from "react";
import { createRun, del, getJSON } from "../api.js";
import InputPanel from "./InputPanel.jsx";
import PipelineRail from "./PipelineRail.jsx";
import Results from "./Results.jsx";
import History from "./History.jsx";
import { Alert, Icon, Tag, shortHash } from "./ui.jsx";

export default function Console({ status, header }) {
  const { health, chain, offline, refreshChain } = status;
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const timer = useRef(null);

  const loadHistory = useCallback(async () => {
    try { setHistory(await getJSON("/runs")); } catch { /* backend offline */ }
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  useEffect(() => {
    const m = /run=([A-Za-z0-9_-]+)/.exec(window.location.hash);
    if (m) setJobId(m[1]);
  }, []);
  useEffect(() => {
    if (!jobId) return;
    window.history.replaceState(null, "", `#console?run=${jobId}`);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return undefined;
    let cancelled = false;
    const tick = async () => {
      try {
        const j = await getJSON(`/runs/${jobId}`);
        if (cancelled) return;
        setJob(j);
        if (j.status === "queued" || j.status === "running") timer.current = setTimeout(tick, 700);
        else { loadHistory(); refreshChain(); }
      } catch (e) {
        if (!cancelled) {
          setError(e.message);
          setJobId(null);
          window.history.replaceState(null, "", "#console");
        }
      }
    };
    tick();
    return () => { cancelled = true; clearTimeout(timer.current); };
  }, [jobId, loadHistory, refreshChain]);

  const busy = !!job && (job.status === "queued" || job.status === "running");

  const onSubmit = async (file, opts, source) => {
    setError(null);
    setJob(null);
    try {
      const { id } = await createRun(file, opts, source);
      setJobId(id);
    } catch (e) {
      setError(e.message);
    }
  };
  const onSelect = (id) => { if (busy || id === jobId) return; setError(null); setJob(null); setJobId(id); };
  const onDelete = async (id) => {
    try {
      await del(`/runs/${id}`);
      if (id === jobId) { setJobId(null); setJob(null); }
      loadHistory();
    } catch (e) { setError(e.message); }
  };

  const chainTag = offline ? <Tag tone="rose">Chain offline</Tag>
    : !chain ? <Tag>Chain</Tag>
    : chain.ok === false ? <Tag tone="rose">Chain error</Tag>
    : chain.backend === "evm" ? <Tag tone="lav">{chain.chain} · {chain.contract ? shortHash(chain.contract, 4) : "no contract"} · {chain.records_anchored} records</Tag>
    : <Tag tone="amber">Simchain · {chain.records_anchored} records</Tag>;
  const statusTag = !job ? <Tag>Idle</Tag>
    : busy ? <Tag tone="lav"><span className="spinner" /> Running</Tag>
    : job.status === "done" ? <Tag tone="mint"><span className="led" /> Done{job.elapsed ? ` · ${job.elapsed}s` : ""}</Tag>
    : job.status === "no_match" ? <Tag tone="amber">No match</Tag>
    : <Tag tone="rose">{job.status.replace("_", " ")}</Tag>;

  return (
    <>
      <div className="console-bg" aria-hidden="true" />
      {header}
      <div className="statusbar">
        <Tag tone={health?.search_engine ? "mint" : "rose"}><span className="led" /> {health?.search_engine ? `Google Lens · ${health.search_engine.split("/")[0]}` : "No search key"}</Tag>
        {chainTag}
        {chain?.account ? <Tag>Signer {shortHash(chain.account, 4)} · {Number(chain.balance_eth).toFixed(2)} ETH</Tag> : null}
        <span className="spacer" />
        {job?.id ? <Tag>Run #{job.id}</Tag> : null}
      </div>

      <main className="console">
        <div className="col">
          <InputPanel busy={busy} disabled={offline || !health?.search_engine} onSubmit={onSubmit} />
          {error ? <Alert tone="red">{error}</Alert> : null}
          {!offline && health && !health.search_engine ? <Alert tone="amber"><code>SERPER_API_KEY</code> or <code>SERPAPI_KEY</code> missing in <code>.env</code></Alert> : null}
        </div>

        <div className="col">
          <section className="card">
            <div className="card__head"><h3>Pipeline</h3>{statusTag}</div>
            <div className="card__body card__body--tight">
              <PipelineRail job={job} />
            </div>
          </section>
          <Results job={job} />
        </div>

        <div className="col col--history">
          <section className="card">
            <div className="card__head">
              <h3>Runs</h3>
              <button className="iconbtn" onClick={loadHistory} aria-label="refresh"><Icon name="refresh" /></button>
            </div>
            <div className="card__body card__body--tight">
              <History items={history} activeId={jobId} onSelect={onSelect} onDelete={onDelete} busy={busy} />
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
