# facechain — Face Identification & Blockchain Verification

> HH Goa 2026 · Shortlisting Task 3

`facechain` is a command-line pipeline that takes a **face scan** (photo or live webcam
capture), **finds a matching post on the web / social media** with a genuine reverse-image
search, **verifies the match biometrically**, and **anchors a tamper-evident fingerprint of
the discovered post on a blockchain** — then proves it can re-verify the evidence against
the on-chain record.

```
 face scan ──► detect + embed ──► reverse image search ──► download every candidate
 (photo /      (YuNet + SFace,     (Google Lens via         and compare its face with
  webcam)       OpenCV DNN)         SerpApi / Serper)       the scanned face (SFace cosine)
                                                                      │
                                                                      ▼
 verify ◄─── read record back ◄─── anchor(recordHash, imageHash, faceHash, url, platform, sim)
 (any time)   from the chain        FaceMatchRegistry.sol on Anvil (local EVM) or Ethereum Sepolia
```

---

## What it does, step by step

| Step | What happens | Where |
|-----:|--------------|-------|
| 1 | **Face scan.** The input image (or a webcam frame) is run through the *YuNet* face detector. The largest face is aligned and encoded into a 128-d *SFace* embedding. Both models are from the OpenCV Model Zoo and run on CPU. | `facechain/face.py` |
| 2 | **Web / social search.** A face crop is uploaded to a short-lived anonymous image host (needed because Google Lens takes a URL), then queried through the **Google Lens** reverse-image API (SerpApi, or Serper.dev). Every returned page is a *candidate*. If Lens recognises the person, the search is widened with keyword image searches on Instagram / X / Facebook via DuckDuckGo. Nothing is hardcoded — the candidate list is whatever the engines return at run time. | `facechain/search.py`, `facechain/uploader.py` |
| 3 | **Biometric verification of candidates.** Every candidate image is downloaded, faces are detected, and each face is compared with the scanned face using SFace cosine similarity. Candidates below the *same-identity* threshold (0.363, OpenCV's recommended value) are rejected. Among the passing ones, social-media posts are preferred and the highest similarity wins. | `facechain/search.py` |
| 4 | **Evidence record.** An evidence bundle is written to `evidence/<run_id>/`: the original image, the aligned face crop, the embedding, the downloaded post image, all candidates with their scores, and `record.json`. Three SHA-256 fingerprints are computed: `recordHash` = hash of the canonical JSON record, `imageHash` = hash of the post image bytes, `faceHash` = hash of the query embedding. | `facechain/evidence.py` |
| 5 | **Blockchain anchoring.** `anchor(...)` is called on the `FaceMatchRegistry` Solidity contract with the three hashes, the post URL, the platform and the similarity. The tx hash, block number, block hash and contract address are saved to `chain_receipt.json`. | `contracts/FaceMatchRegistry.sol`, `facechain/chain/evm.py` |
| 6 | **Re-verification.** `verify` re-reads the bundle from disk, **recomputes** every hash from the raw files, calls `getRecord(recordHash)` on the contract and compares field by field. Any changed byte in the record, the image or the embedding produces a different hash → `NOT FOUND` / `MISMATCH`. `tamper-demo` demonstrates this by editing a copy of the evidence. | `facechain/cli.py` |

---

## Which blockchain

The same Solidity contract is used everywhere; only the RPC endpoint changes.

| Backend | How | When to use |
|---------|-----|-------------|
| **Anvil (Foundry) local EVM** — *default* | `scripts/start_anvil` runs a real EVM node on `http://127.0.0.1:8545` (chain id 31337) with state persisted to `.anvil/state.json`, so records survive restarts. The contract is auto-deployed on first use. | Offline demo, no faucet needed. |
| **Ethereum Sepolia testnet** (or any EVM chain) | Set `RPC_URL` to a Sepolia endpoint and `PRIVATE_KEY` to a funded test wallet, run `python -m facechain deploy` once. Receipts include Etherscan links. | Public, independently verifiable records. |
| **`sim` — pure-Python chain** | `--chain sim` writes proof-of-work blocks to `simchain.json` and validates the hash links on every verify. No node, no dependencies. | Fallback when no EVM node is available. |

### The contract (`contracts/FaceMatchRegistry.sol`, Solidity 0.8.26)

```solidity
struct Record {
    bytes32 recordHash;   // sha256(canonical record.json)
    bytes32 imageHash;    // sha256(matched post image bytes)
    bytes32 faceHash;     // sha256(query face embedding)
    string  postUrl;      // discovered social-media post
    string  platform;     // "instagram" | "x" | "facebook" | ...
    uint16  similarityBps;// cosine similarity * 10000
    uint64  timestamp;    // block.timestamp
    address submitter;
}
function anchor(bytes32 recordHash, bytes32 imageHash, bytes32 faceHash,
                string calldata postUrl, string calldata platform, uint16 similarityBps) external;
function getRecord(bytes32 recordHash) external view returns (Record memory);
function exists(bytes32 recordHash) external view returns (bool);
event RecordAnchored(bytes32 indexed recordHash, bytes32 indexed imageHash, ...);
```

`anchor` reverts with `AlreadyAnchored` if the same record hash is submitted twice. The compiled
ABI + bytecode are committed in `contracts/build/`, so no Solidity toolchain is required to run.

---

## How to run

### 0. Requirements

* Python 3.10+ (tested on 3.13, Windows 11; Linux/macOS work the same)
* A reverse-image-search API key — **one of**
  * [SerpApi](https://serpapi.com) → `SERPAPI_KEY` (free tier: 100 searches / month), or
  * [Serper.dev](https://serper.dev) → `SERPER_API_KEY` (free credits on sign-up)
* For the default local chain: the `anvil` binary (downloaded by a script below). Not needed for `--chain sim`.

### 1. Install

```bash
git clone <this repo> facechain && cd facechain
python -m venv .venv
# Windows:  .venv\Scripts\activate        Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your SERPAPI_KEY or SERPER_API_KEY in .env
```

The two ONNX face models (~39 MB) are downloaded automatically into `facechain/models/` on first run.

### 2. Start a blockchain node (local EVM)

```bash
python scripts/get_anvil.py       # one-time: downloads Foundry's anvil into tools/foundry/
scripts\start_anvil.cmd           # Windows   (keep this terminal open)
./scripts/start_anvil.sh          # Linux/macOS
```

### 3. Run the pipeline

```bash
# from a photo (three CC-licensed sample photos of public figures are in samples/)
python -m facechain run --image samples/elon_musk.jpg

# or scan your face live from the webcam (SPACE = capture, ESC = cancel)
python -m facechain run --webcam
```

Useful flags: `--min-similarity 0.30` (looser match), `--max-candidates 100`,
`--no-expand` (Lens results only), `--chain sim` (no node needed), `--skip-chain`.

### 4. Re-verify against the chain (any time later)

```bash
python -m facechain verify --evidence evidence/<run_id>
python -m facechain tamper-demo --evidence evidence/<run_id>   # edits a copy -> verification fails
python -m facechain chain-info                                 # node, contract, record count
```

### 5. Optional: use the public Ethereum Sepolia testnet

```bash
python scripts/new_wallet.py                  # creates a test wallet, stores PRIVATE_KEY in .env
# fund the printed address with Sepolia ETH (e.g. https://cloud.google.com/application/web3/faucet/ethereum/sepolia)
# in .env:  RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
python -m facechain deploy                    # once; address saved to deployments.json
python -m facechain run --image samples/elon_musk.jpg
```

---

## Repository layout

```
facechain/            Python package (CLI entry: python -m facechain)
  face.py             YuNet detection + SFace embedding, webcam capture
  uploader.py         temporary public hosting of the face crop (uguu.se, tmpfiles.org, ...)
  search.py           Google Lens (SerpApi / Serper), DuckDuckGo expansion, face-verified ranking
  evidence.py         evidence bundle, canonical JSON, SHA-256 fingerprints
  chain/evm.py        web3.py client: deploy / anchor / getRecord (Anvil, Sepolia, any EVM)
  chain/simchain.py   pure-Python proof-of-work chain fallback
  cli.py              run / verify / tamper-demo / deploy / chain-info / face
contracts/            FaceMatchRegistry.sol + compiled artifact + compile.py (py-solc-x)
scripts/              get_anvil.py, start_anvil.cmd/.sh, new_wallet.py
samples/              CC-licensed test photos (see samples/README.md)
evidence/             one folder per run (query, crop, embedding, post image, record.json, receipt)
```

---

## Known limitations

* **Reverse image search needs a third-party API key.** Google Lens has no public API; the
  pipeline uses SerpApi or Serper.dev. Both have free tiers but require sign-up. Results depend
  on how well the person is indexed on the web — public figures work well, private individuals
  usually return nothing (which is, arguably, the right outcome).
* **The face crop is uploaded to a temporary public host** (uguu.se / tmpfiles.org, expiring
  in 1–3 h) so that Google Lens can fetch it. Pass `--image-url` to use an already-public URL
  instead.
* **Social platforms block scrapers.** Instagram, X and Facebook usually serve a login wall to
  bots, so the "post content" that is downloaded and hashed is the image and metadata returned by
  the search engine (plus Open Graph tags when the page is fetchable), not a full page scrape.
* **Accuracy.** SFace is a compact model; the 0.363 cosine threshold gives good precision but
  low-resolution thumbnails, sunglasses or strong pose changes can push true matches below it.
  Use `--min-similarity` to tune, and read the transparency table — every candidate and its score
  is printed and saved in `candidates.json`.
* **Local chain by default.** Anvil is a real EVM but it is local; records are only as
  permanent as `.anvil/state.json`. Use Sepolia (or another public chain) for records that others
  can independently verify.
* **The chain stores hashes, not the content.** Verification proves that the evidence bundle
  you hold is exactly what was anchored; it does not make the post itself immutable (the original
  post can still be deleted by its author).

## Ethics

This was built for a hackathon shortlisting task using CC-licensed photos of public figures.
Face search technology can be misused; do not run it on people who have not consented.
