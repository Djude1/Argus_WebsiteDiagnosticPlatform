import { useEffect, useState } from "react";
import { GoogleLogin } from "@react-oauth/google";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import { apiErrorMessage } from "../../shared/AppShared.jsx";

function RequireAuth({ children }) {
  const accessToken = useArgusStore((state) => state.accessToken);
  const authReady = useArgusStore((state) => state.authReady);
  if (!authReady) {
    return <p className="loading-state">正在驗證登入狀態…</p>;
  }
  if (accessToken) {
    return children;
  }
  // 使用者直接輸入 /scans/123 之類 deep link 但未登入時，帶 next 讓登入後跳回
  const next = encodeURIComponent(
    window.location.pathname + window.location.search,
  );
  return <Navigate to={`/login?next=${next}`} replace />;
}

function LoginPage({ googleOAuthEnabled }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const accessToken = useArgusStore((s) => s.accessToken);
  const setToken = useArgusStore((s) => s.setToken);
  const [tab, setTab] = useState(googleOAuthEnabled ? "google" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const next = searchParams.get("next");
  const redirect = (!next || next === "/login" || !next.startsWith("/")) ? "/dashboard" : next;

  // 已登入則直接跳轉
  if (accessToken) {
    return <Navigate to={redirect} replace />;
  }

  function handleToken(access) {
    setToken(access);
    navigate(redirect, { replace: true });
  }

  async function handleEmailLogin(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/email-login/", { email, password });
      handleToken(res.data.access);
    } catch (err) {
      setError(err.response?.data?.detail || "登入失敗，請確認 Email 與密碼。");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("兩次密碼輸入不一致。");
      return;
    }
    setLoading(true);
    try {
      const res = await api.post("/auth/register/", { email, password });
      handleToken(res.data.access);
    } catch (err) {
      const d = err.response?.data || {};
      setError(d.email || d.password || d.detail || "註冊失敗。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <button
          type="button"
          className="login-back"
          onClick={() => navigate("/project")}
        >
          ← 返回首頁
        </button>
        <div className="login-brand">
          <span className="login-brand-glyph">⟡</span>
          <span className="login-brand-name">ARGUS</span>
        </div>
        <p className="login-sub">授權式 AI 網站健檢平台</p>

        <div className="login-tabs">
          {[
            ...(googleOAuthEnabled ? [{ key: "google", label: "Google 登入" }] : []),
            { key: "login", label: "Email 登入" },
            { key: "register", label: "新帳號" },
          ].map((t) => (
            <button
              key={t.key}
              type="button"
              className={`login-tab ${tab === t.key ? "active" : ""}`}
              onClick={() => { setTab(t.key); setError(""); }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <p className="login-error">{error}</p>}

        {googleOAuthEnabled && tab === "google" && (
          <div className="login-google-wrap">
            <GoogleLogin
              onSuccess={(credentialResponse) => {
                api.post("/auth/google/", { credential: credentialResponse.credential })
                  .then((res) => handleToken(res.data.access))
                  .catch(() => setError("Google 登入失敗，請稍後再試。"));
              }}
              onError={() => setError("Google 登入元件錯誤，請重新整理。")}
              useOneTap={false}
              theme="filled_black"
              shape="pill"
            />
          </div>
        )}

        {tab === "login" && (
          <form className="login-form" onSubmit={handleEmailLogin}>
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
            <input
              className="input"
              type="password"
              placeholder="密碼"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
            <button className="login-submit" type="submit" disabled={loading}>
              {loading ? "登入中…" : "登入"}
            </button>
            <p className="login-forgot-hint">
              <button
                type="button"
                className="login-forgot-link"
                onClick={() => navigate("/password-reset")}
              >
                忘記密碼？
              </button>
            </p>
          </form>
        )}

        {tab === "register" && (
          <form className="login-form" onSubmit={handleRegister}>
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
            <input
              className="input"
              type="password"
              placeholder="密碼（至少 8 字元）"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            <input
              className="input"
              type="password"
              placeholder="確認密碼"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            <button className="login-submit" type="submit" disabled={loading}>
              {loading ? "建立中…" : "建立帳號"}
            </button>
          </form>
        )}

        <p className="login-notice">
          管理員請用上方 Email 登入，登入後於右上角進入 <code>/admin</code> 後台。
        </p>
      </div>
    </div>
  );
}

function PasswordResetRequestPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [serverMessage, setServerMessage] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      const res = await api.post("/auth/password-reset/request/", {
        email: email.trim().toLowerCase(),
      });
      setServerMessage(res.data?.detail || "若該 Email 已註冊，重設信已寄出。");
      setSubmitted(true);
    } catch {
      // 後端設計為永遠成功；網路錯誤才會走到這
      setServerMessage("送出失敗，請檢查網路連線後再試。");
      setSubmitted(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <button
          type="button"
          className="login-back"
          onClick={() => navigate("/login")}
        >
          ← 返回登入
        </button>
        <div className="login-brand">
          <span className="login-brand-glyph">⟡</span>
          <span className="login-brand-name">重設密碼</span>
        </div>
        <p className="login-sub">輸入註冊時的 Email，我們會寄出重設連結（60 分鐘內有效）。</p>

        {submitted ? (
          <div className="login-info-box">
            <p>{serverMessage}</p>
            <p className="login-info-foot">
              收不到信？請檢查垃圾郵件夾，或確認 Email 是否拼寫正確。
            </p>
            <button
              type="button"
              className="login-submit"
              onClick={() => navigate("/login")}
            >
              回到登入頁
            </button>
          </div>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              autoFocus
            />
            <button className="login-submit" type="submit" disabled={loading || !email.trim()}>
              {loading ? "送出中…" : "寄出重設連結"}
            </button>
            <p className="login-forgot-hint">
              Google 帳號的密碼請至 Google 帳號設定管理，本平台無法重設。
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

function PasswordResetConfirmPage() {
  const navigate = useNavigate();
  const [token] = useState(() => (
    new URLSearchParams(window.location.hash.slice(1)).get("token") || ""
  ).trim());
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    }
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("新密碼至少需要 8 個字元。");
      return;
    }
    if (password !== confirm) {
      setError("兩次輸入的密碼不一致。");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/password-reset/confirm/", {
        token,
        new_password: password,
      });
      setDone(true);
    } catch (err) {
      const data = err.response?.data || {};
      setError(data.token || data.new_password || data.detail || "重設失敗，請重新申請。");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="login-page">
        <div className="login-card">
          <button type="button" className="login-back" onClick={() => navigate("/login")}>
            ← 返回登入
          </button>
          <div className="login-brand">
            <span className="login-brand-glyph">⟡</span>
            <span className="login-brand-name">重設密碼</span>
          </div>
          <p className="login-error">
            連結缺少 token；請從信件中重新點擊重設連結，或回到「忘記密碼」重新申請。
          </p>
          <button
            type="button"
            className="login-submit"
            onClick={() => navigate("/password-reset")}
          >
            重新申請
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <button type="button" className="login-back" onClick={() => navigate("/login")}>
          ← 返回登入
        </button>
        <div className="login-brand">
          <span className="login-brand-glyph">⟡</span>
          <span className="login-brand-name">設定新密碼</span>
        </div>

        {done ? (
          <div className="login-info-box">
            <p>密碼已重設成功。</p>
            <p className="login-info-foot">請用新密碼登入。</p>
            <button
              type="button"
              className="login-submit"
              onClick={() => navigate("/login")}
            >
              前往登入
            </button>
          </div>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            <p className="login-sub">請設定新密碼（至少 8 個字元）。設定完成後請用新密碼登入。</p>
            {error && <p className="login-error">{error}</p>}
            <input
              className="input"
              type="password"
              placeholder="新密碼"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              autoFocus
              minLength={8}
            />
            <input
              className="input"
              type="password"
              placeholder="再次輸入新密碼"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              minLength={8}
            />
            <button
              className="login-submit"
              type="submit"
              disabled={loading || !password || !confirm}
            >
              {loading ? "送出中…" : "確認重設"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export {
  RequireAuth,
  LoginPage,
  PasswordResetRequestPage,
  PasswordResetConfirmPage,
};
