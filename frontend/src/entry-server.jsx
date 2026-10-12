// 建置時預先渲染公開頁（scripts/prerender.mjs 呼叫）：讓不執行 JavaScript 的爬蟲與 AI 也讀得到內容。
// 樹狀結構要與 main.jsx 相同，瀏覽器端 hydrate 才接得上。
import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { StaticRouter } from "react-router";

import App, { preloadRoute } from "./App.jsx";

const googleClientId = (import.meta.env.GOOGLE_OAUTH_CLIENT_ID || "").trim();

export async function render(url) {
  // 先載入這一頁的 lazy 元件，renderToString 才會輸出完整內容而不是「正在載入頁面…」
  await preloadRoute(url);
  const app = (
    <StaticRouter location={url}>
      <App googleOAuthEnabled={Boolean(googleClientId)} />
    </StaticRouter>
  );
  return renderToString(
    <StrictMode>
      {googleClientId ? (
        <GoogleOAuthProvider clientId={googleClientId}>{app}</GoogleOAuthProvider>
      ) : app}
    </StrictMode>,
  );
}

export { PRERENDERED_ROUTES } from "./App.jsx";
export { descriptionForPath, titleForPath } from "./shared/documentTitle";
