#!/usr/bin/env sh
# Start a local Anvil dev chain with persistent state (survives restarts).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/.anvil"
ANVIL="$ROOT/tools/foundry/anvil"
[ -x "$ANVIL" ] || ANVIL="$(command -v anvil || true)"
if [ -z "$ANVIL" ]; then
  echo "anvil not found. Run: python scripts/get_anvil.py  (or install Foundry: https://getfoundry.sh)"; exit 1
fi
echo "Starting Anvil (chain id 31337) at http://127.0.0.1:8545 -- state file: $ROOT/.anvil/state.json"
exec "$ANVIL" --state "$ROOT/.anvil/state.json" --state-interval 5 "$@"
