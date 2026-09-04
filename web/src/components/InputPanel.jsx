import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui.jsx";

export default function InputPanel({ busy, disabled, onSubmit }) {
  const [tab, setTab] = useState("upload");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [over, setOver] = useState(false);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [camErr, setCamErr] = useState(null);
  const [shot, setShot] = useState(null);
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
      .catch((e) => setCamErr(e.name === "NotAllowedError" ? "Camera access denied" : `Camera unavailable: ${e.message}`));
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
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) return;
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
    c.toBlob((blob) => { if (blob) setShot({ blob, url: URL.createObjectURL(blob) }); }, "image/jpeg", 0.92);
  }

  function retake() {
    if (shot?.url) URL.revokeObjectURL(shot.url);
    setShot(null);
  }

  const ready = tab === "upload" ? !!file : !!shot;
  const submit = (e) => {
    e.preventDefault();
    if (!ready || busy || disabled) return;
    const opts = {};
    if (tab === "upload") onSubmit(file, opts, "upload");
    else onSubmit(new File([shot.blob], "webcam.jpg", { type: "image/jpeg" }), opts, "webcam");
  };

  return (
    <form className="card" onSubmit={submit}>
      <div className="card__head"><h3>Input</h3></div>
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
                <img className="preview" src={preview} alt="" />
                <div className="preview-actions">
                  <button type="button" className="iconbtn" aria-label="remove" onClick={() => { setFile(null); setPreview(null); }}><Icon name="x" /></button>
                </div>
              </>
            ) : (
              <div>
                <div className="drop__icon"><Icon name="image" /></div>
                <b>Drop a photo</b>
              </div>
            )}
            <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => pick(e.target.files?.[0])} aria-label="choose image" />
          </div>
        ) : (
          <div className="cam">
            {shot ? <img src={shot.url} alt="" /> : <video ref={videoRef} autoPlay playsInline muted />}
            {!shot && !camErr ? <div className="cam__guide" aria-hidden="true"><span /></div> : null}
            {camErr ? <div className="cam__err">{camErr}</div> : null}
            <div className="cam__bar">
              {shot ? (
                <button type="button" className="pill pill--outline pill--xs" onClick={retake}>Retake</button>
              ) : (
                <button type="button" className="pill pill--lav pill--xs" onClick={capture} disabled={!camReady}>Capture</button>
              )}
            </div>
          </div>
        )}

        <div className="submit">
          <button type="submit" className="pill pill--lav pill--block" disabled={!ready || busy || disabled}>
            {busy ? <><span className="spinner" /> Running</> : "Run a scan"}
          </button>
        </div>
      </div>
    </form>
  );
}
