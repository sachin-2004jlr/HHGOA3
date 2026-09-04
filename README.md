# facechain — Face Identification & Blockchain Verification

> HH Goa 2026 · Shortlisting Task 3

A web application (plus CLI) that takes a **face scan** — an uploaded photo or a live webcam
capture — **finds a real post on the web / social media** through a live reverse-image search,
**verifies the match biometrically**, and **anchors a tamper-evident fingerprint of the discovery
on a blockchain**. The evidence can be re-verified against the on-chain record at any time, and a
built-in tamper test shows a single changed byte failing verification.

```
 face scan ──► detect + embed ──► reverse image search ──► download every candidate and
 (upload /     (YuNet + SFace,     (Google Lens, live)      compare its face with the scan
  webcam)       OpenCV DNN)                                 (SFace cosine similarity)
                                                                      │
                                                                      ▼
 verify ◄─── read record back ◄─── anchor(recordHash, imageHash, faceHash, url, platform, sim)
 (any time)   from the chain        FaceMatchRegistry.sol on Anvil (local EVM), Sepolia, or a simulated chain
```

Nothing is pre-picked: the candidate list, the recognised name used to widen the search, the
chosen post and its score are whatever the live engines and the face model return for the image
you give it.

---

## Quick start (one command)

```bash
git clone https://github.com/sachin-2004jlr/HHGOA3.git
cd HHGOA3

python -m venv .venv
.venv\Scripts\activate            # Windows        (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

npm run setup                     # installs the launcher + the React frontend
cp .env.example .env              # optional: SERPER_API_KEY (or SERPAPI_KEY) adds Google Lens
python scripts/get_anvil.py       # optional: local EVM node (otherwise a simulated chain is used)

npm run dev
```

`npm run dev` starts **everything concurrently**: the Anvil EVM node (if installed), the FastAPI
backend and the Vite frontend. It picks free ports automatically (never 5173; defaults are
`4300` for the app and `8010` for the API), prints the URL and opens the browser:

```
  facechain  ->  http://localhost:4300     api: http://127.0.0.1:8010/docs
```

The landing page (Veriface) opens first; **Run a scan** in the header switches into the console,
and **Overview** in the console header returns.

### Using the console

1. **Input** — drop a photo, or switch to *Webcam*, allow the camera and press *Capture*.
   *Options* expose the match threshold, how many candidates to face-check, the social keyword
   widening and the chain backend.
2. Press **Run a scan**. The **Pipeline** rail shows the six steps live, with timings, a progress
   bar for the candidate check and an event log.
3. Results stream in as cards: the detected face and its embedding hash, the search statistics and
   candidate pages, the **match** (your scan next to the found post with the cosine meter), the
   table of every candidate checked, the three SHA-256 digests, the on-chain record (contract,
   transaction, block) and the seal verification.
4. **Re-verify hash** recomputes the hashes from the evidence files and reads the record back from
   the chain. **Tamper test** edits one field in a copy of the evidence and shows verification failing.
5. **Runs** lists every run kept in `evidence/`; click one to load it, or delete it. The landing
   page's *Ledger* section shows the latest sealed run live.

---

## What happens, step by step

| Step | What happens | Code |
|-----:|--------------|------|
| 1 | **Face scan.** *YuNet* detects faces; the largest is aligned and encoded by *SFace* into a 128-d embedding (OpenCV Model Zoo, CPU). | `facechain/face.py` |
| 2 | **Web / social search.** A tight face crop and the whole photo are uploaded to a short-lived anonymous image host (reverse-image engines need a URL). **Yandex reverse image search** (no key; it matches faces and often names the person) gets the crop, and **Google Lens** through Serper.dev or SerpApi (optional key; Lens does not identify people, so it only helps when the photo is already spread around the web) gets every view. Every returned page is a candidate. | `facechain/search.py`, `facechain/uploader.py` |
| 3 | **Biometric verification.** Every candidate image is downloaded and each face in it is compared with the scan by cosine similarity. Below OpenCV's same-identity threshold (0.363) a candidate is rejected. The person's name is then read from the titles of pages whose face matched (falling back to the engine's own guess). With that name, **Apify actors harvest their pictures from Instagram, X, Facebook (official page posts), TikTok, LinkedIn (profile photos and post images) and Google Images**, DuckDuckGo adds Pinterest and keyword hits, and every one of those pictures is face-checked too. Social-media posts are preferred and the highest similarity wins. | `facechain/search.py`, `facechain/pipeline.py` |
| 4 | **Evidence record.** `evidence/<run_id>/` holds the input, the face crop, the embedding, the downloaded post image, every candidate with its score and `record.json`. Fingerprints: `recordHash` = SHA-256 of the canonical record, `imageHash` = SHA-256 of the post image bytes, `faceHash` = SHA-256 of the embedding. | `facechain/evidence.py` |
| 5 | **Blockchain anchoring.** `anchor(...)` on the `FaceMatchRegistry` contract stores the three hashes, the post URL, the platform and the similarity. The receipt (tx hash, block, contract) is saved next to the evidence. | `contracts/FaceMatchRegistry.sol`, `facechain/chain/evm.py` |
| 6 | **Re-verification.** Hashes are recomputed from the files on disk, `getRecord(recordHash)` is read from the contract and compared field by field. | `facechain/verify.py` |

The whole flow lives in `facechain/pipeline.py`, which emits structured progress events consumed
both by the web backend (`server/app.py`) and the CLI.

---

## Which blockchain

The same Solidity contract is used everywhere; only the RPC endpoint changes. The backend picks
the chain automatically: an EVM node if one is reachable, otherwise the simulated chain.

| Backend | How | When |
|---------|-----|------|
| **Anvil (Foundry) local EVM** — default when installed | A real EVM node on `http://127.0.0.1:8545` (chain id 31337) started by `npm run dev`, state persisted in `.anvil/state.json` so records survive restarts. The contract is auto-deployed and the signer auto-funded. | Offline demo, no faucet needed. |
| **Ethereum Sepolia** (or any EVM chain) | Set `RPC_URL` to a Sepolia endpoint and `PRIVATE_KEY` to a funded test wallet (`python scripts/new_wallet.py`), run `python -m facechain deploy` once. Receipts then carry Etherscan links. | Public, independently verifiable records. |
| **Simulated chain** | Proof-of-work blocks in `simchain.json`, hash links validated on every verify. No node, no dependencies. | Fallback when no EVM node is available. |

```solidity
struct Record {
    bytes32 recordHash;    // sha256(canonical record.json)
    bytes32 imageHash;     // sha256(matched post image bytes)
    bytes32 faceHash;      // sha256(query face embedding)
    string  postUrl;       // discovered social-media post
    string  platform;      // "instagram" | "x" | "reddit" | ...
    uint16  similarityBps; // cosine similarity * 10000
    uint64  timestamp;     // block.timestamp
    address submitter;
}
function anchor(bytes32, bytes32, bytes32, string calldata, string calldata, uint16) external;
function getRecord(bytes32 recordHash) external view returns (Record memory);
```

`anchor` reverts with `AlreadyAnchored` for a duplicate record hash. The compiled ABI + bytecode
are committed in `contracts/build/`, so no Solidity toolchain is needed to run.

---

## Commands

| Command | What it does |
|---------|--------------|
| `npm run dev` | Start Anvil + API + frontend with free-port detection, open the browser |
| `npm run build && npm start` | Build the frontend and serve it from the API on one port (`API_PORT`, default 8010) |
| `npm test` | Unit tests (hashing, platform classification, match selection, simulated chain) |
| `python -m facechain run --image photo.jpg` | The same pipeline from the terminal (`--webcam` for a live scan) |
| `python -m facechain verify --evidence evidence/<run_id>` | Re-verify a run against the chain |
| `python -m facechain tamper-demo --evidence evidence/<run_id>` | Tamper a copy and show verification failing |
| `python -m facechain chain-info` | Node, contract and record count |

REST API (used by the frontend): `POST /api/runs` (multipart image) starts a run, `GET /api/runs/{id}`
streams its state, `POST /api/runs/{id}/verify` and `/tamper`, `GET /api/runs` for history,
`GET /api/chain`. Interactive docs at `/docs`.

---

## Repository layout

```
web/                  React + Vite frontend (Veriface landing page + console, dark theme)
server/app.py         FastAPI backend: jobs, evidence files, verify/tamper, history
scripts/dev.js        one-command launcher (free ports, Anvil + API + web)
facechain/            Python package
  pipeline.py         the six-step pipeline with progress events
  face.py             YuNet detection + SFace embedding, webcam capture
  search.py           Google Lens (Serper / SerpApi), DuckDuckGo widening, face-verified ranking
  social.py           Apify actors (Instagram, X, Facebook, TikTok, LinkedIn, Google Images) + DuckDuckGo Pinterest
  uploader.py         temporary public hosting of the face crop
  evidence.py         evidence bundle, canonical JSON, SHA-256
  verify.py           re-verification + tamper copy
  chain/evm.py        web3.py client (Anvil, Sepolia, any EVM)
  chain/simchain.py   pure-Python proof-of-work chain
  cli.py              terminal interface
contracts/            FaceMatchRegistry.sol + compiled artifact + compile.py
evidence/             one folder per run (ignored by git)
```

Configuration lives in `.env` (see `.env.example`): search key, thresholds, `RPC_URL`,
`PRIVATE_KEY`, `CHAIN_BACKEND`.

---

## Known limitations

* **Search coverage depends on the engines.** Yandex reverse image search is scraped from its
  public results page (no API, so it can rate-limit or change), and Google Lens by design does
  not identify people. Results depend on how well the person is indexed: public figures work
  well, private individuals usually return nothing.
* **The face crop is uploaded to a temporary public host** (uguu.se / tmpfiles.org, expiring in
  1–3 hours) so that Google Lens can fetch it.
* **Social platforms block scrapers**, so post content comes from the search engines and the Apify
  actors (image, URL, caption, author) plus Open Graph tags when the page is fetchable, not a full
  page scrape. Apify runs cost credits: roughly a few cents per run on the free plan's $5/month.
* **Accuracy.** SFace is a compact model; the 0.363 cosine threshold gives good precision, but
  small thumbnails, sunglasses or strong pose changes can push true matches below it. The
  threshold is adjustable in the console and every candidate's score is shown.
* **Local chain by default.** Anvil is a real EVM but local; records are as permanent as
  `.anvil/state.json`. Use Sepolia for records others can verify independently.
* **The chain stores hashes, not content.** Verification proves the evidence you hold is exactly
  what was anchored; the original post can still be deleted by its author.
* **One run at a time.** The backend queues runs so the face models and the chain nonce stay
  consistent; a typical run takes 20–70 s depending on how many candidate images are fetched.

## Ethics

Built for a hackathon shortlisting task. Face search can be misused; do not run it on people who
have not consented.
