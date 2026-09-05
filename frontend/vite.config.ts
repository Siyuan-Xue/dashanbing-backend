import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api/v1": loadEnv(mode, ".", "VITE_").VITE_API_PROXY || "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "../app/frontend",
    emptyOutDir: true,
  },
}));
