import React from "react";
import { createRoot, hydrateRoot } from "react-dom/client";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { BrowserRouter } from "react-router-dom";

import App, { preloadRoute } from "./App.jsx";
import "./styles.css";
// 會員區五頁的改版前樣式（只作用在 .member-legacy 內，見 styles/legacy-member/index.css）
import "./styles/legacy-member/index.css";

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

const googleClientId = (import.meta.env.GOOGLE_OAUTH_CLIENT_ID || "").trim();
const app = (
  <BrowserRouter>
    <App googleOAuthEnabled={Boolean(googleClientId)} />
  </BrowserRouter>
);

const tree = (
  <React.StrictMode>
    {googleClientId ? (
      <GoogleOAuthProvider clientId={googleClientId}>{app}</GoogleOAuthProvider>
    ) : app}
  </React.StrictMode>
);
// 公開頁在建置時已預先渲染成 HTML（scripts/prerender.mjs）：接手既有內容，不清空重畫；
// 其他頁面（會員區、後台）的 root 是空的，照常 createRoot
const rootEl = document.getElementById("root");
if (rootEl.hasChildNodes()) {
  // 先載入這一頁的程式碼再 hydrate，避免 hydrate 途中 lazy 區塊未就緒（見 App.jsx lazyNamed）
  preloadRoute(window.location.pathname).catch(() => {}).finally(() => hydrateRoot(rootEl, tree));
} else {
  createRoot(rootEl).render(tree);
}

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
