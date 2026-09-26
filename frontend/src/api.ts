import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";

import type {
  AdminAdjustCoinResponse,
  AdminAuditLogListParams,
  AdminAuditLogListResponse,
  AdminDomainListParams,
  AdminDomainListResponse,
  AdminOrderListParams,
  AdminOrderListResponse,
  AdminReviewListParams,
  AdminReview,
  AdminReviewListResponse,
  AdminScanCancelResponse,
  AdminScanDetailResponse,
  AdminScanListParams,
  AdminScanListResponse,
  AdminScanRequeueResponse,
  AdminTransactionListParams,
  AdminTransactionListResponse,
  AdminUserListParams,
  AdminLoginEventsResponse,
  AdminSubscriptionPlansResponse,
  AdminUserDetailResponse,
  AdminUserListResponse,
  AdminUserSubscriptionResponse,
  AdminVerifiedDomain,
  Announcement,
  AnnouncementInput,
  AnnouncementListResponse,
  AnnouncementPatch,
  PricingPlan,
  PricingPlanInput,
  PricingPlanListResponse,
  PricingPlanPatch,
} from "./shared/apiContracts";

export const api = axios.create({
  // 使用相對路徑讓 local runserver（同 origin）與 Docker compose（nginx 反向代理）皆可正常運作
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  withCredentials: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
});

export function setAccessToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

let refreshRequest: Promise<{ data: { access: string } }> | null = null;

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
export async function subscribePlan(planCode: string) {
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
export async function createVerifiedDomain(domain: string) {
  const response = await api.post("/scans/domains/", { domain });
  return response.data;
}

// 以指定方法（dns_txt / meta_tag / html_file）驗證既有網域；回傳 { ...網域欄位, verified }
export async function verifyVerifiedDomain(
  domainId: number,
  method: "dns_txt" | "meta_tag" | "html_file",
) {
  const response = await api.post(`/scans/domains/${domainId}/verify/`, { method });
  return response.data;
}

// 刪除網域（204 無內容）
export async function deleteVerifiedDomain(domainId: number) {
  await api.delete(`/scans/domains/${domainId}/`);
}

// ---- Admin：網域人工審核 / 使用者登入事件 / 訂閱管理 ----

// 全部使用者的網域驗證清單；params: { page, q, status }；回傳 { domains, page, total_pages, total }
export async function fetchAdminDomains(
  params: AdminDomainListParams,
): Promise<AdminDomainListResponse> {
  const response = await api.get("/admin/domains/", { params });
  return response.data;
}

// 網域人工審核：approve=true 核准（同等於驗證通過）、false 否決；回傳更新後的網域物件
export async function adminDomainOverride(
  domainId: number,
  approve: boolean,
  note = "",
): Promise<AdminVerifiedDomain> {
  const response = await api.post(`/admin/domains/${domainId}/override/`, { approve, note });
  return response.data;
}

// 指定使用者的登入事件（最近 50 筆）；回傳 { events }
export async function fetchUserLoginEvents(userId: number): Promise<AdminLoginEventsResponse> {
  const response = await api.get(`/admin/users/${userId}/login-events/`);
  return response.data;
}

// 指定使用者的訂閱現況；回傳 { subscription }（無訂閱時 subscription=null）
export async function fetchUserSubscription(
  userId: number,
): Promise<AdminUserSubscriptionResponse> {
  const response = await api.get(`/admin/users/${userId}/subscription/`);
  return response.data;
}

// 後台調整訂閱：action=grant 需 planCode 與 periods（1-36）、action=cancel 不需；
// 兩者皆回傳 { subscription }（取消但無訂閱時 404）
export async function adminUserSubscriptionAction(
  userId: number,
  action: "grant" | "cancel",
  planCode: string | null = null,
  periods = 1,
): Promise<AdminUserSubscriptionResponse> {
  const response = await api.post(`/admin/users/${userId}/subscription/`, {
    action,
    plan_code: planCode || undefined,
    periods,
  });
  return response.data;
}

// 後台訂閱方案清單（含停用）；回傳 { plans }
export async function fetchAdminSubscriptionPlans(): Promise<AdminSubscriptionPlansResponse> {
  const response = await api.get("/admin/subscriptions/plans/");
  return response.data;
}

// ---- Admin 列表：查詢參數與回傳型別都綁到後端產生的 schema ----
//
// 參數鍵名一旦打錯（或後端還沒宣告該篩選條件）就是編譯錯誤，不會再出現
// 「網址帶著參數、列表卻沒套用」這種畫面正常但結果錯誤的情況。

export async function fetchAdminScans(
  params: AdminScanListParams,
): Promise<AdminScanListResponse> {
  const response = await api.get("/admin/scans/", { params });
  return response.data;
}

export async function fetchAdminScanDetail(
  scanId: number,
): Promise<AdminScanDetailResponse> {
  const response = await api.get(`/admin/scans/${scanId}/`);
  return response.data;
}

// 合作式終止：worker 在下個檢查點停下，預扣全額退回
export async function adminCancelScan(scanId: number): Promise<AdminScanCancelResponse> {
  const response = await api.post(`/admin/scans/${scanId}/cancel/`);
  return response.data;
}

// 只允許 failed／cancelled；依產品決策不重複扣點
export async function adminRequeueScan(scanId: number): Promise<AdminScanRequeueResponse> {
  const response = await api.post(`/admin/scans/${scanId}/requeue/`);
  return response.data;
}

export async function fetchAdminUsers(
  params: AdminUserListParams,
): Promise<AdminUserListResponse> {
  const response = await api.get("/admin/users/", { params });
  return response.data;
}

export async function fetchAdminUserDetail(userId: number): Promise<AdminUserDetailResponse> {
  const response = await api.get(`/admin/users/${userId}/`);
  return response.data;
}

// 手動補／扣點（走 billing.services.admin_adjust）；delta 不可為 0
export async function adminAdjustCoin(
  userId: number,
  delta: number,
  note: string,
): Promise<AdminAdjustCoinResponse> {
  const response = await api.post(`/admin/users/${userId}/adjust-coin/`, { delta, note });
  return response.data;
}

export async function fetchAdminTransactions(
  params: AdminTransactionListParams,
): Promise<AdminTransactionListResponse> {
  const response = await api.get("/admin/transactions/", { params });
  return response.data;
}

export async function fetchAdminAuditLog(
  params: AdminAuditLogListParams,
): Promise<AdminAuditLogListResponse> {
  const response = await api.get("/admin/audit-log/", { params });
  return response.data;
}

export async function fetchAdminOrders(
  params: AdminOrderListParams,
): Promise<AdminOrderListResponse> {
  const response = await api.get("/admin/orders/", { params });
  return response.data;
}

export async function fetchAdminReviews(
  params: AdminReviewListParams,
): Promise<AdminReviewListResponse> {
  const response = await api.get("/admin/reviews/", { params });
  return response.data;
}

// ---- Admin 評論治理：官方回覆與公開狀態 ----

export async function adminReplyReview(reviewId: number, reply: string): Promise<AdminReview> {
  const response = await api.post(`/admin/reviews/${reviewId}/reply/`, { reply });
  return response.data;
}

export async function adminDeleteReviewReply(reviewId: number): Promise<void> {
  await api.delete(`/admin/reviews/${reviewId}/reply/`);
}

export async function adminModerateReview(
  reviewId: number,
  status: AdminReview["status"],
): Promise<AdminReview> {
  const response = await api.patch(`/admin/reviews/${reviewId}/moderate/`, { status });
  return response.data;
}

// ---- Admin 公告（僅超級管理員）----

export async function fetchAdminAnnouncements(): Promise<AnnouncementListResponse> {
  const response = await api.get("/admin/announcements/");
  return response.data;
}

export async function createAnnouncement(input: AnnouncementInput): Promise<Announcement> {
  const response = await api.post("/admin/announcements/", input);
  return response.data;
}

export async function updateAnnouncement(id: number, patch: AnnouncementPatch): Promise<Announcement> {
  const response = await api.patch(`/admin/announcements/${id}/`, patch);
  return response.data;
}

export async function deleteAnnouncement(id: number): Promise<void> {
  await api.delete(`/admin/announcements/${id}/`);
}

// ---- Admin 購點方案（CMS）----

export async function fetchAdminPlans(): Promise<PricingPlanListResponse> {
  const response = await api.get("/admin/cms/plans/");
  return response.data;
}

export async function createPlan(input: PricingPlanInput): Promise<PricingPlan> {
  const response = await api.post("/admin/cms/plans/", input);
  return response.data;
}

export async function updatePlan(id: number, patch: PricingPlanPatch): Promise<PricingPlan> {
  const response = await api.patch(`/admin/cms/plans/${id}/`, patch);
  return response.data;
}

export async function deletePlan(id: number): Promise<void> {
  await api.delete(`/admin/cms/plans/${id}/`);
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    const isAuthEndpoint = url.startsWith("/auth/");
    const originalRequest = error?.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;
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

