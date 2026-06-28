# content 模組規則

Claude 操作 `backend/apps/content/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

## 職責
**公開 CMS 讀取 API**。Models：`ProjectFeature`、`TeamMember`、`ProjectMilestone`、`AppRelease`。

## 關鍵端點（`/api/content/`，公開唯讀 GET）
| 端點 | View | 對應前台 |
|---|---|---|
| `features/` | `features_list` | `/project` 特色卡片 |
| `team/` | `team_list` | `/team` 成員 |
| `releases/` | `releases_list` | `/download` 版本 |
| `milestones/` | `milestones_list` | `/project` timeline |

## 重點
- 本 app **只服務公開讀取**；**寫入 / 編輯走 `admin_api` 的 `cms_views`**（`/api/admin/cms/*`，需 `IsAdminUser`）。
- `TeamMemberSerializer` 公開輸出**包含 `email` / `github_url`**（團隊頁聯絡資訊，屬刻意公開的團隊自介）→ 確認成員只填**願意公開**的內容；勿把終端使用者個資放進來。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 在 content 加任何寫入 / 編輯端點 | 公開可寫＝內容被竄改 | 寫入一律走 `admin_api/cms`（`IsAdminUser`） |
| 把**終端使用者**個資（`User.email` 等）塞進公開 content 端點 | 個資外洩 | content 只服務團隊自介 / CMS 公開內容，不接觸 User 個資 |
