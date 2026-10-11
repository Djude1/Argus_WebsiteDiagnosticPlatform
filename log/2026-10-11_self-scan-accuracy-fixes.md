# Argus 自掃報告的三項判定修正（Turnstile 誤判被阻擋、AI 解讀排序與幻覺、SRI 例外）

**日期**：2026-10-11  
**操作者**：Claude

## 變更內容
使用者用 Argus 掃 Argus 自己的網站（scan 162，報告 ARGUS-162-20261010-D35E），審查後挑三項修正：

1. **爬蟲：Turnstile 表單元件不再判定為被阻擋**（`crawler.classify_cf_challenge`）
   - 原本頁面只要出現 `cf-turnstile` 就判定為 Cloudflare 攔截頁；網站自己的登入、聯絡表單內嵌 Turnstile 時也有這個字串（`cf-turnstile-response` 欄位），Argus 的登入、商業合作等 3 頁因此被標成被阻擋、完全沒分析。
   - 改為：只有出現攔截頁專屬特徵（`challenge-running`、`cf-chl-bypass`、`/cdn-cgi/challenge-platform/h/`、`_cf_chl_opt` 等）才判定；Turnstile 元件（`CF_TURNSTILE_WIDGET_MARKERS`）只用來決定原因文字。
   - 這個誤判會影響所有在表單上用 Turnstile 的客戶網站。
2. **AI 解讀：未驗證的 Agent 觀察不排第一、刪除捏造的網域**（`ai_insight.py`）
   - 分組時標記 `unverified_ai`（`agent-*` 規則且沒有任何一筆 `evidence_json.tool_verified`）；提示詞在問題清單加「來源」，未驗證的寫「AI Agent 觀察，未經工具驗證」，要求不可排第一、列入時 why 寫明待確認。
   - `validate` 把只對應未驗證 AI 觀察的優先事項排到最後（實例：刻意公開的 `/api/content/scanner-info/` 被 AI 觀察判為洩漏，AI 解讀卻列為第一優先並建議加授權，照做會弄壞 `/scanner` 頁）。
   - 新增 `strip_unknown_hosts`：輸出提到掃描結果（受測網址、問題標題／說明／證據／頁面）沒出現過的網域時，刪掉那一句（只認常見頂級網域，`api.js` 這類檔名不算）；整體診斷刪光就算失敗、可重新產生。實例：報告只有 Turnstile 缺 SRI，AI 解讀卻寫成 Google Fonts。
   - 提示詞另要求「提到具體網址、網域、檔案或第三方服務必須是資料原文出現過的」。
3. **SRI：排除無法鎖雜湊的服務**（`security/sri_scanner._DYNAMIC_SCRIPT_HOSTS`）
   - 補上 `challenges.cloudflare.com`（Turnstile，官方說明不可鎖版本）、`fonts.googleapis.com`（CSS 依瀏覽器回不同內容）、`recaptcha.net`、`hcaptcha.com`。對它們建議 SRI 是做不到的事，加了反而會在更新後被瀏覽器擋掉。

`RULESET_VERSION` 2026.10.10.4 → 2026.10.11（被阻擋判定與 SRI 會改變找出的問題）。

## 原因
使用者請我評估 Argus 自掃報告的價值與需優化處；審查發現以上三項是掃描器本身的判定錯誤，修了每位客戶的報告都會更準。

## 影響範圍
- 有 Turnstile 表單的網站：之前被誤判跳過的頁面會納入分析（問題數、分數可能改變）；「掃描遭防護機制部分阻擋」提示不再因此出現。
- AI 解讀：只影響之後新產生的解讀；不改嚴重度、不影響分數。
- SRI：上述服務不再列為 SRI 缺失，資安分數可能略升。
- 評分版本不同的兩次掃描，前端照既有機制標「評分規則已更新」，不直接比較分數。
- 屬判定準確度修正，未新增對外功能，未動競賽需求書。

## 驗證方式
- 新增測試：`tests.py`（Turnstile 元件不算被阻擋、攔截頁仍判 Turnstile）、`tests_ai_insight.py`（未驗證 Agent 觀察排到最後、已驗證不動、捏造網域的句子被刪、`api.js` 不誤刪）、`tests_security_scanners.py`（Turnstile／Google Fonts／recaptcha.net／hCaptcha 不報）。
- `manage.py test apps.scans apps.agent`：1397 項通過（10 略過）；`ruff check backend` 通過。

## 待人工確認
- 部署後重新掃一次 argus.clouda.dpdns.org，確認登入、商業合作頁有被分析、不再出現「被防護機制部分阻擋」，並重新產生 AI 解讀檢查排序。

## 文件同步
- `backend/apps/scans/CLAUDE.md`（crawler 攔截頁判定、ai_insight 輸出把關）、`backend/apps/scans/security/CLAUDE.md`（SRI 例外）、`docs/scan-stage-checks.md`（被阻擋判斷、SRI 列、AI 解讀把關）。
