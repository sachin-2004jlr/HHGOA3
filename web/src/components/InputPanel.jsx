import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui.jsx";

export default function InputPanel({ busy, disabled, onSubmit }) {
  const [tab, setTab] = useState("upload");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [over, setOver] = useState(false);
  const [thr, setThr] = useState(0.363);
  const [maxC, setMaxC] = useState(60);
  const [expand, setExpand] = useState(true);
  const [chain, setChain] = useState("auto");

  // webcam
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [camErr, setCamErr] = useState(null);
  const [shot, setShot] = useState(null); // { blob, url }
  const [camReady, setCamReady] = useState(false);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  useEffect(() => {
    if (tab !== "webcam" || shot) { stopCam(); return undefined; }
    let cancelled = false;
    setCamErr(null);
    setCamReady(false);
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } }, audio: false })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.onloadedmetadata = () => setCamReady(true);
        }
      })
      .catch((e) => setCamErr(e.name === "NotAllowedError" ? "Camera access was denied. Allow the camera for this site and try again." : `Camera unavailable: ${e.message}`));
    return () => { cancelled = true; stopCam(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, shot]);

  function stopCam() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCamReady(false);
  }

  function pick(f) {
    if (!f) return;
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) { alert("Please choose a JPEG, PNG or WebP image."); return; }
    if (preview) URL.revokeObjectURL(preview);
    setFile(f);
    setPreview(URL.createObjectURL(f));
  }

  function capture() {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0);
    c.toBlob((blob) => {
      if (!blob) return;
      setShot({ blob, url: URL.createObjectURL(blob) });
    }, "image/jpeg", 0.92);
  }

  function retake() {
    if (shot?.url) URL.revokeObjectURL(shot.url);
    setShot(null);
  }

  const ready = tab === "upload" ? !!file : !!shot;
  const submit = (e) => {
    e.preventDefault();
    if (!ready || busy || disabled) return;
    const opts = { min_similarity: thr, max_candidates: maxC, expand, chain };
    if (tab === "upload") onSubmit(file, opts, "upload");
    else onSubmit(new File([shot.blob], "webcam.jpg", { type: "image/jpeg" }), opts, "webcam");
  };

  return (
    <form className="card" onSubmit={submit}>
      <div className="card__head"><h3><Icon name="face" /> Face scan input</h3></div>
      <div className="card__body">
        <div className="tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === "upload"} className={tab === "upload" ? "is-active" : ""} onClick={() => setTab("upload")}><Icon name="upload" /> Upload</button>
          <button type="button" role="tab" aria-selected={tab === "webcam"} className={tab === "webcam" ? "is-active" : ""} onClick={() => setTab("webcam")}><Icon name="camera" /> Webcam</button>
        </div>

        {tab === "upload" ? (
          <div className={`drop ${over ? "is-over" : ""} ${preview ? "has-preview" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]); }}>
            {preview ? (
              <>
                <img className="preview" src={preview} alt="selected face" />
                <div className="preview-actions">
                  <button type="button" className="iconbtn" aria-label="remove image" onClick={() => { setFile(null); setPreview(null); }}><Icon name="x" /></button>
                </div>
              </>
            ) : (
              <div>
                <div className="drop__icon"><Icon name="image" /></div>
                <strong>Drop a photo</strong> or click to browse
                <small>JPEG, PNG or WebP · one clear face works best</small>
              </div>
            )}
            <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => pick(e.target.files?.[0])} aria-label="choose image" />
          </div>
        ) : (
          <div className="cam">
            {shot ? <img src={shot.url} alt="captured frame" /> : <video ref={videoRef} autoPlay playsInline muted />}
            {!shot && !camErr ? <div className="cam__guide" aria-hidden="true"><span /></div> : null}
            {camErr ? <div className="cam__err">{camErr}</div> : null}
            <div className="cam__bar">
              {shot ? (
                <button type="button" className="btn btn--sm" onClick={retake}><Icon name="refresh" /> Retake</button>
              ) : (
                <button type="button" className="btn btn--sm btn--teal" onClick={capture} disabled={!camReady}><Icon name="camera" /> Capture</button>
              )}
            </div>
          </div>
        )}

        <details className="options">
          <summary><Icon name="chevron" /> Advanced options</summary>
          <div className="options__grid">
            <div className="field">
              <label htmlFor="thr">Match threshold <b>{thr.toFixed(3)}</b></label>
              <input id="thr" type="range" min="0.25" max="0.60" step="0.005" value={thr} onChange={(e) => setThr(Number(e.target.value))} />
            </div>
            <div className="field">
              <label htmlFor="maxc">Candidates to face-check <b>{maxC}</b></label>
              <input id="maxc" type="range" min="10" max="150" step="5" value={maxC} onChange={(e) => setMaxC(Number(e.target.value))} />
            </div>
            <label className="check"><input type="checkbox" checked={expand} onChange={(e) => setExpand(e.target.checked)} /> Widen with keyword image search when Lens recognises the person</label>
            <div className="field">
              <label htmlFor="chain">Blockchain</label>
              <select id="chain" value={chain} onChange={(e) => setChain(e.target.value)}>
                <option value="auto">Auto (EVM node if reachable, else simulated)</option>
                <option value="evm">EVM node (Anvil / Sepolia)</option>
                <option value="sim">Simulated chain</option>
              </select>
            </div>
          </div>
        </details>

        <div className="submit">
          <button type="submit" className="btn btn--teal btn--lg btn--block" disabled={!ready || busy || disabled}>
            {busy ? <><span className="spinner" /> Running…</> : <><Icon name="play" /> Identify and anchor</>}
          </button>
          <p className="hint">The face crop is uploaded to a temporary public URL (expires in a few hours) so the reverse-image engine can fetch it.</p>
        </div>
      </div>
    </form>
  );
}
