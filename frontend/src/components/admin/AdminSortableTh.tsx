import type { ReactNode } from "react";

import { nextOrdering } from "../../shared/useListQuery";

// 可排序的表頭儲存格。
//
// 排序由後端 `ordering` 參數完成（見 apps/admin_api/views.py::_apply_ordering）。
// 刻意不做前端排序：後台分頁是 server side，只排當頁 25 筆會讓人誤以為
// 看到的是全域最大的幾筆。
//
// 無障礙：用 aria-sort 宣告目前排序狀態，並以箭頭符號 + 文字說明雙重呈現，
// 不讓「哪一欄在排序」只靠顏色或視覺位置傳達。

type AdminSortableThProps = {
  /** 送給後端 `ordering` 的欄位名（不含 `-`） */
  field: string;
  /** 目前的 `ordering` 值，例如 `-created_at` */
  ordering: string;
  onChange: (ordering: string) => void;
  children: ReactNode;
  numeric?: boolean;
};

export function AdminSortableTh({
  field,
  ordering,
  onChange,
  children,
  numeric = false,
}: AdminSortableThProps) {
  const active = ordering === field || ordering === `-${field}`;
  const descending = ordering === `-${field}`;
  const ariaSort = !active ? "none" : (descending ? "descending" : "ascending");

  return (
    <th className={`${numeric ? "num" : ""} admin-th-sortable`} aria-sort={ariaSort}>
      <button
        type="button"
        className={`admin-sort-btn ${active ? "is-active" : ""}`}
        onClick={() => onChange(nextOrdering(ordering, field))}
      >
        <span>{children}</span>
        <span className="admin-sort-arrow" aria-hidden="true">
          {active ? (descending ? "↓" : "↑") : "↕"}
        </span>
        <span className="sr-only">
          {active
            ? `目前依此欄${descending ? "降冪" : "升冪"}排序，點擊切換`
            : "點擊依此欄排序"}
        </span>
      </button>
    </th>
  );
}
