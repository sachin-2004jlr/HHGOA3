import { useCallback, useEffect, useRef, useState } from "react";
import { createRun, del, getJSON } from "../api.js";
import { useBackendStatus } from "../hooks.js";
import InputPanel from "./InputPanel.jsx";
import PipelineRail from "./PipelineRail.jsx";
import Results from "./Results.jsx";
import History from "./History.jsx";
import { Alert, Icon, Pill, shortHash } from "./ui.jsx";

export default function Console() {
  const { health, chain, offline, refreshChain } = useBackendStatus();
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const timer = useRef(null);

  const loadHistory = useCallback(async () => {
    try { setHistory(await getJSON("/runs")); } catch { /* backend offline */ }
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  // deep link: #console?run=<id>
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
        if (!cancelled) setError(e.message);
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

  const chainChip = offline ? <Pill tone="red" icon="chain">backend offline</Pill>
    : !chain ? <Pill icon="chain">chain…</Pill>
    : chain.ok === false ? <Pill tone="red" icon="chain">chain error</Pill>
    : chain.backend === "evm" ? <Pill tone="indigo" icon="chain">{chain.chain} · {chain.contract ? shortHash(chain.contract, 6) : "no contract yet"} · {chain.records_anchored} records</Pill>
    : <Pill tone="amber" icon="layers">simulated chain (no EVM node) · {chain.records_anchored} records</Pill>;

  return (
    <>
      <div className="statusbar">
        <span className={`dot ${offline ? "dot--off" : "dot--on"}`} aria-hidden="true" />
        <Pill tone={health?.search_engine ? "teal" : "red"} icon="search">{health?.search_engine ? `Google Lens via ${health.search_engine.split("/")[0]}` : "no search key"}</Pill>
        {chainChip}
        {chain?.account ? <Pill icon="key">signer {shortHash(chain.account, 5)} · {Number(chain.balance_eth).toFixed(2)} ETH</Pill> : null}
        <span className="spacer" />
        {job?.id ? <Pill icon="hash">run {job.id}</Pill> : null}
      </div>

      <main className="console">
        <div className="col">
          <InputPanel busy={busy} disabled={offline || !health?.search_engine} onSubmit={onSubmit} />
          {error ? <Alert tone="red">{error}</Alert> : null}
          {!offline && health && !health.search_engine ? (
            <Alert tone="amber">No reverse-image search key configured. Add <code>SERPER_API_KEY</code> or <code>SERPAPI_KEY</code> to <code>.env</code> and restart.</Alert>
          ) : null}
        </div>

        <div className="col">
          <section className="card">
            <div className="card__head">
              <h3><Icon name="zap" /> Pipeline</h3>
              {job ? <Pill tone={busy ? "teal" : job.status === "done" ? "green" : job.status === "no_match" ? "amber" : "red"}>
                {busy ? <span className="spinner" /> : null}{busy ? "running" : job.status.replace("_", " ")}{job.elapsed ? ` · ${job.elapsed}s` : ""}
              </Pill> : <Pill>idle</Pill>}
            </div>
            <div className="card__body card__body--tight">
              <PipelineRail job={job} />
            </div>
          </section>
          <Results job={job} onChanged={loadHistory} />
        </div>

        <div className="col col--history">
          <section className="card">
            <div className="card__head">
              <h3><Icon name="history" /> Previous runs</h3>
              <button className="iconbtn" onClick={loadHistory} aria-label="refresh history"><Icon name="refresh" /></button>
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
