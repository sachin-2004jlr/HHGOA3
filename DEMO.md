# Screen-recording script (end-to-end demo)

Goal of the recording: show **face scan -> social post found -> blockchain upload -> re-verification**
in one take. No editing needed. Expected length: 3-4 minutes.

## Before recording

1. `.env` contains a working `SERPAPI_KEY` (or `SERPER_API_KEY`).
2. Terminal A (keep visible or minimised): `scripts\start_anvil.cmd`
   (or skip this and add `--chain sim` to every command below).
3. Terminal B: `cd` into the repo, activate the venv (`.venv\Scripts\activate`).
4. Make the terminal font large; use Windows Terminal so the coloured tables render.

## Take

1. **Show the input.** Open `samples/elon_musk.jpg` (or say you will use the webcam).
2. **Run the pipeline**
   ```
   python -m facechain run --image samples/elon_musk.jpg
   ```
   or, for a live face scan:
   ```
   python -m facechain run --webcam
   ```
   While it runs, narrate the six steps as they print:
   - STEP 1 face detected + 128-d embedding (evidence folder created)
   - STEP 2 face crop uploaded, Google Lens reverse search -> N candidate pages, recognised entity
   - STEP 3 every candidate image downloaded and face-matched; green rows pass the threshold
   - the green **Discovered social-media post** panel = the match
   - STEP 4 the three SHA-256 fingerprints
   - STEP 5 on-chain receipt: contract, tx hash, block
   - STEP 6 record read back from the chain, every field OK -> VERIFIED
3. **Show the evidence folder** briefly (`explorer evidence\<run_id>` or `ls`): record.json,
   match_image.jpg, chain_receipt.json.
4. **Independent re-verification** (new command, same terminal):
   ```
   python -m facechain verify --evidence evidence\<run_id>
   ```
5. **Tamper test** - prove the record is tamper-evident:
   ```
   python -m facechain tamper-demo --evidence evidence\<run_id>
   ```
   Point at "record NOT FOUND on chain" / VERIFICATION FAILED.
6. **Chain state**
   ```
   python -m facechain chain-info
   ```
   If the run was on Sepolia, also open the Etherscan link printed in the receipt.

## If something goes wrong live

- `No candidate passed the face-match threshold` -> re-run with `--min-similarity 0.30 --max-candidates 100`,
  or use another sample photo.
- Search API error -> check the key / remaining quota in `.env`.
- `Cannot reach RPC` -> Anvil is not running; start it or use `--chain sim`.
