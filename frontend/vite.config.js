import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replaceAll("\\", "/");
          if (!normalizedId.includes("/node_modules/")) return undefined;
          if (
            /\/node_modules\/(?:react|react-dom|react-router|react-router-dom|scheduler|zustand|use-sync-external-store|@remix-run\/router)\//.test(
              normalizedId,
            )
          ) {
            return "vendor-react";
          }
          if (
            /\/node_modules\/(?:reactflow|@reactflow\/|d3-)/.test(normalizedId)
          ) {
            return "vendor-reactflow";
          }
          if (
            normalizedId.includes("/node_modules/axios/") ||
            normalizedId.includes("/node_modules/@react-oauth/google/")
          ) {
            return "vendor-services";
          }
          return "vendor-misc";
        },
      },
    },
  },
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
