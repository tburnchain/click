import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 시 /api, /health 를 FastAPI(8000)로 프록시. 빌드 산출물은 dist/ → FastAPI가 정적 서빙.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  build: { outDir: "dist" },
});
