import { useEffect, useState } from "react";
import { useBackendStatus } from "../hooks.js";
import { Icon, Pill, shortHash } from "./ui.jsx";

const STEPS = [
  { n: "01", t: "Face scan", d: "YuNet finds the face, SFace turns it into a 128-number identity vector. Runs on CPU; nothing leaves the machine yet.", tag: "OpenCV DNN", tone: "cyan" },
  { n: "02", t: "Reverse image search", d: "The face crop is published to a short-lived URL and sent to Google Lens. Every page it returns, on the open web or social media, becomes a candidate.", tag: "Google Lens", tone: "magenta" },
  { n: "03", t: "Widen the net", d: "If Lens recognises the person, keyword image searches on Instagram, X and Facebook add candidates. The name is read from the results, never typed in.", tag: "DuckDuckGo", tone: "magenta" },
  { n: "04", t: "Biometric verification", d: "Each candidate image is downloaded and its face compared with the scan. Only real matches survive; social posts are preferred, best similarity wins.", tag: "cos ≥ 0,363", tone: "yellow" },
  { n: "05", t: "Anchor on chain", d: "SHA-256 fingerprints of the record, the post image and the face vector go into the FaceMatchRegistry contract with the post URL and score.", tag: "Solidity · web3.py", tone: "cyan" },
  { n: "06", t: "Re-verify any time", d: "Verification recomputes every hash from the evidence files and compares them with the on-chain record, field by field. One changed byte fails.", tag: "tamper-evident", tone: "cyan" },
];

function useCounter(target, ms = 900) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (target == null) return undefined;
    const start = performance.now();
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - start) / ms);
      setV(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function HudTag({ k, v, tone = "cyan", style, side = "right" }) {
  return (
    <div className={`hud-tag hud-tag--${tone} hud-tag--${side}`} style={style}>
      <span className="hud-tag__k">{k}</span>
      <span className="hud-tag__v">{v}</span>
    </div>
  );
}

export default function Landing({ onStart }) {
  const { health, chain, offline } = useBackendStatus();
  const records = useCounter(chain?.records_anchored ?? null);
  const chainName = offline ? "backend offline" : chain?.ok === false ? "no chain" : chain?.backend === "sim" ? "simulated chain" : chain?.chain || "…";
  const engine = offline ? "offline" : health?.search_engine ? "Google Lens" : "search key missing";
  const block = chain?.latest_block ?? chain?.blocks;

  return (
    <main className="landing">
      <section className="hero">
        <div className="hero__grid" aria-hidden="true" />
        <div className="hero__copy">
          <span className="eyebrow"><span className="eyebrow__dot" />Face identification · blockchain verification</span>
          <h1>Verify a face against the <span className="hl">real web</span>, then <span className="hl hl--m">prove it</span> on chain.</h1>
          <p className="lede">
            Scan a face, find the actual post it appears in on the web or social media, and anchor a
            tamper-evident fingerprint of that discovery on a blockchain. Re-verify the evidence any
            time, byte for byte.
          </p>
          <div className="hero__cta">
            <button className="btn btn--primary btn--lg" onClick={onStart}>Use the application <Icon name="arrow" /></button>
            <a className="btn btn--lg" href="#how">How it works</a>
          </div>
          <dl className="hero__stats">
            <div><dt>Search</dt><dd>{engine}</dd></div>
            <div><dt>Network</dt><dd>{chainName}</dd></div>
            <div><dt>Records anchored</dt><dd className="num">{chain?.records_anchored != null ? records : "—"}</dd></div>
            <div><dt>Latest block</dt><dd className="num">{block != null ? `#${block}` : "—"}</dd></div>
          </dl>
        </div>

        <div className="hero__visual">
          <div className="subject">
            <span className="subject__glow" aria-hidden="true" />
            <span className="subject__scan" aria-hidden="true" />
            <img src="/hero.webp" alt="A smiling person with face-tracking landmarks, coordinate readouts and a mesh overlay" />
            <span className="bracket bracket--tl" aria-hidden="true" /><span className="bracket bracket--tr" aria-hidden="true" />
            <span className="bracket bracket--bl" aria-hidden="true" /><span className="bracket bracket--br" aria-hidden="true" />
            <HudTag k="DET" v="YuNet · 5 landmarks" tone="cyan" side="left" style={{ left: "-6%", top: "22%" }} />
            <HudTag k="EMB" v="SFace · 128-d · L2" tone="yellow" side="left" style={{ left: "-10%", top: "48%" }} />
            <HudTag k="REG" v={chain?.contract ? shortHash(chain.contract, 6) : "FaceMatchRegistry"} tone="magenta" side="left" style={{ left: "-4%", top: "74%" }} />
          </div>
        </div>
      </section>

      <section className="section" id="how">
        <div className="section__head">
          <span className="label">01 — Pipeline</span>
          <h2>Six steps, every one of them visible.</h2>
          <p>Nothing is pre-picked. The candidates, the match and the score are whatever the live search and the face model produce for the photo you give it.</p>
        </div>
        <div className="steps">
          {STEPS.map((s) => (
            <article className="step" key={s.n} data-tone={s.tone}>
              <div className="step__top"><span className="step__n">{s.n} / 06</span><span className="step__tag">{s.tag}</span></div>
              <h3>{s.t}</h3>
              <p>{s.d}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section__head">
          <span className="label">02 — On-chain record</span>
          <h2>Only fingerprints go on the chain.</h2>
          <p>The chain never stores the photo or the face vector, so the record proves integrity without publishing biometrics.</p>
        </div>
        <div className="split">
          <pre className="codecard"><span className="c">// contracts/FaceMatchRegistry.sol</span>{`
`}<span className="k">struct</span>{` Record {
  `}<span className="t">bytes32</span>{` recordHash;    `}<span className="c">// sha256(canonical record.json)</span>{`
  `}<span className="t">bytes32</span>{` imageHash;     `}<span className="c">// sha256(matched post image bytes)</span>{`
  `}<span className="t">bytes32</span>{` faceHash;      `}<span className="c">// sha256(query face embedding)</span>{`
  `}<span className="t">string</span>{`  postUrl;       `}<span className="c">// discovered social-media post</span>{`
  `}<span className="t">string</span>{`  platform;      `}<span className="c">// "instagram" | "x" | "reddit" ...</span>{`
  `}<span className="t">uint16</span>{`  similarityBps; `}<span className="c">// cosine similarity * 10000</span>{`
  `}<span className="t">uint64</span>{`  timestamp;     `}<span className="c">// block.timestamp</span>{`
  `}<span className="t">address</span>{` submitter;
}
`}<span className="k">function</span>{` `}<span className="f">anchor</span>{`(bytes32, bytes32, bytes32, string, string, uint16)
`}<span className="k">function</span>{` `}<span className="f">getRecord</span>{`(bytes32 recordHash) `}<span className="k">returns</span>{` (Record)
`}<span className="k">event</span>{`    `}<span className="f">RecordAnchored</span>{`(bytes32 indexed recordHash, ...)`}</pre>
          <div className="trust">
            <div className="trust__item" data-tone="magenta">
              <div className="trust__icon"><Icon name="search" /></div>
              <div><h3>Genuine search</h3><p>Google Lens is queried at run time with your face crop. The result list, and the name used to widen it, come back from the engine.</p></div>
            </div>
            <div className="trust__item" data-tone="yellow">
              <div className="trust__icon"><Icon name="shield" /></div>
              <div><h3>Biometric, not textual</h3><p>A candidate is accepted only if the face in its image matches the scan above the SFace same-identity threshold. Titles and rankings do not decide.</p></div>
            </div>
            <div className="trust__item" data-tone="cyan">
              <div className="trust__icon"><Icon name="chain" /></div>
              <div><h3>Tamper-evident</h3><p>Runs on a real EVM (Anvil locally, Sepolia publicly) or a simulated chain. Verification re-hashes the files on disk and looks the record up on chain.</p></div>
            </div>
          </div>
        </div>
      </section>

      <section className="cta-band">
        <div className="cta-band__inner">
          <span className="bracket bracket--tl" aria-hidden="true" /><span className="bracket bracket--br" aria-hidden="true" />
          <div>
            <span className="label label--light">03 — Try it</span>
            <h2>A photo or your webcam. Sixty seconds to an on-chain record.</h2>
            <p>Every step streams into the console as it happens, with the evidence and the receipt kept for re-verification.</p>
          </div>
          <button className="btn btn--cyan btn--lg" onClick={onStart}>Use the application <Icon name="arrow" /></button>
        </div>
      </section>

      <footer className="footer">
        <span>Veriface · facechain pipeline · HH Goa 2026 shortlisting task</span>
        <span className="stack">
          <Pill>OpenCV YuNet + SFace</Pill><Pill>Google Lens</Pill><Pill>FastAPI</Pill><Pill>React</Pill><Pill>Solidity</Pill><Pill>web3.py</Pill><Pill>Anvil / Sepolia</Pill>
        </span>
      </footer>
    </main>
  );
}
