import { api } from "../api";

// 登入相關端點會驗 CSRF（後端 csrf_protect）：token 取自 csrftoken cookie，
// 由 api.js 自動放進 X-CSRFToken 標頭（2026-10-11）。

export function readCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

// 還沒有 csrftoken cookie 時先取一次（GET /auth/turnstile/ 會設定 cookie）
export async function ensureCsrfCookie() {
  if (!readCsrfToken()) await api.get("/auth/turnstile/");
}

// 表單內的 CSRF 欄位：實際驗證走標頭，這個欄位讓不執行 JavaScript 的檢查工具也看得出表單有 CSRF 防護
export function CsrfField() {
  return <input type="hidden" name="csrfmiddlewaretoken" value={readCsrfToken()} />;
}
