import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import { useInstallPrompt } from "../../shared/AppShared.jsx";

export default function NavActions() {
  const { accessToken, setToken, wallet, fetchWallet, me, fetchMe } = useArgusStore();
  const navigate = useNavigate();
  const { canInstall, installed, trigger } = useInstallPrompt();
  useEffect(() => {
    if (accessToken && !wallet) fetchWallet();
    if (accessToken && !me) fetchMe();
  }, [accessToken, wallet, fetchWallet, me, fetchMe]);
  if (!accessToken) return null;

  async function handleLogout() {
    try {
      await api.post("/auth/logout/");
    } finally {
      setToken(null);
      navigate("/login");
    }
  }

  const balance = wallet?.balance;
  return (
    <>
      {canInstall && !installed && (
        <button
          className="install-chip"
          type="button"
          onClick={trigger}
          title="把 Argus 安裝到主畫面，像 APP 一樣使用"
        >
          <span aria-hidden="true">⬇</span>
          <span>安裝 APP</span>
        </button>
      )}
      <button
        className="coin-chip"
        type="button"
        onClick={() => navigate("/billing")}
        title="前往購點"
      >
        <span className="coin-chip-icon" aria-hidden="true">💎</span>
        <span className="coin-chip-value">
          {balance == null ? "—" : balance.toLocaleString()}
        </span>
        <span className="coin-chip-unit">coin</span>
      </button>
      <button className="nav-logout-btn" type="button" onClick={handleLogout}>
        登出
      </button>
    </>
  );
}
