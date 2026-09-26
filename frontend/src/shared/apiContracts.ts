// 後台 API 的型別出入口。
//
// apiTypes.ts 是 drf-spectacular → OpenAPI → openapi-typescript 產生的，
// 不要手改；它的 `components["schemas"]["X"]` 寫法在呼叫端太吵，所以這裡把
// 後台實際會用到的幾個型別取好名字再 re-export。
//
// 重點是查詢參數：`AdminScanListParams` 直接來自後端宣告的 query parameters，
// 打錯鍵名或給錯型別都會是編譯錯誤——先前 `?user=` 沒被宣告、列表靜默不篩選，
// 就是這一類問題，當時沒有任何東西擋得住。
//
// 後端改了欄位要重新產生：
//   uv run python backend/manage.py spectacular --file frontend/openapi.json --format openapi-json
//   cd frontend && npx openapi-typescript openapi.json -o src/shared/apiTypes.ts

import type { components, operations } from "./apiTypes";

type Schemas = components["schemas"];

/** 列表項目 */
export type AdminScanJob = Schemas["AdminScanJob"];
export type AdminUser = Schemas["AdminUserList"];
export type AdminCoinTransaction = Schemas["AdminCoinTransaction"];
export type AdminAuditLog = Schemas["AdminAuditLog"];
export type AdminVerifiedDomain = Schemas["AdminVerifiedDomain"];
export type AdminPurchaseOrder = Schemas["AdminPurchaseOrder"];
export type AdminReview = Schemas["AdminReview"];

/** 列表信封（`{ <key>: [...], page, total_pages, total }`） */
export type AdminScanListResponse = Schemas["AdminScanListResponse"];
export type AdminUserListResponse = Schemas["AdminUserListResponse"];
export type AdminTransactionListResponse = Schemas["AdminTransactionListResponse"];
export type AdminAuditLogListResponse = Schemas["AdminAuditLogListResponse"];
export type AdminDomainListResponse = Schemas["AdminDomainListResponse"];
export type AdminOrderListResponse = Schemas["AdminOrderListResponse"];
export type AdminReviewListResponse = Schemas["AdminReviewListResponse"];
export type AdminScanDetailResponse = Schemas["AdminScanDetailResponse"];
export type AdminScanCancelResponse = Schemas["AdminScanCancelResponse"];
export type AdminScanRequeueResponse = Schemas["AdminScanRequeueResponse"];
export type AdminUserDetailResponse = Schemas["AdminUserDetailResponse"];
export type AdminAdjustCoinResponse = Schemas["AdminAdjustCoinResponse"];
export type AdminLoginEventsResponse = Schemas["AdminLoginEventsResponse"];
export type AdminUserSubscriptionResponse = Schemas["AdminUserSubscriptionResponse"];
export type AdminSubscriptionPlansResponse = Schemas["AdminSubscriptionPlansResponse"];
export type AdminUserSubscription = Schemas["AdminUserSubscription"];
export type AdminSubscriptionPlan = Schemas["AdminSubscriptionPlan"];
export type AdminLoginEvent = Schemas["AdminLoginEvent"];

/** 交易類型：後端 CoinTransaction.Kind 的完整集合 */
export type CoinTransactionKind = Schemas["KindEnum"];

// 注意：drf-spectacular 對同名欄位（多個 model 都有 status）產生的 enum 名稱帶雜湊後綴
// （如 StatusA7fEnum），其他 enum 變動時可能改名。取 enum 型別一律從所屬 schema 的欄位
// 索引，不要直接引用這類名稱。
export type VerifiedDomainStatus = AdminVerifiedDomain["status"];
export type AdminAuditAction = AdminAuditLog["action"];

export type Announcement = Schemas["Announcement"];
export type AnnouncementInput = Schemas["AnnouncementRequest"];
export type AnnouncementPatch = Schemas["PatchedAnnouncementRequest"];
export type AnnouncementListResponse = Schemas["AnnouncementListResponse"];

export type PricingPlan = Schemas["PricingPlanWrite"];
export type PricingPlanInput = Schemas["PricingPlanWriteRequest"];
export type PricingPlanPatch = Schemas["PatchedPricingPlanWriteRequest"];
export type PricingPlanListResponse = Schemas["PricingPlanListResponse"];

/** 查詢參數：鍵名與型別由後端的 `@list_schema(filters=...)` 決定 */
type Query<O extends { parameters: { query?: unknown } }> = NonNullable<O["parameters"]["query"]>;

export type AdminScanListParams = Query<operations["admin_scans_retrieve"]>;
export type AdminUserListParams = Query<operations["admin_users_retrieve"]>;
export type AdminTransactionListParams = Query<operations["admin_transactions_retrieve"]>;
export type AdminAuditLogListParams = Query<operations["admin_audit_log_retrieve"]>;
export type AdminDomainListParams = Query<operations["admin_domains_retrieve"]>;
export type AdminOrderListParams = Query<operations["admin_orders_retrieve"]>;
export type AdminReviewListParams = Query<operations["admin_reviews_retrieve"]>;
