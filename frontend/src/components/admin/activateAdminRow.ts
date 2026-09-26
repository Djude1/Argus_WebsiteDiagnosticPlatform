import type { KeyboardEvent } from "react";

/**
 * 讓 `role="link"` 的表格列可用鍵盤開啟（Enter／空白鍵）。
 * 原本定義在 AdminPages.jsx 內部；掃描頁拆出去後兩邊都要用，所以抽到這裡。
 */
export function activateAdminRow(event: KeyboardEvent, action: () => void) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    action();
  }
}
