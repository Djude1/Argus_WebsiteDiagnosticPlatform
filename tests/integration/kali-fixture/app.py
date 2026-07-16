"""⚠️ 警告：本檔案是刻意脆弱的測試靶機（ Argus Kali SQLmap 整合測試專用）。

禁止事項（在任何情況下都適用）：
  * 永遠不得部署到「整合測試用的臨時 kind workflow」以外的任何環境（包含本機、dev、
    staging、production、任何雲端叢集）。
  * 永遠不得與真實資料庫或任何 production 系統連線；本程式使用 sqlite3 在記憶體以外的
    /tmp 內建立一次性資料表。
  * 永遠不得放在公開 Ingress 後面——fixture.yaml 的 Service 一律走 ClusterIP +
    externalIPs=[93.184.216.34]。注意：93.184.216.34 是 example.com 真實可路由的
    公網 IP（IANA 文檔用，並非 RFC 5737 TEST-NET），故意挑它讓 runner 的「公網目標」
    檢查通過；真正的 containment 是 kube-proxy externalIPs interception 把 runner 對
    93.184.216.34:80 的流量攔截導向本 fixture Service，加上 runner NetworkPolicy 擋下
    任何其他公網 IP，因此流量永遠不會離開 CI kind 叢集。

為什麼要刻意脆弱：
  Argus 的 kali-runner image 會用 sqlmap 對本靶機發動授權範圍內的 SQL injection
  主動驗證，必須有「真的可被注入」的端點才能證明攻擊鏈正確運作。本程式只使用 stdlib
  （http.server + sqlite3），監聽 0.0.0.0:8080，並刻意把 query 參數字串插值進 SQL，
  讓 sqlmap 能確認注入點。除了這個整合測試以外，本檔案沒有任何授權用途。
"""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# 走 /tmp（容器內可寫、且容器銷毀後自動消失），避免與任何 host volume 衝突。
DB_PATH = "/tmp/argus-fixture.db"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8080


def init_db() -> None:
    """初始化一次性 sqlite 資料表；已存在則保留（冪等）。"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT)"
        )
        cur = conn.execute("SELECT COUNT(*) FROM products")
        if cur.fetchone()[0] == 0:
            # 放入固定示範資料，讓 ?q=phone / ?q=laptop 等查詢有結果。
            conn.executemany(
                "INSERT INTO products (name) VALUES (?)",
                [
                    ("phone",),
                    ("phone case",),
                    ("laptop",),
                    ("tablet",),
                    ("watch",),
                ],
            )
            conn.commit()
    finally:
        conn.close()


class FixtureHandler(BaseHTTPRequestHandler):
    """處理 GET /?q=<query>；刻意以 f-string 將 query 插值進 SQL（注入點）。"""

    def do_GET(self) -> None:  # noqa: N802 - http.server 要求此命名
        parsed = urlparse(self.path)
        query_values = parse_qs(parsed.query).get("q", [""])
        query = query_values[0] if query_values else ""

        # ⚠️ 刻意脆弱：將使用者輸入直接字串插值進 SQL——這是本靶機唯一的存在目的。
        # 與 brief Step 1 指定的脆弱形式完全相同，請勿改成參數化查詢。
        sql = f"SELECT id, name FROM products WHERE name LIKE '%{query}%'"

        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                rows = conn.execute(sql).fetchall()
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 - 靶機要讓 SQL 錯誤外顯以便 sqlmap 判讀
            payload = json.dumps({"error": str(exc), "query": query})
            self._respond(500, payload)
            return

        payload = json.dumps(
            {
                "query": query,
                "count": len(rows),
                "results": [{"id": row[0], "name": row[1]} for row in rows],
            }
        )
        self._respond(200, payload)

    def _respond(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args: object) -> None:  # noqa: D401, ARG002 - 靜默避免汙染 log
        return


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), FixtureHandler)
    # serve_forever 直到容器終止；本靶機沒有 graceful shutdown 需求。
    server.serve_forever()


if __name__ == "__main__":
    main()
