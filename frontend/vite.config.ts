import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Use the same backend as the native Arduino/camera bridges.
export default defineConfig(({ mode }) => {
  const BACKEND = loadEnv(mode, "..", "BACKEND_URL").BACKEND_URL || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": BACKEND,
        "/audio": BACKEND,
        "/ws": { target: BACKEND, ws: true },
      },
    },
  };
});
