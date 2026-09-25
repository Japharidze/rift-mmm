import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The API runs separately in development (`r3m serve`); in production
  // FastAPI serves this build from the same origin. Either way the frontend
  // calls /api/... relative, so there is no base URL to configure anywhere.
  // No rewrite: the API serves these paths under /api in every environment,
  // so development must ask for the same path production will.
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
