import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";

import type {
  AdminAdjustCoinResponse,
  AdminSetStaffResponse,
  AdminSuspendUserResponse,
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

// ---- MCP 接入中心（/api/mcp-access/）----

// 訂閱權益、用量、端點網址、憑證清單、最近呼叫與工具清單
export async function fetchMcpOverview() {
  const response = await api.get("/mcp-access/overview/");
  return response.data;
}

// 建立憑證；回應的 secret 是明文，只會出現這一次
export async function createMcpKey(name: string) {
  const response = await api.post("/mcp-access/keys/", { name });
  return response.data;
}

export async function revokeMcpKey(keyId: number) {
  const response = await api.post(`/mcp-access/keys/${keyId}/revoke/`);
  return response.data;
}

// 「驗證連線」：since 之後是否收到 initialize／工具呼叫
export async function checkMcpConnection(since: string, keyId?: number) {
  const response = await api.get("/mcp-access/connection/", {
    params: { since, ...(keyId ? { key_id: keyId } : {}) },
  });
  return response.data;
}

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

// 訂閱方案：送出方案與買受人／發票資料，回傳 { order, payment }（綠界定期定額結帳表單）；
// 首期付款成功的通知到達後才開通。付費關閉 503、已有自動扣款中的訂閱 409
export async function subscribePlan(planCode: string, buyer: Record<string, unknown>) {
  const response = await api.post("/billing/subscription/subscribe/", {
    plan_code: planCode,
    ...buyer,
  });
  return response.data;
}

// 取消訂閱（當期權益保留到期滿）；回傳 { subscription }
export async function cancelSubscription() {
  const response = await api.post("/billing/subscription/cancel/");
  return response.data;
}

// ---- 大頭貼（accounts）：後端會重新編碼成 256×256 PNG ----

// 上傳大頭貼（JPG／PNG／WebP，≤ 2 MB）；回傳 { avatar_url }
export async function uploadAvatar(file: File) {
  const form = new FormData();
  form.append("avatar", file);
  const response = await api.post("/auth/me/avatar/", form);
  return response.data as { avatar_url: string | null };
}

// 移除大頭貼（204）
export async function deleteAvatar() {
  await api.delete("/auth/me/avatar/");
}

// ---- 網域驗證（/api/domains/）：主動式資安測試的技術性閘門 ----

// 自己的網域驗證清單；回傳 DRF 分頁 { count, next, previous, results }
export async function fetchVerifiedDomains() {
  const response = await api.get("/domains/");
  return response.data;
}

// 新增待驗證網域；成功（201）回傳 { ...網域欄位, token, instructions }，重複時 409
export async function createVerifiedDomain(domain: string) {
  const response = await api.post("/domains/", { domain });
  return response.data;
}

// 以指定方法（search_console / dns_txt / meta_tag / html_file）驗證既有網域；回傳 { ...網域欄位, verified }
export async function verifyVerifiedDomain(
  domainId: number,
  method: "search_console" | "dns_txt" | "meta_tag" | "html_file",
) {
  const response = await api.post(`/domains/${domainId}/verify/`, { method });
  return response.data;
}

// 刪除網域（204 無內容）
export async function deleteVerifiedDomain(domainId: number) {
  await api.delete(`/domains/${domainId}/`);
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

// 設為／取消一般管理員（後端只允許超級管理員；不能動自己與超級管理員）
export async function adminSetStaff(userId: number, isStaff: boolean): Promise<AdminSetStaffResponse> {
  const response = await api.post(`/admin/users/${userId}/staff/`, { is_staff: isStaff });
  return response.data;
}

// 停用（封號）或恢復使用者；管理員對象只有超級管理員能處理（後端 _manage_target_error）
export async function adminSuspendUser(
  userId: number,
  suspended: boolean,
  reason = "",
): Promise<AdminSuspendUserResponse> {
  const response = await api.post(`/admin/users/${userId}/suspend/`, { suspended, reason });
  return response.data;
}

// 刪除使用者帳號（與使用者自行刪除相同：個資全刪、帳務匿名保留）；confirm 必須是「刪除帳號」
export async function adminDeleteUser(userId: number, confirm: string, reason = ""): Promise<void> {
  await api.post(`/admin/users/${userId}/delete/`, { confirm, reason });
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

