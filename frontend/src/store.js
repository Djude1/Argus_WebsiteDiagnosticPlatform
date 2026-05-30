import { create } from "zustand";

import { api, setAccessToken } from "./api";

const storedToken = window.localStorage.getItem("argus_access_token");
setAccessToken(storedToken);

export const useArgusStore = create((set, get) => ({
  accessToken: storedToken,
  // wallet 為 null 代表尚未載入；登入後 fetchWallet 會填上
  wallet: null,
  walletLoading: false,
  // 目前登入者的 staff 旗標；用於決定是否顯示後台入口
  me: null,
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
