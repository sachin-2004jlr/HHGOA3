"""Face detection (YuNet) + face embedding (SFace) via the OpenCV DNN module.

Both models come from the OpenCV Model Zoo and run on CPU with no extra deps.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from . import config  # noqa: E402

MAX_SIDE = 1280  # downscale big images before detection


@dataclass
class Face:
    bbox: tuple[int, int, int, int]        # x, y, w, h  (in the analysed image)
    score: float
    landmarks: list[tuple[float, float]]    # 5 points: eyes, nose, mouth corners
    embedding: Optional[np.ndarray] = None  # 128-d SFace vector (L2-normalised)
    aligned: Optional[np.ndarray] = field(default=None, repr=False)  # 112x112 crop

    @property
    def area(self) -> int:
        return self.bbox[2] * self.bbox[3]


def ensure_models() -> None:
    """Download the ONNX models on first use."""
    import requests

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for path, url in ((config.YUNET_MODEL, config.YUNET_URL), (config.SFACE_MODEL, config.SFACE_URL)):
        if path.exists() and path.stat().st_size > 100_000:
            continue
        print(f"[models] downloading {path.name} ...")
        r = requests.get(url, timeout=120, allow_redirects=True)
        r.raise_for_status()
        path.write_bytes(r.content)


class FaceEngine:
    """Detect faces and compute identity embeddings."""

    def __init__(self, det_threshold: float = 0.8):
        ensure_models()
        self._lock = threading.Lock()  # OpenCV DNN nets are not safe for concurrent forward()
        self._det = cv2.FaceDetectorYN.create(
            str(config.YUNET_MODEL), "", (320, 320), det_threshold, 0.3, 5000
        )
        self._rec = cv2.FaceRecognizerSF.create(str(config.SFACE_MODEL), "")

    # ---------------------------------------------------------------- utils
    @staticmethod
    def load_image(path: str | Path) -> np.ndarray:
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Could not decode image: {path}")
        return img

    @staticmethod
    def decode_bytes(data: bytes) -> Optional[np.ndarray]:
        if not data:
            return None
        arr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    @staticmethod
    def _prepare(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        scale = min(1.0, MAX_SIDE / max(h, w))
        if scale < 1.0:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        # YuNet needs a reasonably sized input; upscale tiny thumbnails.
        h, w = img.shape[:2]
        if max(h, w) < 160:
            f = 160 / max(h, w)
            img = cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_CUBIC)
        return img

    # ------------------------------------------------------------- pipeline
    def detect(self, img: np.ndarray) -> tuple[np.ndarray, list[Face]]:
        """Return (analysed_image, faces). Faces sorted largest-first."""
        img = self._prepare(img)
        h, w = img.shape[:2]
        self._det.setInputSize((w, h))
        _, dets = self._det.detect(img)
        faces: list[Face] = []
        if dets is not None:
            for d in dets:
                x, y, bw, bh = (int(round(float(v))) for v in d[:4])
                lm = [(float(d[4 + 2 * i]), float(d[5 + 2 * i])) for i in range(5)]
                faces.append(Face(bbox=(x, y, bw, bh), score=float(d[14]), landmarks=lm))
        faces.sort(key=lambda f: f.area, reverse=True)
        return img, faces

    def embed(self, img: np.ndarray, face: Face) -> Face:
        """Align, crop and embed a detected face (fills face.embedding / aligned)."""
        det = np.array(
            [*face.bbox, *[c for pt in face.landmarks for c in pt], face.score], dtype=np.float32
        )
        aligned = self._rec.alignCrop(img, det)
        feat = self._rec.feature(aligned)  # shape (1,128)
        vec = np.asarray(feat, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        face.embedding = vec / norm if norm > 0 else vec
        face.aligned = aligned
        return face

    def analyze(self, img: np.ndarray, max_faces: int = 5) -> tuple[np.ndarray, list[Face]]:
        with self._lock:
            img, faces = self.detect(img)
            for f in faces[:max_faces]:
                self.embed(img, f)
        return img, faces[:max_faces]

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity of two embeddings (SFace same-identity threshold ~0.363)."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    # -------------------------------------------------------------- webcam
    def capture_webcam(self, device: int = 0) -> np.ndarray:
        """Live face scan: camera preview, SPACE captures, ESC aborts."""
        cap = cv2.VideoCapture(device, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(device)
        if not cap.isOpened():
            raise RuntimeError("Could not open webcam")
        print("[webcam] SPACE = capture, ESC = cancel")
        frame = None
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Webcam read failed")
                view = frame.copy()
                _, faces = self.detect(view)
                for f in faces:
                    x, y, w, h = f.bbox
                    cv2.rectangle(view, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(view, "SPACE: capture   ESC: cancel", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("facechain - face scan", view)
                k = cv2.waitKey(1) & 0xFF
                if k == 27:
                    raise KeyboardInterrupt("capture cancelled")
                if k == 32:
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()
        return frame


def draw_faces(img: np.ndarray, faces: list[Face]) -> np.ndarray:
    out = img.copy()
    for i, f in enumerate(faces):
        x, y, w, h = f.bbox
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
        for (px, py) in f.landmarks:
            cv2.circle(out, (int(px), int(py)), 2, (0, 0, 255), -1)
        cv2.putText(out, f"#{i} {f.score:.2f}", (x, max(0, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out


def crop_face(img: np.ndarray, face: Face, margin: float = 0.45,
              min_size: int = 400, max_size: int = 900) -> np.ndarray:
    """Face crop with context margin (what we send to the reverse-image engine)."""
    H, W = img.shape[:2]
    x, y, w, h = face.bbox
    cx, cy = x + w / 2, y + h / 2
    side = max(w, h) * (1 + margin)
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x1, y1 = int(min(W, cx + side / 2)), int(min(H, cy + side / 2))
    crop = img[y0:y1, x0:x1]
    s = max(crop.shape[:2])
    if s < min_size:
        f = min_size / s
        crop = cv2.resize(crop, (int(crop.shape[1] * f), int(crop.shape[0] * f)), interpolation=cv2.INTER_CUBIC)
    elif s > max_size:
        f = max_size / s
        crop = cv2.resize(crop, (int(crop.shape[1] * f), int(crop.shape[0] * f)), interpolation=cv2.INTER_AREA)
    return crop


def encode_jpeg(img: np.ndarray, quality: int = 92) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def search_image(img: np.ndarray, max_side: int = 1280) -> np.ndarray:
    """The whole photo, downscaled for the reverse-image engine (context helps identify people)."""
    h, w = img.shape[:2]
    f = min(1.0, max_side / max(h, w))
    if f < 1.0:
        return cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)
    return img
