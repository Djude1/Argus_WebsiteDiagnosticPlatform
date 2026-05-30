# Argus 26 項修正設計規格

**日期**：2026-05-26  
**作者**：Claude + SmallLoOwO  
**狀態**：已確認，待實作

---

## 範疇總覽

共 26 項問題，分 6 個執行 Phase，依優先順序排列如下：

| Phase | 主題 | Issues | 預估量 |
|---|---|---|---|
| 1 | 路由、登入與資安 | #1, 2, 6, 16 | 中 |
| 2 | 公開頁面改善 | #3, 4, 5, 10 | 低 |
| 3 | 掃描與計費修正 | #7, 8, 9, 14 | 中高 |
| 4 | Reviews、Settings 改善 | #11, 12, 13, 15 | 低中 |
| 5 | 後台大改造 | #17~24 | 高 |
| 6 | 公告系統 | #25, 26 | 中 |

建議執行順序：**1 → 3 → 6 → 2 → 4 → 5**（核心功能先、法規合規次之、視覺優化最後）

---

## Phase 1：路由、登入與資安

### Issue #1 首頁路由修正

**問題**：`http://argus6.qzz.io/` 無法正確開啟（ALLOWED_HOSTS 未含外部域名）。

**修正**：
- `backend/config/settings.py`：`ALLOWED_HOSTS` 加入 `argus6.qzz.io`
- 確認根路由 `/`（`App.jsx` 末尾）未登入時導向 `/project`，已登入時導向 `/dashboard`

### Issue #2 登入頁改造

**問題**：只有 Google OAuth，缺一般帳號登入、註冊、忘記密碼。

**後端**（`backend/apps/accounts/`）：
- 新增 `POST /api/auth/register/`：接收 `email + password`，建立 `User`，回傳 token
- 新增 `POST /api/auth/login/`（email/password 版本）：驗證後回傳 access token
- 「忘記密碼」暫不寄信（無 SMTP），端點 `POST /api/auth/password-reset/` 先回傳固定提示「請聯絡管理員」（待後續接入 SMTP 再啟用）

**前端**（`LoginPage`）：
- 切換成 3 個 tab 或分段顯示：
  1. **Google 登入**（保留現有 GoogleLogin 元件）
  2. **Email 登入**（email + password 表單）
  3. **新帳號**（email + password + 確認密碼）
- 「忘記密碼？」連結點擊後顯示提示文字，不跳頁
- 「跳過登入」dev-login 按鈕保留（僅 DEBUG=true 顯示）

### Issue #6 登入後跳 /dashboard

**修正**：`LoginPage` 登入成功後 `navigate(next || "/dashboard")`（next 若為 `/login` 則改為 `/dashboard`）。

### Issue #16 移除後台入口按鈕 + 資安

**修正**：
- 移除前台所有 DOM 中指向 `/admin` 的按鈕（含 `admin-entry-chip`、sidebar footer 的管理後台連結）
- 新增 `backend/config/robots.txt`（Django `TemplateView` serve）：
  ```
  User-agent: *
  Disallow: /admin/
  Disallow: /django-admin/
  ```
- Admin layout 頁面的 `<head>` 加 `<meta name="robots" content="noindex, nofollow">`

---

## Phase 2：公開頁面改善

### Issue #3 Team 頁後台入口

**說明**：後台 `/admin/content` 已有 TeamMember CRUD API（`cms_views.py`），前台 `/team` 已從 `/api/content/team/` 讀取。問題在後台 UI 不易使用，留待 Phase 5 改善。

### Issue #5 四位組員 seed 資料

**修正**：更新 seed migration（或新增 management command）寫入 4 位組員：

| 順序 | 名稱 | 角色 | 負責項目 |
|---|---|---|---|
| 0（組長） | 組長A | 全端整合 / 專題組長 | 專案規劃、系統整合、後端架構 |
| 1 | B同學 | 前端工程師 | React UI、樣式設計、PWA |
| 2 | C同學 | 後端 / 資料庫 | Django API、資料庫設計、Celery |
| 3 | D同學 | 網頁架設 / 資料處理 | 伺服器部署、Playwright 爬蟲、資料分析 |

skills、skill_levels、contributions 隨機寫入符合角色的內容；avatar_emoji 各給一個合適 emoji。

### Issue #4 Download PWA 卡片可用性

**修正**：
- `DownloadPage` 的 `public-release-card` 加醒目的安裝 CTA 按鈕
- 確認 `useInstallPrompt` hook 的 `prompt` 函式有連接到安裝按鈕的 `onClick`
- 若瀏覽器不支援 PWA 安裝（`promptEvent` 為 null），顯示說明文字而非空白按鈕
- 卡片加說明：「需使用 Chrome / Edge / Safari（行動版）才能安裝」

### Issue #10 Dashboard TopNav 修正

**修正**：
- 移除 `INNER_NAV_ITEMS`（或 `TOP_NAV_ITEMS`）中的「下載」entry（`{ to: "/download", ... }`）
- Brand Logo 元件加 `onClick={() => navigate("/project")}` 並加 `cursor: pointer`
- Nav items 最前面加「首頁」連結 `{ to: "/project", label: "首頁", emoji: "🏠" }`

---

## Phase 3：掃描與計費修正

### Issue #7 預掃描費用估算

**後端**：新增 `POST /api/scans/estimate/` 端點
- 接收 `{ url: string }`
- 用 `httpx` 非同步抓取目標首頁 + sitemap（`/sitemap.xml`、`/robots.txt` 的 Sitemap 指令）
- 計算連結數估算總頁數（上限 500 頁）
- 回傳 `{ estimated_pages: int, estimated_cost: int, confidence: "high"|"medium"|"low", method: "sitemap"|"crawl" }`
- 超時設定 8 秒，逾時回傳 `confidence: "low"` 的保守估算
- 此端點需登入（IsAuthenticated），但不扣點

**前端**：
- 建立掃描表單在 URL 輸入框旁加「估算費用」按鈕
- 點擊後 loading 狀態，完成後顯示估算卡片（頁數、花費點數、信心等級）
- 整站掃描模式下顯示；單頁掃描固定 1 頁不需估算

### Issue #8 移除最大頁數上限

**修正**：
- 掃描選項只有「單頁掃描」和「整站掃描」
- 移除 `maxPages` state、slider、輸入框
- 整站掃描：`max_pages` 固定傳 `500`（前端 hardcode，後端 `tasks.py` 同樣以 500 為上限）
- 單頁掃描：`max_pages=1, max_depth=1`

### Issue #9 發票邏輯修正

**問題**：「電子發票」和「載具」同時顯示造成混淆；缺少統編欄位說明。

**修正後 UI 邏輯**：

```
發票類型（radio）：
  ○ 個人電子發票
      └─ 雲端發票（預設，自動歸戶）
      └─ 手機條碼載具（輸入 /XXXXXXX）
      └─ 自然人憑證載具（輸入 AB12345678901234）
  ○ 公司統一發票
      └─ 公司名稱（必填）
      └─ 統一編號（必填）
```

- 「公司統一發票」選項顯示時，不再顯示載具輸入框
- 後端 `PurchaseOrder` model 確認有 `tax_id` 欄位（已有）

### Issue #14 Billing account-bar 位置

**修正**：
- 移除 `LoginPage` / `TopNav` 下方的 `<div className="account-bar">` 獨立懸浮列
- 帳戶餘額改整合到 `BillingPage` 頁面頂部 `<header>` 區塊（Step 1 方案選擇前顯示）
- 不再佔用全域 TopNav 下方空間

---

## Phase 4：Reviews、Settings 改善

### Issue #11 Reviews 官方標籤問題

**問題**：`ReviewMessage` 的 `is_admin` 計算方式可能把一般用戶的回覆也標為「Argus 官方」。

**修正**：
- 後端 `ReviewMessageSerializer`：`is_admin` 欄位改為 `message.author.is_staff`（`is_staff=True` 才是官方）
- 前端：`msg.is_admin` 為 true 才顯示「Argus 官方」badge，並用 `🛡️` 頭像；一般用戶用真實名稱首字

### Issue #12 Reviews 圖片 lightbox

**確認**：`ReviewMessageCard` 已有 `onImageClick` prop，`LightboxModal` 已實作。

**修正**（若有 bug）：
- 確認 `<img ... onClick={() => onImageClick(msg.image_url)}>` 已掛上
- 確認 `onImageClick` 從 `ReviewCard` → `ReviewsPage` 的 `useState` 正確傳遞
- 縮圖加 `cursor: pointer` 與 hover 效果，讓可點擊性更明顯

### Issue #13 Reviews 資料庫確認

**說明**：`PlatformReview` + `ReviewMessage` model 已存在，API 已實作。此項確認現有資料是否有正確寫入（跑一次 smoke test）。

### Issue #15 Settings 頁重設計

**移除**：累計掃描、findings 統計、技術棧、版本、資料夾位置等開發者資訊。

**新增**：
- **個人資料區**：顯示 email、名稱（可編輯）、頭像 emoji（可選）
- **登入方式**：顯示 Google 連結帳號或 Email 帳號；Google 用戶顯示「透過 Google 管理密碼」
- **更改密碼**（僅 email 帳號）：舊密碼 → 新密碼 → 確認
- **帳號刪除**：危險區，二次確認 modal

後端：新增 `PATCH /api/auth/me/` 端點（更新 display_name、avatar_emoji）。

---

## Phase 5：後台大改造

### Issue #17 確認唯一後台

`/admin` React 後台是主要後台；`/django-admin` 保留為 superuser 後門，前台不連結。此項無需改動，確認即可。

### Issue #18 Admin Overview 改 AI API Key 用量

**修正**：
- 移除「最近掃描」面板
- 新增「AI Provider 用量」面板：從 `agent/` app 的使用紀錄讀取（或從 `AdminAuditLog` type=agent 的記錄）
- 顯示：每個 provider 的 call 數量、token 用量（prompt/completion）、本月費用估算
- 若無資料，顯示「尚無 AI 使用紀錄」

### Issue #19 合併操作日誌

**修正**：
- `ADMIN_NAV_ITEMS` 移除 `transactions` 和 `scans` 獨立入口
- `/admin/audit-log`（改名為「操作日誌」）頁面新增 3 個子 Tab：
  - **操作紀錄**（原 AdminAuditLog 列表）
  - **交易紀錄**（原 /admin/transactions 內容）
  - **掃描紀錄**（原 /admin/scans 內容）
- Superuser 才看到「操作日誌」入口（現有行為保留）

### Issue #20 重命名操作紀錄 → 操作日誌

所有出現「操作紀錄」的 label、title、breadcrumb 全改為「操作日誌」。

### Issue #21 Admin Reviews 美化

**修正**：
- 改為卡片式布局（類似前台 ReviewCard 風格）
- 每張卡片顯示：評分星星、用戶名、內容摘要、精選標記、留言數
- 回覆按鈕改為明顯 CTA
- 頂部加摘要統計（總評論數、平均評分、待回覆數）

### Issue #22 Content 移除專案特色

**修正**：
- `/admin/content` 頁面移除「專案特色」Tab（移除 `FEATURE_SCHEMA` 定義和對應 UI）
- 前台 `/project` 目前從 `GET /api/content/features/` 讀取特色卡片；改為靜態 hardcode（直接在 `ProjectPage` 元件內定義陣列），移除 API 呼叫
- 後端 `ProjectFeature` model 和 API 端點保留（不刪除，避免 migration 衝突），但前台和後台均不再使用

### Issue #23 Content 團隊成員 + APP 版本改善

**TeamMember 後台改善**：
- `TeamMember` model 新增 `avatar_url = models.URLField(blank=True)` 欄位，搭配 migration；`avatar_emoji` 保留作備用
- 表單加大頭照圖片 URL 欄位（填入後前台優先顯示圖片，為空則 fallback 至 emoji）
- GitHub URL、Email 確認已有欄位且在表單可編輯
- 顯示改為卡片預覽（左邊是資料、右邊即時顯示小卡片預覽）

**AppRelease 後台改善**：
- 改為卡片式列表（顯示平台 badge、版本號、發布時間）
- 新增/編輯用側滑 Drawer panel（而非行內編輯）

### Issue #24 Plans 美化

**修正**：
- 定價方案管理改為視覺卡片（類似前台 `billing-plan-card` 樣式）
- 卡片顯示：方案名稱、價格、coin 數量、rate、badge、啟用狀態
- 新增/編輯用 Modal（有即時預覽）

---

## Phase 6：公告系統

### Issue #25 公告系統（後端 + 前端）

**後端**：新增 `Announcement` model（放在 `admin_api` app）

```python
class Announcement(models.Model):
    class Type(models.TextChoices):
        PERMANENT = "permanent", "常駐公告"
        TEMPORARY = "temporary", "臨時公告"

    title = models.CharField(max_length=128)
    content = models.TextField()
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.TEMPORARY)
    active_days = models.PositiveSmallIntegerField(
        default=7, help_text="臨時公告顯示天數（常駐公告忽略此欄位）"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_currently_active(self):
        if not self.is_active:
            return False
        if self.type == self.Type.PERMANENT:
            return True
        from django.utils import timezone
        return (timezone.now() - self.created_at).days < self.active_days
```

- 新增 `GET /api/announcements/active/`：回傳目前有效的公告列表（需登入）
- 後台 CRUD：`/admin` 新增「公告管理」Tab

**前端**：
- `/dashboard` useEffect 呼叫 `GET /api/announcements/active/`
- 以 Modal 逐則顯示（若有多則，加「下一則」按鈕）
- 常駐公告：每次登入後都顯示（除非用戶點「確認」，寫 `localStorage.setItem("announcement_confirmed_<id>", Date.now())`，24 小時內不再顯示）
- 臨時公告：「不再顯示」寫 `localStorage.setItem("announcement_dismissed_<id>", "1")`，永不再顯示
- Modal 有「確認」和「不再顯示」（臨時公告才有）按鈕

### Issue #26 台灣法律公告

**seed 資料**（migration 或 management command）：

```python
Announcement.objects.get_or_create(
    title="⚠️ 重要法律聲明 — 授權掃描義務",
    defaults={
        "type": "permanent",
        "is_active": True,
        "content": (
            "依台灣《電腦處理個人資料保護法》、《刑法》第 358、359、360 條及相關法規，"
            "未經網站擁有者明確書面授權，對他人網站進行自動化掃描、爬取或滲透測試，"
            "可能構成非法入侵電腦罪，面臨刑事追訴。\n\n"
            "使用 Argus 時，您必須確認：\n"
            "1. 您是該網站的擁有者，或\n"
            "2. 您已取得網站擁有者的書面授權。\n\n"
            "Argus 對任何未授權掃描行為不承擔法律責任，"
            "因違法使用產生的一切後果由使用者自行承擔。"
        ),
    }
)
```

---

## 關鍵檔案影響範圍

| 檔案 | 影響的 Phase |
|---|---|
| `frontend/src/App.jsx` | 1, 2, 3, 4, 5, 6（所有 Phase） |
| `frontend/src/styles.css` | 2, 3, 4, 5 |
| `backend/config/settings.py` | 1 |
| `backend/apps/accounts/views.py` | 1, 4 |
| `backend/apps/scans/views.py` | 3 |
| `backend/apps/content/models.py` | 5 |
| `backend/apps/admin_api/models.py` | 5, 6 |
| `backend/apps/admin_api/views.py` | 5, 6 |
| `backend/apps/admin_api/cms_views.py` | 5 |
| `backend/apps/reviews/serializers.py` | 4 |
| `backend/apps/billing/models.py` | 3 |

---

## 不在本規格範疇的事項

- Email / SMTP 服務接入（忘記密碼完整功能）
- 真實頭像圖片上傳（僅 URL）
- 多語系 i18n
- 行動版完整 RWD（僅維持現有水準）
