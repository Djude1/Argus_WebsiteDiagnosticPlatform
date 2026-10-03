import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import { api } from "../api";

// Cloudflare Turnstile 人機驗證（註冊、Email 登入、忘記密碼、商業合作洽談）。
// 是否啟用與 site key 由後端 GET /api/auth/turnstile/ 決定，前後端不會一邊開一邊關；
// 讀不到設定時視為未啟用（後端若有啟用，送出時會回 403 與提示文字）。
// token 只能用一次：每次送出（不論成功失敗）後呼叫 ref.reset() 取新的 token。

export const TURNSTILE_FIELD = "cf-turnstile-response";
const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let configPromise = null;
let scriptPromise = null;

function loadConfig() {
  if (!configPromise) {
    configPromise = Promise.resolve()
      .then(() => api.get("/auth/turnstile/"))
      .then((response) => ({ enabled: Boolean(response.data?.enabled && response.data?.site_key), siteKey: response.data?.site_key || "" }))
      .catch(() => {
        configPromise = null;
        return { enabled: false, siteKey: "" };
      });
  }
  return configPromise;
}

function loadScript() {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("turnstile")));
      script.onerror = () => {
        scriptPromise = null;
        script.remove();
        reject(new Error("turnstile"));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

// 回傳 { loading, enabled, siteKey }
export function useTurnstileConfig() {
  const [config, setConfig] = useState({ loading: true, enabled: false, siteKey: "" });
  useEffect(() => {
    let cancelled = false;
    loadConfig().then((value) => !cancelled && setConfig({ loading: false, ...value }));
    return () => {
      cancelled = true;
    };
  }, []);
  return config;
}

// 在表單內顯示驗證元件；token 變動（取得、過期、失敗）時呼叫 onToken。
export const TurnstileWidget = forwardRef(function TurnstileWidget({ siteKey, action, onToken }, ref) {
  const containerRef = useRef(null);
  const widgetIdRef = useRef(null);
  const onTokenRef = useRef(onToken);
  const [failed, setFailed] = useState(false);
  onTokenRef.current = onToken;

  useImperativeHandle(ref, () => ({
    reset() {
      onTokenRef.current("");
      if (window.turnstile && widgetIdRef.current !== null) window.turnstile.reset(widgetIdRef.current);
    },
  }));

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    loadScript()
      .then((turnstile) => {
        if (cancelled || !containerRef.current) return;
        widgetIdRef.current = turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          // 跟網站主題（html[data-theme]），不是作業系統偏好；網站預設深色
          theme: document.documentElement.dataset.theme === "light" ? "light" : "dark",
          language: "zh-tw",
          callback: (token) => onTokenRef.current(token),
          "expired-callback": () => onTokenRef.current(""),
          "error-callback": () => onTokenRef.current(""),
        });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (window.turnstile && widgetIdRef.current !== null) window.turnstile.remove(widgetIdRef.current);
      widgetIdRef.current = null;
    };
  }, [siteKey, action]);

  return (
    <div className="turnstile-field">
      <div ref={containerRef} className="turnstile-widget" />
      {failed && (
        <p className="turnstile-error" role="alert">
          無法載入人機驗證，請檢查網路或關閉阻擋 challenges.cloudflare.com 的擴充功能後重新整理。
        </p>
      )}
    </div>
  );
});

export default TurnstileWidget;
