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

// ---- 訂閱（billing subscription）：回傳 data，錯誤丟給呼叫端以 axios error 處理 ----

// 公開的訂閱方案清單；回傳 { plans, payment_mode, subscribe_enabled }
export async function fetchSubscriptionPlans() {
  const response = await api.get("/billing/subscription/plans/");
  return response.data;
}

// 自己的訂閱狀態；回傳 { subscription: {...} | null }
export async function fetchMySubscription() {
  const response = await api.get("/billing/subscription/");
  return response.data;
}

// 訂閱方案（plan_code）；成功回傳 { subscription, payment_mode }，付費關閉時 503
export async function subscribePlan(planCode) {
  const response = await api.post("/billing/subscription/subscribe/", {
    plan_code: planCode,
  });
  return response.data;
}

// 取消訂閱（當期權益保留到期滿）；回傳 { subscription }
export async function cancelSubscription() {
  const response = await api.post("/billing/subscription/cancel/");
  return response.data;
}

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

