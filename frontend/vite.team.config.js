// The AIMVA team app: the internal console on its own address (TEAM_URL, e.g. https://team.aimva.in).
//   npm run dev:team    → http://localhost:5174
//   npm run build:team  → dist-team/ (served by the backend on the team address; see backend/app/team_host.py)
// It shares components with the customer app but is a separate build: customers never download its code.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  root: path.resolve(import.meta.dirname, "team"),
  publicDir: path.resolve(import.meta.dirname, "public"),
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: { outDir: path.resolve(import.meta.dirname, "dist-team"), emptyOutDir: true, assetsDir: "team-assets" },
  server: {
    port: 5174,
    fs: { allow: [import.meta.dirname] },
    proxy: { "/api": "http://localhost:8000" },
  },
});
