/**
 * Vite config for the Service Photo review UI.
 *
 * Key behaviors:
 *  - Dev server runs on http://localhost:5173 (Vite default).
 *  - Any request the app makes to `/api/...` is proxied to the FastAPI backend
 *    at http://localhost:8000, with the `/api` prefix stripped. This avoids
 *    needing CORS config on the backend during development — the browser only
 *    ever talks to the Vite origin.
 *  - `@/` resolves to `src/` for cleaner imports.
 */

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Backend routes live under /api/v1. The frontend hits the same path
      // verbatim — we just forward. Also forward /openapi.json for tooling.
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/openapi.json": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
