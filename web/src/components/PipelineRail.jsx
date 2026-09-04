import { useEffect, useState } from "react";
import { Icon } from "./ui.jsx";

const TITLES = {
  1: "Face scan: detect and encode the face",
  2: "Reverse image search on the web and social media",
  3: "Face verification of every candidate",
  4: "Evidence record and SHA-256 fingerprints",
  5: "Anchor on the blockchain",
  6: "Read back from the chain and verify",
};

function useNow(active) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

export default function PipelineRail({ job }) {
  const running = !!job && (job.status === "queued" || job.status === "running");
  const now = useNow(running);
  const steps = job?.steps || {};
  const restored = !!job?.restored;
  const r = job?.result;

  const rows = [1, 2, 3, 4, 5, 6].map((n) => {
    let s = steps[String(n)];
    if (restored) {
      const has = { 1: r?.query, 2: r?.search, 3: r?.match, 4: r?.hashes, 5: r?.receipt, 6: r?.receipt }[n];
      s = { status: has ? "done" : "pending", message: n === 6 && has ? "loaded from evidence - use Re-verify below" : null };
    }
    s = s || { status: "pending" };
    const dur = s.duration != null ? s.duration : s.status === "running" && s.started ? (now / 1000 - s.started) : null;
    return { n, ...s, dur };
  });

  return (
    <ol className="rail" aria-label="pipeline steps">
      {rows.map((s) => (
        <li key={s.n} className="rail__item" data-status={s.status}>
          <span className="rail__icon">
            {s.status === "done" ? <Icon name="check" /> : s.status === "error" ? <Icon name="x" /> : s.status === "running" ? <span className="spinner" /> : s.n}
          </span>
          <div>
            <div className="rail__title">{s.title || TITLES[s.n]}</div>
            {s.message ? <div className="rail__msg">{s.message}</div> : null}
            {s.status === "running" && s.progress?.total ? (
              <div className="bar" role="progressbar" aria-valuenow={s.progress.done} aria-valuemax={s.progress.total}>
                <span style={{ width: `${(100 * s.progress.done) / s.progress.total}%` }} />
              </div>
            ) : null}
            {s.status === "running" && s.progress?.total ? <div className="rail__msg num">{s.progress.done} / {s.progress.total} candidate images checked</div> : null}
          </div>
          <span className="rail__time num">{s.dur != null ? `${s.dur.toFixed(1)}s` : ""}</span>
        </li>
      ))}
      {job?.log?.length ? (
        <li className="log" aria-label="event log">
          {job.log.slice(-40).map((l, i) => (
            <div key={i}><span className="t num">{l.t.toFixed(1)}s</span><span className={l.status === "error" ? "err" : ""}>[{l.step}] {l.message}</span></div>
          ))}
        </li>
      ) : null}
    </ol>
  );
}
