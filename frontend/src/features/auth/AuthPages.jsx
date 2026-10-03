import { useEffect, useId, useRef, useState } from "react";
import { GoogleLogin } from "@react-oauth/google";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { ArgusLogo, ArgusMark } from "../../components/brand/ArgusMark";
import { ThemeToggle } from "../../components/navigation/NavActions";
import { useArgusStore } from "../../store";
import { ArrowLeftIcon, CheckIcon } from "../../shared/ActionIcons";
import { LockIcon, ScoreIcon, ShieldIcon } from "../../shared/LineIcons";
import PasswordInput from "../../shared/PasswordInput";
import { TURNSTILE_FIELD, TurnstileWidget, useTurnstileConfig } from "../../shared/TurnstileWidget";

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

// ============================================================
// 共用版型：左側品牌敘事（寬螢幕）＋右側表單卡；手機單欄
// ============================================================

const TRUST_POINTS = [
  {
    Icon: ShieldIcon,
    title: "授權式掃描",
    body: "主動式資安測試只對你驗證過所有權的網域執行。",
  },
  {
    Icon: ScoreIcon,
    title: "五維一次看見",
    body: "SEO、AEO、GEO、資安、UX 同一份報告，附證據截圖。",
  },
  {
    Icon: LockIcon,
    title: "直接給修法",
    body: "不只列問題，還產出可套用的 JSON-LD、meta 與 llms.txt。",
  },
];

function AuthShell({ children, backTo, backLabel }) {
  return (
    <div className="auth-shell">
      <aside className="auth-story ag-surface-grid" aria-label="關於 Argus">
        <ArgusLogo size={40} subtitle="AI 網站健檢平台" />
        <div className="auth-story-copy">
          <p className="ag-eyebrow">Night Watch</p>
          <p className="auth-story-title">
            讓Argus替你守望網站，<br />
            <span>看見問題，也拿到修法。</span>
          </p>
          <p className="auth-story-sub">
            Argus 以瀏覽器逐頁巡視你的網站，找出搜尋、AI 答案引擎、資安與體驗上的缺口，並直接給出可用的修正。
          </p>
        </div>
        <ul className="auth-trust">
          {TRUST_POINTS.map((point) => (
            <li key={point.title}>
              <span className="auth-trust-icon" aria-hidden="true"><point.Icon /></span>
              <span>
                <strong>{point.title}</strong>
                <small>{point.body}</small>
              </span>
            </li>
          ))}
        </ul>
        <div className="auth-story-eye" aria-hidden="true">
          <ArgusMark size={220} />
        </div>
      </aside>

      <div className="auth-main">
        <div className="auth-topbar">
          <Link to={backTo} className="auth-back">
            <ArrowLeftIcon /> {backLabel}
          </Link>
          <ThemeToggle />
        </div>
        <div className="auth-card ag-viewfinder">
          <div className="auth-card-mark">
            <ArgusLogo size={32} subtitle={null} />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

function AuthField({ id, label, hint, children }) {
  return (
    <div className="auth-field">
      <label className="auth-label" htmlFor={id}>{label}</label>
      {children}
      {hint && <p className="auth-hint" id={`${id}-hint`}>{hint}</p>}
    </div>
  );
}

function AuthError({ children }) {
  if (!children) return null;
  return <p className="auth-error" role="alert">{children}</p>;
}

function SubmitButton({ loading, loadingText, children, disabled }) {
  return (
    <button className="primary-button auth-submit" type="submit" disabled={loading || disabled} aria-busy={loading || undefined}>
      {loading && <span className="auth-spinner" aria-hidden="true" />}
      {loading ? loadingText : children}
    </button>
  );
}

// ============================================================
// 登入／註冊
// ============================================================

function LoginPage({ googleOAuthEnabled }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const accessToken = useArgusStore((s) => s.accessToken);
  const setToken = useArgusStore((s) => s.setToken);
  const [tab, setTab] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const uid = useId();
  const turnstile = useTurnstileConfig();
  const [captcha, setCaptcha] = useState("");
  const captchaRef = useRef(null);
  // 設定還沒讀到、或已啟用但還沒通過驗證時不能送出（送了也會被後端 403）
  const captchaBlocking = turnstile.loading || (turnstile.enabled && !captcha);

  const next = searchParams.get("next");
  const redirect = (!next || next === "/login" || !next.startsWith("/")) ? "/dashboard" : next;

  // 已登入則直接跳轉
  if (accessToken) {
    return <Navigate to={redirect} replace />;
  }

  // token 只能用一次；每次送出後由 finally 重設元件取得新的
  function withCaptcha(body) {
    return turnstile.enabled ? { ...body, [TURNSTILE_FIELD]: captcha } : body;
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
      const res = await api.post("/auth/email-login/", withCaptcha({ email, password }));
      handleToken(res.data.access);
    } catch (err) {
      setError(err.response?.data?.detail || "登入失敗，請確認 Email 與密碼。");
    } finally {
      setLoading(false);
      captchaRef.current?.reset();
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
      const res = await api.post("/auth/register/", withCaptcha({ email, password }));
      handleToken(res.data.access);
    } catch (err) {
      const d = err.response?.data || {};
      setError(d.email || d.password || d.detail || "註冊失敗。");
    } finally {
      setLoading(false);
      captchaRef.current?.reset();
    }
  }

  const tabs = [
    { key: "login", label: "Email 登入" },
    { key: "register", label: "新帳號" },
  ];
  const isRegister = tab === "register";

  return (
    <AuthShell backTo="/project" backLabel="返回首頁">
      <header className="auth-head">
        <h1 className="auth-title">{isRegister ? "建立 Argus 帳號" : "登入 Argus"}</h1>
        <p className="auth-sub">授權式 AI 網站健檢平台</p>
      </header>

      <div className="auth-tabs" role="tablist" aria-label="登入方式">
        {tabs.map((t) => (
          <button
            key={t.key}
            id={`${uid}-tab-${t.key}`}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            aria-controls={`${uid}-panel`}
            className={`auth-tab ${tab === t.key ? "is-active" : ""}`}
            onClick={() => { setTab(t.key); setError(""); setCaptcha(""); }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id={`${uid}-panel`} role="tabpanel" aria-labelledby={`${uid}-tab-${tab}`} className="auth-panel">
        {googleOAuthEnabled && (
          <>
            <div className="auth-google">
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
                text={isRegister ? "signup_with" : "signin_with"}
              />
            </div>
            <p className="auth-divider"><span>或使用 Email</span></p>
          </>
        )}

        <AuthError>{error}</AuthError>

        {!isRegister && (
          <form className="auth-form" onSubmit={handleEmailLogin}>
            <AuthField id={`${uid}-email`} label="Email">
              <input
                id={`${uid}-email`}
                className="input"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </AuthField>
            <div className="auth-field">
              <div className="auth-label-row">
                <label className="auth-label" htmlFor={`${uid}-password`}>密碼</label>
                <button
                  type="button"
                  className="auth-link"
                  onClick={() => navigate("/password-reset")}
                >
                  忘記密碼？
                </button>
              </div>
              <PasswordInput
                id={`${uid}-password`}
                placeholder="輸入密碼"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            {turnstile.enabled && (
              <TurnstileWidget key="login" ref={captchaRef} siteKey={turnstile.siteKey} action="login" onToken={setCaptcha} />
            )}
            <SubmitButton loading={loading} loadingText="登入中…" disabled={captchaBlocking}>登入</SubmitButton>
          </form>
        )}

        {isRegister && (
          <form className="auth-form" onSubmit={handleRegister}>
            <AuthField id={`${uid}-reg-email`} label="Email">
              <input
                id={`${uid}-reg-email`}
                className="input"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </AuthField>
            <AuthField id={`${uid}-reg-password`} label="密碼" hint="至少 8 字元">
              <PasswordInput
                id={`${uid}-reg-password`}
                placeholder="密碼（至少 8 字元）"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                aria-describedby={`${uid}-reg-password-hint`}
              />
            </AuthField>
            <AuthField id={`${uid}-reg-confirm`} label="確認密碼">
              <PasswordInput
                id={`${uid}-reg-confirm`}
                placeholder="再輸入一次"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
                invalid={Boolean(confirmPassword) && confirmPassword !== password}
              />
            </AuthField>
            {turnstile.enabled && (
              <TurnstileWidget key="signup" ref={captchaRef} siteKey={turnstile.siteKey} action="signup" onToken={setCaptcha} />
            )}
            <SubmitButton loading={loading} loadingText="建立中…" disabled={captchaBlocking}>建立帳號</SubmitButton>
          </form>
        )}
      </div>
    </AuthShell>
  );
}

// ============================================================
// 忘記密碼：寄送重設連結
// ============================================================

function PasswordResetRequestPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [serverMessage, setServerMessage] = useState("");
  const [error, setError] = useState("");
  const uid = useId();
  const turnstile = useTurnstileConfig();
  const [captcha, setCaptcha] = useState("");
  const captchaRef = useRef(null);
  const captchaBlocking = turnstile.loading || (turnstile.enabled && !captcha);

  async function handleSubmit(e) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError("");
    try {
      const body = { email: email.trim().toLowerCase() };
      if (turnstile.enabled) body[TURNSTILE_FIELD] = captcha;
      const res = await api.post("/auth/password-reset/request/", body);
      setServerMessage(res.data?.detail || "若該 Email 已註冊，重設信已寄出。");
      setSubmitted(true);
    } catch (err) {
      if (err.response?.status === 403) {
        // 人機驗證未通過：留在表單讓使用者重新驗證
        setError(err.response.data?.detail || "人機驗證未通過，請重新驗證後再送出。");
      } else {
        // 後端設計為永遠成功；網路錯誤才會走到這
        setServerMessage("送出失敗，請檢查網路連線後再試。");
        setSubmitted(true);
      }
    } finally {
      setLoading(false);
      captchaRef.current?.reset();
    }
  }

  return (
    <AuthShell backTo="/login" backLabel="返回登入">
      <header className="auth-head">
        <h1 className="auth-title">重設密碼</h1>
        <p className="auth-sub">輸入註冊時的 Email，我們會寄出重設連結（60 分鐘內有效）。</p>
      </header>

      {submitted ? (
        <div className="auth-result" role="status">
          <span className="auth-result-icon" aria-hidden="true"><CheckIcon /></span>
          <p className="auth-result-title">{serverMessage}</p>
          <p className="auth-result-foot">
            收不到信？請檢查垃圾郵件夾，或確認 Email 是否拼寫正確。
          </p>
          <button
            type="button"
            className="primary-button auth-submit"
            onClick={() => navigate("/login")}
          >
            回到登入頁
          </button>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit}>
          <AuthField id={`${uid}-email`} label="Email">
            <input
              id={`${uid}-email`}
              className="input"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              autoFocus
            />
          </AuthField>
          <AuthError>{error}</AuthError>
          {turnstile.enabled && (
            <TurnstileWidget ref={captchaRef} siteKey={turnstile.siteKey} action="password_reset" onToken={setCaptcha} />
          )}
          <SubmitButton loading={loading} loadingText="送出中…" disabled={!email.trim() || captchaBlocking}>
            寄出重設連結
          </SubmitButton>
          <p className="auth-notice">
            Google 帳號的密碼請至 Google 帳號設定管理，本平台無法重設。
          </p>
        </form>
      )}
    </AuthShell>
  );
}

// ============================================================
// 重設密碼：從信件連結（token 在 hash）設定新密碼
// ============================================================

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
  const uid = useId();

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
      <AuthShell backTo="/login" backLabel="返回登入">
        <header className="auth-head">
          <h1 className="auth-title">重設密碼</h1>
        </header>
        <AuthError>
          連結缺少 token；請從信件中重新點擊重設連結，或回到「忘記密碼」重新申請。
        </AuthError>
        <button
          type="button"
          className="primary-button auth-submit"
          onClick={() => navigate("/password-reset")}
        >
          重新申請
        </button>
      </AuthShell>
    );
  }

  return (
    <AuthShell backTo="/login" backLabel="返回登入">
      <header className="auth-head">
        <h1 className="auth-title">設定新密碼</h1>
        {!done && <p className="auth-sub">請設定新密碼（至少 8 個字元）。設定完成後請用新密碼登入。</p>}
      </header>

      {done ? (
        <div className="auth-result" role="status">
          <span className="auth-result-icon" aria-hidden="true"><CheckIcon /></span>
          <p className="auth-result-title">密碼已重設成功。</p>
          <p className="auth-result-foot">請用新密碼登入。</p>
          <button
            type="button"
            className="primary-button auth-submit"
            onClick={() => navigate("/login")}
          >
            前往登入
          </button>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit}>
          <AuthError>{error}</AuthError>
          <AuthField id={`${uid}-new`} label="新密碼">
            <PasswordInput
              id={`${uid}-new`}
              placeholder="至少 8 個字元"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              autoFocus
              minLength={8}
            />
          </AuthField>
          <AuthField id={`${uid}-confirm`} label="再次輸入新密碼">
            <PasswordInput
              id={`${uid}-confirm`}
              placeholder="再輸入一次"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              minLength={8}
              invalid={Boolean(confirm) && confirm !== password}
            />
          </AuthField>
          <SubmitButton loading={loading} loadingText="送出中…" disabled={!password || !confirm}>
            確認重設
          </SubmitButton>
        </form>
      )}
    </AuthShell>
  );
}

export {
  RequireAuth,
  LoginPage,
  PasswordResetRequestPage,
  PasswordResetConfirmPage,
};
