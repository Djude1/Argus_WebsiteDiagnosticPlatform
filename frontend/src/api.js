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

// ---- 網域驗證（scans/domains）：主動式資安測試的技術性閘門 ----

// 自己的網域驗證清單；回傳 DRF 分頁 { count, next, previous, results }
export async function fetchVerifiedDomains() {
  const response = await api.get("/scans/domains/");
  return response.data;
}

// 新增待驗證網域；成功（201）回傳 { ...網域欄位, token, instructions }，重複時 409
export async function createVerifiedDomain(domain) {
  const response = await api.post("/scans/domains/", { domain });
  return response.data;
}

// 以指定方法（dns_txt / meta_tag / html_file）驗證既有網域；回傳 { ...網域欄位, verified }
export async function verifyVerifiedDomain(domainId, method) {
  const response = await api.post(`/scans/domains/${domainId}/verify/`, { method });
  return response.data;
}

// 刪除網域（204 無內容）
export async function deleteVerifiedDomain(domainId) {
  await api.delete(`/scans/domains/${domainId}/`);
}

// ---- Admin：網域人工審核 / 使用者登入事件 / 訂閱管理 ----

// 全部使用者的網域驗證清單；params: { page, q, status }；回傳 { domains, page, total_pages, total }
export async function fetchAdminDomains(params) {
  const response = await api.get("/admin/domains/", { params });
  return response.data;
}

// 網域人工審核：approve=true 核准（同等於驗證通過）、false 否決；回傳更新後的網域物件
export async function adminDomainOverride(domainId, approve, note = "") {
  const response = await api.post(`/admin/domains/${domainId}/override/`, { approve, note });
  return response.data;
}

// 指定使用者的登入事件（最近 50 筆）；回傳 { events }
export async function fetchUserLoginEvents(userId) {
  const response = await api.get(`/admin/users/${userId}/login-events/`);
  return response.data;
}

// 指定使用者的訂閱現況；回傳 { subscription }（無訂閱時 subscription=null）
export async function fetchUserSubscription(userId) {
  const response = await api.get(`/admin/users/${userId}/subscription/`);
  return response.data;
}

// 後台調整訂閱：action=grant 需 planCode 與 periods（1-36）、action=cancel 不需；
// 兩者皆回傳 { subscription }（取消但無訂閱時 404）
export async function adminUserSubscriptionAction(userId, action, planCode = null, periods = 1) {
  const response = await api.post(`/admin/users/${userId}/subscription/`, {
    action,
    plan_code: planCode || undefined,
    periods,
  });
  return response.data;
}

// 後台訂閱方案清單（含停用）；回傳 { plans }
export async function fetchAdminSubscriptionPlans() {
  const response = await api.get("/admin/subscriptions/plans/");
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

