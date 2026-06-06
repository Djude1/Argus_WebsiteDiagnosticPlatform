# 更正快速接手流程 ONBOARDING.md

**日期**：2026-06-02  
**操作者**：Claude（Cowork）

## 變更內容
更正 `ONBOARDING.md` 與實際程式碼不符的過時/矛盾敘述：

- **Jazzmin 已移除**：§0、§2.4、§2.5、§3、§4 多處仍稱 `/django-admin/` 為「Jazzmin 美化」、技術棧列 `django-jazzmin`、uv sync 註解列該套件。實際 W4 已 `uv remove`（pyproject/uv.lock 已無此套件），全部改為「Django 預設樣式」。
- **app 數 7 → 8**：§4 目錄樹、§5 表頭與內容皆漏 `apps.insights`。補上 insights 列與目錄樹條目。
- **insights API / 公開頁補齊**：新增 §7.8 三個公開端點（`/api/insights/speed-test|phishing-url|phishing-email`，皆 AllowAny、不扣 coin），§6.1 公開路由補 `/free-tools`（FreeToolsPage），landmine #20 TopNav return null 的公開頁清單補 `/free-tools`、`/reviews`。
- **測試數字統一**：原文同時出現 192 與 212（§0/§2.5/§10/§14），統一為實際測試方法數約 252，並標註以 `manage.py test apps` 實跑為準。
- **build 指令修正（最關鍵）**：§2.4/§2.5/§14/附錄C 的快速上手原本叫人 `npm.cmd run build`，違反 CLAUDE.md 禁止事項（本機 Node v24 + Rollup 4 在 Windows 會 `STATUS_STACK_BUFFER_OVERRUN` crash）。全部改為 `cd frontend ; .\build-node22.ps1 ; cd ..`，並在 §2.1 prerequisites 補 D:\node22 說明；run-all 串接改為 PowerShell 正確語法（無 `&&`）。

### CLAUDE.md（同次一併更正 + 根因規則）
- 修正相同的過時事實：「7 個 Django App」→ 8 並補 insights 列；後端 API 路由地圖補 `/api/insights/*` 與 `/api/content/milestones/`；前端路由地圖補 `/free-tools`；移除「Jazzmin 主題 / Jazzmin Django Admin」改為 Django 預設樣式；常用命令測試數 192 → 約 252。
- **新增「文件同步強制規則（Documentation Sync）」專節**（根因修復）：規則 A（改程式須同次同步文件，附「事實→文件對應表」）、規則 B（純文件改動動筆前須以 Grep/Read 對照程式碼驗證每條事實）、規則 C（完成後 grep 全檔殘留掃描 + 跨檔一致性），並列出須長期同步的接手文件清單。
- 原因補充：使用者指出此問題會發生，是因為撰寫專題 docx 需要精確的參數名稱／欄位名稱，文件若不精確會直接污染 docx。

### ONBOARDING §7 參數層級核對（逐一對照 serializer / view）
為支援後續 docx 撰寫，將 §7 各端點補上實際 request 參數，並修正/補齊漏列端點（全部對照程式碼）：
- **§7.1 認證**：移除已不存在的 `dev-login/`（`accounts/tests.py::test_dev_login_route_is_removed` 斷言 404），補真實端點 `register/`、`email-login/`、`me/`（GET/PATCH）、`change-password/` 與各自 body。連帶修正 §4 目錄樹、§5 accounts 一段話、§6.1 `/login`、§11 任務 #3 的 dev-login 殘留敘述。
- **§7.2 掃描**：補漏列的 `POST /api/estimate/`；新增「`POST /api/scans/` body 參數表」（`ScanJobCreateSerializer` 8 欄位含預設與 active/第三方授權規則）。
- **§7.3 點數**：purchase body 補 `carrier_type`、`carrier_id`（W1 載具），改為完整參數表（含公司/個人發票必填條件、格式）。
- **§7.4 評論**：補 `sort` query、`mine` POST body（rating/comment）、messages multipart（body/image）。
- **§7.6 管理員**：每列補 query/path/body 參數；adjust-coin（delta/note）、reply（reply/rating）；**補漏列的整組 `announcements/*` 端點**（active/列表/建立/詳情）與 `AnnouncementSerializer` 欄位表。
- **§7.8 insights**：補三端點 body（speed-test 的 url+authorization_confirmed、phishing-url 的 url、phishing-email 的 raw_email）。
- 跨檔一致性：CLAUDE.md 後端 API 路由地圖同步修正 auth 列（移除不存在的 login/logout、補 register/email-login/me/change-password）、scans 補 estimate、admin 補 announcements/me。

### §8 資料模型欄位層級核對（對照各 models.py）
逐一對照實際 model 欄位與 TextChoices，修正 docx 來源：
- **CLAUDE.md 關鍵 Model 速查（實質錯誤）**：
  - `CoinTransaction`：欄位是 `kind` 不是 `type`，值為 monthly_bonus/purchase/scan_hold/scan_refund/admin_adjust（原寫 purchase/hold/settle/refund/bonus/manual 全錯）；FK 是 `scan_job`，另有 `balance_after`/`plan`/`admin_actor`。
  - `PlatformReview`：欄位是 `comment`（不是 `content`），有 `is_featured`；**無 images(JSON)、無 parent**；thread 在獨立 model `ReviewMessage`。
  - `AdminAuditLog`：欄位是 `admin_actor`/`payload`（不是 actor/`detail`），另有 `target_object_repr`；action 列舉 coin_adjust/review_reply/review_delete/user_toggle_staff/other。
  - 禁止事項表：補正交易由 `type=manual` 改為正確的 `kind=admin_adjust`。
- **ONBOARDING §8（補強，原列舉大致正確）**：model 清單補 `ProjectMilestone`、`Announcement`、`ReviewHelpful`/`ReviewMessageHelpful`；欄位速查補正 `PlatformReview.comment`、`ReviewMessage.image`(單一 ImageField)、`AdminAuditLog.payload`、`CoinTransaction` 完整欄位、`PurchaseOrder` 補 invoice_type/carrier_type/carrier_id。
- 已驗證：`ScanJob.progress` keys = pages_done/pages_total/phase/phase_started_at（tasks.py `_write_progress`）；reviews 確無 parent/images 欄位。

### 五份 MD 跨檔總體檢（規則 C）
對 `CLAUDE.md`、`ONBOARDING.md`、`frontend/CLAUDE.md`、`billing/CLAUDE.md`、`scans/CLAUDE.md` 做最後一致性掃描，再修出兩處子目錄檔殘留矛盾：
- **billing/CLAUDE.md**：services.py 函式一覽整段對照 `services.py` 修正——`grant_monthly_bonus`→`grant_monthly_bonus_if_needed`、`purchase_coins(user,plan,order)`→`purchase_plan(user,plan)`、`adjust_coin_manual(wallet,delta,note,actor)`→`admin_adjust(*,target_user,delta,admin_actor,note)`，並補回實際簽章（hold/settle/refund 皆 user+scan_job）、補 `get_or_create_wallet`/`estimate_scan_cost`；import 範例同步；「CoinTransaction.type 枚舉」整節改為 `kind`（monthly_bonus/purchase/scan_hold/scan_refund/admin_adjust，已確認 settle 退差與全退同用 scan_refund）。
- **App.jsx 行號**：實際 6549 行、`<Routes>` 在 6462。CLAUDE.md／ONBOARDING／frontend CLAUDE.md 的「4500+ 行 / 約第 5380 行」全部更新為「6500+ 行 / 約第 6460 行」。
- **CLAUDE.md 職責表 accounts**：殘留「dev-login 後門」改為「Email 註冊/登入、改密碼（dev-login 已移除）」。
- 掃描結果：app 數五檔一致為 8（僅事故描述句保留「7 個」字樣）；無 type/hold/settle/bonus/manual/content/images/parent/detail 等舊枚舉殘留；無 4500/5380 殘留；無不當 jazzmin/npm run build 指示（ONBOARDING §10 變更紀錄「Jazzmin 美化（後 W4 砍掉）」為正確歷史紀錄，保留）。狀態機與 progress 格式三檔一致。

## 原因
使用者要求先掃描與更正快速接手流程，後續將據此撰寫專題文件，要求零錯誤。過時的接手文件會讓新接手者（人或 Claude）依錯誤指令操作（尤其 build crash）並寫出與實況不符的專題文件。

## 影響範圍
- 僅改文件 `ONBOARDING.md`，不動程式碼，無功能性副作用。
- 與 CLAUDE.md 仍有平行待修項：CLAUDE.md「7 個 Django App」「後端 API 路由地圖」未含 insights、`/api/content/milestones`，建議下一步一併更正以保持跨檔一致（本次未動 CLAUDE.md）。

## 驗證方式
- 以程式碼核對事實：`settings.py` INSTALLED_APPS 含 8 app、`config/urls.py` 含 `api/insights/`、`insights/urls.py` 3 端點皆 AllowAny、`content/urls.py` 含 milestones、`frontend/build-node22.ps1` 存在、`App.jsx` 含 `/free-tools` 路由、pyproject/uv.lock 已無 jazzmin。
- 測試方法數：各 app `def test_` 加總 = 252（accounts11/scans120/agent20/billing35/reviews19/admin_api34/content7/insights6）。本環境無 `.env` 且沙箱未裝 Django，未能實跑完整套件，數字以方法計數為準。
- 最終 grep 掃描 ONBOARDING.md：無殘留 192/212、無「7 個 app」、無不當 `npm run build` 指示。
