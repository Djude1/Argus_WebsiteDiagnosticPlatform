# WebSocket 安全測試

tags: websocket, ws, cswsh, cross site

## 發現
network log 找 ws://／wss:// 連線（升級請求 Upgrade: websocket）。
從 JS 原始碼找 new WebSocket(...).

## 通用測試面
- **認證檢查**：WS 連線是否驗 token/origin？無驗證＝任何人可連
- **CSWSH**（跨站 WebSocket 劫持）：WS 握手無 Origin 檢查——惡意頁面
  可用受害者憑證連線。判定：握手請求帶 cookie 但 server 不驗 Origin
- **訊息授權**：連上後發的訊息（subscribe/pull 類）是否驗權限——
  改 id 訂閱他人頻道＝IDOR
- **訊息注入**：JSON 訊息欄位塞 XSS/SQL/NoSQL 探測字串（server 端
  parser 同 REST 面）
- 敏感資料推送：訂閱後收到的訊息含他人資料/內部事件

## 判定
WS 面的缺陷與 REST 同級 report（未授權訂閱＝IDOR；CSWSH＝CSRF 類）。
