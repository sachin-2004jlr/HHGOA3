import { useBackendStatus } from "../hooks.js";
import { Icon, Pill } from "./ui.jsx";

const STEPS = [
  { n: "01", t: "Face scan", d: "YuNet finds the face, SFace turns it into a 128-number identity vector. Runs on CPU, nothing leaves the machine yet.", tag: "OpenCV DNN" },
  { n: "02", t: "Reverse image search", d: "The face crop is published to a short-lived URL and sent to Google Lens. Every page it returns, on the open web or social media, becomes a candidate.", tag: "Google Lens" },
  { n: "03", t: "Widen the net", d: "If Lens recognises the person, keyword image searches on Instagram, X and Facebook add more candidates. The name is read from the results, never typed in.", tag: "DuckDuckGo" },
  { n: "04", t: "Biometric verification", d: "Each candidate image is downloaded and its face compared with the scan. Only real matches survive; social posts are preferred, best similarity wins.", tag: "cosine ≥ 0.363" },
  { n: "05", t: "Anchor on chain", d: "SHA-256 fingerprints of the record, the post image and the face vector go into the FaceMatchRegistry contract with the post URL and score.", tag: "Solidity · web3.py" },
  { n: "06", t: "Re-verify any time", d: "Verification recomputes every hash from the evidence files and compares them with the on-chain record, field by field. One changed byte fails.", tag: "tamper-evident" },
];

export default function Landing({ onStart }) {
  const { health, chain, offline } = useBackendStatus();
  const chainLabel = offline ? "backend offline" : chain?.ok === false ? "no chain" : chain?.chain || (chain?.backend === "sim" ? "simulated chain" : "…");
  const engine = health?.search_engine ? "Google Lens" : "search key missing";

  return (
    <main className="landing">
      <section className="hero">
        <div>
          <span className="eyebrow">Face identification · blockchain verification</span>
          <h1>From a face to a <em>verifiable</em> record.</h1>
          <p className="lede">
            Scan a face, find the real post it appears in on the web or social media, and anchor a
            tamper-evident fingerprint of that discovery on a blockchain. Then prove, any time later,
            that the evidence has not changed.
          </p>
          <div className="hero__cta">
            <button className="btn btn--primary btn--lg" onClick={onStart}>Use the application <Icon name="arrow" /></button>
            <a className="btn btn--lg" href="#how">How it works</a>
          </div>
          <div className="hero__meta">
            <Pill tone={offline ? "red" : "teal"} icon="search">{engine}</Pill>
            <Pill tone={offline ? "red" : "indigo"} icon="chain">{chainLabel}{chain?.records_anchored != null ? ` · ${chain.records_anchored} records` : ""}</Pill>
            <Pill icon="shield">SHA-256 · Solidity 0.8</Pill>
          </div>
        </div>

        <div className="strip" aria-label="pipeline illustration">
          <div className="strip__title"><span>Pipeline</span><span>end to end</span></div>
          <div className="strip__nodes">
            <div className="strip__line"><span className="strip__dot" /></div>
            <div className="node" data-tone="teal"><div className="node__icon"><Icon name="face" /></div><h4>Face scan</h4><p>detect + embed</p></div>
            <div className="node" data-tone="amber"><div className="node__icon"><Icon name="search" /></div><h4>Search</h4><p>reverse image</p></div>
            <div className="node" data-tone="green"><div className="node__icon"><Icon name="shield" /></div><h4>Match</h4><p>face-verified post</p></div>
            <div className="node" data-tone="indigo"><div className="node__icon"><Icon name="chain" /></div><h4>Anchor</h4><p>on-chain record</p></div>
          </div>
          <div className="strip__foot">
            <div>Registry contract<b>{chain?.contract || "auto-deployed on first run"}</b></div>
            <div>Network<b>{chainLabel}</b></div>
          </div>
        </div>
      </section>

      <section className="section" id="how">
        <div className="section__head">
          <h2>Six steps, every one of them visible.</h2>
          <p>Nothing is pre-picked. The candidates, the match and the score are whatever the live search and the face model produce for the photo you give it.</p>
        </div>
        <div className="steps">
          {STEPS.map((s) => (
            <article className="step" key={s.n}>
              <span className="step__n">{s.n}</span>
              <h3>{s.t}</h3>
              <p>{s.d}</p>
              <span className="step__tag"><Pill>{s.tag}</Pill></span>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section__head">
          <h2>What goes on the chain.</h2>
          <p>Only fingerprints. The chain never stores the photo or the face vector, so the record proves integrity without publishing biometrics.</p>
        </div>
        <div className="split">
          <pre className="codecard">{`// contracts/FaceMatchRegistry.sol
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
            <div className="trust__item">
              <div className="trust__icon" style={{ background: "var(--amber-soft)", color: "var(--amber)" }}><Icon name="search" /></div>
              <div><h3>Genuine search</h3><p>Google Lens is queried at run time with your face crop. The result list, and the name used to widen it, come back from the engine.</p></div>
            </div>
            <div className="trust__item">
              <div className="trust__icon" style={{ background: "var(--green-soft)", color: "var(--green)" }}><Icon name="shield" /></div>
              <div><h3>Biometric, not textual</h3><p>A candidate is accepted only if the face in its image matches the scan above the SFace same-identity threshold. Titles and rankings do not decide.</p></div>
            </div>
            <div className="trust__item">
              <div className="trust__icon" style={{ background: "var(--indigo-soft)", color: "var(--indigo)" }}><Icon name="chain" /></div>
              <div><h3>Tamper-evident</h3><p>Runs on a real EVM (Anvil locally, Sepolia publicly) or a simulated chain. Verification re-hashes the files on disk and looks the record up on chain.</p></div>
            </div>
          </div>
        </div>
      </section>

      <section className="cta-band">
        <div className="cta-band__inner">
          <div>
            <h2>Try it with a photo or your webcam.</h2>
            <p>Every step streams into the console as it happens, with the evidence and the on-chain receipt kept for re-verification.</p>
          </div>
          <button className="btn btn--lg" style={{ background: "#fff", color: "var(--ink)", borderColor: "#fff" }} onClick={onStart}>
            Use the application <Icon name="arrow" />
          </button>
        </div>
      </section>

      <footer className="footer">
        <span>facechain · HH Goa 2026 · built for the shortlisting task</span>
        <span className="stack">
          <Pill>OpenCV YuNet + SFace</Pill><Pill>Google Lens</Pill><Pill>FastAPI</Pill><Pill>React</Pill><Pill>Solidity</Pill><Pill>web3.py</Pill><Pill>Anvil / Sepolia</Pill>
        </span>
      </footer>
    </main>
  );
}
