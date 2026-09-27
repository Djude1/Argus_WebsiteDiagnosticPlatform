import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, fetchMySubscription } from "../../api";
import { accountInitial } from "../../components/navigation/NavActions";
import { useArgusStore } from "../../store";
import { useConfirmDialogs } from "../../shared/AppShared";
import { MoonIcon, SunIcon } from "../../shared/ActionIcons";
import { formatDate } from "../../shared/formatters";
import PasswordInput from "../../shared/PasswordInput";

// ============================================================
// Settings 頁
// ============================================================

function SettingsPage() {
  const navigate = useNavigate();
  const wallet = useArgusStore((s) => s.wallet);
  const setToken = useArgusStore((s) => s.setToken);
  const theme = useArgusStore((s) => s.theme);
  const toggleTheme = useArgusStore((s) => s.toggleTheme);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdError, setPwdError] = useState("");
  const [pwdBusy, setPwdBusy] = useState(false);

  const [meData, setMeData] = useState(null);
  // 訂閱摘要：undefined=載入中、null=無訂閱（載入失敗也寬容當作無訂閱，詳細狀態以 /billing 為準）
  const [subscription, setSubscription] = useState(undefined);
  useEffect(() => {
    api.get("/auth/me/").then((r) => {
      setMeData(r.data);
      setFirstName(r.data.first_name || "");
      setLastName(r.data.last_name || "");
    }).catch(() => {});
    fetchMySubscription()
      .then((r) => setSubscription(r.subscription || null))
      .catch(() => setSubscription(null));
  }, []);

  const balance = wallet?.balance ?? 0;
  const purchased = wallet?.total_purchased_ntd ?? 0;
  const scansUsed = wallet?.total_scans_used ?? 0;
  const isEmailAccount = meData?.auth_provider === "email";
  const displayName = meData?.display_name?.trim() || meData?.email || meData?.username || "—";

  async function handleSaveProfile(e) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg("");
    try {
      await api.patch("/auth/me/", { first_name: firstName, last_name: lastName });
      setSaveMsg("已儲存");
    } catch {
      setSaveMsg("儲存失敗");
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    setPwdError("");
    if (newPwd !== confirmPwd) { setPwdError("兩次密碼不一致"); return; }
    if (newPwd.length < 8) { setPwdError("新密碼至少 8 個字元"); return; }
    setPwdBusy(true);
    try {
      await api.post("/auth/change-password/", { old_password: oldPwd, new_password: newPwd });
      setToken(null);
      navigate("/login", { replace: true });
    } catch (err) {
      setPwdError(err.response?.data?.detail || "密碼變更失敗");
    } finally {
      setPwdBusy(false);
    }
  }

  return (
    <div className="acct-page">
      <header className="acct-page-head">
        <div>
          <p className="ag-eyebrow">Settings</p>
          <h1 className="acct-page-title">帳號設定</h1>
          <p className="acct-page-sub">管理個人資料、登入安全、外觀與點數。</p>
        </div>
      </header>

      <div className="set-layout">
        <aside className="set-summary" aria-label="帳號摘要">
          <div className="set-card set-profile-card">
            <span className="app-avatar is-xl" aria-hidden="true">{accountInitial(meData)}</span>
            <div className="set-profile-id">
              <strong>{displayName}</strong>
              {meData?.email && meData.email !== displayName && <small>{meData.email}</small>}
              {meData && (
                <span className="set-provider-chip">
                  {isEmailAccount ? "Email 帳號" : "Google 帳號"}
                </span>
              )}
            </div>
          </div>

          <section className="set-card set-wallet" aria-labelledby="set-wallet-title">
            <h2 id="set-wallet-title" className="set-card-label">點數錢包</h2>
            <p className="set-wallet-balance ag-num">
              {balance.toLocaleString()} <span>coin</span>
            </p>
            <p className="set-hint">累積購買 NT$ {purchased.toLocaleString()} · 累計 {scansUsed} 次掃描</p>
            <button className="primary-button set-block-btn" type="button" onClick={() => navigate("/billing")}>前往購點</button>
          </section>

          <section className="set-card" aria-labelledby="set-sub-title">
            <h2 id="set-sub-title" className="set-card-label">訂閱狀態</h2>
            {subscription === undefined ? (
              <p className="set-hint">載入訂閱狀態中…</p>
            ) : subscription ? (
              <>
                <p className="set-value">{subscription.plan_name}（{subscription.status_label}）</p>
                <p className="set-hint">
                  本期到期 {formatDate(subscription.current_period_end)} · 剩餘 {subscription.periods_remaining} 期
                </p>
              </>
            ) : (
              <>
                <p className="set-value">尚未訂閱</p>
                <p className="set-hint">月訂閱每月自動發點，長期使用比單次購點更划算</p>
              </>
            )}
            <button className="secondary-button set-block-btn" type="button" onClick={() => navigate("/billing")}>
              {subscription ? "管理訂閱" : "前往訂閱"}
            </button>
          </section>
        </aside>

        <div className="set-main">
          <section className="set-section" aria-labelledby="set-profile-title">
            <header className="set-section-head">
              <h2 id="set-profile-title">個人資料</h2>
              <p>顯示在報告與收據上的名稱。</p>
            </header>
            <form className="set-form" onSubmit={handleSaveProfile}>
              <div className="set-field set-field-full">
                <span className="set-label" id="set-email-label">Email</span>
                <p className="set-readonly" aria-labelledby="set-email-label">{meData?.email || meData?.username || "—"}</p>
              </div>
              <div className="set-field">
                <label className="set-label" htmlFor="set-first-name">名字</label>
                <input id="set-first-name" className="input" value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="名" autoComplete="given-name" />
              </div>
              <div className="set-field">
                <label className="set-label" htmlFor="set-last-name">姓氏</label>
                <input id="set-last-name" className="input" value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="姓" autoComplete="family-name" />
              </div>
              <div className="set-form-actions">
                <button className="primary-button" type="submit" disabled={saving}>
                  {saving ? "儲存中…" : "儲存變更"}
                </button>
                {saveMsg && (
                  <p className={`set-msg ${saveMsg === "已儲存" ? "tone-good" : "tone-bad"}`} role="status">{saveMsg}</p>
                )}
              </div>
            </form>
          </section>

          <section className="set-section" aria-labelledby="set-theme-title">
            <header className="set-section-head">
              <h2 id="set-theme-title">外觀</h2>
              <p>夜間主題適合長時間閱讀報告；設定只存在這台裝置。</p>
            </header>
            <div className="set-theme-options" role="radiogroup" aria-labelledby="set-theme-title">
              {[
                { value: "dark", label: "夜間", hint: "預設・深夜墨藍", Icon: MoonIcon },
                { value: "light", label: "日間", hint: "明亮・適合列印對照", Icon: SunIcon },
              ].map((opt) => (
                <label key={opt.value} className="set-theme-option">
                  <input
                    type="radio"
                    name="theme"
                    value={opt.value}
                    checked={theme === opt.value}
                    onChange={() => { if (theme !== opt.value) toggleTheme(); }}
                  />
                  <span className={`set-theme-swatch is-${opt.value}`} aria-hidden="true"><opt.Icon /></span>
                  <span className="set-theme-copy">
                    <strong>{opt.label}</strong>
                    <small>{opt.hint}</small>
                  </span>
                </label>
              ))}
            </div>
          </section>

          <section className="set-section" aria-labelledby="set-auth-title">
            <header className="set-section-head">
              <h2 id="set-auth-title">登入方式</h2>
              <p>{isEmailAccount ? "Email 帳號" : "Google 帳號（透過 Google 管理密碼）"}</p>
            </header>
            {isEmailAccount && (
              <form className="set-form" onSubmit={handleChangePassword} aria-label="更改密碼">
                <h3 className="set-subtitle set-field-full">更改密碼</h3>
                <div className="set-field set-field-full">
                  <label className="set-label" htmlFor="set-old-pwd">目前密碼</label>
                  <PasswordInput id="set-old-pwd" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} autoComplete="current-password" />
                </div>
                <div className="set-field">
                  <label className="set-label" htmlFor="set-new-pwd">新密碼</label>
                  <PasswordInput id="set-new-pwd" placeholder="至少 8 字元" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} autoComplete="new-password" invalid={Boolean(pwdError)} />
                </div>
                <div className="set-field">
                  <label className="set-label" htmlFor="set-confirm-pwd">確認新密碼</label>
                  <PasswordInput id="set-confirm-pwd" value={confirmPwd} onChange={(e) => setConfirmPwd(e.target.value)} autoComplete="new-password" invalid={Boolean(pwdError)} />
                </div>
                {pwdError && <p className="set-msg tone-bad set-field-full" role="alert">{pwdError}</p>}
                <div className="set-form-actions">
                  <button className="primary-button" type="submit" disabled={pwdBusy}>
                    {pwdBusy ? "更新中…" : "更新密碼"}
                  </button>
                  <span className="set-hint">更新後需重新登入。</span>
                </div>
              </form>
            )}
          </section>

          <section className="set-section set-danger" aria-labelledby="set-danger-title">
            <header className="set-section-head">
              <h2 id="set-danger-title">危險操作</h2>
              <p>刪除帳號將移除所有掃描紀錄與點數，此操作無法復原。</p>
            </header>
            <button
              className="set-danger-btn"
              type="button"
              onClick={async () => {
                if (await confirmDialog("確定要刪除帳號嗎？此操作無法復原。", { danger: true })) {
                  notifyDialog("請聯絡管理員協助刪除帳號。");
                }
              }}
            >
              刪除帳號
            </button>
          </section>
        </div>
      </div>
      {dialogHost}
    </div>
  );
}

export default SettingsPage;
export { SettingsPage };
