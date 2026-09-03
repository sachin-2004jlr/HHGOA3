import { fileUrl } from "../api.js";
import { Icon, PlatformPill, fmtTime } from "./ui.jsx";

export default function History({ items, activeId, onSelect, onDelete, busy }) {
  if (!items.length) return <p className="hint" style={{ padding: 8 }}>No runs yet. Results of every run are kept in <code>evidence/</code> and listed here.</p>;
  return (
    <div className="history">
      {items.map((h) => (
        <div key={h.id} className={`hitem ${h.id === activeId ? "is-active" : ""}`}>
          <button type="button" style={{ display: "contents" }} onClick={() => onSelect(h.id)} disabled={busy} aria-label={`open run ${h.id}`}>
            {h.image_file ? <img src={fileUrl(h.id, h.image_file)} alt="" loading="lazy" /> : <span className="ph"><Icon name={h.status === "running" ? "clock" : "image"} /></span>}
            <span style={{ minWidth: 0 }}>
              <span className="hitem__t">{h.title || (h.status === "running" ? "running…" : h.status === "no_match" ? "no match" : h.id)}</span>
              <span className="hitem__s">
                {h.platform ? <PlatformPill platform={h.platform} /> : null}
                {h.similarity != null ? <span className="hitem__sim">{Number(h.similarity).toFixed(3)}</span> : null}
                <span>{fmtTime(h.created_at)}</span>
              </span>
            </span>
          </button>
          <button type="button" className="iconbtn" aria-label="delete run" onClick={() => { if (confirm(`Delete evidence for run ${h.id}?`)) onDelete(h.id); }} disabled={busy}><Icon name="trash" /></button>
        </div>
      ))}
    </div>
  );
}
