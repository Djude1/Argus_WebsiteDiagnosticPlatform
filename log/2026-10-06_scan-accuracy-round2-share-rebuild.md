# 掃描準確度第二輪、掃描頁分頁重排、頁面優化分享、GSC 共用授權

**日期**：2026-10-06  
**操作者**：Claude

## 變更內容

### 判定準確度（依使用者提供的 argus-scan-17 獨立審查，逐項評估後採用）
- AEO 答案蘊含（`aeo/questions.py` `anchors`、`aeo/answers.py` `entails`／`is_testimonial`）：段落要真的在談主題才算回答；心得／見證不當答案；沒有任何段落談主題就判 `missing`。實測 ntubimdbirc.tw：「申請資格」由「可回答」（引用學員心得）改為「無可用答案」。
- 標題標籤裡的整段內文（`aeo/content.py` `_is_body_text`）當段落處理：隱私權政策寫在 h3 的 Email 找得到了，消除資安「公開 Email」與 AEO「找不到 Email」的矛盾。
- WAF 措辭（`tasks._waf_blocked_nuclei_note`、`site_profile.py`）：Nuclei 0 項發現不再寫「已部署有效的入侵防護」；偵測到 CDN 只寫「無法從外部確認 WAF 規則」，掃描被 403／challenge 攔截才寫「確認防護規則已生效」。
- 嚴重度（`scanners.py`）：缺少 CSP 中→低；CSP frame-ancestors 視為具備防點擊劫持；沒有 H1 中→低、多個 H1 低→info；登入／註冊等帳號頁跳過 SEO／AEO／GEO；觸控目標描述區分 Argus 建議與 WCAG 2.2 AA（24×24）／AAA（44×44）；llms.txt 標明新興做法。
- SEO 根因合併（`seo/site_findings.py`）：www 未統一＋og:url／canonical／sitemap 指向另一主機 → 單一「主網址設定不一致」（`seo-primary-url-inconsistent`），症狀列在 evidence。
- 網站優勢（原「做得好的地方」）每項附 `evidence` 與 `confidence`（confirmed／likely）；載入時間改稱「載入時間在合理範圍」並註明是單次實驗室量測。
- 新增 `tech_stack.py`：被動辨識網站使用的技術（框架、CMS、分析、伺服器），寫進 `site_profile.technologies`（version 2）。
- 報告（`RENDERER_VERSION` 6）：摘要頁先列「建議先處理這 3 件事」；網站優勢附依據、推論標示；第 3、5 章不強制換頁；浮水印縮小；分數說明註明是 Argus 自訂模型。

### Search Console 共用授權（`seo_views.py`）
- 網域驗證頁連接過 Google，SEO 分析頁 `GET gsc/` 自動沿用同一授權建立專案連線，並自動選好唯一相符的資源。
- 中斷連線時，同一 refresh token 仍被其他連線使用就只刪本地、不撤銷 Google 授權。

### 掃描頁與頁面優化（前端）
- 掃描詳情上方分頁改為「報告／網站優勢／網站架構」；網站架構＝一句話流量路徑＋使用的技術＋IP 細節收合＋網站結構圖。報告分頁只留一行 CDN 提醒。
- 移除「修正產出」分頁（`FixOutputSection.jsx` 與其樣式刪除；後端 API 保留）。理由：產生的 JSON-LD／OG／llms.txt 片段與頁面優化重疊，頁面優化直接給整頁成品；舊網址 `/fixes` 轉回報告、`/topology` 轉到網站架構。
- 頁面優化（`PageRebuildPanel`）從掃描詳情移到專案側邊欄「頁面」分頁每列的「優化此頁」。
- 分享連結：`POST/DELETE /api/rebuilds/<id>/share/`、公開 `GET /api/share/rebuilds/<token>/`（＋`html/`）、前端 `/share/rebuilds/:token`（並排比較、修改清單、說明）。7 天有效、可停止；HTML 以 CSP sandbox（無 script、無表單）、只能被本站 iframe 內嵌（`Sec-Fetch-Dest: document` 回 403）。migration `rebuild/0006`。
- `apply_edits` 拒絕新增 script／事件屬性／iframe／form／base／javascript:／meta refresh 的修改（提示注入防線，產出可能被部署）。

### OpenCode agent
- 新增 `docs/opencode-agents/argus-rebuild.md`（優化後的 agent 定義與系統提示詞）；`prompts.py` 回覆格式改為「已修改／未處理／請人工確認」三段並加入安全底線，兩邊一致。

## 原因
使用者提供 ChatGPT 對 ntubimdbirc.tw 報告的獨立審查（不一定正確，自行判斷）；要求 GSC 不重複授權、掃描頁加網站優勢／網站架構分頁、評估修正產出、頁面優化移到「頁面」並可分享給 UI/UX 工程師，以及優化網頁優化 agent 的 prompt。

審查中評估後**未採用或延後**的項目：完整 Confidence 欄位與 Severity 多因子模型（改以逐條調整嚴重度＋優勢的可信度標示）、CrUX／GSC 效能資料整合、Coverage Map、逐項自動驗證規則、Evidence 補 redirect chain／selector／timestamp——屬較大的資料模型改動，留待後續。

## 影響範圍
- 既有掃描的 finding 不會自動改變；重新掃描後才套用新規則（`site_profile` version 2、新的 SEO 合併規則）。
- 報告快取因 `RENDERER_VERSION` 6 重新產生。
- 正式環境需套用 migration `rebuild/0006`（只新增欄位）；agent 主機需手動更新 `argus-rebuild.md` 並重啟 opencode。
- 前端 `/scans/:id/fixes`、`/topology` 舊連結會轉址。

## 驗證方式
- `uv run ruff check backend`：通過；`makemigrations --check`：無缺漏。
- 後端：`apps.scans`、`apps.rebuild` 全數通過（含新增 `tests_accuracy_review.py`、AEO GOLD_SITES 新案例（舊程式碼會失敗兩項）、GSC 共用授權、`RebuildShareTests`、`UnsafeEditTests`、`TechStackTests`）；全套 `manage.py test apps` 1469 項通過（skipped 1）。
- 前端：`npm run lint`（0 error）、`npm run typecheck`、`npm test`（213 passed）、`vite build` 通過。
- 本機瀏覽器（scan 45，ntubimdbirc.tw 真實 DOM）：三個分頁正常、舊網址轉址、390px 無水平捲動；「頁面」分頁優化此頁 → 建立分享連結 → 未登入瀏覽器開啟可看到原樣頁（套用原站 CSS）；直接開 HTML 網址回 403。
- 需在正式環境手動確認：GSC 共用授權（需真實 Google 帳號）、OpenCode 啟用後的優化與分享實際產出。
