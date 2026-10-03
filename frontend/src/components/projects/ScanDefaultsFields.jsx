import { Link } from "react-router-dom";

import { CATEGORY_META, CATEGORY_ORDER } from "./DashboardWidgets.jsx";

// 網站專案的預設掃描設定欄位（範圍、維度、模式）；新增專案頁與專案設定共用。
// 這些只是「掃描」分頁表單的初始值，每次建立掃描仍可調整；費用與主動測試的授權都在建立掃描時才確認。

export const SCOPE_OPTIONS = [
  { value: "site", label: "整個網站", hint: "從起始網址爬同網站多頁（最多 50 頁）" },
  { value: "single", label: "單一頁面", hint: "只檢查起始網址這一頁，最快、最省點數" },
];

export const MODE_OPTIONS = [
  { value: "passive", label: "被動偵測", hint: "只讀取公開頁面與回應標頭，不送出測試請求" },
  { value: "active", label: "主動測試", hint: "另做敏感檔案探測與弱點驗證；需完成網域驗證" },
];

export const DEFAULT_SCAN_SETTINGS = {
  default_scope: "site",
  default_categories: [...CATEGORY_ORDER],
  default_scan_mode: "passive",
};

/**
 * @param {{ value: { default_scope: string, default_categories: string[], default_scan_mode: string },
 *   onChange: (next: object) => void, domainVerified?: boolean | null, hostname?: string, idPrefix?: string }} props
 */
export default function ScanDefaultsFields({ value, onChange, domainVerified = null, hostname = "", idPrefix = "defaults" }) {
  const categories = value.default_categories;

  function set(field, fieldValue) {
    const next = { ...value, [field]: fieldValue };
    // 主動測試屬資安檢測：選主動時自動補上資安維度（後端同樣會檢查）
    if (next.default_scan_mode === "active" && !next.default_categories.includes("security")) {
      next.default_categories = [...next.default_categories, "security"];
    }
    onChange(next);
  }

  function toggleCategory(category) {
    const next = categories.includes(category) ? categories.filter((item) => item !== category) : [...categories, category];
    if (!next.length) return; // 至少保留一個維度
    if (value.default_scan_mode === "active" && !next.includes("security")) return; // 主動測試不可取消資安
    set("default_categories", CATEGORY_ORDER.filter((item) => next.includes(item)));
  }

  return (
    <>
      <fieldset className="project-fieldset">
        <legend>掃描範圍</legend>
        <div className="project-choice-row">
          {SCOPE_OPTIONS.map((option) => (
            <label key={option.value} className={`project-choice ${value.default_scope === option.value ? "active" : ""}`}>
              <input
                type="radio"
                name={`${idPrefix}-scope`}
                value={option.value}
                checked={value.default_scope === option.value}
                onChange={() => set("default_scope", option.value)}
              />
              <span>
                <strong>{option.label}</strong>
                <small>{option.hint}</small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="project-fieldset">
        <legend>掃描維度（至少一項）</legend>
        <div className="project-category-choices">
          {CATEGORY_ORDER.map((category) => {
            const meta = CATEGORY_META[category];
            const locked = value.default_scan_mode === "active" && category === "security";
            return (
              <label key={category} className={`project-choice is-category ${categories.includes(category) ? "active" : ""}`}>
                <input
                  type="checkbox"
                  checked={categories.includes(category)}
                  disabled={locked}
                  onChange={() => toggleCategory(category)}
                />
                <span className={`project-choice-icon cat-${category}`} aria-hidden="true">
                  <meta.Icon />
                </span>
                <span>
                  <strong>{meta.label}</strong>
                  <small>{locked ? "主動測試必選" : meta.desc}</small>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <fieldset className="project-fieldset">
        <legend>掃描模式</legend>
        <div className="project-choice-row">
          {MODE_OPTIONS.map((option) => (
            <label key={option.value} className={`project-choice ${value.default_scan_mode === option.value ? "active" : ""}`}>
              <input
                type="radio"
                name={`${idPrefix}-mode`}
                value={option.value}
                checked={value.default_scan_mode === option.value}
                onChange={() => set("default_scan_mode", option.value)}
              />
              <span>
                <strong>{option.label}</strong>
                <small>{option.hint}</small>
              </span>
            </label>
          ))}
        </div>
        {value.default_scan_mode === "active" && domainVerified === false && (
          <p className="project-field-note" role="note">
            {hostname ? `${hostname} 尚未完成網域驗證，` : "網站尚未完成網域驗證，"}
            驗證前建立掃描只能使用被動偵測。<Link className="project-text-link" to="/domains">前往網域驗證 →</Link>
          </p>
        )}
      </fieldset>
    </>
  );
}

export { ScanDefaultsFields };
