import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API port is injected by scripts/dev.js (free-port detection); 8010 is the default.
const API = process.env.VITE_API_PORT || "8010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4300,
    strictPort: false,
    open: false,
    proxy: { "/api": { target: `http://127.0.0.1:${API}`, changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: false },
});
