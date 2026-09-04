import { useEffect, useState } from "react";
import { Icon } from "./ui.jsx";

// The brief's three stages; the backend reports six internal steps that map onto them.
const STAGES = [
  { n: 1, title: "Face scan", steps: [1] },
  { n: 2, title: "Web / social media search", steps: [2, 3] },
  { n: 3, title: "Blockchain upload and verification", steps: [4, 5, 6] },
];

function useNow(active) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function stageState(stage, steps, restored, r) {
  if (restored) {
    const has = { 1: r?.query, 2: r?.match, 3: r?.receipt };
    return { status: has[stage.n] ? "done" : "pending", message: null, duration: null, progress: null };
  }
  const subs = stage.steps.map((k) => steps[String(k)] || { status: "pending" });
  const running = subs.find((s) => s.status === "running");
  const error = subs.find((s) => s.status === "error");
  const allDone = subs.every((s) => s.status === "done");
  const status = error ? "error" : running ? "running" : allDone ? "done" : subs.some((s) => s.status === "done") ? "running" : "pending";
  const active = error || running || subs.filter((s) => s.status === "done").slice(-1)[0];
  const started = Math.min(...subs.filter((s) => s.started).map((s) => s.started));
  const finished = Math.max(...subs.filter((s) => s.finished).map((s) => s.finished));
  return {
    status, message: active?.message || null, progress: running?.progress || null,
    started: Number.isFinite(started) ? started : null,
    duration: allDone && Number.isFinite(started) && Number.isFinite(finished) ? finished - started : null,
  };
}

export default function PipelineRail({ job }) {
  const running = !!job && (job.status === "queued" || job.status === "running");
  const now = useNow(running);
  const steps = job?.steps || {};
  const rows = STAGES.map((st) => ({ ...st, ...stageState(st, steps, !!job?.restored, job?.result) }));

  return (
    <ol className="rail" aria-label="pipeline stages">
      {rows.map((s) => {
        const dur = s.duration != null ? s.duration : s.status === "running" && s.started ? now / 1000 - s.started : null;
        return (
          <li key={s.n} className="rail__item" data-status={s.status}>
            <span className="rail__icon">
              {s.status === "done" ? <Icon name="check" /> : s.status === "error" ? <Icon name="x" /> : s.status === "running" ? <span className="spinner" /> : s.n}
            </span>
            <div>
              <div className="rail__title">{s.title}</div>
              {s.message ? <div className="rail__msg">{s.message}</div> : null}
              {s.status === "running" && s.progress?.total ? (
                <div className="bar" role="progressbar" aria-valuenow={s.progress.done} aria-valuemax={s.progress.total}>
                  <span style={{ width: `${(100 * s.progress.done) / s.progress.total}%` }} />
                </div>
              ) : null}
            </div>
            <span className="rail__time num">{dur != null ? `${dur.toFixed(1)}s` : ""}</span>
          </li>
        );
      })}
      {job?.log?.length ? (
        <li className="log" aria-label="event log">
          {job.log.slice(-30).map((l, i) => (
            <div key={i}><span className="t num">{l.t.toFixed(1)}s</span><span className={l.status === "error" ? "err" : ""}>{l.message}</span></div>
          ))}
        </li>
      ) : null}
    </ol>
  );
}
