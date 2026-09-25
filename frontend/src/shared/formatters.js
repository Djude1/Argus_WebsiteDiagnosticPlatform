// 跨 feature 共用的顯示格式化工具。
//
// 存在理由：專案原本把 `new Date(x).toLocaleString("zh-Hant")` 直接寫在各頁 JSX 裡
// （後台就有十餘處），要調整格式得逐一改、也無法保證一致。所有「把資料變成畫面文字」
// 的邏輯集中在這裡。

const DATE_TIME_FORMAT = new Intl.DateTimeFormat("zh-Hant", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const DATE_FORMAT = new Intl.DateTimeFormat("zh-Hant", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function toDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** 日期時間；無值或不可解析時回傳 fallback（預設破折號，而非 "Invalid Date"）。 */
export function formatDateTime(value, fallback = "—") {
  const date = toDate(value);
  return date ? DATE_TIME_FORMAT.format(date) : fallback;
}

/** 只要日期。 */
export function formatDate(value, fallback = "—") {
  const date = toDate(value);
  return date ? DATE_FORMAT.format(date) : fallback;
}

/**
 * 相對時間（「12 分鐘前」）。後台用來表達「這筆已經等多久」，
 * 絕對時間看不出嚴重性，相對時間才看得出。
 */
export function formatRelative(value, fallback = "—") {
  const date = toDate(value);
  if (!date) return fallback;
  const diffSec = Math.round((Date.now() - date.getTime()) / 1000);
  const abs = Math.abs(diffSec);
  const suffix = diffSec >= 0 ? "前" : "後";
  if (abs < 60) return `${abs} 秒${suffix}`;
  if (abs < 3600) return `${Math.floor(abs / 60)} 分鐘${suffix}`;
  if (abs < 86400) return `${Math.floor(abs / 3600)} 小時${suffix}`;
  return `${Math.floor(abs / 86400)} 天${suffix}`;
}

/** 經過秒數 → 「1 分 20 秒」；後台掃描耗時用。 */
export function formatDuration(seconds, fallback = "—") {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return fallback;
  }
  const total = Math.max(0, Math.round(Number(seconds)));
  if (total < 60) return `${total} 秒`;
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return sec ? `${min} 分 ${sec} 秒` : `${min} 分`;
}

/** 千分位整數。 */
export function formatNumber(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  const num = Number(value);
  return Number.isNaN(num) ? fallback : num.toLocaleString("zh-Hant");
}

/** 新台幣金額。 */
export function formatNtd(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  const num = Number(value);
  return Number.isNaN(num) ? fallback : `NT$ ${num.toLocaleString("zh-Hant")}`;
}
