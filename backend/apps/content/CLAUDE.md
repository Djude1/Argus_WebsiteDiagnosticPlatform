# content 模組規則

Claude Code 進 `backend/apps/content/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

## 職責
**公開 CMS 讀取 API**，外加唯一的公開寫入端點：商業合作洽談表單。Models：`ProjectFeature`、`TeamMember`、`ProjectMilestone`、`AppRelease`、`PartnerInquiry`。

## 關鍵端點（`/api/content/`，公開唯讀 GET）
| 端點 | View | 對應前台 |
|---|---|---|
| `features/` | `features_list` | `/project` 特色卡片 |
| `team/` | `team_list` | 團隊成員（公開 `/team` 頁已於 2026-09-28 移除，目前前台無消費端） |
| `releases/` | `releases_list` | `/download` 版本 |
| `milestones/` | `milestones_list` | `/project` timeline |
| `partner-inquiries/`（**POST**） | `partner_inquiry_create` | `/partners` 洽談表單；`AllowAny`＋`partner_inquiry` throttle（預設 5/hour）＋誘餌欄位 `website`（有值仍回同樣成功訊息，但存成 `status=spam`「疑似垃圾訊息」而不丟棄——2026-09-28 真人送出後台看不到，推定是瀏覽器自動填入誘餌欄位被默默丟掉；前端誘餌欄位 name 改為 `argus_hp_field`、標籤不含「網站／公司」字眼） |

## 重點
- 本 app **只服務公開讀取**；**寫入 / 編輯走 `admin_api` 的 `cms_views`**（`/api/admin/cms/*`，需 `IsAdminUser`）。
- **唯一例外是 `partner-inquiries/`**：只「新增」一筆洽談（對方主動提供的商業聯絡資訊），不能讀取或修改任何資料；後台在 `/api/admin/cms/partner-inquiries/`（React 後台側欄「客戶 → 合作洽談」，路由 `/admin/partner-inquiries`）檢視，只能改 `status`／`admin_note` 與刪除，不能新增。
- `TeamMemberSerializer` 公開輸出**包含 `email` / `github_url`**（團隊頁聯絡資訊，屬刻意公開的團隊自介）→ 確認成員只填**願意公開**的內容；勿把終端使用者個資放進來。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 在 content 加任何寫入 / 編輯端點（`partner-inquiries/` 的只新增例外除外） | 公開可寫＝內容被竄改 | 寫入一律走 `admin_api/cms`（`IsAdminUser`） |
| 把**終端使用者**個資（`User.email` 等）塞進公開 content 端點 | 個資外洩 | content 只服務團隊自介 / CMS 公開內容，不接觸 User 個資 |
