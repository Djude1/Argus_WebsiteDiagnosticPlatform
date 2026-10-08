import { Link } from "react-router-dom";

import { formatDateTime } from "../../shared/formatters";

// 點數紀錄（購點頁）：錢包 API 的 recent_transactions（最新 20 筆，後端 CoinTransactionSerializer）。
// 掃描會先「預扣」頁數上限的點數，完成後依實際頁數「退款」差額，兩筆相減才是實際扣的點數；
// 每次掃描實際扣的點數另外列在歷史報告（scan.coins_charged）。
function CoinHistory({ transactions }) {
  return (
    <section className="panel coin-history" aria-labelledby="coin-history-title">
      <h2 id="coin-history-title" className="section-title">點數紀錄</h2>
      <p className="coin-estimate-hint">
        掃描建立時先預扣頁數上限的點數，完成後依實際檢查的頁數退回差額；失敗或取消全額退回。
      </p>
      {transactions?.length ? (
        <div className="coin-history-wrap">
          <table className="coin-history-table">
            <thead>
              <tr>
                <th scope="col">時間</th>
                <th scope="col">項目</th>
                <th scope="col">點數</th>
                <th scope="col">餘額</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{formatDateTime(tx.created_at)}</td>
                  <td>
                    {tx.kind_label}
                    {tx.scan_job && (
                      <>
                        {"　"}
                        <Link className="coin-history-link" to={`/scans/${tx.scan_job}`}>
                          {tx.scan_origin || `掃描 #${tx.scan_job}`}
                        </Link>
                      </>
                    )}
                  </td>
                  <td className={tx.amount < 0 ? "coin-history-debit" : "coin-history-credit"}>
                    {tx.amount > 0 ? `+${tx.amount.toLocaleString()}` : tx.amount.toLocaleString()}
                  </td>
                  <td>{tx.balance_after.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint-text">還沒有點數紀錄。</p>
      )}
    </section>
  );
}

export { CoinHistory };
