# Argus 系統手冊 v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 `gen_argus_v2.py` 為基礎，產生全新的 `gen_argus_v3.py`，輸出符合 `115年_系統手冊模板.doc` 規範與使用者優化清單的 `Argus_系統手冊_v3.docx`（第 1–8 章）。v2 完全保留作為參考。

**Architecture:** 單一 Python 腳本以 `python-docx` 程式化產生 Word 文件，`matplotlib` 產生統計圖，UML/架構圖以 PlantUML 原始碼輸出（文件內放佔位圖）。新增一支 `verify_v3.py` 驗證腳本，開啟產出的 docx 以 oxml 斷言各項硬性需求（邊界、行距、首行縮排字元、無「估計/估算」字串、表格 cantSplit/tblHeader、甘特圖/分工表結構等），作為每個任務的回歸測試。

**Tech Stack:** Python 3.12、python-docx 1.1、matplotlib 3.9、uv（執行：`uv run --project C:\Users\ntub\Desktop\Argus python 專題文件生成\<script>.py`）。Word 欄位（TOC / Table of Figures）以 oxml `w:fldSimple`/`w:instrText` 注入，開啟時自動更新。

**重要約束（來自使用者，最高優先）：**
- 禁止估算/猜測，所有數據需真實可引用並附「標題＋連結」於參考資料。
- 章節名稱嚴格依模板大綱（第 1–8 章），子章節亦同。
- 圖標號在圖下、表標號在表上；caption 不寫「(PlantUML)」。
- 組員 4 人（含組長），一律用佔位符 `○○○`。
- 配色淺色系（仿黃金屋範例），取代深藍表頭。
- 所有回覆與註解使用繁體中文。
- 任務完成後依 `CLAUDE.md` 規則在 `log/` 建立記錄，並與程式碼同次 commit。

**路徑常數（全程使用絕對路徑）：**
- 工作目錄：`C:\Users\ntub\Desktop\Argus`
- 腳本：`專題文件生成\gen_argus_v3.py`
- 驗證腳本：`專題文件生成\verify_v3.py`
- 真實數據記錄：`專題文件生成\data_sources_v3.md`
- 輸出：`專題文件生成\Argus_系統手冊_v3.docx`、`專題文件生成\plantuml_diagrams_v3.txt`
- 標楷體字型：`C:\Windows\Fonts\kaiu.ttf`
- 佔位圖：`專題文件生成\留空用照片.png`

---

## File Structure

| 檔案 | 角色 | 動作 |
|---|---|---|
| `專題文件生成\gen_argus_v3.py` | 文件產生主程式（由 v2 複製改寫） | Create |
| `專題文件生成\verify_v3.py` | docx 硬性需求斷言（回歸測試） | Create |
| `專題文件生成\data_sources_v3.md` | 真實數據與引用來源清單 | Create |
| `專題文件生成\Argus_系統手冊_v3.docx` | 產出文件 | Generated |
| `專題文件生成\plantuml_diagrams_v3.txt` | PlantUML 圖碼 | Generated |
| `log\2026-05-29_argus-manual-v3.md` | 任務記錄 | Create（最後） |

> 採單檔腳本是因 v2 即單檔且文件產生邏輯彼此高度耦合（共用排版 helper）；拆檔反而增加複雜度，違反專案 YAGNI 原則。

---

## Task 0：建立 v3 腳本骨架與驗證 harness

**Files:**
- Create: `專題文件生成\gen_argus_v3.py`（複製自 `gen_argus_v2.py`）
- Create: `專題文件生成\verify_v3.py`

- [ ] **Step 1：複製 v2 為 v3 並改輸出路徑**

PowerShell：
```powershell
Copy-Item "C:\Users\ntub\Desktop\Argus\專題文件生成\gen_argus_v2.py" "C:\Users\ntub\Desktop\Argus\專題文件生成\gen_argus_v3.py"
```
然後在 `gen_argus_v3.py` 修改常數（Edit）：
```python
OUT_DOCX     = os.path.join(BASE_DIR, "Argus_系統手冊_v3.docx")
OUT_PLANTUML = os.path.join(BASE_DIR, "plantuml_diagrams_v3.txt")
```
並把檔頭註解第 2 行改為：
```python
# gen_argus_v3.py  生成 Argus 系統手冊 v3（初審版，大學部，第1-8章）
```

- [ ] **Step 2：建立驗證 harness `verify_v3.py`（先寫會失敗的斷言）**

```python
# -*- coding: utf-8 -*-
# verify_v3.py  驗證 Argus_系統手冊_v3.docx 是否符合硬性需求
import os, sys
from docx import Document
from docx.shared import Cm
from docx.oxml.ns import qn

BASE = os.path.dirname(os.path.abspath(__file__))
DOCX = os.path.join(BASE, "Argus_系統手冊_v3.docx")

failures = []
def check(cond, msg):
    if not cond:
        failures.append(msg)

doc = Document(DOCX)

# 1. 版面：上下左右 1.5cm、頁首頁尾 1cm、裝訂邊位置左
sec = doc.sections[0]
def cm(v): return round(v.cm, 2) if v is not None else None
check(cm(sec.top_margin) == 1.5, f"top_margin={cm(sec.top_margin)} 應為 1.5")
check(cm(sec.bottom_margin) == 1.5, f"bottom_margin={cm(sec.bottom_margin)} 應為 1.5")
check(cm(sec.left_margin) == 1.5, f"left_margin={cm(sec.left_margin)} 應為 1.5")
check(cm(sec.right_margin) == 1.5, f"right_margin={cm(sec.right_margin)} 應為 1.5")
check(cm(sec.header_distance) == 1.0, f"header_distance={cm(sec.header_distance)} 應為 1.0")
check(cm(sec.footer_distance) == 1.0, f"footer_distance={cm(sec.footer_distance)} 應為 1.0")
pgMar = sec._sectPr.find(qn('w:pgMar'))
check(pgMar is not None and pgMar.get(qn('w:gutter')) is not None, "缺少 gutter 設定")

# 2. 內文段落：單行間距、首行縮排 firstLineChars=200、adjustRightInd
body_paras = [p for p in doc.paragraphs if p.text.strip()]
single_ok = adj_ok = fl_ok = False
for p in body_paras:
    pPr = p._p.find(qn('w:pPr'))
    if pPr is None: continue
    spc = pPr.find(qn('w:spacing'))
    if spc is not None and spc.get(qn('w:line')) == "240" and spc.get(qn('w:lineRule')) == "auto":
        single_ok = True
    if pPr.get(qn('w:adjustRightInd')) == "1":
        adj_ok = True
    ind = pPr.find(qn('w:ind'))
    if ind is not None and ind.get(qn('w:firstLineChars')) == "200":
        fl_ok = True
check(single_ok, "找不到單行間距(240/auto)的內文段落")
check(adj_ok, "找不到 adjustRightInd=1 的段落")
check(fl_ok, "找不到 firstLineChars=200 的首行縮排段落")

# 3. 禁止估算/猜測字眼
full_text = "\n".join(p.text for p in doc.paragraphs)
for tbl in doc.tables:
    for row in tbl.rows:
        for c in row.cells:
            full_text += "\n" + c.text
for word in ["估計", "估算", "猜測", "推估"]:
    check(word not in full_text, f"文件出現禁用字「{word}」")

# 4. caption 不得出現 (PlantUML)
check("（PlantUML）" not in full_text and "(PlantUML)" not in full_text,
      "caption 仍出現 (PlantUML)")

# 5. TOC / 圖表目錄欄位存在
xml = doc.element.xml
check("TOC \\o" in xml or 'TOC \\\\o' in xml or "w:instrText" in xml, "缺少 TOC 欄位")

# 6. 表格列防截斷：至少存在 cantSplit 與 tblHeader
has_cantsplit = has_tblheader = False
for tbl in doc.tables:
    for tr in tbl._tbl.findall(qn('w:tr')):
        trPr = tr.find(qn('w:trPr'))
        if trPr is None: continue
        if trPr.find(qn('w:cantSplit')) is not None: has_cantsplit = True
        if trPr.find(qn('w:tblHeader')) is not None: has_tblheader = True
check(has_cantsplit, "沒有任何 row 設定 cantSplit")
check(has_tblheader, "沒有任何表格設定 tblHeader（標題列重複）")

if failures:
    print("[FAIL] 驗證未通過：")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("[OK] 所有硬性需求驗證通過")
```

- [ ] **Step 3：執行 v3 產生基準檔**

Run:
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python "C:\Users\ntub\Desktop\Argus\專題文件生成\gen_argus_v3.py"
```
Expected: 印出 `[OK] 已儲存：...Argus_系統手冊_v3.docx`

- [ ] **Step 4：執行驗證（預期失敗）**

Run:
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python "C:\Users\ntub\Desktop\Argus\專題文件生成\verify_v3.py"
```
Expected: FAIL，列出多項未通過（邊界 3.0、無 firstLineChars=200、無 TOC 欄位、無 tblHeader 等）。確認 harness 能抓到差異。

- [ ] **Step 5：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py" "專題文件生成/verify_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "chore: 建立 v3 腳本骨架與 verify harness"
```

---

## Task 1：全域版面修正（邊界 / 裝訂邊 / 行距 / 首行縮排 / 右側縮排）

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（`set_page_margins`、`_set_para_spacing`、`add_body`、`add_page_number` 頁尾距離）

- [ ] **Step 1：改寫 `set_page_margins`（邊界 1.5、裝訂邊左、頁首尾 1cm）**

```python
from docx.enum.section import WD_SECTION_START  # 已 import docx.* 即可，必要時補

def set_page_margins(doc):
    for sec in doc.sections:
        sec.top_margin    = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin   = Cm(1.5)
        sec.right_margin  = Cm(1.5)
        sec.header_distance = Cm(1.0)
        sec.footer_distance = Cm(1.0)
        # 裝訂邊（gutter）位置左、寬度 0；oxml 直接設定
        pgMar = sec._sectPr.find(qn('w:pgMar'))
        pgMar.set(qn('w:gutter'), "0")
        # 裝訂邊位置左：w:gutterAtTop 不設、預設靠左；明確寫入 docGrid 不需要
```

- [ ] **Step 2：改寫 `_set_para_spacing` 為單行間距並支援右側縮排自動調整**

```python
def _set_para_spacing(p, before=0, after=6, ls=None):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after  = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE   # 單行間距
    # adjustRightInd=1（文件格線時自動調整右側縮排）
    pPr = p._p.get_or_add_pPr()
    pPr.set(qn('w:adjustRightInd'), "1")
    pPr.set(qn('w:snapToGrid'), "0")
```
> 移除原本 `ls=1.5` 多倍行距；保留參數簽章相容（呼叫端傳 `ls=` 會被忽略）。

- [ ] **Step 3：改寫 `add_body` 首行縮排為 2 字元（firstLineChars=200）**

```python
def add_body(doc, text, indent=False, bold=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    _set_run_font(run, BODY_SIZE, bold=bold)
    _set_para_spacing(p, before=0, after=4)
    if indent:
        pPr = p._p.get_or_add_pPr()
        ind = pPr.find(qn('w:ind'))
        if ind is None:
            ind = OxmlElement('w:ind'); pPr.append(ind)
        ind.set(qn('w:firstLineChars'), "200")   # 位移 2 字元
    return p
```
> 移除 `p.paragraph_format.first_line_indent = Cm(1)`。

- [ ] **Step 4：產生並驗證版面項通過**

Run（依序）：
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python "C:\Users\ntub\Desktop\Argus\專題文件生成\gen_argus_v3.py"
uv run --project C:\Users\ntub\Desktop\Argus python "C:\Users\ntub\Desktop\Argus\專題文件生成\verify_v3.py"
```
Expected: 版面（邊界/頁首尾/gutter）、單行間距、firstLineChars=200、adjustRightInd 斷言通過；其餘（TOC、tblHeader 等）仍 FAIL。

- [ ] **Step 5：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 全域版面 1.5cm/單行間距/首行2字元/右側縮排"
```

---

## Task 2：標題樣式 + 目錄/圖目錄/表目錄 Word 欄位（點點＋頁碼＋可點擊）

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（`add_chapter`、`add_section` 套 Heading 樣式；`add_fig_caption`、`add_table_caption` 改用 SEQ；`add_toc_pages` 改插入欄位；`main` 設定開啟更新欄位）

- [ ] **Step 1：新增 oxml 欄位工具函式**

```python
def _add_field(paragraph, instr, default_text="（請按 F9 更新欄位）"):
    """插入 Word 欄位（begin/instrText/separate/text/end）"""
    run = paragraph.add_run()
    r = run._r
    fc1 = OxmlElement('w:fldChar'); fc1.set(qn('w:fldCharType'), 'begin'); r.append(fc1)
    it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = instr; r.append(it)
    fc2 = OxmlElement('w:fldChar'); fc2.set(qn('w:fldCharType'), 'separate'); r.append(fc2)
    t = OxmlElement('w:t'); t.text = default_text; r.append(t)
    fc3 = OxmlElement('w:fldChar'); fc3.set(qn('w:fldCharType'), 'end'); r.append(fc3)
    _set_run_font(run, BODY_SIZE)

def _add_seq_caption(doc, prefix, chapter_no, text, above):
    """圖/表標號：prefix='圖'|'表'；編號用 SEQ，章節碼以固定前綴。
    例：'圖 ' + chapter_no + '-' + SEQ(圖chapter) + '　' + text"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 標號樣式套 Caption 以便 Table of Figures 收集
    try:
        p.style = doc.styles['Caption']
    except KeyError:
        pass
    run = p.add_run(f"{prefix} {chapter_no}-")
    _set_run_font(run, BODY_SIZE)
    # SEQ 欄位（每章一個序列：圖1 / 表1 ...）
    seqrun = p.add_run()
    for tag, txt in [('begin', None), (None, f' SEQ {prefix}{chapter_no} \\* ARABIC '), ('end', None)]:
        if tag:
            fc = OxmlElement('w:fldChar'); fc.set(qn('w:fldCharType'), tag); seqrun._r.append(fc)
        else:
            it = OxmlElement('w:instrText'); it.set(qn('xml:space'),'preserve'); it.text = txt; seqrun._r.append(it)
    _set_run_font(seqrun, BODY_SIZE)
    tail = p.add_run("　" + text)
    _set_run_font(tail, BODY_SIZE)
    _set_para_spacing(p, before=(12 if above else 4), after=(4 if above else 12))
    return p
```
> 說明：以「章碼 + 章內流水號」呈現如「圖 3-1」「表 8-2」。模板/範例採「圖 章-節-序」三層，但子節層級用 SEQ 難以可靠重置；本計畫採「章-序」兩層（範例 PDF 圖標號實務上也是章內流水），並確保圖目錄/表目錄由欄位自動收集、可點擊、有頁碼。若後續要三層，於人工驗證後再議。

- [ ] **Step 2：`add_chapter`/`add_section` 套真正 Heading 樣式**

```python
def add_chapter(doc, text):
    p = doc.add_paragraph(style='Heading 1')
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    _set_run_font(run, CHAP_SIZE, bold=True)
    run.font.color.rgb = RGBColor(0,0,0)   # 取消預設藍色
    _set_para_spacing(p, before=18, after=10)

def add_section(doc, text):
    p = doc.add_paragraph(style='Heading 2')
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    _set_run_font(run, SEC_SIZE, bold=True)
    run.font.color.rgb = RGBColor(0,0,0)
    _set_para_spacing(p, before=12, after=6)
```
> 標題套 Heading 樣式才能被 `TOC \o "1-2"` 收集；字型/顏色以 run 覆寫成標楷體黑色。

- [ ] **Step 3：`add_toc_pages` 改為插入三個欄位（目錄/圖目錄/表目錄）**

刪除原本手寫的 `toc`/`figs`/`tbls` 清單，改為：
```python
def add_toc_pages(doc):
    def heading(title):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(title)
        _set_run_font(run, CHAP_SIZE, bold=True); run.font.color.rgb = RGBColor(0,0,0)
        _set_para_spacing(p, before=12, after=12)

    heading("目　　錄")
    p = doc.add_paragraph()
    _add_field(p, 'TOC \\o "1-2" \\h \\z \\u')
    doc.add_page_break()

    heading("圖 目 錄")
    p = doc.add_paragraph()
    _add_field(p, 'TOC \\h \\z \\c "圖"')
    doc.add_page_break()

    heading("表 目 錄")
    p = doc.add_paragraph()
    _add_field(p, 'TOC \\h \\z \\c "表"')
    doc.add_page_break()
```

- [ ] **Step 4：`add_fig_caption`/`add_table_caption` 轉接到 SEQ caption**

因現有各章呼叫 `add_fig_caption(doc, "圖 3-1-1　...")` 傳入完整字串，為降低改動面，保留函式但**改為解析章碼**：
```python
import re
def _parse_caption(full):
    m = re.match(r'^(圖|表)\s*(\d+)-\d+-\d+\s*[　 ]\s*(.*)$', full)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m2 = re.match(r'^(圖|表)\s*[　 ]\s*(.*)$', full)
    return (m2.group(1), "0", m2.group(2)) if m2 else ("圖","0",full)

def add_fig_caption(doc, text):
    prefix, ch, body = _parse_caption(text)
    _add_seq_caption(doc, prefix, ch, body, above=False)

def add_table_caption(doc, text):
    prefix, ch, body = _parse_caption(text)
    _add_seq_caption(doc, prefix, ch, body, above=True)
```
> 各章 caption 字串維持「圖 3-1-1　名稱」格式即可被解析；輸出呈現為「圖 3-1　名稱」（章-SEQ）。

- [ ] **Step 5：`main` 設定開啟時自動更新欄位**

在 `main()` 的 `doc.save` 前加入：
```python
    settings = doc.settings.element
    upd = OxmlElement('w:updateFields'); upd.set(qn('w:val'), 'true')
    settings.append(upd)
```

- [ ] **Step 6：產生並驗證 TOC 欄位通過**

Run gen + verify（同前指令）。Expected: TOC 欄位斷言通過。
另以 PowerShell 確認欄位字串存在：
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python -c "from docx import Document; d=Document(r'C:\Users\ntub\Desktop\Argus\專題文件生成\Argus_系統手冊_v3.docx'); print('TOC' in d.element.xml, 'SEQ 圖' in d.element.xml.replace(' ',''))"
```
Expected: `True True`

- [ ] **Step 7：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 目錄/圖目錄/表目錄改用 Word 欄位(可點擊+頁碼)"
```

---

## Task 3：表格防截斷與固定欄寬（cantSplit / tblHeader / gridCol）

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（新增 helper；`add_std_table` 套用；`_bmc_table`、`_swot_table`、`_gantt_table` 套用）

- [ ] **Step 1：新增表格 helper**

```python
def _table_no_split(tbl, repeat_header=True):
    """所有資料列不跨頁斷裂；首列設為跨頁重複標題"""
    rows = tbl._tbl.findall(qn('w:tr'))
    for i, tr in enumerate(rows):
        trPr = tr.find(qn('w:trPr'))
        if trPr is None:
            trPr = OxmlElement('w:trPr'); tr.insert(0, trPr)
        cs = OxmlElement('w:cantSplit'); trPr.append(cs)
        if i == 0 and repeat_header:
            th = OxmlElement('w:tblHeader'); th.set(qn('w:val'), 'true'); trPr.append(th)

def _table_fixed_widths(tbl, widths_cm):
    """固定欄寬，避免同表欄寬不一致"""
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    layout = OxmlElement('w:tblLayout'); layout.set(qn('w:type'), 'fixed'); tblPr.append(layout)
    for row in tbl.rows:
        for idx, cell in enumerate(row.cells):
            if idx < len(widths_cm):
                cell.width = Cm(widths_cm[idx])

def _keep_table_together(tbl):
    """強制整表不跨頁（BMC/SWOT 用）：所有列 cantSplit 且不重複標題"""
    for tr in tbl._tbl.findall(qn('w:tr')):
        trPr = tr.find(qn('w:trPr'))
        if trPr is None:
            trPr = OxmlElement('w:trPr'); tr.insert(0, trPr)
        trPr.append(OxmlElement('w:cantSplit'))
```

- [ ] **Step 2：`add_std_table` 末尾套用防截斷**

在 `add_std_table` 的 `doc.add_paragraph()` 之前加入：
```python
    _table_no_split(tbl, repeat_header=True)
```

- [ ] **Step 3：BMC 與 SWOT 套整表不跨頁**

`_bmc_table` 與 `_swot_table` 於 `doc.add_paragraph()` 前加入：
```python
    _keep_table_together(tbl)
```

- [ ] **Step 4：甘特圖固定欄寬**

`_gantt_table` 於建立 `tbl` 後加入（任務名稱欄 3.2cm、10 個月各 1.1cm）：
```python
    _table_fixed_widths(tbl, [3.2] + [1.1]*len(months))
    _table_no_split(tbl, repeat_header=True)
```

- [ ] **Step 5：產生並驗證**

Run gen + verify。Expected: cantSplit 與 tblHeader 斷言通過。

- [ ] **Step 6：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 表格防截斷(cantSplit/tblHeader)與固定欄寬"
```

---

## Task 4：圖表重做（CJK 字型 / 去重複標號 / 移除估計圖 / PlantUML caption）

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（matplotlib 字型設定；`_make_cost_chart`；移除 `_make_market_pie` 與其插入；圖目錄/caption 文字）

- [ ] **Step 1：設定 matplotlib 標楷體（解決亂碼）**

在 import 區塊後加入：
```python
from matplotlib import font_manager as fm
_KAIU = r"C:\Windows\Fonts\kaiu.ttf"
if os.path.exists(_KAIU):
    fm.fontManager.addfont(_KAIU)
    plt.rcParams["font.family"] = "DFKai-SB"   # 標楷體 family 名
plt.rcParams["axes.unicode_minus"] = False
```
> 若 `DFKai-SB` 取不到，改用 `fm.FontProperties(fname=_KAIU)` 逐元素套用（見 Step 2 備援）。

- [ ] **Step 2：`_make_cost_chart` 去除圖內重複標號、套字型、改淺色**

```python
def _make_cost_chart():
    fp = fm.FontProperties(fname=_KAIU)
    tools  = ["Argus\n（本系統）", "Google\nSearch Console", "Screaming Frog",
              "Ahrefs（入門）", "SEMrush（入門）"]
    costs  = COST_DATA   # 由 Task 5 data_sources_v3.md 填入真實 NT$ 數值
    colors = ["#7E9BD0", "#9CCB9C", "#E8A6A0", "#A6C8E0", "#F2D49B"]  # 淺色系
    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(tools, costs, color=colors, edgecolor="gray", linewidth=0.5)
    ax.set_ylabel("每月費用（新台幣 NT$）", fontproperties=fp, fontsize=10)
    ax.set_title("主要競品月費比較（2024年）", fontproperties=fp, fontsize=12, fontweight="bold")
    for lbl in ax.get_xticklabels():
        lbl.set_fontproperties(fp); lbl.set_fontsize(9)
    for bar, cost in zip(bars, costs):
        label = "免費" if cost == 0 else f"NT${cost:,}"
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max(costs)*0.01,
                label, ha="center", va="bottom", fontproperties=fp, fontsize=9, fontweight="bold")
    plt.tight_layout()
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig); buf.seek(0); return buf
```
> 圖內標題不再含「圖 2-1-1」；該標號由 caption 提供。`COST_DATA` 於 Task 5 以真實官方定價填入（暫以模組頂層常數 `COST_DATA = [...]` 宣告）。

- [ ] **Step 3：移除「目標市場區隔分布（估計）」圓餅圖**

- 刪除 `_make_market_pie` 函式。
- 刪除 ch2 中 `_insert_chart(doc, _make_market_pie(), "圖 2-1-2　目標市場區隔分布（估計）")` 整行。
- 刪除其後「市場估計依據：…」段落（含「估計」字眼）。
- 從圖目錄移除「圖 2-1-2」（已於 Task 2 改成自動欄位，無需手動）。

- [ ] **Step 4：所有 caption 去除「(PlantUML)」字樣**

以 Edit 將下列 caption 文字改寫（移除「（PlantUML）」）：
- ch3：`add_placeholder(doc, "圖 3-1-1　Argus 系統架構圖", width=Cm(14))`
- 確認 ch5/6/7/8 placeholder caption 不含「(PlantUML)」（目前不含，僅內文有「PlantUML 圖碼見…」敘述，保留內文敘述即可，但 caption 不寫）。

- [ ] **Step 5：產生並驗證（亂碼需人工目視）**

Run gen + verify。Expected: 「(PlantUML)」斷言通過；「估計」字眼斷言通過（圓餅圖已移除）。
**人工驗證項**：開啟 docx 確認競品月費長條圖中文無亂碼。

- [ ] **Step 6：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 圖表套標楷體去亂碼/移除估計圓餅圖/去除PlantUML字樣"
```

---

## Task 5：真實數據查證與記錄（data_sources_v3.md）

**Files:**
- Create: `專題文件生成\data_sources_v3.md`
- Modify: `專題文件生成\gen_argus_v3.py`（填入 `COST_DATA` 與背景統計引用）

- [ ] **Step 1：以 WebSearch/WebFetch 查證並記錄下列項目（每項需 標題＋URL＋擷取數值＋查證日期）**

待查清單（查不到精確值者標記「無可引用來源 → 移除/改質化」）：
1. Ahrefs 月費（官方 pricing 頁，月繳方案最低價，USD→NT$ 換算註明匯率來源）。
2. SEMrush 月費（官方 prices 頁）。
3. Screaming Frog SEO Spider 年費（官方頁，年費折月，GBP→NT$）。
4. Google Search Console（免費，官方說明頁）。
5. Nmap / Dirsearch / Katana / MTMG SEO 功能與授權（官方/GitHub）。
6. OWASP Top 10（2021，官方頁）——背景敘述引用。
7. 全球網站數量 / Google 索引量（Statista 或官方，附頁）——若無精確可引用值則改質化敘述。
8. AI 搜尋採用趨勢（可引用研究報告，附連結）——否則移除百分比。
9. 台灣中小企業 / 電商規模（資策會 MIC 或政府開放資料 data.gov.tw，附頁）——否則移除數字、改質化。
10. 技術棧版本官方文件（已具備，逐一確認連結有效）。

將結果寫入 `data_sources_v3.md`，格式：
```markdown
# Argus 手冊 v3 真實數據來源（查證日：2026-05-29）
## 競品月費
- Argus：本系統定價 NT$300/月（自訂，非引用）
- Ahrefs Lite：US$<實值>/月 ≈ NT$<換算>（匯率：<來源>） — <官方URL>
- ...（逐項）
## 背景統計
- OWASP Top 10 (2021)：<引用句> — https://owasp.org/www-project-top-ten/
- ...
## 無可引用來源（已移除/改質化）
- <項目> — 原因
```

- [ ] **Step 2：將 `COST_DATA` 與背景敘述以真實值回填 `gen_argus_v3.py`**

```python
COST_DATA = [300, 0, <真實>, <真實>, <真實>]   # 對應 [Argus, GSC, Screaming Frog, Ahrefs, SEMrush]
```
- 將 ch1 背景介紹中無來源的數字（17 億網站、1300 億索引、54%）替換為 `data_sources_v3.md` 中的可引用數值與引用；查不到者刪除該句或改質化。
- 將 ch2 可行性分析中的「年收入潛力 NT$2,100 萬」「1% 滲透率」「35 萬家」等推估，依 Step 1 結果：有來源→附引用；無來源→改為質化敘述（例如「台灣中小企業普遍具網站健檢需求」不帶杜撰數字）。

- [ ] **Step 3：產生並驗證無禁用字**

Run gen + verify。Expected: 「估計/估算/推估/猜測」斷言通過。
再以 PowerShell 抓殘留：
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python -c "from docx import Document; d=Document(r'C:\Users\ntub\Desktop\Argus\專題文件生成\Argus_系統手冊_v3.docx'); t='\n'.join(p.text for p in d.paragraphs); import sys; print([w for w in ['估計','估算','推估','猜測','約','潛力'] if w in t])"
```
Expected: `[]`（或僅剩經人工確認合理的詞）。

- [ ] **Step 4：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py" "專題文件生成/data_sources_v3.md"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 回填真實可引用數據並移除推估值"
```

---

## Task 6：第 2 章 BMC 九宮格與 SWOT 四宮格改版（淺色、編號、單頁）

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（`_bmc_table`、`_swot_table`）

- [ ] **Step 1：BMC 加 1–9 編號、改淺色、縮字級確保單頁**

於 `_bmc_table` 的每格 title 前加編號（照 `商業九宮格-範本.webp`）：KP=8、KA=7、VP=2、CR=4、CS=1、KR=6、CH=3、C$=9、R$=5。
```python
    bmc_titles = {
        (0,0): "8 | KP 關鍵合作夥伴", (0,1): "7 | KA 關鍵活動", (0,2): "2 | VP 價值主張",
        (0,3): "4 | CR 顧客關係", (0,4): "1 | CS 目標客層", (1,1): "6 | KR 關鍵資源",
        (1,3): "3 | CH 通路", (2,0): "9 | C$ 成本結構", (2,2): "5 | R$ 收益流",
    }
```
- 將 `title` 改用 `bmc_titles[(r,c)]`。
- 底色改淺色：KP/KA/KR→`DCE6F1`；VP→`EBF1DE`；CR/CH/CS→`FDEADA`；C$/R$→`F2F2F2`（淺色系）。
- 標題字級 Pt(9)、項目 Pt(8)、`_set_para_spacing(... after=1)`，確保整表單頁。
- 末尾 `_keep_table_together(tbl)`（Task 3 已加）。

- [ ] **Step 2：SWOT 改為對齊範例的四宮格 TOWS、淺色、精簡內容**

依 `swot_範例.png`：左上角斜分「內部/外部」，上排欄 `優勢(Strengths)`/`劣勢(Weakness)`，左欄 `機會(Opportunity)`/`威脅(Threats)`，四宮格放 SO/WO/ST/WT 策略（各 3 條，多層次清單）。
```python
def _swot_table(doc):
    add_table_caption(doc, "表 2-4-1　競爭力分析 SWOT-TOWS 矩陣")
    tbl = doc.add_table(rows=3, cols=3); tbl.style="Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    def corner(cell):
        _cell_shading(cell, "EDE7F6")
        p = cell.paragraphs[0]; p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
        r=p.add_run("內部 →"); _set_run_font(r,Pt(9),bold=True)
        p2=cell.add_paragraph(); p2.alignment=WD_ALIGN_PARAGRAPH.LEFT
        r2=p2.add_run("外部 ↓"); _set_run_font(r2,Pt(9),bold=True)
    def hdr(cell, text):
        _cell_shading(cell, "D9D2E9")
        p=cell.paragraphs[0]; p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        r=p.add_run(text); _set_run_font(r,Pt(10),bold=True)
    def body(cell, title, items, fill):
        _cell_shading(cell, fill); cell.vertical_alignment=WD_ALIGN_VERTICAL.TOP
        p0=cell.paragraphs[0]; r=p0.add_run(title); _set_run_font(r,Pt(9),bold=True)
        for it in items:
            _cell_add_para(cell, it, size=Pt(9), left_indent_cm=0.2, bullet="• ")
    corner(tbl.cell(0,0))
    hdr(tbl.cell(0,1), "優勢（Strengths）")
    hdr(tbl.cell(0,2), "劣勢（Weakness）")
    hdr(tbl.cell(1,0), "機會（Opportunity）")
    hdr(tbl.cell(2,0), "威脅（Threats）")
    body(tbl.cell(1,1), "SO 攻勢策略", [
        "進攻 AEO/GEO 藍海，主打四維差異化",
        "以圖形化 GUI 降低門檻搶占中小企業",
        "推 AI 代理試用建立品牌聲量",
    ], "EAF3EA")
    body(tbl.cell(1,2), "WO 扭轉策略", [
        "與行銷代理商白牌合作擴散品牌",
        "經營 AEO/GEO 教育內容降低認知門檻",
        "加速主動式資安掃描功能迭代",
    ], "FFFBEA")
    body(tbl.cell(2,1), "ST 多角化策略", [
        "強化報告深度對抗大廠跟進",
        "建立企業訂閱方案穩定營收",
        "持續跟進演算法更新維持有效性",
    ], "EAF0FB")
    body(tbl.cell(2,2), "WT 防禦策略", [
        "縮短 Phase 2 商業驗證週期",
        "建立使用者回饋機制持續改善",
        "控管 AI API 成本優化計費模型",
    ], "FBEAF0")
    _table_fixed_widths(tbl, [3.0, 6.0, 6.0])
    _keep_table_together(tbl)
    doc.add_paragraph()
```
> 移除 v2 中冗長的 S1–S5/W1–W5/O/T 條列（使用者指其「好亂、多餘」）。

- [ ] **Step 3：產生並驗證 + 人工目視**

Run gen + verify。Expected: 全綠。
**人工驗證項**：BMC 與 SWOT 各自單頁完整、淺色、不截斷。

- [ ] **Step 4：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): BMC九宮格編號淺色單頁 + SWOT四宮格對齊範例"
```

---

## Task 7：第 3 章硬體表（只留正式部署＋用戶端）與長表標題重複

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（ch3 表 3-2-1）

- [ ] **Step 1：移除「開發環境」列，只保留正式部署與用戶端**

將 `表 3-2-1　硬體環境需求規格` 的 rows 改為：
```python
        [
            ("正式部署","CPU","vCPU × 4（AWS t3.xlarge 或同等級）","Celery Worker 並行需求"),
            ("正式部署","RAM","16 GB","Django + Celery + PostgreSQL + Redis"),
            ("正式部署","儲存空間","SSD 100 GB（含資料庫與截圖儲存）","截圖 50–200 KB/頁"),
            ("正式部署","頻寬","100 Mbps（對外爬蟲流量）","BFS 爬蟲並發需求"),
            ("用戶端（瀏覽器）","瀏覽器","Chrome 120+、Firefox 120+、Edge 120+","支援 ES2020"),
        ],
```
> 對應使用者「只說正式部署公網配置，本地測試不寫」。3-2-2 軟體需求與 3-3 工具表已具官方連結，僅需 Task 3 的 tblHeader 自動重複標題（軟體表 17 列會跨頁，標題列會重現）。

- [ ] **Step 2：產生並驗證**

Run gen + verify。Expected: 全綠。
**人工驗證項**：表 3-2-2 跨頁時，次頁頂端自動重現標題列。

- [ ] **Step 3：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 3-2硬體表只留正式部署+用戶端"
```

---

## Task 8：第 4 章甘特圖配色與分工表 4 人分組格式

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（`_gantt_table`、ch4 分工表與貢獻度表）

- [ ] **Step 1：甘特圖表頭改淺紫、年份跨欄列、圖例小標籤**

於 `_gantt_table`：
- 表頭底色 `HDR_FILL` 改為淺紫 `E4DFEC`，文字色改黑（移除白字設定）。
- 在月份列之上新增一列「113/114 年」跨欄（合併 month 欄）置中，淺紫底。
- 圖例維持「▢ 預期進度 / ▮ 實際進度」小標籤（已具備，確認顏色 `D9D9D9`/`595959`）。
- 任務名稱欄左對齊、月份欄等寬（Task 3 已 `_table_fixed_widths`）。
> 任務時程沿用 v2（114/09–115/06，與 4-1 內文一致），僅調整配色與年份列。

- [ ] **Step 2：分工表改為模板格式（4 人、分組列、學號/姓名欄）**

依模板「表4-2」與 `專業組織與分工表範例`，重寫 ch4 分工表：欄位＝`項目` + 4 位（`學號 姓名` 佔位 `○○○○○ ○○○`）；列以分組呈現（後端開發/前端開發/美術設計/文件撰寫統整），● 主要、○ 次要（每項 1 主、≤2 次）。
```python
    # 表頭
    add_std_table(doc,
        ["項目 / 組員","組長\n○○○","組員\n○○○","組員\n○○○","組員\n○○○"],
        [
            ("【後端開發】","","","",""),
            ("Django REST API","●","○","",""),
            ("資料庫設計（PostgreSQL）","○","●","",""),
            ("點數計費 BillingService","●","","","○"),
            ("BFS 爬蟲 / 四維掃描","","●","○",""),
            ("Celery 任務佇列","○","●","",""),
            ("【前端開發】","","","",""),
            ("React SPA 介面","","","●","○"),
            ("ReactFlow 拓樸圖","","","○","●"),
            ("後台管理介面","","","●","○"),
            ("【美術設計】","","","",""),
            ("UI/UX 設計","","","○","●"),
            ("配色與視覺規範","","","","●"),
            ("【文件撰寫統整】","","","",""),
            ("系統手冊撰寫","●","○","",""),
            ("報告簡報製作","○","","","●"),
        ],
        "表 4-2-1　專案組織分工表（● 主要負責，○ 次要協助）")
```
> 分組標題列（如「【後端開發】」）以空白協助欄呈現分隔。每項僅 1 個 ●、≤2 個 ○，須逐列檢查符合規則。

- [ ] **Step 3：貢獻度表改 4 人各 25%**

```python
    add_std_table(doc,
        ["序號","姓名","工作內容（各限 100 字以內）","貢獻度"],
        [
            ("1","○○○（組長）","整體系統架構、後端 API（Django+DRF）、點數計費 BillingService 原子交易設計、文件統整。","25%"),
            ("2","○○○（組員）","PostgreSQL 資料庫設計、BFS 爬蟲（Playwright+Celery）與 ScanJob 狀態機開發。","25%"),
            ("3","○○○（組員）","React 前端 SPA、ReactFlow 拓樸圖、後台管理介面與 UI/UX 設計。","25%"),
            ("4","○○○（組員）","四維掃描引擎（SEO/AEO/GEO/Security）、Docker 容器化部署與 Word 報告生成。","25%"),
        ],
        "表 4-2-2　專題成果工作內容與貢獻度表")
```

- [ ] **Step 4：修正 4-2 前言敘述（5 名→4 名）**

將 ch4 中「本組共 5 名成員」改為「本組共 4 名成員（含組長）。每項工作指定 1 位主要負責人（●），次要協助最多 2 位（○）。」

- [ ] **Step 5：產生並驗證 + 人工目視**

Run gen + verify。Expected: 全綠。新增臨時檢查 4 人：
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python -c "from docx import Document; d=Document(r'C:\Users\ntub\Desktop\Argus\專題文件生成\Argus_系統手冊_v3.docx'); t='\n'.join(p.text for p in d.paragraphs); print('5 名成員' not in t and '4 名成員' in t)"
```
Expected: `True`

- [ ] **Step 6：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 甘特圖淺紫配色 + 分工表4人分組格式 + 貢獻度4人"
```

---

## Task 9：參考資料改版（[n] 標題：可點擊連結 + 分隔線）

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（`add_references`）

- [ ] **Step 1：新增真正可點擊超連結 helper**

```python
def _add_hyperlink(paragraph, url, text):
    part = paragraph.part
    r_id = part.relate_to(url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    hl = OxmlElement('w:hyperlink'); hl.set(qn('r:id'), r_id)
    run = OxmlElement('w:r'); rPr = OxmlElement('w:rPr')
    color = OxmlElement('w:color'); color.set(qn('w:val'), "0563C1"); rPr.append(color)
    u = OxmlElement('w:u'); u.set(qn('w:val'), "single"); rPr.append(u)
    rf = OxmlElement('w:rFonts'); rf.set(qn('w:ascii'), EN_FONT); rf.set(qn('w:hAnsi'), EN_FONT); rf.set(qn('w:eastAsia'), CH_FONT); rPr.append(rf)
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), "28"); rPr.append(sz)  # 14pt
    run.append(rPr)
    t = OxmlElement('w:t'); t.set(qn('xml:space'), 'preserve'); t.text = text; run.append(t)
    hl.append(run); paragraph._p.append(hl)
```

- [ ] **Step 2：改寫 `add_references` 為「[n] 標題：連結」+ 條目間分隔線**

依 `參考資料範例.png`（標題在前、連結在後、條目間水平線）：
```python
def _add_hr(doc):
    p = doc.add_paragraph(); pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr'); bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'),'single'); bottom.set(qn('w:sz'),'6'); bottom.set(qn('w:space'),'1'); bottom.set(qn('w:color'),'BFBFBF')
    pbdr.append(bottom); pPr.append(pbdr)
    _set_para_spacing(p, before=2, after=2)

def add_references(doc):
    add_chapter(doc, "參考資料")
    refs = REFS_V3   # 由 data_sources_v3.md 整理：list[(標題, url)]，全部真實
    for i, (title, url) in enumerate(refs, 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(1.0)
        p.paragraph_format.first_line_indent = Cm(-1.0)
        head = p.add_run(f"[{i}] {title}：")
        _set_run_font(head, BODY_SIZE)
        if url:
            _add_hyperlink(p, url, url)
        _set_para_spacing(p, before=4, after=2)
        _add_hr(doc)
    # AI 使用說明表（模板規定保留）
    doc.add_paragraph()
    add_body(doc, "※ 使用人工智慧輔助說明：", bold=True)
    add_std_table(doc,
        ["序號","使用工具名稱","使用範圍及說明","頁碼"],
        [("1","Claude（Anthropic）","輔助系統手冊初稿撰寫與排版格式整理","全文")],
        "表 參-1　人工智慧使用說明表")
```

- [ ] **Step 3：以 Task 5 結果定義 `REFS_V3`（全部真實連結，標題用中文敘述）**

於模組頂層定義 `REFS_V3 = [("Ahrefs 官方定價", "https://ahrefs.com/pricing"), ...]`，逐筆對應 `data_sources_v3.md` 實際引用；移除文中未實際引用的條目。

- [ ] **Step 4：產生並驗證連結有效**

Run gen + verify。再檢查 hyperlink 關聯存在：
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python -c "import zipfile,re; z=zipfile.ZipFile(r'C:\Users\ntub\Desktop\Argus\專題文件生成\Argus_系統手冊_v3.docx'); x=z.read('word/_rels/document.xml.rels').decode(); print('hyperlink' in x, x.count('TargetMode=\"External\"'))"
```
Expected: `True` 且外部連結數 > 0。

- [ ] **Step 5：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 參考資料改[n]標題:可點擊連結+分隔線"
```

---

## Task 10：第 1 章競品表與全章節名稱對照 + PlantUML 輸出檔名

**Files:**
- Modify: `專題文件生成\gen_argus_v3.py`（ch1 表 1-2-1 資料來源；確認 ch5–8 章節名稱；`PLANTUML_CODE` 無 caption「(PlantUML)」需求不影響）

- [ ] **Step 1：核對第 1–8 章與子章節名稱完全符合模板大綱**

逐一比對（模板大綱見 spec）。v2 既有名稱已符合，僅需確認下列無偏差並修正任何「估計/約」殘留：
- 2-2 標題用「商業模式（Business Model）」，2-4 用「競爭力分析（SWOT-TOWS 分析）」——與模板一致，保留。
- ch1 表 1-2-1 資料來源段落改用 Task 5 真實連結，移除「Argus 系統實測（2024）」這類無法佐證者或改為「本系統規格」。

- [ ] **Step 2：確認 PlantUML 圖碼輸出到 v3 檔名**

`main()` 已用 `OUT_PLANTUML`（Task 0 已改為 `plantuml_diagrams_v3.txt`）。確認 `PLANTUML_CODE` 內標題不影響 docx caption（docx caption 已於 Task 4 去除 PlantUML 字樣）。

- [ ] **Step 3：產生並驗證**

Run gen + verify。Expected: 全綠。

- [ ] **Step 4：commit**

```powershell
git add "專題文件生成/gen_argus_v3.py"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "feat(v3): 第1章競品來源真實化+章節名稱對照模板"
```

---

## Task 11：最終整體驗證與任務記錄

**Files:**
- Create: `log\2026-05-29_argus-manual-v3.md`

- [ ] **Step 1：完整重產 + 驗證全綠**

Run:
```powershell
uv run --project C:\Users\ntub\Desktop\Argus python "C:\Users\ntub\Desktop\Argus\專題文件生成\gen_argus_v3.py"
uv run --project C:\Users\ntub\Desktop\Argus python "C:\Users\ntub\Desktop\Argus\專題文件生成\verify_v3.py"
```
Expected: `[OK] 所有硬性需求驗證通過`

- [ ] **Step 2：列出需使用者人工驗證的項目清單**

輸出給使用者逐項目視（Word 開啟）：
1. 開啟後 Ctrl+A → F9 更新欄位 → 目錄/圖目錄/表目錄出現頁碼與引導點，可 Ctrl+點擊跳轉。
2. 版面 1.5cm/裝訂邊左/頁首尾 1cm/單行間距/首行 2 字元。
3. 競品月費長條圖中文無亂碼。
4. BMC 九宮格、SWOT 四宮格各自單頁完整、淺色。
5. 長表（軟體需求、8-2 資料表）跨頁時標題列重現。
6. 甘特圖淺紫、欄寬一致、雙列預期/實際 + 圖例。
7. 分工表 4 人、分組（後端/前端/美術/文件）、學號姓名欄。
8. 參考資料 [n] 標題：可點擊連結、條目分隔線。
9. 無「估計/估算/推估/猜測」字眼。
10. 架構圖/ UML 為留空佔位圖；PlantUML 圖碼在 `plantuml_diagrams_v3.txt`，貼至 plantuml.com 產圖後替換佔位圖。

- [ ] **Step 3：撰寫 `log\2026-05-29_argus-manual-v3.md`（依 CLAUDE.md 格式）**

內容涵蓋：變更內容（新增 gen_argus_v3.py / verify_v3.py / data_sources_v3.md，產出 v3 docx）、原因（使用者優化清單）、影響範圍（v2 保留不動）、驗證方式（verify_v3 全綠 + 人工清單）。

- [ ] **Step 4：commit（含 log）**

```powershell
git add "專題文件生成/gen_argus_v3.py" "專題文件生成/verify_v3.py" "專題文件生成/data_sources_v3.md" "log/2026-05-29_argus-manual-v3.md"
git -c user.name="傑" -c user.email="90761973+XiuJie2@users.noreply.github.com" commit -m "docs(v3): 最終驗證通過 + 任務記錄"
```

---

## Self-Review（對照 spec）

- **A 全域版面** → Task 1 ✓（邊界/裝訂邊/頁首尾/單行/首行2字元/adjustRightInd，verify 斷言）
- **B 三目錄欄位** → Task 2 ✓（Heading 樣式 + TOC/Table of Figures 欄位 + updateFields）
- **C 圖表重做** → Task 4 ✓（CJK 字型、去重複標號、移除估計圖、去 PlantUML 字樣）
- **D 表格防截斷** → Task 3 ✓（cantSplit/tblHeader/固定欄寬；BMC/SWOT 整表不跨頁）
- **E 內容真實化** → Task 5、9、10 ✓（查證記錄 + 回填 + 參考資料可點擊連結 + 競品來源）
- **F 章節校正** → Task 6（BMC/SWOT）、7（硬體表）、8（甘特圖/分工4人）、10（章節名稱）✓
- **已拍板解讀**：正式部署 only（Task 7）、移除圓餅圖（Task 4/5）、上網查證（Task 5）✓
- **Placeholder 掃描**：研究依賴值（`COST_DATA`、`REFS_V3`、背景統計）皆由 Task 5 的具體產出 `data_sources_v3.md` 提供真實值再回填，非空泛佔位；組員 `○○○` 為使用者明確指定之佔位符。
- **型別/命名一致**：helper 名稱 `_table_no_split`/`_table_fixed_widths`/`_keep_table_together`/`_add_field`/`_add_seq_caption`/`_add_hyperlink`/`_add_hr` 全程一致。

> **三層圖表標號取捨**（圖 章-節-序 → 改 章-序）已於 Task 2 Step 1 說明並標記人工驗證點；若驗收要求嚴格三層，於人工驗證後追加調整任務。
