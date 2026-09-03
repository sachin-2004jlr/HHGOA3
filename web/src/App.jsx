import { useEffect, useState } from "react";
import Landing from "./components/Landing.jsx";
import Console from "./components/Console.jsx";
import { Icon } from "./components/ui.jsx";

const REPO = "https://github.com/sachin-2004jlr/HHGOA3";

function viewFromHash() {
  return window.location.hash === "#console" ? "console" : "landing";
}

export default function App() {
  const [view, setView] = useState(viewFromHash);

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

  return (
    <div className={`app app--${view}`}>
      <header className="topbar">
        <a className="brand" href="#" onClick={(e) => { e.preventDefault(); go("landing"); }}>
          <span className="brand__mark"><Icon name="face" /></span>
          <span className="brand__name">facechain</span>
        </a>

        <div className="seg" role="tablist" aria-label="Switch between overview and console">
          <button role="tab" aria-selected={view === "landing"} className={view === "landing" ? "is-active" : ""} onClick={() => go("landing")}>
            Overview
          </button>
          <button role="tab" aria-selected={view === "console"} className={view === "console" ? "is-active" : ""} onClick={() => go("console")}>
            Console
          </button>
          <span className="seg__thumb" data-pos={view} aria-hidden="true" />
        </div>

        <div className="topbar__right">
          <a className="btn btn--ghost" href={REPO} target="_blank" rel="noreferrer"><Icon name="github" /> GitHub</a>
          {view === "landing" ? (
            <button className="btn btn--primary" onClick={() => go("console")}>Use the application <Icon name="arrow" /></button>
          ) : null}
        </div>
      </header>

      {view === "landing" ? <Landing onStart={() => go("console")} /> : <Console />}
    </div>
  );
}
