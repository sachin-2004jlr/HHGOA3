import { useEffect, useState } from "react";
import Landing from "./components/Landing.jsx";
import Console from "./components/Console.jsx";
import { useBackendStatus } from "./hooks.js";
import { chainLine } from "./components/ui.jsx";

function viewFromHash() {
  return window.location.hash.startsWith("#console") ? "console" : "landing";
}

export function Header({ view, go, chain, offline }) {
  const console_ = view === "console";
  return (
    <header className={`hdr ${console_ ? "hdr--console" : ""}`}>
      <div className="hdr__left">
        <button className="logo" aria-label="Veriface" onClick={() => go("landing")}><i /></button>
        <nav className="nav">
          {console_ ? (
            <button onClick={() => go("landing")}>Overview</button>
          ) : (
            <>
              <a href="#pipeline">Pipeline</a>
              <a href="#ledger">Ledger</a>
              <a href="#stack">Stack</a>
            </>
          )}
        </nav>
      </div>
      <div className="hdr__right">
        <div className="hdr__chain">{chainLine(chain, offline)}</div>
        {console_ ? null : <button className="pill pill--outline pill--sm" onClick={() => go("console")}>Run a scan</button>}
      </div>
    </header>
  );
}

export default function App() {
  const [view, setView] = useState(viewFromHash);
  const status = useBackendStatus();

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (v) => {
    if (v === view) return;
    window.history.replaceState(null, "", v === "console" ? "#console" : window.location.pathname);
    setView(v);
    window.scrollTo({ top: 0 });
  };

  return view === "landing"
    ? <Landing go={go} status={status} header={<Header view={view} go={go} chain={status.chain} offline={status.offline} />} />
    : <Console status={status} header={<Header view={view} go={go} chain={status.chain} offline={status.offline} />} />;
}
