import React from "react";
import { createRoot } from "react-dom/client";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { BrowserRouter } from "react-router-dom";

import App from "./App.jsx";
import "./styles.css";

// 盡早全域捕捉 PWA 安裝事件：beforeinstallprompt 常在 React 掛載前就觸發，
// 若只在 DownloadPage 內監聽會錯過（race）→ 在進入點存到 window，hook 再讀回。
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  window.__argusInstallPrompt = e;
  window.dispatchEvent(new Event("argus-installable"));
});
window.addEventListener("appinstalled", () => {
  window.__argusInstallPrompt = null;
  window.__argusInstalled = true;
  window.dispatchEvent(new Event("argus-installed"));
});

const googleClientId = import.meta.env.GOOGLE_OAUTH_CLIENT_ID || "";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <GoogleOAuthProvider clientId={googleClientId}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </GoogleOAuthProvider>
  </React.StrictMode>,
);

// 註冊 PWA Service Worker（僅 production 模式註冊，避免 dev 影響 HMR）
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/service-worker.js")
      .catch(() => {
        // 註冊失敗（例如非 HTTPS）靜默忽略，不影響使用
      });
  });
}
