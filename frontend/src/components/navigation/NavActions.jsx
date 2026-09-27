import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import { useInstallPrompt } from "../../shared/AppShared";
import {
  DownloadIcon,
  LogoutIcon,
  MoonIcon,
  ShieldAdminIcon,
  SunIcon,
} from "../../shared/ActionIcons";
import { CoinIcon, GearIcon } from "../../shared/LineIcons";

/** 登出：先通知後端撤銷 refresh cookie，無論成功與否都清掉前端 token 並回登入頁。 */
export function useLogout() {
  const setToken = useArgusStore((s) => s.setToken);
  const navigate = useNavigate();
  return async function logout() {
    try {
      await api.post("/auth/logout/");
    } finally {
      setToken(null);
      navigate("/login");
    }
  };
}

/** 日／夜主題切換（登入後導覽列與登入頁共用）。 */
export function ThemeToggle({ className = "" }) {
  const theme = useArgusStore((s) => s.theme);
  const toggleTheme = useArgusStore((s) => s.toggleTheme);
  const isLight = theme === "light";
  const label = isLight ? "切換為夜間主題" : "切換為日間主題";
  return (
    <button
      type="button"
      className={`app-theme-toggle ${className}`}
      onClick={toggleTheme}
      aria-label={label}
      title={label}
    >
      {isLight ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}

/** 帳號名稱縮寫（頭像用）：優先名字，其次 email 首字。 */
export function accountInitial(me) {
  const source = (me?.first_name || me?.display_name || me?.email || me?.username || "?").trim();
  return source.charAt(0).toUpperCase();
}

function AccountMenu() {
  const me = useArgusStore((s) => s.me);
  const navigate = useNavigate();
  const logout = useLogout();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    function onPointer(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        wrapRef.current?.querySelector(".app-account-trigger")?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    // 開啟時把焦點移到第一個選項，鍵盤使用者不必再 Tab 進去
    wrapRef.current?.querySelector('[role="menuitem"]')?.focus();
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function go(path) {
    setOpen(false);
    navigate(path);
  }

  const displayName = me?.display_name?.trim() || me?.email || me?.username || "我的帳號";

  return (
    <div className="app-account" ref={wrapRef}>
      <button
        type="button"
        className="app-account-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label="帳號選單"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="app-avatar" aria-hidden="true">{accountInitial(me)}</span>
      </button>
      {open && (
        <div className="app-account-menu" id={menuId} role="menu" aria-label="帳號">
          <div className="app-account-head">
            <span className="app-avatar is-lg" aria-hidden="true">{accountInitial(me)}</span>
            <span className="app-account-id">
              <strong>{displayName}</strong>
              {me?.email && me.email !== displayName ? <small>{me.email}</small> : null}
            </span>
          </div>
          <button type="button" role="menuitem" className="app-account-item" onClick={() => go("/settings")}>
            <GearIcon /> 帳號設定
          </button>
          <button type="button" role="menuitem" className="app-account-item" onClick={() => go("/billing")}>
            <CoinIcon /> 購點與訂閱
          </button>
          {me?.is_staff && (
            <button type="button" role="menuitem" className="app-account-item" onClick={() => go("/admin")}>
              <ShieldAdminIcon /> 管理後台
            </button>
          )}
          <button
            type="button"
            role="menuitem"
            className="app-account-item is-danger"
            onClick={() => { setOpen(false); logout(); }}
          >
            <LogoutIcon /> 登出
          </button>
        </div>
      )}
    </div>
  );
}

export default function NavActions() {
  const { accessToken, wallet, fetchWallet, me, fetchMe } = useArgusStore();
  const navigate = useNavigate();
  const { canInstall, installed, trigger } = useInstallPrompt();
  useEffect(() => {
    if (accessToken && !wallet) fetchWallet();
    if (accessToken && !me) fetchMe();
  }, [accessToken, wallet, fetchWallet, me, fetchMe]);
  if (!accessToken) return null;

  const balance = wallet?.balance;
  return (
    <div className="app-nav-actions">
      {canInstall && !installed && (
        <button
          className="app-install-chip"
          type="button"
          onClick={trigger}
          title="把 Argus 安裝到主畫面，像 APP 一樣使用"
        >
          <DownloadIcon />
          <span>安裝 APP</span>
        </button>
      )}
      <ThemeToggle />
      <button
        className="app-coin-chip"
        type="button"
        onClick={() => navigate("/billing")}
        title="前往購點"
        aria-label={`點數餘額 ${balance == null ? "載入中" : balance.toLocaleString()} coin，前往購點`}
      >
        <CoinIcon className="app-coin-chip-icon" />
        <span className="app-coin-chip-value ag-num">
          {balance == null ? "—" : balance.toLocaleString()}
        </span>
        <span className="app-coin-chip-unit">coin</span>
      </button>
      <AccountMenu />
    </div>
  );
}
