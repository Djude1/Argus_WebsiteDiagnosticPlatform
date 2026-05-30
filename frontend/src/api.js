import axios from "axios";

export const api = axios.create({
  // 使用相對路徑讓 local runserver（同 origin）與 Docker compose（nginx 反向代理）皆可正常運作
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
});

export function setAccessToken(token) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

// F5 後若 localStorage 內的 token 已過期（JWT_ACCESS_TOKEN_LIFETIME 預設 60 分）
// 後端會回 401。沒這段攔截，使用者會卡在「尚無掃描任務」/「無法載入掃描資料」永遠出不去。
// 攔截後：清 token、清 Authorization、強制回到 /login（保留 next 以便登入後跳回）。
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    // 登入端點本身回 401 不是 token 過期，不要無限導向
    const isAuthEndpoint = url.startsWith("/auth/");
    if (status === 401 && !isAuthEndpoint) {
      window.localStorage.removeItem("argus_access_token");
      delete api.defaults.headers.common.Authorization;
      if (window.location.pathname !== "/login") {
        const next = encodeURIComponent(
          window.location.pathname + window.location.search,
        );
        window.location.href = `/login?next=${next}`;
      }
    }
    return Promise.reject(error);
  },
);

