// 後台共用分頁。原本定義在 AdminPages.jsx 內部，新頁面無法重用；抽出後
// 各列表頁共用同一個，行為與外觀不會再各自漂移。

type AdminPaginationProps = {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  /** 總筆數；有值才顯示「共 N 筆」 */
  total?: number;
};

export function AdminPagination({ page, totalPages, onChange, total }: AdminPaginationProps) {
  if (totalPages <= 1) {
    // 只有一頁時仍顯示總筆數：使用者需要知道「就這麼多」，而不是懷疑被截斷
    return total ? (
      <div className="admin-pagination is-single">
        <span className="admin-pagination-total">共 {total.toLocaleString("zh-Hant")} 筆</span>
      </div>
    ) : null;
  }
  return (
    <div className="admin-pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >← 上一頁</button>
      <span>
        {page} / {totalPages}
        {total ? <span className="admin-pagination-total"> · 共 {total.toLocaleString("zh-Hant")} 筆</span> : null}
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >下一頁 →</button>
    </div>
  );
}
