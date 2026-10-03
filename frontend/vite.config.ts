import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Python UI bridge (backend/server.py) runs on :8000; proxy its routes so
// the page can use relative URLs.
const BACKEND = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": BACKEND,
      "/audio": BACKEND,
      "/ws": { target: BACKEND, ws: true },
    },
  },
});
