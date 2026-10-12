# 系統手冊第 14 章補上開源專案與學術論文（14-2、14-3）

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
- 新增 `專題文件生成/系統手冊_參考資料補充.md`：接在 14-1 之後。
  - 14-2 開源專案與工具 [9]–[33]：25 個，每項註明 Argus 用它做什麼。三類：直接借鑑規則（geo-optimizer-skill、claude-seo）、掃描使用的工具與規則庫（Nuclei、nuclei-templates、Katana、ZAP、sqlmap、Retire.js、axe-core、MDN HTTP Observatory、Playwright）、Hermes-Agent 設計參考與調研對象。
  - 14-3 學術論文 [34]–[72]：39 篇，GEO（KDD 2024）與直接影響 Agent 設計的 6 篇在前（附用途），其餘依 arXiv 編號排列。
- 系統手冊 Word 修訂版同步加入（目錄新增 14-2、14-3；表 A-1 第 8 列頁碼改為 56、82～85、89～97，說明加上整理參考資料）。
- 依使用者要求刪除 14-1 原 [5]、[6]（Argus 系統手冊 v4、v8 內部版本），原 [7]–[10] 改為 [5]–[8]；正文引用同步改號（AHHA、GeoWeb、白皮書、GitHub repo），附錄二導言原本引用 [6] 的標註一併移除。
- `Word文件同步規則.md`、`專題文件生成/CLAUDE.md` 登記新的內容 md。

## 原因
使用者要求把開發時參考的開源專案（geo-optimizer-skill、claude-seo 等）與論文全部補進系統手冊參考資料。

## 影響範圍
- 只影響文件。來源：程式註解與 log 中「借鑑／移植自」的專案、`docs/research-dast-llm-pentest-2026.md`、`docs/research/2026-09-26-ai-pentest-agent-landscape.md` 與 log 引用的 arXiv 論文。
- 不列：研究文件已標明編號錯誤或查無的論文（2304.12697、2310.18323、2509.01961、2310.11491、PhantomCTF、AutoAttacker）；git 查不到的 repo（dark-warlord14/ReconAIzer）；只評估未採用的傳統工具（whatweb、ffuf、wapiti、Nikto）；一般框架與套件（Django 已在 [2]，其餘依賴不列）。

## 驗證方式
- 論文標題、作者、年份由 arXiv API 取得（38＋1 篇全部查得），未手打。
- 25 個 repo 以 `git ls-remote` 確認存在。
- docx 通過 OOXML 驗證；LibreOffice 轉 PDF 檢查 14-2、14-3 版面與目錄頁碼。
