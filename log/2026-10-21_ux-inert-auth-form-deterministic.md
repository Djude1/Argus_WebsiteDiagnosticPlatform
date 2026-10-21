# 2026-10-21 確定性補位：登入／註冊表單疑似未接上功能（ux-auth-form-inert）

## 背景（使用者回報 186F 報告）

最新一次掃描（ARGUS-20261021-186F，ntubimdbirc.tw）有勾 AI Agent、AI UX 測試也確實有跑
（報告出現 `AGENT_UX_2829E22DD5`、`AGENT_UX_91B71F1B3C` 兩筆 agent UX 發現），但這一輪
agent 把步數花在 footer→`/service/*` 的 404 連結上，**沒有走到 `/management/login` 去實際操作
表單**，所以 1D47 那次出現過的「後台登入頁完全無功能（輸入框打不了字、按鈕沒反應、密碼明文）」
UX 問題這次沒進報告。

診斷：UX agent 由首頁單一起點（`_pick_starting_page`）開始、LLM 驅動、步數／token 有上限，
每次探索路徑不固定，高價值但位置固定的壞頁不一定每次都被走到。密碼明文那半已由確定性規則
`form-password-unmasked`（資安）穩定抓到；但「輸入框無綁定、按鈕無提交路徑」這半只有互動式
agent 能測，這次漏了。

使用者選擇方案 B：加一條**確定性靜態 UX 檢查**補這類「死表單」訊號。

## 修改

`backend/apps/scans/scanners.py`：新增 `_ux_inert_auth_form(page_input)`，掛進 `analyze_ux`。

判定（渲染後 DOM、純解析零請求；`_AuthFormParser`）。只有**多個「未完成」結構訊號同時成立**
才報，避免誤判正常 SPA 表單：

1. 是登入／註冊頁：網址路徑（`_AUTH_URL_RE`）或按鈕／submit 文字（`_AUTH_INTENT_RE`，
   涵蓋 登入／註冊／sign in／sign up／login／register…）。
2. ≥2 個可輸入欄位，且有一個像密碼的欄位（沿用 `security.form_scanner` 的 `_NAME_RE`／
   `_LABEL_RE`／`_NOT_PASSWORD_RE` 字庫，lazy import 避免循環匯入）。
3. 這些可輸入欄位**完全沒有** name／id／autocomplete——接不上狀態或密碼管理員，是未接線
   佔位頁的特徵（正常表單至少會有其一）。
4. 頁面**沒有任何 `<form>`**——無原生提交路徑、100% 依賴 JS；有 `<form>` 時 Enter／submit
   至少能原生送出（即使只是導回同頁），不列入，正常以 `<form onSubmit>` 實作的 SPA 也因此排除。

→ `ux-auth-form-inert`（LOW、category=ux、impact_area=usability、priority_score=48）。

### 刻意的限制（已在描述與文件標明）

onClick／onChange 等事件處理**不會序列化進 HTML**，無法只憑 HTML 100% 斷定「死按鈕」。
因此這條只做高機率的結構訊號補位：一律低風險、描述明寫「請以互動測試為準」。要「高風險／
blocking」等級的斷定仍只能靠互動式 AI UX agent（方案 A）。

與 `form-password-unmasked`（資安、看密碼明文）角度不同、各自獨立；此為 UX 類，不進
`security/cross_layer` 去重。

## 驗證

- `uv run ruff check backend/apps/scans/scanners.py backend/apps/scans/tests_ux_signals.py` → All checks passed
- `uv run python backend/manage.py test apps.scans apps.agent` → 1691 passed（skipped 13；EPSS／OSV
  連線警告為測試無外網所致，與本次無關）
- 新增測試 `apps/scans/tests_ux_signals.py::InertAuthFormTests`：
  - 未完成佔位登入頁（無 `<form>`、欄位只有 class、密碼欄 `type=text`、按鈕無 type）→ 報一筆 LOW。
  - 正常 SPA 表單（欄位有 name／autocomplete）→ 不報。
  - 有 `<form action>` 原生提交路徑 → 不報。
  - 非登入頁（搜尋框、無密碼欄）→ 不報。
  - 只有單一欄位 → 不報。

## 文件同步

- `backend/apps/scans/CLAUDE.md` UX 來源清單：新增 `_ux_inert_auth_form` 條。
- `docs/scan-stage-checks.md` UX 檢查表：新增一列。
- `RULESET_VERSION` 已是 `2026.10.21`（同日新增規則，版本一致，無需再動）。
