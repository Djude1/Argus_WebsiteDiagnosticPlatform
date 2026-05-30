import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
      "/static": "http://127.0.0.1:8000",
      "/django-admin": "http://127.0.0.1:8000",
    },
  },
  // 從專案根目錄讀取 .env（與後端 python-dotenv 共用同一份）
  envDir: "..",
  // 預設 VITE_ 前綴外，額外把 GOOGLE_OAUTH_CLIENT_ID 暴露給前端，避免與後端重複設定
  envPrefix: ["VITE_", "GOOGLE_OAUTH_CLIENT_ID"],
});
