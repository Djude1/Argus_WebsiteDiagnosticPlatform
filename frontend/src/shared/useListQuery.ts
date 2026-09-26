import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

// 把列表頁的「搜尋 / 篩選 / 排序 / 分頁」狀態放進網址。
//
// 存在理由：後台原本這些狀態全部只存在 useState 裡（整份 AdminPages.jsx 的
// useSearchParams 用量是 0），造成三個具體問題——
//   1. 篩選後的畫面無法分享，只能口頭描述「你自己點一下待審檢舉」
//   2. 瀏覽器 Back 不會回到前一組篩選，而是直接離開頁面
//   3. 從詳情頁返回列表時，先前的篩選與頁碼全部消失，要重設一次
//
// 只有「非預設值」才寫進網址，避免乾淨的初始狀態拖著一長串 ?page=1&q=&status=。

function readParams<T extends Record<string, string | number>>(
  searchParams: URLSearchParams,
  defaults: T,
): T {
  const result: Record<string, string | number> = {};
  for (const [key, fallback] of Object.entries(defaults)) {
    const raw = searchParams.get(key);
    if (raw === null) {
      result[key] = fallback;
    } else if (typeof fallback === "number") {
      const parsed = Number(raw);
      result[key] = Number.isFinite(parsed) ? parsed : fallback;
    } else {
      result[key] = raw;
    }
  }
  return result as T;
}

/**
 * `defaults` 同時是「預設值」與「這個列表認得哪些參數」的唯一宣告。
 *
 * 型別上把它綁成泛型，`params` 與 `setParam` 的 key 都只能是 defaults 裡有的鍵——
 * 這正是先前 `?user=` 靜默失效的成因：參數沒列進 defaults，hook 讀不到、
 * 列表不套用篩選，但畫面看起來完全正常。現在拼錯或漏加會是編譯錯誤。
 */
export function useListQuery<T extends Record<string, string | number>>(
  defaults: T,
): {
  params: T;
  setParam: <K extends keyof T>(key: K, value: T[K]) => void;
  setParams: (patch: Partial<T>) => void;
  resetFilters: () => void;
  hasFilters: boolean;
} {
  const [searchParams, setSearchParams] = useSearchParams();

  const params = useMemo(
    () => readParams(searchParams, defaults),
    // defaults 通常是模組層常數；用 JSON 比對避免呼叫端每次 render 傳新物件造成迴圈
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [searchParams, JSON.stringify(defaults)],
  );

  const setParams = useCallback((patch: Partial<T>) => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      for (const [key, value] of Object.entries(patch)) {
        const fallback = defaults[key as keyof T];
        // 與預設相同就從網址移除，網址只保留「使用者實際改過的東西」
        if (value === fallback || value === "" || value === null || value === undefined) {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
      }
      // 改動篩選條件時回到第一頁：留在第 5 頁常常直接落到空結果
      if (!("page" in patch) && Object.keys(patch).length > 0) {
        next.delete("page");
      }
      return next;
    }, { replace: true });   // 用 replace：篩選不該在 Back 堆疊裡留下一長串中間狀態
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setSearchParams, JSON.stringify(defaults)]);

  const setParam = useCallback(
    // 計算屬性名在 TS 會被推成 { [x: string]: T[K] }，與 Partial<T> 不重疊，
    // 因此先經 Partial<Record<keyof T, T[K]>> 再窄化，而不是粗暴轉 unknown
    <K extends keyof T>(key: K, value: T[K]) => {
      const patch = { [key]: value } as Partial<Record<keyof T, T[K]>>;
      setParams(patch as Partial<T>);
    },
    [setParams],
  );

  const resetFilters = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true });
  }, [setSearchParams]);

  const hasFilters = useMemo(
    () => Object.entries(params).some(
      ([key, value]) => key !== "page" && value !== defaults[key as keyof T],
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [params, JSON.stringify(defaults)],
  );

  return { params, setParam, setParams, resetFilters, hasFilters };
}

/**
 * 切換排序方向。同一欄位再點一次就反向；換欄位時預設降冪
 * （後台大多數欄位——金額、分數、問題數——使用者要看的是最大的那幾筆）。
 */
export function nextOrdering(current: string, field: string): string {
  if (current === `-${field}`) return field;
  if (current === field) return `-${field}`;
  return `-${field}`;
}
