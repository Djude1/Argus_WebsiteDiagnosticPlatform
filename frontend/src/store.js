import { create } from "zustand";

import { api, setAccessToken } from "./api";

const storedToken = window.localStorage.getItem("argus_access_token");
setAccessToken(storedToken);

const storedTheme = (() => {
  try { return window.localStorage.getItem("argus_theme") === "light" ? "light" : "dark"; }
  catch { return "dark"; }
})();
try { document.documentElement.setAttribute("data-theme", storedTheme); } catch { /* 無 DOM 環境 */ }

export const useArgusStore = create((set, get) => ({
  accessToken: storedToken,
  // wallet 為 null 代表尚未載入；登入後 fetchWallet 會填上
  wallet: null,
  walletLoading: false,
  // 目前登入者的 staff 旗標；用於決定是否顯示後台入口
  me: null,
  // 首次進站動畫旗標（localStorage argus_intro_seen 持久化）；品牌 icon 可呼叫 replayIntro 重播
  introSeen: (() => {
    try { return window.localStorage.getItem("argus_intro_seen") === "1"; }
    catch { return true; }
  })(),
  markIntroSeen: () => {
    try { window.localStorage.setItem("argus_intro_seen", "1"); } catch { /* 無痕模式 */ }
    set({ introSeen: true });
  },
  replayIntro: () => {
    try { window.localStorage.removeItem("argus_intro_seen"); } catch { /* 無痕模式 */ }
    set({ introSeen: false });
  },
  // 雙色主題（dark 預設 / light）；data-theme 設在 <html>，公開頁 shell 套用 light
  theme: storedTheme,
  toggleTheme: () => {
    const next = get().theme === "light" ? "dark" : "light";
    try { window.localStorage.setItem("argus_theme", next); } catch { /* 無痕 */ }
    try { document.documentElement.setAttribute("data-theme", next); } catch { /* 無 DOM */ }
    set({ theme: next });
  },
  setToken: (token) => {
    if (token) {
      window.localStorage.setItem("argus_access_token", token);
    } else {
      window.localStorage.removeItem("argus_access_token");
    }
    setAccessToken(token);
    set({
      accessToken: token,
      wallet: token ? get().wallet : null,
      me: token ? get().me : null,
    });
  },
  fetchWallet: async () => {
    if (!get().accessToken) return null;
    set({ walletLoading: true });
    try {
      const response = await api.get("/billing/wallet/");
      set({ wallet: response.data, walletLoading: false });
      return response.data;
    } catch {
      set({ walletLoading: false });
      return null;
    }
  },
  setWallet: (wallet) => set({ wallet }),
  fetchMe: async () => {
    if (!get().accessToken) return null;
    try {
      const response = await api.get("/admin/me/");
      set({ me: response.data });
      return response.data;
    } catch {
      return null;
    }
  },
}));
