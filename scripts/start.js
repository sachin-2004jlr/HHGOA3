#!/usr/bin/env node
/* Production-style start: serve the built frontend (web/dist) from the API on one port.
 *   npm run build && npm start
 */
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..");
const isWin = process.platform === "win32";
const py = fs.existsSync(path.join(ROOT, ".venv")) ?
  path.join(ROOT, ".venv", isWin ? "Scripts/python.exe" : "bin/python") : (isWin ? "python" : "python3");
if (!fs.existsSync(path.join(ROOT, "web", "dist", "index.html"))) {
  console.error("web/dist not found - run `npm run build` first");
  process.exit(1);
}
const port = process.env.API_PORT || "8010";
console.log(`facechain -> http://localhost:${port}`);
spawn(py, ["-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", port], { stdio: "inherit", cwd: ROOT });
