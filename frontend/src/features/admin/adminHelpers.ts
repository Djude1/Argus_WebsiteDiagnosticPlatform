import { STATUS_LABELS } from "../../shared/AppShared.jsx";

// 後台 .tsx 頁面共用的小工具。原本寫在 AdminScansPages.tsx 內，使用者頁也要用，
// 之後其餘列表頁轉 TypeScript 時同樣需要，所以集中在這裡。

/**
 * 網址上的值可能是任何字串；只回傳白名單內的值，否則 undefined。
 * 用在 `ordering` 等後端有白名單的參數——壞值不送，交給後端用預設值。
 */
export function toAllowed<T extends string>(value: string, allowed: readonly T[]): T | undefined {
  return (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

/** 網址上的 id 是字串；後端要正整數，壞值回傳 undefined（等同不篩選）。 */
export function toPositiveInt(value: string): number | undefined {
  const n = Number(value);
  return value && Number.isInteger(n) && n > 0 ? n : undefined;
}

type StatusLabel = { label: string };

/** 掃描狀態的中文標籤；未知狀態原樣顯示。 */
export function statusLabel(status: string | undefined): string {
  if (!status) return "—";
  return (STATUS_LABELS as Record<string, StatusLabel | undefined>)[status]?.label || status;
}

/** 下拉選單用的掃描狀態清單 */
export const STATUS_OPTIONS = Object.entries(STATUS_LABELS as Record<string, StatusLabel>);

/** 從 axios 錯誤取出後端的 detail；取不到就用 fallback。 */
export function errorDetail(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: string } }; message?: string } | null;
  return e?.response?.data?.detail || e?.message || fallback;
}

/**
 * DRF 的驗證錯誤（400）格式是 `{ 欄位: ["訊息", ...] }`；轉成「欄位 → 第一則訊息」，
 * 讓表單能把錯誤顯示在對應欄位旁（AdminField 的 error）。不是這種格式就回傳空物件。
 */
export function fieldErrors(err: unknown): Record<string, string> {
  const data = (err as { response?: { status?: number; data?: unknown } } | null)?.response;
  if (data?.status !== 400 || !data.data || typeof data.data !== "object") return {};
  const result: Record<string, string> = {};
  for (const [field, messages] of Object.entries(data.data as Record<string, unknown>)) {
    if (Array.isArray(messages) && typeof messages[0] === "string") result[field] = messages[0];
  }
  return result;
}

