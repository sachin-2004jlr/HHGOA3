#!/usr/bin/env node
/* One command to start everything:  npm run dev
 *   - finds free ports (never 5173), starting at WEB_PORT=4300 / API_PORT=8010
 *   - starts Anvil (if tools/foundry/anvil exists), the FastAPI backend and the Vite frontend
 *   - opens http://localhost:<web port>
 */
const { spawn } = require("node:child_process");
const net = require("node:net");
const fs = require("node:fs");
const path = require("node:path");
const concurrently = require("concurrently");

const ROOT = path.resolve(__dirname, "..");
const isWin = process.platform === "win32";

function portFree(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(false));
    srv.once("listening", () => srv.close(() => resolve(true)));
    srv.listen(port, "127.0.0.1");
  });
}
async function pickPort(start, avoid = []) {
  for (let p = start; p < start + 200; p += 1) {
    if (avoid.includes(p)) continue;
    if (await portFree(p)) return p;
  }
  throw new Error(`no free port near ${start}`);
}
function venvPython() {
  const c = isWin ? path.join(ROOT, ".venv", "Scripts", "python.exe") : path.join(ROOT, ".venv", "bin", "python");
  return fs.existsSync(c) ? c : (isWin ? "python" : "python3");
}
function anvilBinary() {
  const local = path.join(ROOT, "tools", "foundry", isWin ? "anvil.exe" : "anvil");
  return fs.existsSync(local) ? local : null;
}

(async () => {
  const WEB = await pickPort(Number(process.env.WEB_PORT || 4300), [5173]);
  const API = await pickPort(Number(process.env.API_PORT || 8010), [WEB, 5173]);
  const anvilPortFree = await portFree(8545);
  const anvil = anvilBinary();
  fs.mkdirSync(path.join(ROOT, ".anvil"), { recursive: true });

  const commands = [
    {
      name: "api", prefixColor: "cyan",
      command: `"${venvPython()}" -m uvicorn server.app:app --host 127.0.0.1 --port ${API} --log-level warning`,
      env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
    },
    {
      name: "web", prefixColor: "magenta",
      command: `npm --prefix web run dev -- --port ${WEB} --strictPort`,
      env: { ...process.env, VITE_API_PORT: String(API) },
    },
  ];
  if (anvil && anvilPortFree) {
    commands.unshift({
      name: "anvil", prefixColor: "yellow",
      command: `"${anvil}" --state "${path.join(ROOT, ".anvil", "state.json")}" --state-interval 5 --silent`,
    });
  } else if (!anvilPortFree) {
    console.log("[dev] port 8545 already in use - assuming an Ethereum node is running there.");
  } else {
    console.log("[dev] anvil not found (python scripts/get_anvil.py) - backend will use the simulated chain.");
  }

  console.log(`\n  facechain  ->  http://localhost:${WEB}     api: http://127.0.0.1:${API}/docs\n`);
  if (!process.env.NO_OPEN) setTimeout(() => {
    const url = `http://localhost:${WEB}`;
    const opener = isWin ? ["cmd", ["/c", "start", "", url]] : process.platform === "darwin" ? ["open", [url]] : ["xdg-open", [url]];
    try { spawn(opener[0], opener[1], { stdio: "ignore", detached: true }).unref(); } catch (_) { /* ignore */ }
  }, 2500);

  const { result } = concurrently(commands, { prefix: "name", killOthersOn: ["failure"], restartTries: 0, cwd: ROOT });
  result.then(() => process.exit(0), () => process.exit(1));
})();
