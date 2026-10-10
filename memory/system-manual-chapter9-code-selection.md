# 系統手冊第 9 章程式碼選錄

## 核對範圍與版本

- 日期：2026-10-11；程式碼基準為遠端 `05378fd`。本次僅依程式碼核對使用者提供的第 9 章截圖並選取短片段，未改寫應用程式或線上 Word。
- 同步遠端時保留先前的第 3 章文件提交；該提交涉及的三份文件與遠端更新沒有重疊，重新套用後為 `f5340cf`。
- 程式碼摘錄應標示來源函式、用途及省略前後文；片段不是獨立可執行程式。保留元件表，將摘錄接在 9-2 相對應的說明後，避免刊載完整檔案。

## 六段選錄與依據

| 主題 | 程式來源 | 選錄內容與解釋邊界 |
|---|---|---|
| 掃描執行條件 | `backend/apps/scans/scan_plan.py::build_scan_execution_plan`，27–38 行（略去說明註解）及 40–49 行 | 單頁／全網站、主動模式與額外授權、UX 維度決定工具計畫；真正執行還有功能開關、網域資格及執行環境檢查。 |
| AEO 可回答性 | `backend/apps/scans/aeo/evaluate.py::_score`，154–157 行 | 題目權重乘上判定值；`answers.py::VERDICT_VALUE` 為可回答 1、資訊不足 0.5、衝突 0.25、無答案 0。輸入為經 `is_scored` 篩選後的題目，需至少三題才能評分。 |
| 整體評分 | `backend/apps/scans/scanners.py::calculate_scores`，2048–2057 行 | 分類分數由 `score_breakdown` 處理，再平均實際回傳的分類。`tasks.py::tested_categories_for` 提供已評估分類；不能因函式相容舊呼叫的預設值而宣稱每次都測完五維。 |
| 掃描預扣 | `backend/apps/billing/services.py::hold_for_scan`，227–231 行 | 選錄付費路徑的餘額再檢查及扣款。完整函式具 `transaction.atomic`、錢包 `select_for_update`，另處理免費試用及交易紀錄；節錄不可取代完整計費入口。 |
| 修正資料來源政策 | `backend/apps/scans/fixgen/policy.py::identity_field`，25–32 行 | 識別值有語料支持才標示 verified，否則填入 placeholder；verified 是程式來源政策判定，不代表第三方認證或事實真實性保證。 |
| MCP 共用掃描入口 | `backend/apps/mcp_access/tools.py::create_scan`，270–279 行 | 共用 `ScanJobCreateSerializer` 和 `enqueue_created_scan`；serializer 的建立流程呼叫 `hold_for_scan`。不要將這段描述成一套獨立的 MCP 扣點流程。 |

## 截圖內容需要修訂的事實

- `reviews`：新版公開 API／前端不再提供討論串、訊息點讚與圖片上傳。改述為已驗證評論、本人編修／刪除、官方回覆、有幫助與檢舉治理；舊資料模型仍保留相容用途。來源：`backend/apps/reviews/CLAUDE.md`、`urls.py`、`views.py`。
- `features/projects`：加入資安分頁；歷史分頁導向 scans，合併為「掃描與報告」。來源：`frontend/src/App.jsx`。
- `features/scans`：目前路由含報告、網站優勢、網站架構、效能及分數說明；舊 topology 轉到 architecture、舊 fixes 轉回報告。優化結果與分享頁位於 `features/optimize`，不宜繼續將優化工作區列在 `features/scans`。
- 修正產出：後端 fixgen 仍在，但前端修正產出分頁已移除。選錄這段應定位為後端既有來源政策，不能描述成目前可由報告分頁操作的功能。
- AEO：`is_scored` 排除 verdict 為 MISSING、source 為 intent、answer_type 不是 PHONE／EMAIL／ADDRESS／HOURS 的題目；篩選後不足三題也未充分評估。原文僅寫正文與最初題數門檻不夠完整。
- 評分：最新 `SCORE_DECAY_CONSTANT=100.0`；同分類規則去重、info 零扣分、不列優先改善、AEO 題目分已含於基準分。指數衰減是本專案評分模型，不能描述為外部標準評分。
- API 表中的 `/api/pages/` 與 `/api/findings/` 可保留：`config/urls.py` 將 `apps.scans.urls` 掛於 `/api/`，不是 `/api/scans/`；應由實際掛載點組合 router 路徑。
- Kali：Repo 的 K8s 設定為 disabled；沒有在本次連線驗證正式叢集，不延伸宣稱線上工具已啟用或實跑成功。

## 驗證及後續使用

- 已對照六段原始檔、計分呼叫端、MCP serializer 計費入口、前端路由、評論 API 及 K8s 設定。
- 已檢查來源檔語法與摘錄語法、行號範圍、MEMORY.md 引用、Markdown 空白及本次差異；未執行掃描、應用測試或前端建置。
- 手冊摘錄可沿用上述選錄；重新選錄前應再次核對版本，避免行號或前端入口隨改版漂移。線上 Word 須由使用者貼入及確認排版。

## Word 交付

- 依後續要求建立 [程式碼選錄 Word](../專題文件生成/系統手冊第9章_程式碼選錄.docx)，內容來源為 [對應內容 Markdown](../專題文件生成/系統手冊第9章_程式碼選錄.md)。
- 文件包含六段可選取的原始碼文字、用途說明、來源函式及四列元件表修訂內容；沒有以圖片取代程式碼，也沒有改動使用者線上手冊。
- 檢查重新開啟 DOCX 後的六段文字與來源摘錄一致，表格共四列內容。移除預設 Title 樣式的裝飾底線。
- 標準套件 renderer 缺少可用 LibreOffice，改由 Word 唯讀匯出 PDF，再轉為 PNG；逐頁檢查最終三頁，中文、縮排及表格均正常。PDF 與 PNG 僅供排版核對，交付 DOCX。

## 原手冊第9章擷取與重排

- 使用者後續提供原手冊 ODT，要求只保留第9章，依「9-1 元件清單及其規格描述」及「9-2 其他附屬之各種元件」排序。產出 [第9章修訂版 Word](../專題文件生成/系統手冊_第9章_修訂版.docx)，來源為 [第9章修訂版內容](../專題文件生成/系統手冊_第9章_修訂版.md)。
- 擷取正文第9章標題至第10章之前，共25個原始頂層元素；移除其他章節與目錄，沿用原四張表格、Letter頁面、楷體正文14pt與標題樣式。
- 9-1保留後端／前端元件表，再加入9-1-1至9-1-6六段核心程式碼及規格說明；9-2保留API、診斷工具、評分統計及附屬修正／優化說明。這取代前次獨立選錄的章節安排建議。
- 本次遠端程式基準更新為 `ce8dea6`，重新套用三筆本機文件提交時沒有衝突。六段程式碼仍與最新版一致。
- 最新前端 `/scans/:scanId/topology` 已恢復獨立網站拓撲分頁；早先 `05378fd` 的「topology轉至architecture」紀錄僅適用該舊版本，不再作為目前路由描述。另補手動AI解讀及後端 `ai-insight` 入口。
- 已修正評論討論／圖片、專案歷史合併、優化模組、AEO有效題數及前端修正分頁移除等內容；Kali僅描述Repo設定停用，不推論正式叢集實際狀態。
- 使用ODT副本轉為Word，沒有改動上傳原檔。最終六頁逐頁檢查：程式碼與說明同頁、工具表完整、字型與原表格樣式正常，頁碼由1開始；六段程式碼及四張表格完整，作者中繼資料已清空。
