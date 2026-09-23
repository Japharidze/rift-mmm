import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The API runs separately (`r3m serve`). Proxying keeps the frontend
  // origin-relative, so there is no base URL to configure per environment.
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", rewrite: p => p.replace(/^\/api/, "") } } },
});
