import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, deleteAvatar, fetchMySubscription, uploadAvatar } from "../../api";
import { AccountAvatar } from "../../components/navigation/NavActions";
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
  const fetchMe = useArgusStore((s) => s.fetchMe);
  const { confirmDialog, dialogHost } = useConfirmDialogs();

  const avatarInputRef = useRef(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarMsg, setAvatarMsg] = useState("");

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
  const [deletePwd, setDeletePwd] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
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
  const hasPassword = Boolean(meData?.has_password);
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

  // 大頭貼：前端先擋格式與大小，實際驗證與重新編碼由後端（apps.accounts.avatars）負責
  async function handleAvatarChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setAvatarMsg("只接受 JPG、PNG 或 WebP 圖片");
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setAvatarMsg("圖片不可超過 2 MB");
      return;
    }
    setAvatarBusy(true);
    setAvatarMsg("");
    try {
      const { avatar_url: url } = await uploadAvatar(file);
      setMeData((prev) => ({ ...prev, avatar_url: url }));
      fetchMe();
      setAvatarMsg("頭像已更新");
    } catch (err) {
      setAvatarMsg(err.response?.data?.detail || "上傳失敗，請稍後再試");
    } finally {
      setAvatarBusy(false);
    }
  }

  async function handleAvatarRemove() {
    setAvatarBusy(true);
    setAvatarMsg("");
    try {
      await deleteAvatar();
      setMeData((prev) => ({ ...prev, avatar_url: null }));
      fetchMe();
      setAvatarMsg("已移除頭像");
    } catch {
      setAvatarMsg("移除失敗，請稍後再試");
    } finally {
      setAvatarBusy(false);
    }
  }

  // 刪除帳號：後端 /api/auth/me/delete/（accounts/deletion.py）。個資與內容全部刪除、帳務匿名保留，不可復原
  async function handleDeleteAccount(e) {
    e.preventDefault();
    setDeleteError("");
    if (!(await confirmDialog("確定要永久刪除帳號嗎？所有網站專案、掃描與報告都會刪除，無法復原。", { danger: true }))) {
      return;
    }
    setDeleteBusy(true);
    try {
      await api.post("/auth/me/delete/", { password: deletePwd, confirm: deleteConfirm });
      // 整頁重新載入：清掉所有前端狀態，也避免 RequireAuth 先把畫面導到 /login?next=…
      setToken(null);
      window.location.replace("/login?deleted=1");
    } catch (err) {
      const data = err.response?.data || {};
      setDeleteError(data.password || data.confirm || data.detail || "刪除失敗，請稍後再試。");
      setDeleteBusy(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    setPwdError("");
    if (newPwd !== confirmPwd) { setPwdError("兩次密碼不一致"); return; }
    if (newPwd.length < 10) { setPwdError("新密碼至少 10 個字元"); return; }
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
            <AccountAvatar me={meData} className="is-xl" />
            <div className="set-profile-id">
              <strong>{displayName}</strong>
              {meData?.email && meData.email !== displayName && <small>{meData.email}</small>}
              {meData?.handle && <span className="set-provider-chip">@{meData.handle}</span>}
            </div>
            <div className="set-avatar-actions">
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                onChange={handleAvatarChange}
                aria-label="選擇大頭貼圖片"
              />
              <button
                type="button"
                className="secondary-button"
                disabled={avatarBusy || !meData}
                onClick={() => avatarInputRef.current?.click()}
              >
                {avatarBusy ? "處理中…" : meData?.avatar_url ? "更換頭像" : "上傳頭像"}
              </button>
              {meData?.avatar_url && (
                <button type="button" className="set-link-btn" disabled={avatarBusy} onClick={handleAvatarRemove}>
                  移除
                </button>
              )}
              <p className="set-hint" role="status">{avatarMsg || "JPG、PNG 或 WebP，2 MB 以內；會裁成正方形。"}</p>
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
              <div className="set-field">
                <span className="set-label" id="set-email-label">Email</span>
                <p className="set-readonly" aria-labelledby="set-email-label">{meData?.email || "—"}</p>
              </div>
              <div className="set-field">
                <span className="set-label" id="set-handle-label">用戶名</span>
                <p className="set-readonly" aria-labelledby="set-handle-label">{meData?.handle || "—"}</p>
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
              <p>Email 或用戶名＋密碼，也可以用 Google 帳號登入。</p>
            </header>
            {hasPassword && (
              <form className="set-form" onSubmit={handleChangePassword} aria-label="更改密碼">
                <h3 className="set-subtitle set-field-full">更改密碼</h3>
                <div className="set-field set-field-full">
                  <label className="set-label" htmlFor="set-old-pwd">目前密碼</label>
                  <PasswordInput id="set-old-pwd" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} autoComplete="current-password" />
                </div>
                <div className="set-field">
                  <label className="set-label" htmlFor="set-new-pwd">新密碼</label>
                  <PasswordInput id="set-new-pwd" placeholder="至少 10 字元，含英文與數字" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} autoComplete="new-password" invalid={Boolean(pwdError)} />
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
              <h2 id="set-danger-title">刪除帳號</h2>
              <p>
                永久刪除帳號與所有個人資料：網站專案、掃描、報告與截圖、Search Console 連線、網域驗證、MCP 憑證、評論與登入紀錄，
                並立即登出所有裝置。剩餘點數會一併失效；點數交易與購點訂單依法只保留匿名的金額與時間。此操作無法復原。
              </p>
            </header>
            {meData?.is_staff ? (
              <p className="set-hint">管理員帳號不能自行刪除，請聯絡其他管理員處理。</p>
            ) : (
              <form className="set-form" onSubmit={handleDeleteAccount} aria-label="刪除帳號">
                <div className="set-field">
                  <label className="set-label" htmlFor="set-delete-pwd">目前密碼</label>
                  <PasswordInput id="set-delete-pwd" value={deletePwd} onChange={(e) => setDeletePwd(e.target.value)} autoComplete="current-password" required />
                </div>
                <div className="set-field">
                  <label className="set-label" htmlFor="set-delete-confirm">請輸入「刪除帳號」確認</label>
                  <input id="set-delete-confirm" className="input" value={deleteConfirm} onChange={(e) => setDeleteConfirm(e.target.value)} placeholder="刪除帳號" required />
                </div>
                {deleteError && <p className="set-msg tone-bad set-field-full" role="alert">{deleteError}</p>}
                <div className="set-form-actions">
                  <button className="set-danger-btn" type="submit" disabled={deleteBusy || deleteConfirm.trim() !== "刪除帳號" || !deletePwd}>
                    {deleteBusy ? "刪除中…" : "永久刪除帳號"}
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      </div>
      {dialogHost}
    </div>
  );
}

export default SettingsPage;
export { SettingsPage };
