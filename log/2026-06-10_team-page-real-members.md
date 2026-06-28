# 團隊頁改用系統手冊真實組員 + 學號徽章與精緻排版

**日期**：2026-06-10
**操作者**：Claude

## 變更內容

依《Argus_系統手冊_v4.docx》表 4-2-2（工作內容與貢獻度表）、表 4-2-1（分工表）把
公開團隊頁 `/team` 的佔位資料換成真實 4 位組員（第115401組）。

**後端（content app）**
- `models.py`：`TeamMember` 新增 `student_id`（CharField, blank, 學號）。
- `migrations/0008_teammember_student_id.py`：makemigrations 自動產生的 schema migration。
- `migrations/0009_seed_real_team.py`：新增 data migration。先清除兩套佔位成員
  （職稱名「後端工程師/前端工程師/AI / Agent/DevOps / QA」＋舊 seed「組長A/B同學/C同學/D同學」），
  再以 `student_id` 為冪等鍵建立 4 位真實組員（侯雨利/羅建凱/李仕傑/曾子睿）。reverse 為 noop（不誤刪）。
- `management/commands/seed_team.py`：`TEAM_DATA` 改寫成同一份真實資料、改以 `student_id` 為鍵並清佔位，
  消除「migration 種子」與「seed_team 種子」名字不一致的舊 bug。
- `serializers.py`（公開讀）與 `admin_api/cms_views.py`（後台寫）：兩個 serializer 都加入 `student_id`。
- `admin.py`：`TeamMemberAdmin` 的 `list_display` / `search_fields` 加入 `student_id`。
- `tests.py`：新增 `test_team_seeded_with_real_members`（真實組員存在、佔位不殘留、學號正確回傳）。

**前端（App.jsx / styles.css，需經 build 生效）**
- `TeamMemberCard`：角色下方新增 `.public-team-id-badge`（顯示「學號 …」）。
- `TEAM_SCHEMA`：後台 `/admin/content` 團隊表單與列表加入 `student_id` 欄位（staff 可編輯）。
- `styles.css`：新增 `.public-team-id-badge`（等寬玻璃膠囊）、`.public-team-card-pro::before`
  （頂部漸層飾條、hover 點亮）、以及 badge 的 light theme 對應。**只新增、未改動既有共用樣式**。

組員內容對映（皆依手冊）：bio 取自表 4-2-2 工作內容；contributions 取自表 4-2-1 的 ● 主責項目；
email 用 NTUB 校信箱格式 `學號@ntub.edu.tw`（組長 11246034 為已知，其餘 3 人依格式推得、可後台改）；
github_url 留空（手冊無資料，待提供）。貢獻度百分比依使用者決定不公開顯示。

## 原因

使用者要求「依系統手冊做網站的組員部分」並檢查網站是否有做錯的地方。
審查發現團隊頁對外展示的是佔位假資料（職稱當人名），且有兩套互相打架的種子資料
（migrate 後再跑 seed_team 會產生 8 筆髒資料）。這對一份對外公開、且為評分用的學校專題是嚴重問題。

## 影響範圍

- 公開頁 `/team`、後台 `/admin/content` 團隊分頁、Django admin TeamMember。
- 團隊資料是執行期由 `/api/content/team/` 提供 → **資料修正（migration/seed）一套用就生效，前端免 rebuild**；
  本次的卡片版面（徽章/飾條）屬前端改動，**需重建前端**才會出現。
- 使用者明示「網站既有技術數字保持原樣、不必與手冊一致」→ 未動 hero 統計（8 apps / 249+ 測試）等。

## 驗證方式

- `uv run python backend/manage.py makemigrations --check --dry-run` → No changes detected（model 與 migration 一致）。
- `uv run python backend/manage.py test apps.content -v 2` → 8 tests OK（含新測試）。
- `uv run python backend/manage.py test apps.admin_api` → 34 tests OK（CMS 寫入 serializer 無回歸）。
- 前端因本機無 node22/node_modules **無法 build 驗證** → 需在部署機 build（見下）並肉眼確認。

## 尚未生效，待部署機執行（線上目前仍是舊佔位資料）

```powershell
# 部署機（有 Docker）：重建前端 + 套用 migration
docker compose up -d --build         # frontend 用 node:20-alpine 在容器內 build，不需本機 node22
docker compose exec web python manage.py migrate   # 套用 content 0008/0009 → 寫入真實組員
# （或既有資料想重跑）docker compose exec web python manage.py seed_team
```

**需使用者肉眼驗證（Ctrl+Shift+R）**：
1. `/team` 顯示侯雨利/羅建凱/李仕傑/曾子睿 4 人、各自學號徽章、技能條與負責項目。
2. 不再出現「後端工程師/前端工程師/AI / Agent/DevOps / QA」或「組長A」等佔位。
3. 後台 `/admin/content` → 團隊成員，可看到/編輯「學號」欄位。
4. email/GitHub 若要調整，於後台 CMS 修改（GitHub 目前留空）。
