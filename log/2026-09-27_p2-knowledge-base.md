# P2：search_knowledge 離線知識庫（第 24 工具）

**日期**：2026-09-27
**操作者**：ZCode（GLM-5.3）

## 變更內容
- `backend/apps/agent/knowledge/*.md`（11 檔 45 段）：密碼重置答案推理、
  XSS 進階（CSP 繞過/儲存型/注入面擴展）、JWT 深攻（kid/jku/降級）、
  NoSQL $regex 盲注、商業邏輯（優惠碼規律/重放時序）、上傳深攻
  （polyglot/.htaccess）、SSRF 無 OOB 判定、目錄備份殘留、站內 OSINT
  交叉比對、CAPTCHA/OTP 缺陷、注入家族判定
- `backend/apps/agent/tools.py`：`search_knowledge(query)`（第 24 工具，
  **全域**——純本地無目標互動）；`_tokenize`（英文詞＋中文 2-gram）、
  `_load_knowledge`（## 段落切割＋模組快取）、`_search_knowledge`
  （tags×3＋標題×2＋內文評分，top 3）
- `backend/apps/agent/loop.py` system prompt：卡住/陌生漏洞類型先查知識庫
- 文件同步：架構文件（24 工具＋知識庫段）、agent CLAUDE.md

## 原因
使用者指示：給 agent「小型圖書館」自主閱讀（agent 無網路搜尋——23 工具
全目標互動型）。設計採離線版（Excalibur 2602.17622 檢索增強背書）；
網路搜尋裁定不做（黑箱抄 writeup＋目標資訊外洩搜尋引擎）。
泛化紅線：知識檔全為通用方法論（WSTG/PayloadsAllTheThings/jwt_tool
層級），零目標路徑/參數/答案。

## 影響範圍
- 所有 agent session（含 passive）多一個知識查詢工具
- 知識檔隨 app 打包（Dockerfile COPY backend 全拷）；內容為靜態資產

## 驗證方式
- 檢索品質：6 查詢（reset/jwt/優惠碼/upload/csp/ssrf）全中正確主題
- apps.agent 64 tests OK（新 4）；ruff 通過
- #40 輪 scoreboard diff 驗收（目標 30/112 迭代起點）
