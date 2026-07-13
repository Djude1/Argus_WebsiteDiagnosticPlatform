import axios from "axios";

export const api = axios.create({
  // 使用相對路徑讓 local runserver（同 origin）與 Docker compose（nginx 反向代理）皆可正常運作
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  withCredentials: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
});

export function setAccessToken(token) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

let refreshRequest = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    const isAuthEndpoint = url.startsWith("/auth/");
    const originalRequest = error?.config;
    if (status === 401 && !isAuthEndpoint && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        if (!refreshRequest) {
          refreshRequest = api.post("/auth/refresh/").finally(() => {
            refreshRequest = null;
          });
        }
        const refreshed = await refreshRequest;
        setAccessToken(refreshed.data.access);
        originalRequest.headers.Authorization = `Bearer ${refreshed.data.access}`;
        return api(originalRequest);
      } catch {
        setAccessToken(null);
      }
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

