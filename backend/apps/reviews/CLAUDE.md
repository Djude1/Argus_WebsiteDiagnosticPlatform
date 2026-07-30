# reviews 模組規則

Claude 操作 `backend/apps/reviews/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

## 職責

平台評論採「一人一則、完成掃描才可發表」：公開頁只顯示可驗證使用體驗，評論本人可編修或刪除，其他登入使用者可標記有幫助或檢舉；管理員只能提供單一官方回覆與治理公開狀態，不得改寫評分或原文。

## Models

| Model | 重點 |
|---|---|
| `PlatformReview` | `OneToOne` user、rating 1-5、title/comment/show_partial_email、published/hidden、experience_at；`display_name` 僅保留舊資料相容；本人可編修或刪除 |
| `ReviewResponse` | 每則評論最多一則官方回覆；管理員可新增、更新或移除 |
| `ReviewRevision` | 儲存每次本人編修前的 rating/title/comment/show_partial_email 與舊版 display_name，只供內部稽核 |
| `ReviewReport` | 評論或官方回覆的檢舉原因與 pending/resolved/dismissed 治理狀態；兩種目標分開計數與結案 |
| `ReviewHelpful` | 每位使用者對每則評論最多一筆「有幫助」標記 |
| `ReviewResponseHelpful` | 每位使用者對每則官方回覆最多一筆按讚標記 |

`ReviewMessage` / `ReviewMessageHelpful` 只為舊資料與 migration 相容而保留；新版公開 API 與前端不再提供 thread、訊息點讚或圖片上傳。

## 關鍵端點（`/api/reviews/`）

- `GET ""`：公開列表，支援 `sort=helpful|newest`、`rating=1..5`、`page`。
- `GET summary/`：公開總數、平均分與星等分布。
- `GET/POST/PATCH/DELETE mine/`：資格查詢、建立、本人編修與刪除。
- `POST <id>/helpful/`：登入使用者切換「有幫助」，不可標記自己的評論。
- `POST <id>/report/`：登入使用者檢舉他人評論。
- `POST responses/<id>/helpful/`：登入使用者切換官方回覆的讚，不可替自己的官方回覆按讚。
- `POST responses/<id>/report/`：登入使用者檢舉他人的官方回覆。
- 管理員治理走 `admin_api`：`reviews/<id>/reply/` 與 `reviews/<id>/moderate/`。

## 公信力與隱私規則

- 建立評論必須有完成的 `ScanJob`；staff 帳號不得冒充一般使用者發表。
- 公開列表、統計及所有按讚／檢舉端點只納入 `status=published` 且 `experience_at` 不為空的評論。
- 使用者不得自填公開名稱；`show_partial_email=false` 顯示「匿名已驗證使用者」，勾選後才由後端從已登入帳號產生遮罩 Email，公開 API 不得輸出完整 Email。
- 使用者可修正 rating 與原文；每次 PATCH 前先建立 `ReviewRevision`。
- 管理員不得覆寫 rating、title、comment 或 show_partial_email，只能管理 `ReviewResponse` 與 published/hidden。
- 隱藏評論時只將該則使用者評論的待處理檢舉結案；官方回覆檢舉維持獨立計數與狀態，避免被父評論操作誤結案；治理操作寫 `review_moderate` audit。
- 列表、待回覆與檢舉數使用 DB annotation，禁止在 serializer 逐則查詢或用 Python loop 造成 N+1。
