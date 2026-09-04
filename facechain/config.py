"""Central configuration (paths + environment variables)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PKG_DIR = ROOT / "facechain"
MODELS_DIR = PKG_DIR / "models"
EVIDENCE_DIR = ROOT / "evidence"
CONTRACT_ARTIFACT = ROOT / "contracts" / "build" / "FaceMatchRegistry.json"
DEPLOYMENTS_FILE = ROOT / "deployments.json"
SIMCHAIN_FILE = ROOT / "simchain.json"

YUNET_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
    "face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
    "face_recognition_sface_2021dec.onnx"
)

# --- search ---------------------------------------------------------------
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
SEARCH_ENGINE = os.getenv("SEARCH_ENGINE", "auto").strip().lower()  # auto|yandex|serpapi|serper
# Also run a Google Lens "exact matches" query (costs one extra SerpApi credit per run).
LENS_EXACT_MATCHES = os.getenv("LENS_EXACT_MATCHES", "false").strip().lower() in ("1", "true", "yes")
# How many Lens results to ask for per query (Serper `num`).
LENS_NUM_RESULTS = int(os.getenv("LENS_NUM_RESULTS", "40"))

# SFace cosine-similarity threshold recommended by OpenCV for "same identity".
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.363"))
MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "60"))
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# --- blockchain -----------------------------------------------------------
CHAIN_BACKEND = os.getenv("CHAIN_BACKEND", "evm").strip().lower()  # evm|sim
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545").strip()
# Default = Anvil first pre-funded dev account (public knowledge, test-only).
ANVIL_DEV_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip() or ANVIL_DEV_KEY
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "").strip()

SOCIAL_PLATFORMS = {
    "instagram.com": "instagram",
    "x.com": "x",
    "twitter.com": "x",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "linkedin.com": "linkedin",
    "reddit.com": "reddit",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "pinterest.com": "pinterest",
    "pinterest.co.uk": "pinterest",
    "threads.net": "threads",
    "threads.com": "threads",
    "tumblr.com": "tumblr",
    "flickr.com": "flickr",
    "vk.com": "vk",
    "weibo.com": "weibo",
    "snapchat.com": "snapchat",
    "imgur.com": "imgur",
    "quora.com": "quora",
    "medium.com": "medium",
}
