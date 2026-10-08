# 複賽修補 W4 收尾：全套驗證＋文件數字統一

- **日期**：2026-09-19
- **操作者**：ZCode（main session）

## 變更內容

- `AGENTS.md`：後端測試數「約 252 項」→「約 1020 項（以實跑為準）」（過時數字）
- `專題文件生成/需求書_複賽版完整內容.md`＋`需求書_複賽版_修訂提示詞包.md`：測試數 940→1020 統一（5 處）
- `專題文件生成/初賽與複賽差異對照.md`：「本波進行中」改「本波已完成」總表（含各功能對應 commit）；更新記錄補齊
- 前一 commit（ca54906）已含 ONBOARDING.md 全面同步與提示詞包事實註記收尾

## 原因

- W4 收尾：規則 A/C——測試數字跨檔一致、無殘留舊事實；差異對照反映全部完成。

## 影響範圍

- 純文件；本 commit 為複賽修補（評審五問）最後一個收尾 commit。

## 驗證方式

- **全套測試**：`manage.py test apps`＝**1023 tests**——無字型環境變數時 72 errors 全數為報告渲染 CJK 字型缺失（本機限制；設 `ARGUS_REPORT_FONT_REGULAR/BOLD` 指向 Windows 內建 msjh.ttc/msjhbd.ttc 後，apps.scans 711 tests 僅剩 1 error＝既有 WinError 32 檔案鎖 flake〔`test_missing_file_is_rebuilt...` 的 unlink 撞外部程序占用，A2/B1 兩次以乾淨 HEAD worktree 對照證實與本波無關〕；其餘 312 項〔accounts/billing/admin_api/reviews/content/rebuild/insights〕全綠）
- `uv run ruff check backend`：All checks passed
- 前端 `build-node22.ps1`：最後一次前端變更後全綠（✓ 6.10s，最大 chunk 187.6 kB < 500 kB）
- `rg` 殘留掃描：252/940/32 條/拓樸/F-001～032 等舊事實全部清零

## 人工步驟清單（交付後需使用者執行）

1. **產出複賽版 docx**：依 `專題文件生成/需求書_複賽版_修訂提示詞包.md`——先貼「共同說明」再依序 R1→R8 貼給 Word Claude（套用於根目錄 `…_複賽版.docx`），每段跑段驗收，最後跑總驗收（含頁數回報）
2. **渲染 PlantUML 圖**（若要放進文件）：`專題文件生成/設計文件_圖表與成本模組.md` 內 25 張圖的原始碼，用 PlantUML 渲染成 PNG（本機無 java/plantuml/pandoc，需另尋工具或線上渲染）
3. **複賽文件規定複查**：確認複賽是否只收需求書——決定設計文件（UML/ER/成本）組裝進需求書新章節或獨立文件
4. **部署**（另行確認後才 push）：push→image build→Argo CD→migration PreSync（3 個新 migration）→正式煙霧（網域驗證/訂閱/登入記錄）；若動 ConfigMap 記得 bump config-revision
