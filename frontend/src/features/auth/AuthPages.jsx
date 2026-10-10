import { useEffect, useId, useRef, useState } from "react";
import { GoogleLogin } from "@react-oauth/google";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

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
  const profile = useArgusStore((state) => state.profile);
  const fetchProfile = useArgusStore((state) => state.fetchProfile);
  const location = useLocation();

  useEffect(() => {
    if (accessToken && !profile) fetchProfile();
  }, [accessToken, profile, fetchProfile]);

  if (!authReady) {
    return <p className="loading-state">正在驗證登入狀態…</p>;
  }
  if (accessToken) {
    // 舊帳號缺用戶名或密碼：先補設才能使用其他功能（後端 /api/auth/me/ 的 needs_setup）
    if (profile?.needs_setup && location.pathname !== "/account/setup") {
      const back = encodeURIComponent(location.pathname + location.search);
      return <Navigate to={`/account/setup?next=${back}`} replace />;
    }
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
    title: "主動檢測需驗證網域",
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
        <ArgusLogo size={40} subtitle="AI網站健檢平台" />
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

const HANDLE_HINT = "3–30 個英文小寫字母、數字或 _ . -，可用來登入";

function fieldError(data, fallback) {
  const first = (value) => (Array.isArray(value) ? value[0] : value);
  return first(data?.handle) || first(data?.password) || first(data?.signup_token) || data?.detail || fallback;
}

function TermsNote() {
  return (
    <p className="auth-hint auth-terms">
      建立帳號即表示你同意 <Link to="/terms" target="_blank">服務條款</Link> 與{" "}
      <Link to="/privacy" target="_blank">隱私權政策</Link>。
    </p>
  );
}

/**
 * 註冊第二步：Google 已確認 Email，設定用戶名與密碼後建立帳號（POST /auth/register/）。
 * signup 由 /auth/register/google/ 或 Google 登入時「尚未註冊」的 409 回應取得（15 分鐘有效）。
 */
function RegisterDetailsForm({ signup, onDone, onRestart }) {
  const uid = useId();
  const [handle, setHandle] = useState(signup.suggested_handle || "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("兩次密碼輸入不一致。");
      return;
    }
    setLoading(true);
    try {
      const res = await api.post("/auth/register/", { signup_token: signup.signup_token, handle, password });
      onDone(res.data.access);
    } catch (err) {
      setError(fieldError(err.response?.data, "註冊失敗，請稍後再試。"));
      setLoading(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={submit}>
      <p className="auth-step">步驟 2／2：設定用戶名與密碼</p>
      <AuthError>{error}</AuthError>
      <AuthField id={`${uid}-email`} label="Google 帳號 Email">
        <input id={`${uid}-email`} className="input" type="email" value={signup.email} readOnly />
      </AuthField>
      <AuthField id={`${uid}-handle`} label="用戶名" hint={HANDLE_HINT}>
        <input
          id={`${uid}-handle`}
          className="input"
          value={handle}
          onChange={(e) => setHandle(e.target.value.toLowerCase())}
          required
          minLength={3}
          maxLength={30}
          autoComplete="username"
          aria-describedby={`${uid}-handle-hint`}
        />
      </AuthField>
      <AuthField id={`${uid}-password`} label="密碼" hint="至少 10 個字元，需包含英文字母與數字">
        <PasswordInput
          id={`${uid}-password`}
          placeholder="設定密碼"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="new-password"
          aria-describedby={`${uid}-password-hint`}
        />
      </AuthField>
      <AuthField id={`${uid}-confirm`} label="確認密碼">
        <PasswordInput
          id={`${uid}-confirm`}
          placeholder="再輸入一次"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
          autoComplete="new-password"
          invalid={Boolean(confirmPassword) && confirmPassword !== password}
        />
      </AuthField>
      <TermsNote />
      <SubmitButton loading={loading} loadingText="建立中…">建立帳號</SubmitButton>
      <button type="button" className="auth-link auth-restart" onClick={onRestart}>改用其他 Google 帳號</button>
    </form>
  );
}

function LoginPage({ googleOAuthEnabled }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const accessToken = useArgusStore((s) => s.accessToken);
  const setToken = useArgusStore((s) => s.setToken);
  const [tab, setTab] = useState(searchParams.get("tab") === "register" ? "register" : "login");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [signup, setSignup] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(searchParams.get("deleted") ? "帳號已刪除。感謝你使用 Argus。" : "");
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

  function switchTab(key) {
    setTab(key);
    setError("");
    setNotice("");
    setSignup(null);
    setCaptcha("");
  }

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/email-login/", withCaptcha({ email: identifier, password }));
      handleToken(res.data.access);
    } catch (err) {
      setError(err.response?.data?.detail || "登入失敗，請確認帳號與密碼。");
    } finally {
      setLoading(false);
      captchaRef.current?.reset();
    }
  }

  // 登入分頁的 Google：已註冊直接登入；尚未註冊（409）直接進入設定用戶名與密碼
  async function googleLogin(credential) {
    setError("");
    try {
      const res = await api.post("/auth/google/", { credential });
      handleToken(res.data.access);
    } catch (err) {
      const data = err.response?.data;
      if (err.response?.status === 409 && data?.code === "registration_required") {
        setTab("register");
        setSignup(data);
        setNotice("這個 Google 帳號還沒有註冊，請設定用戶名與密碼完成註冊。");
      } else {
        setError(data?.credential || data?.detail || "Google 登入失敗，請稍後再試。");
      }
    }
  }

  // 註冊分頁的 Google：只確認 Email，回傳 signup_token，帳號在第二步才建立
  async function googleRegister(credential) {
    setError("");
    try {
      const res = await api.post("/auth/register/google/", { credential });
      setSignup(res.data);
      setNotice("");
    } catch (err) {
      const data = err.response?.data;
      if (err.response?.status === 409 && data?.code === "already_registered") {
        setTab("login");
        setNotice("這個 Google 帳號已經註冊，請直接登入。");
      } else {
        setError(data?.credential || data?.detail || "Google 授權失敗，請稍後再試。");
      }
    }
  }

  const tabs = [
    { key: "login", label: "登入" },
    { key: "register", label: "註冊" },
  ];
  const isRegister = tab === "register";

  return (
    <AuthShell backTo="/project" backLabel="返回首頁">
      <header className="auth-head">
        <h1 className="auth-title">{isRegister ? "建立 Argus 帳號" : "登入 Argus"}</h1>
        <p className="auth-sub">AI網站健檢平台</p>
      </header>

      <div className="auth-tabs" role="tablist" aria-label="登入或註冊">
        {tabs.map((t) => (
          <button
            key={t.key}
            id={`${uid}-tab-${t.key}`}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            aria-controls={`${uid}-panel`}
            className={`auth-tab ${tab === t.key ? "is-active" : ""}`}
            onClick={() => switchTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id={`${uid}-panel`} role="tabpanel" aria-labelledby={`${uid}-tab-${tab}`} className="auth-panel">
        {notice && <p className="auth-notice-inline" role="status">{notice}</p>}

        {!isRegister && (
          <>
            {googleOAuthEnabled && (
              <>
                <div className="auth-google">
                  <GoogleLogin
                    onSuccess={(response) => googleLogin(response.credential)}
                    onError={() => setError("Google 登入元件錯誤，請重新整理。")}
                    useOneTap={false}
                    theme="filled_black"
                    shape="pill"
                    text="signin_with"
                  />
                </div>
                <p className="auth-divider"><span>或使用帳號密碼</span></p>
              </>
            )}
            <AuthError>{error}</AuthError>
            <form className="auth-form" onSubmit={handleLogin}>
              <AuthField id={`${uid}-identifier`} label="Email 或用戶名">
                <input
                  id={`${uid}-identifier`}
                  className="input"
                  type="text"
                  placeholder="you@example.com 或用戶名"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  autoComplete="username"
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
          </>
        )}

        {isRegister && !signup && (
          <div className="auth-form">
            <p className="auth-step">步驟 1／2：使用 Google 帳號授權</p>
            <p className="auth-hint">
              註冊需要以 Google 帳號確認 Email，下一步再設定用戶名與密碼；之後可用 Email 或用戶名加密碼登入，也能繼續用 Google 登入。
            </p>
            <AuthError>{error}</AuthError>
            {googleOAuthEnabled ? (
              <div className="auth-google">
                <GoogleLogin
                  onSuccess={(response) => googleRegister(response.credential)}
                  onError={() => setError("Google 授權元件錯誤，請重新整理。")}
                  useOneTap={false}
                  theme="filled_black"
                  shape="pill"
                  text="signup_with"
                />
              </div>
            ) : (
              <p className="auth-error" role="alert">網站尚未設定 Google 授權，暫時無法註冊新帳號。</p>
            )}
            <TermsNote />
          </div>
        )}

        {isRegister && signup && (
          <RegisterDetailsForm
            signup={signup}
            onDone={handleToken}
            onRestart={() => { setSignup(null); setNotice(""); }}
          />
        )}
      </div>
    </AuthShell>
  );
}

/**
 * /account/setup：舊帳號缺用戶名或密碼時，登入後一律先到這裡補設（RequireAuth 依 profile.needs_setup 導過來）。
 */
function AccountSetupPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const profile = useArgusStore((s) => s.profile);
  const fetchProfile = useArgusStore((s) => s.fetchProfile);
  const uid = useId();
  const [handle, setHandle] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const next = searchParams.get("next");
  const redirect = next && next.startsWith("/") && !next.startsWith("/account/setup") ? next : "/dashboard";

  if (!profile) return <p className="loading-state">載入帳號資料中…</p>;
  if (!profile.needs_setup) return <Navigate to={redirect} replace />;
  const needHandle = !profile.handle;
  const needPassword = !profile.has_password;

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (needPassword && password !== confirmPassword) {
      setError("兩次密碼輸入不一致。");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/me/setup/", { handle, password });
      await fetchProfile();
      navigate(redirect, { replace: true });
    } catch (err) {
      setError(fieldError(err.response?.data, "設定失敗，請稍後再試。"));
      setLoading(false);
    }
  }

  return (
    <AuthShell backTo="/project" backLabel="返回首頁">
      <header className="auth-head">
        <h1 className="auth-title">完成帳號設定</h1>
        <p className="auth-sub">
          {profile.email} 需要設定{[needHandle && "用戶名", needPassword && "密碼"].filter(Boolean).join("與")}後才能繼續使用。
        </p>
      </header>
      <form className="auth-form" onSubmit={submit}>
        <AuthError>{error}</AuthError>
        {needHandle && (
          <AuthField id={`${uid}-handle`} label="用戶名" hint={HANDLE_HINT}>
            <input
              id={`${uid}-handle`}
              className="input"
              value={handle}
              onChange={(e) => setHandle(e.target.value.toLowerCase())}
              required
              minLength={3}
              maxLength={30}
              autoComplete="username"
              aria-describedby={`${uid}-handle-hint`}
            />
          </AuthField>
        )}
        {needPassword && (
          <>
            <AuthField id={`${uid}-password`} label="密碼" hint="至少 10 個字元，需包含英文字母與數字">
              <PasswordInput
                id={`${uid}-password`}
                placeholder="設定密碼"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                aria-describedby={`${uid}-password-hint`}
              />
            </AuthField>
            <AuthField id={`${uid}-confirm`} label="確認密碼">
              <PasswordInput
                id={`${uid}-confirm`}
                placeholder="再輸入一次"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
                invalid={Boolean(confirmPassword) && confirmPassword !== password}
              />
            </AuthField>
          </>
        )}
        <SubmitButton loading={loading} loadingText="儲存中…">完成設定</SubmitButton>
      </form>
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
            重設的是 Argus 的登入密碼，不會影響你的 Google 帳號密碼。
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
  AccountSetupPage,
  RequireAuth,
  LoginPage,
  PasswordResetRequestPage,
  PasswordResetConfirmPage,
};
