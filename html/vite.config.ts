import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Base path: "/" when FastAPI serves the console, or "/<repo>/" when the
// bundle is published to GitHub Pages.
const base = process.env.VITE_BASE ?? "/";

export default defineConfig({
  base,
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Dev server talks to the FastAPI app; VITE_API_URL stays empty so the
      // browser uses same-origin paths.
      "/api": {
        target: process.env.VITE_DEV_API ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
