# Argus 系統手冊 v3 製作（第 1–8 章，大學部初審版）

**日期**：2026-05-29
**操作者**：Claude（Opus 4.7）

## 變更內容

新增 `專題文件生成/gen_argus_v3.py`（由 v2 複製後改寫，v2 保留作參考），
重新產生 `Argus_系統手冊_v3.docx` 與 `plantuml_diagrams_v3.txt`。
另新增驗證腳本 `verify_v3.py`、資料來源記錄 `data_sources_v3.md`。

依 12 個 Task 完成：

- **版面**：上下左右 1.5cm、頁首尾 1cm、裝訂邊 gutter、單行間距、首行縮排
  `firstLineChars=200`、`adjustRightInd=1`（`set_page_margins` / `_set_para_spacing` / `add_body`）。
- **三目錄**：章節改套 Heading 1/2 樣式，插入 Word 原生 TOC／圖目錄／表目錄欄位
  （`_add_field`），圖表標號改 `SEQ` caption（`_add_seq_caption`，`\s 1` 每章重置），
  設 `updateFields=true`（開檔自動更新頁碼與可點擊跳轉）。
- **表格防截斷**：`_table_no_split`（cantSplit + tblHeader，支援多列表頭）、
  `_table_fixed_widths`（固定欄寬）、`_keep_table_together`（BMC/SWOT 單頁）。
- **圖表重做**：matplotlib 載入標楷體 kaiu.ttf 解決亂碼；`_make_cost_chart` 改用
  `COST_DATA` 真實官方定價、淺色系、移除圖內重複「圖 2-1-1」標號；刪除目標市場
  圓餅圖（查無可引用比例）。
- **真實數據**：競品月費取自 Ahrefs/SEMrush/Screaming Frog/GSC 官方定價頁，外幣依
  台灣銀行牌告匯率換算；市場規模改用經濟部《2024 中小企業白皮書》167.4 萬家；
  移除「1% 滲透率→年收入 2,100 萬」等推估。
- **BMC**：九宮格加 ①–⑨ 標準編號、淺色、單頁。
- **SWOT-TOWS**：表頭由深藍白字改淺紫黑字，單頁鎖定。
- **第 3 章硬體表**：移除開發環境列，僅留正式部署＋用戶端（只寫正式公網配置）。
- **甘特圖**：新增年份跨欄列（114/115 年）、淺紫表頭、雙表頭跨頁重複、圖例。
- **分工表**：`_division_table` 4 名成員依後端/前端/美術/文件分組，●主要○次要
  （每項 1 主 ≤2 次）；貢獻度表 4 人各 25%；封面組員改 4 人。
- **參考資料**：`_add_hyperlink` 真正可點擊外部連結 + `_para_bottom_border` 分隔線，
  改「[n] 標題：連結」格式；修正 SEMrush/Screaming Frog 連結；AI 使用說明表。
- **第 1 章表 1-2-1**：來源存疑的「MTMG SEO」改為可引用的 Ahrefs。

## 原因

使用者要求製作 v3 版系統手冊（v2 作參考），嚴格遵守模板版面與大學部大綱，
核心硬性規範：**禁止估算/猜測，所有數據須真實可引用（標題＋連結）**、全文淺色系、
表格不得不良截斷、三目錄可點擊跳轉、分工表 4 人、只寫正式公網部署配置。

## 影響範圍

- 僅新增 `專題文件生成/` 下檔案，未動 Argus 後端/前端程式碼。
- v2 腳本與 docx 完全保留，未覆蓋。

## 驗證方式

- `uv run python 專題文件生成/gen_argus_v3.py` 無錯誤產出 docx 與 txt。
- `uv run python 專題文件生成/verify_v3.py` → `[OK] 所有硬性需求驗證通過`
  （版面 1.5cm/頁首尾 1cm/gutter、單行間距、firstLineChars=200、adjustRightInd、
  無估計/估算/猜測/推估、無 (PlantUML) caption、TOC 欄位、cantSplit + tblHeader）。
- 殘留語句掃描：估計/估算/猜測/推估/滲透率/年收入潛力/MTMG 皆為 0。
- 結構：27 個表格、35 個 Heading 段落、26 個可點擊外部超連結。

## 需使用者手動驗證（Word 開啟後）

1. 開檔時允許「更新功能變數」，或全選後按 F9：目錄/圖目錄/表目錄帶出頁碼且可
   Ctrl+點擊跳轉（docx 內無法預先計算頁碼）。
2. 版面：頁邊 1.5cm、裝訂邊靠左、首行縮排 2 字元、單行間距外觀正確。
3. 圖表中文無亂碼（標楷體）；競品月費長條圖數值與配色正確。
4. BMC 九宮格、SWOT 矩陣各自單頁完整不跨頁；甘特圖年份跨欄與表頭跨頁重現正常。
5. 長表（3-2 軟體、8-2 各資料表）跨頁時標題列自動重複。
6. 參考資料連結可點擊開啟、條目間分隔線顯示正常。
7. 封面與分工表組員均為佔位符 ○○○（4 人），待填入真實學號姓名。
