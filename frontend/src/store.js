import { create } from "zustand";

import { api, setAccessToken } from "./api";

const CURRENT_PROJECT_KEY = "argus_current_project";
// 目前網站專案只是個人便利設定（下次登入回到同一個網站），存在瀏覽器即可、不寫後端
const storedProjectId = (() => {
  try {
    const value = Number(window.localStorage.getItem(CURRENT_PROJECT_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
})();

const storedTheme = (() => {
  try { return window.localStorage.getItem("argus_theme") === "light" ? "light" : "dark"; }
  catch { return "dark"; }
})();
try { document.documentElement.setAttribute("data-theme", storedTheme); } catch { /* 無 DOM 環境 */ }

export const useArgusStore = create((set, get) => ({
  accessToken: null,
  authReady: false,
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
    setAccessToken(token);
    set({
      accessToken: token,
      authReady: true,
      wallet: token ? get().wallet : null,
      me: token ? get().me : null,
      projects: token ? get().projects : null,
    });
  },
  restoreSession: async () => {
    try {
      const response = await api.post("/auth/refresh/");
      get().setToken(response.data.access);
    } catch {
      setAccessToken(null);
      set({ accessToken: null, authReady: true, wallet: null, me: null, projects: null });
    }
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
  // 網站專案（會員區以網站為單位，見 docs/adr/0003-site-project-workspace.md）。
  // projects 為 null＝尚未載入；切換器、所有專案頁與舊入口轉址共用這份清單。
  projects: null,
  currentProjectId: storedProjectId,
  fetchProjects: async () => {
    if (!get().accessToken) return null;
    try {
      const response = await api.get("/projects/");
      set({ projects: response.data });
      return response.data;
    } catch {
      return null;
    }
  },
  setCurrentProject: (projectId) => {
    try { window.localStorage.setItem(CURRENT_PROJECT_KEY, String(projectId)); } catch { /* 無痕模式 */ }
    set({ currentProjectId: projectId });
  },
  // 單一專案的最新資料（新增、改名、恢復）併回清單；封存的從清單移除
  upsertProject: (project) => {
    const list = get().projects;
    if (!list) return;
    if (project.archived_at) {
      set({ projects: list.filter((item) => item.id !== project.id) });
    } else if (list.some((item) => item.id === project.id)) {
      set({ projects: list.map((item) => (item.id === project.id ? project : item)) });
    } else {
      set({ projects: [project, ...list] });
    }
  },
  removeProject: (projectId) => {
    const list = get().projects;
    if (list) set({ projects: list.filter((item) => item.id !== projectId) });
  },
}));
