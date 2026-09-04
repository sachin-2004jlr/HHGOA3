import { useEffect, useState } from "react";

const PATHS = {
  upload: ["M12 16V4", "m7 9 5-5 5 5", "M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"],
  camera: ["M4 8h3l2-3h6l2 3h3v11H4z", "M12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"],
  check: ["m5 12.5 4.5 4.5L19 7.5"],
  x: ["M6 6l12 12", "M18 6 6 18"],
  alert: ["M12 3 2 20h20z", "M12 10v4", "M12 17.5v.5"],
  copy: ["M9 9h10v10H9z", "M5 15H4V4h11v1"],
  external: ["M14 4h6v6", "M20 4 10 14", "M18 13v6H5V6h6"],
  chevron: ["m9 6 6 6-6 6"],
  history: ["M3 12a9 9 0 1 0 3-6.7", "M3 4v5h5", "M12 7v5l3 2"],
  trash: ["M4 7h16", "M10 11v6", "M14 11v6", "M6 7l1 13h10l1-13", "M9 7V4h6v3"],
  refresh: ["M21 12a9 9 0 1 1-2.6-6.4", "M21 4v5h-5"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3 2"],
  image: ["M4 5h16v14H4z", "m4 16 5-5 4 4 3-3 4 4", "M15.5 9.5h.01"],
};

export function Icon({ name, className }) {
  const d = PATHS[name] || PATHS.alert;
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {d.map((p, i) => <path key={i} d={p} />)}
    </svg>
  );
}

export function Tag({ tone, children, className = "" }) {
  return <span className={`tag ${tone ? `tag--${tone}` : ""} ${className}`}>{children}</span>;
}

export function PlatformTag({ platform }) {
  const p = platform || "web";
  return <Tag tone={p === "web" ? undefined : "lav"}>{p === "x" ? "X" : p}</Tag>;
}

export function Hash({ value, prefix = true, label }) {
  const [copied, setCopied] = useState(false);
  const v = value ? (prefix && !value.startsWith("0x") ? "0x" + value : value) : "";
  useEffect(() => { if (!copied) return undefined; const t = setTimeout(() => setCopied(false), 1400); return () => clearTimeout(t); }, [copied]);
  const copy = async () => { try { await navigator.clipboard.writeText(v); setCopied(true); } catch { /* ignore */ } };
  return (
    <span className={`hash ${copied ? "is-copied" : ""}`} title={v}>
      <span className="hash__text">{v || "—"}</span>
      <button type="button" onClick={copy} aria-label={`copy ${label || "value"}`}><Icon name={copied ? "check" : "copy"} /></button>
    </span>
  );
}

export function Meter({ value, threshold }) {
  const pct = Math.max(0, Math.min(1, value));
  const r = 60, c = 2 * Math.PI * r;
  const pass = value >= threshold;
  const color = pass ? "var(--mint)" : "var(--amber)";
  return (
    <div className="meter">
      <svg viewBox="0 0 150 150" role="img" aria-label={`cosine ${value.toFixed(3)}`}>
        <circle className="meter__ring" cx="75" cy="75" r={r} />
        <circle className="meter__val" cx="75" cy="75" r={r} strokeDasharray={c} strokeDashoffset={c * (1 - pct)} style={{ stroke: color, color }} />
        <text className="meter__num" x="75" y="80" textAnchor="middle">{value.toFixed(3)}</text>
        <text className="meter__lbl" x="75" y="100" textAnchor="middle">COSINE</text>
      </svg>
      <p>{pass ? "above" : "below"} threshold {threshold}</p>
    </div>
  );
}

export function Alert({ tone = "red", icon = "alert", children }) {
  return <div className={`alert alert--${tone}`}><Icon name={icon} /><div>{children}</div></div>;
}

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function shortHash(h, n = 10) {
  if (!h) return "";
  const v = h.startsWith("0x") ? h : "0x" + h;
  return v.length > 2 * n + 3 ? `${v.slice(0, n + 2)}…${v.slice(-n)}` : v;
}

export function chainLine(chain, offline, withContract = false) {
  if (offline) return "OFFLINE";
  if (!chain) return "";
  if (chain.ok === false) return "NO CHAIN";
  const name = chain.backend === "sim" ? "SIMCHAIN" : (chain.chain || "EVM").toUpperCase().replace(" (LOCAL)", "");
  const block = chain.latest_block ?? chain.blocks;
  if (withContract && chain.contract) return `${name} · CONTRACT ${shortHash(chain.contract, 4)}`;
  return block != null ? `${name} · BLOCK ${Number(block).toLocaleString()}` : name;
}

export function engineLabel(engine) {
  if (!engine) return "Search offline";
  const names = { yandex: "Yandex", serper: "Google Lens", serpapi: "Google Lens" };
  return engine.split("+").map((e) => names[e.split("/")[0]] || e).join(" + ");
}
