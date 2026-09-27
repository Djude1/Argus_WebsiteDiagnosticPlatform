// 公開評論頁的資料形狀。
//
// 公開評論端點（/api/reviews/*）尚未納入 OpenAPI 產生的 apiTypes.ts，
// 這裡依 backend/apps/reviews/serializers.py 的 PlatformReviewSerializer／
// ReviewResponseSerializer 描述；後端欄位異動時要同步修改。

export type ReviewOfficialResponse = {
  id: number;
  body: string;
  helpful_count: number;
  my_helpful: boolean;
  created_at: string;
  updated_at: string;
};

export type PublicReview = {
  id: number;
  rating: number;
  title: string;
  comment: string;
  show_partial_email: boolean;
  /** 後端已遮罩的顯示名稱（部分 Email 或「匿名已驗證使用者」） */
  user_display: string;
  is_mine: boolean;
  verified_experience: boolean;
  experience_at: string | null;
  helpful_count: number;
  my_helpful: boolean;
  response: ReviewOfficialResponse | null;
  created_at: string;
  updated_at: string;
};

/** 按讚／檢舉的對象：使用者評論本身，或其下的官方回覆 */
export type ReviewTarget = "review" | "response";

export type ReviewPayload = {
  rating: number;
  comment: string;
  show_partial_email: boolean;
};

export type ReportDraft = {
  target: ReviewTarget;
  reviewId: number;
  responseId: number | null;
  reason: string;
  detail: string;
};

export const RATING_LABELS: Record<number, string> = {
  1: "很不滿意",
  2: "不滿意",
  3: "普通",
  4: "滿意",
  5: "很滿意",
};
