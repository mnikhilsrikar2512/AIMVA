import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  // Pre-bundle lazily loaded libraries up front so Vite never re-optimises (and duplicates React) mid-session.
  optimizeDeps: { include: ["three", "@react-three/fiber", "@react-three/drei", "framer-motion"] },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/s/": "http://localhost:8000",
    },
  },
});
