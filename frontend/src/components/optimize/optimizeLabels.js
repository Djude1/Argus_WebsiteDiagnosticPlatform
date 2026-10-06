// 頁面優化結果的分類與文字（後端 apps/rebuild/services.py 的 _CATEGORIES、metrics.py 的分類）。

// 結果頁的四個分組：使用者先看「視覺有什麼不同」，再看技術、無障礙、效能
export const CHANGE_GROUPS = [
  { key: "visual", label: "視覺與 UX" },
  { key: "seo", label: "SEO 與 Meta" },
  { key: "accessibility", label: "無障礙與語意" },
  { key: "performance", label: "效能" },
];

export const CATEGORY_LABELS = {
  seo: "SEO",
  meta: "Meta",
  links: "連結",
  accessibility: "無障礙",
  semantic: "語意結構",
  forms: "表單",
  performance: "效能",
  layout: "版面",
  hierarchy: "視覺層次",
  typography: "文字排版",
  spacing: "間距對齊",
  navigation: "導覽",
  cta: "行動按鈕",
  responsive: "行動版",
  interaction: "互動回饋",
  consistency: "一致性",
};

const GROUP_OF_CATEGORY = {
  seo: "seo",
  meta: "seo",
  links: "seo",
  accessibility: "accessibility",
  semantic: "accessibility",
  forms: "accessibility",
  performance: "performance",
};

/** 一筆修改屬於哪個分組：visual 層一律歸「視覺與 UX」，其餘依分類。 */
export function changeGroup(edit) {
  if (edit.layer === "visual") return "visual";
  return GROUP_OF_CATEGORY[edit.category] || "seo";
}

export const OWNER_LABELS = { server: "伺服器設定", content: "內容負責人", design: "設計決策" };

export const SEVERITY_LABELS = {
  critical: "嚴重",
  high: "高",
  medium: "中",
  low: "低",
  info: "提示",
};

export const ACCESS_OPTIONS = [
  { value: "private", label: "僅限我", hint: "只有你能在 Argus 裡看到這次優化結果。" },
  { value: "link", label: "知道連結的任何人", hint: "不需要 Argus 帳號，拿到連結就能檢視。" },
  { value: "login", label: "知道連結且已登入 Argus 的人", hint: "對方要先登入 Argus 才能檢視。" },
];

/** 指標值的顯示：布林顯示有／無。 */
export function metricValue(value) {
  if (value === true) return "有";
  if (value === false) return "無";
  return String(value);
}
