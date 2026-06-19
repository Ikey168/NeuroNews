import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development, requests to `/api` and the unversioned backend
// route prefixes are proxied to the FastAPI backend (default :8000).
// Override the target with VITE_API_PROXY_TARGET.
const apiTarget = process.env.VITE_API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/news": { target: apiTarget, changeOrigin: true },
      "/news_sentiment": { target: apiTarget, changeOrigin: true },
      "/topics": { target: apiTarget, changeOrigin: true },
      "/graph": { target: apiTarget, changeOrigin: true },
      "/search": { target: apiTarget, changeOrigin: true },
    },
  },
});
