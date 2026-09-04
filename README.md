<div align="center">

<img src="docs/landing.jpg" alt="Veriface" width="100%">

# Veriface

**Scan a face → find the real social media post it appears in → seal the proof on a blockchain.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](#)
[![React](https://img.shields.io/badge/React-18-20232A?logo=react&logoColor=61DAFB)](#)
[![Solidity](https://img.shields.io/badge/Solidity-0.8-363636?logo=solidity&logoColor=white)](#)
[![OpenCV](https://img.shields.io/badge/OpenCV-YuNet%20%2B%20SFace-5C3EE8?logo=opencv&logoColor=white)](#)
[![License](https://img.shields.io/badge/License-MIT-d6a8ff)](LICENSE)

*HH Goa 2026 · Shortlisting Task 3*

</div>

<br>

## What it is

Veriface is a small web app. You give it a face (a photo or a webcam capture). It finds a real post on the
web or social media that shows the same face, and then writes a fingerprint of that discovery to a
blockchain. Later, anyone with the saved evidence can prove it has not been changed by checking it
against the chain.

Nothing is pre-picked. Every result comes from live searches and a real face comparison at run time.

```mermaid
flowchart LR
    A([📷 Face scan]) --> B[Detect + encode<br/>YuNet · SFace]
    B --> C[Reverse image search<br/>Yandex · Google Lens]
    C --> D[Face-check every result]
    D --> E([✅ Matching post])
    E --> F[SHA-256 digests]
    F --> G[(⛓ Smart contract<br/>Anvil / Sepolia)]
    G --> H([🔍 Re-verify any time])
```

<br>

## How it works, step by step

**1 · Face scan.** The photo goes through OpenCV's *YuNet* detector, which finds the face, and *SFace*,
which turns it into a list of 128 numbers (an "embedding"). Two faces of the same person give similar
numbers; the similarity is measured as a cosine score from −1 to 1. OpenCV's threshold for
"same person" is 0.363.

**2 · Reverse image search.** A tight crop of the face and the whole photo are uploaded to a temporary
public link and sent to *Yandex* (which can match faces) and, if you add a key, *Google Lens*. Every
page they return is a candidate.

**3 · Face check.** Each candidate image is downloaded and the faces in it are compared with your scan.
Only candidates above the threshold survive. The person's name is read from the titles of those
matching pages (never typed in), a quick keyword image search widens the pool with more social posts,
and those are face-checked too. The highest-scoring social media post wins; a post from the person's
own account or a photo network gets a small bonus.

**4 · Fingerprints.** Three SHA-256 digests are computed: the evidence record, the post image bytes and
the face embedding. Everything is saved in `evidence/<run_id>/`.

**5 · Blockchain.** The digests, post URL, platform and score are written to the `FaceMatchRegistry`
smart contract. You get the contract address, transaction hash and block number.

**6 · Verification.** The record is read back from the chain and compared field by field. At any later
time, **Re-verify hash** recomputes every digest from the files on disk and checks them against the
chain. **Tamper test** changes one field in a copy of the evidence and shows the check fail.

<br>

## Example run

Input: a photo of Virat Kohli. Local Anvil chain. No API keys except the optional Google Lens one.

| | |
|---|---|
| Search hits | 209 pages from Yandex + Google Lens, widened by 36 |
| Identified as | Virat Kohli (read from matching pages) |
| Faces checked | 96 candidate images, 89 matched |
| Best post | YouTube post, cosine similarity **0.983** |
| On chain | Anvil, block 13, transaction `0x4055…56d5` |
| Verification | all 9 checks OK; tamper test detected |
| Time | 34.5 seconds |

<div align="center">
<img src="docs/console.jpg" alt="Console: pipeline, face scan, search results and the 0.983 match" width="92%">
<br><br>
<img src="docs/verify.jpg" alt="Seal card: verified against the chain, tamper test detected" width="60%">
</div>

<br>

## Run it

You need Python 3.10 or newer, Node.js 18 or newer, and git.

```bash
git clone https://github.com/sachin-2004jlr/HHGOA3.git
cd HHGOA3

python -m venv .venv
.venv\Scripts\activate                 # Windows      (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

npm run setup                          # installs the launcher and the web app
python scripts/get_anvil.py            # downloads the local blockchain node (one time, ~100 MB)

npm run dev
```

`npm run dev` starts three things together, on free ports, and opens the browser:
the Anvil blockchain node, the Python API and the web app.

In the browser: press **Run a scan** in the header, drop a photo or open the webcam, and press
**Run a scan**. The six steps run live; the cards fill in as each finishes.

<br>

## What you see in the console

| Card | What it shows |
|---|---|
| **Input** | Photo upload or webcam capture. *Options*: match threshold, how many candidates to check, keyword widening on or off, which chain |
| **Pipeline** | The six steps with timings, a progress bar and an event log |
| **01 · Face scan** | The detected face, the aligned crop, the search crop and the hash of the embedding |
| **02 · Open-web search** | Engines used, number of hits, who the face was identified as, the candidate pages |
| **03 · Match** | Your scan beside the found post with the similarity meter and a link to the post |
| **Candidates** | Every image that was face-checked, with its score |
| **04 · Digest** | The three SHA-256 fingerprints |
| **05 · On-chain record** | Contract, transaction, block, time and gas |
| **06 · Seal** | **Re-verify hash** and **Tamper test**, with a field-by-field comparison |
| **Runs** | Every past run, reloadable; delete with the bin icon |

<br>

## Settings (all optional)

Copy `.env.example` to `.env` and fill in what you want.

| Setting | What it does |
|---|---|
| `SERPER_API_KEY` or `SERPAPI_KEY` | Adds Google Lens next to Yandex ([serper.dev](https://serper.dev) has free credits) |
| `RPC_URL` and `PRIVATE_KEY` | Use a public chain, for example Ethereum Sepolia, instead of local Anvil |
| `FACE_MATCH_THRESHOLD` | Same-person threshold, default 0.363 |
| `MAX_CANDIDATES` | How many candidate images to face-check, default 60 |

<br>

## The blockchain

The same Solidity contract runs everywhere; only the endpoint changes.

| Backend | How | When to use |
|---|---|---|
| **Anvil** (default) | A real local Ethereum node started by `npm run dev`; its state is kept in `.anvil/` so records survive restarts | Offline demo, nothing to fund |
| **Ethereum Sepolia** | Create a wallet with `python scripts/new_wallet.py`, fund it from a faucet, set `RPC_URL`, run `python -m facechain deploy` once | Public records with Etherscan links |
| **Simulated chain** | Proof-of-work blocks in `simchain.json` | No node at all |

```solidity
struct Record {
    bytes32 recordHash;     // sha256 of the evidence record
    bytes32 imageHash;      // sha256 of the post image
    bytes32 faceHash;       // sha256 of the face embedding
    string  postUrl;
    string  platform;
    uint16  similarityBps;  // similarity × 10000
    uint64  timestamp;
    address submitter;
}
function anchor(bytes32, bytes32, bytes32, string, string, uint16) external;
function getRecord(bytes32 recordHash) external view returns (Record memory);
```

The chain stores only hashes. It proves the saved evidence is exactly what was anchored; the photo and
the embedding never leave your machine.

<br>

## From the terminal

The same pipeline without the web app:

```bash
python -m facechain run --image photo.jpg                  # or --webcam
python -m facechain verify --evidence evidence/<run_id>
python -m facechain tamper-demo --evidence evidence/<run_id>
python -m facechain chain-info
```

<br>

## Project layout

```
web/              React front end (landing page + console)
server/app.py     FastAPI back end: runs, evidence files, verify, tamper
facechain/
  pipeline.py     the six steps, with progress events
  face.py         YuNet detection, SFace embedding, webcam capture
  search.py       Yandex + Google Lens, face-checked ranking, keyword widening
  evidence.py     evidence folder and SHA-256 digests
  verify.py       re-verification and the tamper copy
  chain/          web3.py client for any EVM chain, plus the simulated chain
contracts/        FaceMatchRegistry.sol and its compiled artifact
scripts/          one-command launcher, Anvil download, wallet helper
tests/            unit tests (python -m unittest discover -s tests)
evidence/         one folder per run (not committed)
```

<br>

## If something goes wrong

| Symptom | What to do |
|---|---|
| "No matching post" | The face may not be on the public web. Try a clearer, front-facing photo, or lower the threshold in *Options* |
| Search step fails with a Yandex captcha | Wait a minute and run again; Yandex briefly rate-limits |
| Webcam does not start | Allow camera access in the browser; it works on `localhost` without HTTPS |
| "Cannot reach RPC" | Anvil is not running; use `npm run dev`, or choose *Simulated* chain in *Options* |
| Ports busy | The launcher picks the next free ports and prints the URL |

<br>

## Good to know

- Only people who exist on the public web can be found; private faces return "no match".
- Google Lens does not identify people by design, so it helps only when the exact photo is already online. Yandex does match faces.
- A score just above 0.363 can be a false positive for a private person; the higher the score, the safer the match.
- Face search can be misused. Do not run it on people who have not consented.

<br>

<div align="center">
<sub>OpenCV · Yandex · Google Lens · FastAPI · React · Solidity · web3.py · Anvil</sub>
</div>
