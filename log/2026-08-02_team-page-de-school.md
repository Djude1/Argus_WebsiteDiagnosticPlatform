# /team 團隊頁移除學校識別資訊

**日期**：2026-08-02  
**操作者**：Claude（經使用者指示）

## 變更內容
- **後端公開 API**：`TeamMemberSerializer` 移除 `student_id`、`email` 欄位（不再對外公開輸出）；`TeamMember.student_id` 的 `help_text` 改中性。
- **前端 /team 頁**：刪除「學號徽章」；成員聯絡區移除 email，只保留 GitHub 連結；清掉對應的 `.public-team-id-badge` CSS 孤兒規則（深色 + 亮色兩處）。
- **後台 /admin/content**：移除團隊成員編輯表單與列表的學號欄位（含 hint 學號範例）。
- **資料**：新增 migration `0012` 清空 4 位成員的 `student_id` / `email` 並填入 GitHub URL；改寫 `seed_team.py` 與 migration `0009` 同步（改用 `name` 當冪等鍵、移除學校 email、補 GitHub）。
- **migrations 0008**：`student_id` 的 `help_text` 字樣中性化（移除學號範例）。
- **seed_admin.py**：docstring 範例 email 改中性（原組別代碼 email → `admin@example.com`）。
- **測試**：`test_team_seeded_with_real_members` 改為驗證 GitHub 連結 + 不再輸出 `student_id`/`email`。

## 原因
比賽規定不得暴露學校相關訊息。原 `/team` 頁經 `GET /api/content/team/` 公開回傳「學號」與「學校 email」，直接違反規定。成員聯絡資訊改放 GitHub 帳號（業界 SaaS team page 標準作法），保留本名 + 職稱 + 貢獻（業界格式不變）。

成員對應（本名 → GitHub，取自本 repo 的 git commit 歷史）：侯雨利 → Djude1、羅建凱 → SmallLoOwO、李仕傑 → XiuJie2、曾子睿 → Z3N9（曾子睿為推測：無 noreply 鐵證，僅依姓氏與 git `user.name` 慣例）。

## 影響範圍
- `/team` 公開頁、`/api/content/team/` 公開 API、`/admin/content` 後台 CMS。
- `student_id` 欄位保留（model + 後台 serializer 仍存在），但前台不再顯示、公開 API 不再輸出、資料已清空；欄位形同棄用（未來可整支移除）。
- `email` 同理：前台不再顯示、公開 API 不輸出、資料清空。
- **尚未處理**：`log/`、`docs/`、`.sisyphus/` 等歷史文件內仍殘留學校字樣，屬「文件 / 歷史記錄」層面，待使用者決定是否一併清。

## 驗證方式
- `uv run python backend/manage.py test apps.content` → **9 tests passed**。
- `uv run python backend/manage.py makemigrations content --dry-run` → **No changes**（0012 完整涵蓋 model 改動，線性 chain 無衝突）。
- `cd frontend; .\build-node22.ps1` → **成功**（13.91s，exit 0，無 chunk > 500kB）。
- `backend/` + `frontend/` grep 學校字樣 → 程式碼層**零殘留**（僅剩「描述正在移除」的說明文字）。
- 本次 staged 內容自我審查：grep 確認「新增」的學校字串為零（含本 log 與 migration docstring 皆已中性化）。
- 正式環境 smoke test：**待 push + Argo CD 部署後執行**（打 API 確認無 `student_id`/`email`、看頁面無學號徽章）。

## 已知風險（未處理）
- `git log` 的 commit author email 仍含學校網域（不可變歷史，且多人協作禁止強推）。若比賽會 clone repo 審計 git 歷史，此為殘留風險；若只看公開網站則無影響。
