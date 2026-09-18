# 前端整合：網域驗證精靈頁＋掃描表單徽章＋Admin 三新功能

- **日期**：2026-09-19
- **操作者**：ZCode（subagent 實作，main 驗收）

## 變更內容

- 新檔 `frontend/src/features/domains/DomainVerifyPage.jsx`＋路由 `/domains`（RequireAuth＋lazyNamed 獨立 chunk）＋登入區導覽「網域驗證」入口：
  - 三步驟膠囊（①新增②設定③驗證）；新增網域後展開 instructions 卡——三種方法頁籤（DNS TXT 三欄位／meta 原始碼／驗證檔路徑＋網址＋內容）全部一鍵複製（clipboard＋execCommand fallback）
  - 我的網域清單：狀態徽章（待驗證/已驗證/已否決/已過期）＋人工核准標記＋方法 chip＋到期日與剩餘天數；方法選擇 segmented＋驗證按鈕（成功綠閃示／失敗顯示後端 last_error）；刪除確認對話框
- `ScanExperience.jsx` ScanJobForm：載入已驗證網域並以 hostname 比對（===或 endswith 子網域）顯示綠色「已驗證網域」徽章；主動模式且未驗證時警示區塊＋「前往網域驗證→」連結（未動授權勾選邏輯）
- Admin 後台：AdminUserDetailPage 新增「訂閱管理」（方案下拉＋期數 1-36 開通／取消確認對話框）與「登入記錄時間軸」（方法徽章＋IP＋時間，最近 50 筆）；新頁 `/admin/domains` AdminDomainsPage（搜尋＋狀態篩選＋分頁；每列備註輸入＋人工核准/否決確認對話框）；AdminIcons 新增 AdminDomainsIcon
- `api.js` 新增 9 個函式（domains CRUD/verify＋admin domains/override/login-events/subscription action/plans）
- `styles.css` ~470 行：`.domain-*` 全套（前台 fade-up stagger＋hover）、`.scan-verified-badge`/`.scan-domain-warning`、`.admin-sub-*`/`.admin-login-*`/`.admin-domain-*`（後台輕動效）；皆支援 prefers-reduced-motion
- `frontend/CLAUDE.md` 路由表與核心檔案表同步（規則 A）

## 原因

- 複賽評審問題 1 的 UI 呈現（「要讓評審知道我們做了什麼」）：網域驗證頁為 demo 主秀；問題 5 的 admin 登入記錄/訂閱管理/網域人工審核介面。

## 影響範圍

- 僅 frontend/**＋frontend/CLAUDE.md；後端無改動（API 已於 5dbec18/6ab4a7a 上線）。
- 已知限制：admin 使用者訂閱端點目前僅 POST，後台訂閱面板初始無法載入現況（隨後以獨立 commit 補 GET 端點）。

## 驗證方式

- `build-node22.ps1` 兩次全綠（✓ 6.78s/6.49s；DomainVerifyPage chunk 11.39 kB；最大 chunk 187.6 kB < 500 kB）
- 回應欄位名逐項對照 backend serializers 查證（is_effectively_verified/days_until_expiry/instructions 結構/409 格式）
- 已載入 argus-ui-design skill；新路由掛對 guard（/domains 要登入、/admin/domains 要 admin）
