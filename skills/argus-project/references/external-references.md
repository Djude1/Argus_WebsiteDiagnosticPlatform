# External References

## 參考專案

使用者提供下列專案作為可借鏡來源。需要實作相關功能時，可以查閱其架構與優點，但不要盲目複製程式碼；先確認授權、技術棧相容性與 Argus 需求。

- `https://github.com/yaojingang/GEOFlow`
- `https://github.com/rtk-ai/rtk`
- `https://github.com/D4Vinci/Scrapling`
- `https://github.com/chikodilee/aeo-site`
- `https://optimeyes-site.netlify.app/`
- `https://github.com/luka2chat/awesome-geo`

## 參考方向

- GEOFlow：已檢視 README。可借鏡多模型內容生成、任務佇列、素材/知識庫、RAG 切片、審核發布流程、SEO metadata、Open Graph、結構化資料、Docker Compose 部署與「內容必須可信，不製造資訊噪音」的產品原則。Argus 只取 workflow/scoring/report 思路，不搬 Laravel/PHP 技術棧。
- RTK：已檢視 README。可借鏡大型命令輸出壓縮、Codex/AGENTS.md 整合、token 節省流程；本專案已使用本機 `D:\RTK\bin\rtk.exe` 規則。
- Scrapling：已檢視 README。可借鏡 Scrapy-like spider API、concurrency/throttling、session、pause/resume、streaming results、blocked request detection、robots.txt compliance、development cache replay。Argus 仍以 Playwright Python async 為固定棧，不引入 Scrapling 取代。
- aeo-site：已檢視 GitHub 頁。可借鏡 AEO score、actionable recommendations、AI answer engine visibility、網站分析與簡潔 landing/product messaging。
- Optimeyes site：已檢視網站。可借鏡即時 URL 分析、AEO vs SEO 對比、20+ factors、AI summary visibility、feature voting、keyword tracking、competitor analysis、API integration 等產品化呈現。
- awesome-geo：已檢視 README。可借鏡 GEO resource taxonomy、research/tools/monitoring/case studies、GEO checklist、FAST framework、AI crawler robots rules、`llms.txt`、schema、brand mention/citation monitoring。
- RTK：用於壓縮大型命令輸出；本機位置為 `D:\RTK\bin\rtk.exe`。

## GEO 檢查清單

### 發布前檢查

- 內容是否提供獨特價值。
- 是否包含可驗證的事實和數據。
- 是否有清晰的結構和標題層次。
- 是否實施適當的 Schema 標記。
- 作者資訊是否完整且可信。
- 是否引用權威來源。
- 內容是否回答使用者核心問題。
- 是否包含易於引用的段落。

### 技術檢查

- 頁面載入速度是否優化。
- 行動端體驗是否良好。
- `robots.txt` 是否允許 AI 爬蟲。
- `llms.txt` 是否配置準確網站資訊。
- 結構化資料是否正確實施。
- 網站是否使用 HTTPS。
- 是否啟用服務端渲染，方便 AI 爬蟲存取。

### 發布後監測

- 是否設定 AI 引用監測。
- 是否追蹤品牌提及。
- 是否定期更新內容。
- 是否分析 AI 引用準確性。

## RTK 使用摘要

- PowerShell 呼叫：`& "D:\RTK\bin\rtk.exe" <subcommand> <args>`
- 預期輸出超過約 50 行且屬 git/test/build/docker/log/curl 大 JSON 時使用。
- 檔案搜尋與讀取仍優先用 `rg`、`Get-Content` 或 Codex 內建工具，不用 RTK 的 Unix proxy 子命令。

## 採納矩陣

可採納技術、延後技術與明確不採納項，見 `skills/argus-project/references/technology-adoption.md`。
