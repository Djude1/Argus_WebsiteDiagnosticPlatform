"""Argus 網站健檢報告 generator — data (JSON) in, styled .docx out.

Public API:
    generate_report(data: dict, out_path: str, workdir: str = None) -> str

The design (layout, palette, cards, watermark) is fixed here; the Agent supplies
only the data. See schema.json for the expected input shape.
"""
import os
import tempfile

from docx import Document
from docx.shared import Pt, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from . import theme as T
from . import charts as C
from . import _xml as X

EMU_PER_IN = 914400


# ---------- run / paragraph helpers ----------
def _rgb(hexstr):
    return RGBColor.from_string(hexstr)


def _set_font(run, mono=False):
    name = T.FONT_MONO if mono else T.FONT_CJK
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(a), name)


def add_run(paragraph, text, size=10, color=T.SLATE, bold=False, mono=False, chip=None):
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color)
    _set_font(run, mono=mono)
    if chip:
        # shaded run (severity chip)
        rPr = run._r.get_or_add_rPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), chip)
        rPr.append(shd)
    return run


def add_para(doc_or_cell, runs=None, align=None, before=0, after=6, line=1.15,
             keep_next=False):
    p = doc_or_cell.add_paragraph()
    pf = p.paragraph_format
    if align:
        p.alignment = align
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    if keep_next:
        pf.keep_with_next = True
    if runs:
        for r in runs:
            add_run(p, **r)
    return p


def chip_run(paragraph, severity, size=9):
    meta = T.SEVERITY[severity]
    add_run(paragraph, f" {severity} ", size=size, color=meta["text"], bold=True,
            chip=meta["fill"])


# ---------- headings ----------
def h1(doc, num, title, page_break=True):
    p = doc.add_paragraph()
    if page_break:
        p.paragraph_format.page_break_before = True
    p.paragraph_format.space_before = Pt(0 if page_break else 18)
    p.paragraph_format.space_after = Pt(10)
    # 不換頁的章節標題（短章節接在前一章後面，減少半頁留白）要跟著下一段，不能孤懸頁尾
    p.paragraph_format.keep_with_next = True
    add_run(p, f"{num}　", size=T.TYPE["h1"], color=T.LIGHTGREY, bold=True)
    add_run(p, title, size=T.TYPE["h1"], color=T.NAVY, bold=True)
    X.set_para_borders(p, {"bottom": (8, T.BORD, "6")})
    return p


def h2(doc, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    add_run(p, title, size=T.TYPE["h2"], color=T.NAVY, bold=True)
    return p


# ---------- tables ----------
def _dxa(cols):  # column widths list
    return cols


def data_table(doc, headers, rows, widths, grid=True, keep_together=None):
    """rows: list of lists; each cell is str OR list-of-run-dicts OR ('chip',sev).

    欄寬寫進表格格線（w:gridCol）：只設儲存格寬度時 LibreOffice 轉 PDF 會平均分欄，
    「#」欄和「問題」欄一樣寬、說明欄擠成窄條（2026-10-11 逐頁審查）。
    keep_together：短表（預設 6 列以內）整張不跨頁，避免只剩一兩列被擠到下一頁、
    那一頁幾乎全白。
    """
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    # header
    hdr = table.rows[0]
    X.set_row_cant_split(hdr)
    hdr._tr.get_or_add_trPr().append(_tbl_header_mark())
    for i, htext in enumerate(headers):
        cell = hdr.cells[i]
        cell.width = Emu(int(widths[i] * 635))
        _fill_cell(cell, [[{"text": htext, "size": 9.5, "color": T.NAVY, "bold": True}]],
                   fill=T.BGBLUE)
    # body
    for ri, row in enumerate(rows):
        tr = table.add_row()
        X.set_row_cant_split(tr)
        fill = T.BG if ri % 2 == 1 else None
        for i, cell_data in enumerate(row):
            cell = tr.cells[i]
            cell.width = Emu(int(widths[i] * 635))
            _fill_cell(cell, _normalize_cell(cell_data), fill=fill)
    _apply_table_borders(table)
    if grid:
        for i, col in enumerate(table.columns):
            col.width = Emu(int(widths[i] * 635))
    if keep_together is None:
        keep_together = len(rows) <= 6
    if keep_together:
        for tr in table.rows[:-1]:
            for cell in tr.cells:
                for para in cell.paragraphs:
                    para.paragraph_format.keep_with_next = True
    return table


def _normalize_cell(cell_data):
    """Return list-of-paragraphs, each a list-of-run-dicts."""
    if isinstance(cell_data, tuple) and cell_data[0] == "chip":
        return [("chip", cell_data[1])]
    if isinstance(cell_data, list):
        return [cell_data]  # single paragraph of runs
    return [[{"text": str(cell_data), "size": 9.5, "color": T.SLATE}]]


def _fill_cell(cell, paragraphs, fill=None):
    # clear default empty paragraph
    cell.text = ""
    first = True
    for para in paragraphs:
        if first:
            p = cell.paragraphs[0]
            first = False
        else:
            p = cell.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.1
        if isinstance(para, tuple) and para[0] == "chip":
            chip_run(p, para[1])
        else:
            for r in para:
                add_run(p, **r)
    if fill:
        X.set_cell_shading(cell, fill)
    X.set_cell_margins(cell)
    X.set_cell_vertical_center(cell)
    X.set_cell_borders(cell, sz=2, color=T.LINE)


def _tbl_header_mark():
    e = OxmlElement("w:tblHeader")
    return e


def _apply_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge, color in (("top", T.BORD), ("left", T.BORD), ("bottom", T.BORD),
                        ("right", T.BORD), ("insideH", T.LINE), ("insideV", T.LINE)):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "2")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), color)
        borders.append(e)
    tblPr.append(borders)


# ---------- images ----------
def add_image(doc_or_cell, path, width_in):
    p = doc_or_cell.add_paragraph() if hasattr(doc_or_cell, "add_paragraph") else doc_or_cell
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(path, width=Emu(int(width_in * EMU_PER_IN)))
    return p


# ---------- finding card ----------
# 版面規則（2026-10-06 重新設計）：
# - 不用任何彩色左邊條（全站規則），層次靠字級、字重與留白。
# - 中風險以上用完整卡片；低風險與資訊提示用精簡條目（不印逐頁證據），
#   讓讀者把注意力放在真正要處理的項目。
_FULL_CARD_SEVERITIES = {"嚴重風險", "高風險", "中風險"}


def finding_card(doc, f):
    if f["severity"] not in _FULL_CARD_SEVERITIES:
        return compact_card(doc, f)
    # 標題列：編號（淺灰）＋問題名稱（深藍、最大字級），下方一條細線
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    add_run(p, f'{f["id"]}　', size=T.TYPE["finding"], color=T.LIGHTGREY, bold=True)
    add_run(p, f["title"], size=T.TYPE["finding"], color=T.NAVY, bold=True)
    X.set_para_borders(p, {"bottom": (4, T.LINE, "3")})
    # 中繼資料：嚴重度標籤、分類、範圍
    mp = doc.add_paragraph()
    mp.paragraph_format.space_before = Pt(3)
    mp.paragraph_format.space_after = Pt(4)
    mp.paragraph_format.keep_with_next = True
    chip_run(mp, f["severity"])
    add_run(mp, f'　{f["category"]}　·　{f["scope"]}', size=T.TYPE["meta"], color=T.GREY)
    if f.get("urls") and not f.get("locations"):
        up = doc.add_paragraph()
        up.paragraph_format.space_after = Pt(4)
        add_run(up, f["urls"], size=T.TYPE["meta"], color=T.LIGHTGREY)
    _card_label(doc, "問題是什麼")
    add_para(doc, [{"text": f["problem"], "size": T.TYPE["body"], "color": T.SLATE}],
             after=5, line=1.45)
    _card_label(doc, "怎麼修")
    fp = add_para(doc, [{"text": f["fix"], "size": T.TYPE["body"], "color": T.SLATE}],
                  after=5, line=1.45)
    X.set_para_shading(fp, T.FIXBLUE)
    X.set_para_indent(fp, left=120, right=120)
    # 檢測依據：逐頁證據（資料層已限制最多 5 頁，其餘收成「…另 N 處」）
    _card_label(doc, "檢測依據")
    locations = f.get("locations") or []
    if locations:
        for loc in locations:
            ep = add_para(doc, [
                {"text": loc["url"], "size": T.TYPE["meta"], "color": T.GREY},
                {"text": "\n" + (loc.get("evidence") or "（無）"), "size": T.TYPE["evidence"],
                 "color": T.SLATE, "mono": True},
            ], before=1, after=2, line=1.3)
            X.set_para_shading(ep, T.BG)
            X.set_para_indent(ep, left=120, right=120)
        if f.get("locations_more"):
            add_para(doc, [{"text": f["locations_more"], "size": T.TYPE["meta"],
                            "color": T.LIGHTGREY}], before=1, after=3)
    else:
        ep = add_para(doc, [{"text": f["evidence"], "size": T.TYPE["evidence"], "color": T.SLATE,
                             "mono": True}], before=2, after=3, line=1.35)
        X.set_para_shading(ep, T.BG)
        X.set_para_indent(ep, left=120, right=120)
    # 判定依據：高風險與 AI 觀察項目交代成立條件、實際觀察、尚缺證據、驗證方法
    if f.get("assessment"):
        _card_label(doc, "判定依據")
        a = f["assessment"]
        for label, key in (("成立條件", "condition"), ("實際觀察", "observed"),
                           ("尚缺證據", "missing"), ("驗證方法", "verify")):
            if a.get(key):
                add_para(doc, [{"text": f"{label}：", "size": T.TYPE["small"], "color": T.NAVY,
                                "bold": True},
                               {"text": a[key], "size": T.TYPE["small"], "color": T.SLATE}],
                         after=1, line=1.35)
    if f.get("basis"):
        add_para(doc, [{"text": f["basis"], "size": T.TYPE["meta"], "color": T.GREY}],
                 before=3, after=2, line=1.35)
    # 追溯資訊（規則、時間、來源）放最後、最小字：給工程師核對用，不干擾一般讀者
    if f.get("trace"):
        add_para(doc, [{"text": f["trace"], "size": 7.5, "color": T.LIGHTGREY}],
                 before=2, after=4)


def compact_card(doc, f):
    """低風險／資訊提示：一行標題＋一句問題＋一句建議，不列逐頁證據。"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.keep_with_next = True
    add_run(p, f'{f["id"]}　', size=T.TYPE["finding_compact"], color=T.LIGHTGREY, bold=True)
    add_run(p, f["title"], size=T.TYPE["finding_compact"], color=T.NAVY, bold=True)
    add_run(p, f'　{f["category"]}　·　{f["scope"]}', size=T.TYPE["meta"], color=T.GREY)
    add_para(doc, [{"text": "問題　", "size": T.TYPE["label"], "color": T.GREY, "bold": True},
                   {"text": f["problem"], "size": T.TYPE["small"], "color": T.SLATE}],
             after=1, line=1.4)
    add_para(doc, [{"text": "建議　", "size": T.TYPE["label"], "color": T.GREY, "bold": True},
                   {"text": f["fix"], "size": T.TYPE["small"], "color": T.SLATE}],
             after=2, line=1.4)


def _card_label(doc, text, color=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    add_run(p, text, size=T.TYPE["label"], color=color or T.GREY, bold=True)


def severity_group_header(doc, severity, count):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    # 2026-10-11 使用者回饋：分組標題要比問題名稱明顯大，一眼看出分段
    chip_run(p, severity, size=12)
    add_run(p, f"  {severity}項目（{count} 項）", size=15, color=T.NAVY, bold=True)


# ---------- section/header/footer ----------
def _setup_section(doc):
    sec = doc.sections[0]
    sec.page_width = Emu(12240 * 635)
    sec.page_height = Emu(15840 * 635)
    sec.top_margin = Emu(1440 * 635)
    sec.bottom_margin = Emu(1440 * 635)
    sec.left_margin = Emu(1700 * 635)
    sec.right_margin = Emu(1700 * 635)
    sec.header_distance = Emu(720 * 635)
    sec.footer_distance = Emu(600 * 635)
    return sec


def _build_header(sec, site_url):
    header = sec.header
    header.is_linked_to_previous = False
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, f"ARGUS 網站健檢報告　|　{site_url}", size=9, color="5B6B7C")
    X.add_watermark_to_header(header)


def _build_footer(sec, report_id):
    footer = sec.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    X.set_para_borders(p, {"top": (4, T.LINE, "6")})
    add_run(p, "Argus AI網站健檢平台　|　第 ", size=8, color=T.GREY)
    X.add_page_number_field(p)
    add_run(p, f" 頁　|　{report_id}", size=8, color=T.GREY)


# ---------- main ----------
def generate_report(data, out_path, workdir=None):
    workdir = workdir or tempfile.mkdtemp(prefix="argus_")
    chart_paths = C.build_all(data, workdir)

    doc = Document()
    # default font
    style = doc.styles["Normal"]
    style.font.name = T.FONT_CJK
    style.font.size = Pt(10)
    style.font.color.rgb = _rgb(T.SLATE)
    _set_font_style_eastasia(style)

    sec = _setup_section(doc)
    s = data["summary"]
    meta = data["meta"]
    _build_header(sec, meta["site_url"])
    _build_footer(sec, meta["report_id"])

    _cover(doc, data, chart_paths)
    _summary(doc, data, chart_paths)
    _priorities(doc, data)
    _why_matters(doc, data)
    _findings(doc, data)
    # 第 5 章起依實際有的內容編號：有 AEO 問答檢測時獨立一章，掃描資訊與附錄順延
    next_no = 5
    if (data.get("appendix") or {}).get("aeo_items"):
        _aeo_chapter(doc, data, next_no)
        next_no += 1
    _scan_info(doc, data, chart_paths, next_no)
    _appendix(doc, data, next_no + 1)

    X.fix_zoom_setting(doc)
    doc.save(out_path)
    return out_path


def _set_font_style_eastasia(style):
    rpr = style.element.get_or_add_rPr()
    rFonts = rpr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rpr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), T.FONT_CJK)


# ---------- sections ----------
def _cover(doc, data, ch):
    s, meta = data["summary"], data["meta"]
    add_para(doc, before=70, after=0)
    add_para(doc, [{"text": "ARGUS", "size": 38, "color": T.NAVY, "bold": True}],
             align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    add_para(doc, [{"text": "網站健檢報告", "size": 18, "color": T.SLATE}],
             align=WD_ALIGN_PARAGRAPH.CENTER, after=12)
    add_image(doc, ch["score"], 2.0)
    band = T.score_band_label(s["overall_score"])
    add_para(doc, [
        {"text": f'整體分數 {s["overall_score"]} / 100　', "size": 13,
         "color": T.score_band_color(s["overall_score"]), "bold": True},
        {"text": f"（{band}）", "size": 12, "color": T.GREY}],
        align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=3)
    add_para(doc, [{"text": meta["site_url"], "size": 11, "color": T.NAVY, "bold": True}],
             align=WD_ALIGN_PARAGRAPH.CENTER, after=15)
    add_para(doc, [{"text": f'掃描完成：{s["scan_date"]}　|　報告產生：{meta.get("generated_at", s["scan_date"])}',
                    "size": 9, "color": T.GREY}],
             align=WD_ALIGN_PARAGRAPH.CENTER, after=1)
    add_para(doc, [{"text": "報告編號　", "size": 10, "color": T.SLATE},
                   {"text": meta["report_id"], "size": 10, "color": T.NAVY, "bold": True}],
             align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=1)
    add_para(doc, [{"text": "可至 Argus 網站「報告查驗」頁（/verify）輸入編號，核對本報告真偽與內容指紋。",
                    "size": 8, "color": T.LIGHTGREY}],
             align=WD_ALIGN_PARAGRAPH.CENTER, after=0)


def _summary(doc, data, ch):
    s = data["summary"]
    h1(doc, "1", "網站總覽")
    if s.get("headline"):
        add_para(doc, [{"text": s["headline"], "size": T.TYPE["body"], "color": T.SLATE}],
                 after=8, line=1.5)
    # 2026-10-11 使用者要求：第一章先用圖表呈現整體狀況（分數、分佈、前次比較、
    # 效能、連結、搜尋、拓撲與架構），要處理的問題從第 2 章開始
    h2(doc, "各分類分數")
    add_image(doc, ch["categories"], 5.5)
    add_para(doc, [{"text": "虛線為 60 / 80 分門檻。分數為各「已評估」分類的平均；標示「未評估」者不納入計算。",
                    "size": 8, "color": T.LIGHTGREY}], after=8)
    # 滿分不等於「這個面向沒有風險」。掃描器能證明的只有「我們檢查的項目沒發現
    # 問題」，證明不了完美；100 分直接呈現給不熟術語的讀者，很容易被讀成後者。
    # 這裡不人為壓低分數——把 100 改成 95 或 98 都是憑空取的數字，沒有依據——
    # 改成把這個限制明講。分類名稱取自 findings 的 category，與佔比圖同一來源。
    scored_counts = {}
    for f in data["findings"]:
        scored_counts[f["category"]] = scored_counts.get(f["category"], 0) + 1
    perfect = [
        c["name"] for c in s["categories"]
        if c.get("score") == 100 and not scored_counts.get(c["name"])
    ]
    if perfect:
        add_para(doc, [{"text": f"{'、'.join(perfect)} 為滿分，意思是本次檢查的項目全部通過，"
                                "而不是該面向已無任何風險——Argus 涵蓋的檢查項目有其範圍，"
                                "範圍見「掃描資訊與範圍」。",
                        "size": 8, "color": T.LIGHTGREY}], after=8)
    h2(doc, "發現項目分佈")
    add_image(doc, ch["severity"], 5.5)
    counts = {}
    for f in data["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    runs = []
    for sev in T.SEVERITY_ORDER:
        if counts.get(sev):
            runs.append(("chip", sev))
            runs.append({"text": f"  {counts[sev]} 項　", "size": 9, "color": T.GREY})
    # chips need special handling
    p = add_para(doc, after=8)
    for r in runs:
        if isinstance(r, tuple):
            chip_run(p, r[1])
        else:
            add_run(p, **r)
    # 分類佔比：回答「問題集中在哪一類」，與上方「各分類分數」的「這一類做得多好」
    # 互補。圖上只標得下較寬的分段，數量一律由下方文字圖例補齊。
    if "category_share" in ch:
        h2(doc, "問題集中在哪些分類")
        add_image(doc, ch["category_share"], 5.5).paragraph_format.keep_with_next = True
        cat_counts = {}
        for f in data["findings"]:
            cat_counts[f["category"]] = cat_counts.get(f["category"], 0) + 1
        legend = add_para(doc, after=8, keep_next=True)
        for name, n in [(c["name"], cat_counts.get(c["name"], 0)) for c in s["categories"]]:
            if not n:
                continue
            add_run(legend, "■ ", size=9, color=T.category_color(name))
            add_run(legend, f"{name} {n} 項　", size=9, color=T.GREY)
        # 明講數的是什麼。這裡是合併重複後的項目數，與「發現項目」章節一致；
        # Argus 網頁上的同名圖表數的是原始筆數（同一問題出現在幾個頁面就算幾筆）。
        # 兩個數字都對，但回答的是不同問題，不標註就會被當成其中一邊算錯。
        add_para(doc, [{"text": "數量為合併重複後的項目數：同一個問題出現在多個頁面只計一次，"
                                "與「發現項目」章節的項目數一致。",
                        "size": 8, "color": T.LIGHTGREY}], after=8)

    # trend
    if s.get("previous") and "trend" in ch:
        h2(doc, "與前次掃描比較")
        _trend_block(doc, s, ch)
    # scoring legend (fixed reference)
    h2(doc, "分數怎麼看")
    if s.get("score_note"):
        add_para(doc, [{"text": s["score_note"], "size": 9, "color": T.SLATE}],
                 after=6, line=1.4)
    data_table(doc, ["分數", "評級", "建議"], [
        ["80–100", "良好", "持續維持即可，建議定期複檢。"],
        ["60–79", "需改善", "有幾項體質問題值得排入維護排程。"],
        ["40–59", "建議儘快處理", "累積的問題已可能影響流量或安全，建議近期處理。"],
        ["0–39", "需優先處理", "存在較高風險的項目，建議優先安排修補。"],
    ], [1600, 2100, 4400])
    _site_metrics(doc, data, ch)
    _site_profile(doc, data.get("site_profile") or {})


def _site_profile(doc, sp):
    """網站架構（是否位於 CDN／反向代理之後）與網站優勢：報告不只列負面問題。

    每項優勢附上量到的依據；由間接訊號推論的（例如單次實驗室量測的速度）標「推論」，
    不和直接量到的設定用同樣確定的語氣（2026-10-06 審查）。
    """
    strengths = sp.get("strengths") or []
    if strengths:
        h2(doc, "網站優勢")
        for item in strengths:
            title = item["title"] + ("（推論）" if item.get("confidence") == "likely" else "")
            runs = [
                {"text": "✓  ", "size": T.TYPE["body"], "color": "15803D", "bold": True},
                {"text": title, "size": T.TYPE["body"], "color": T.SLATE, "bold": True},
                {"text": f"　{item['detail']}", "size": T.TYPE["small"], "color": T.GREY},
            ]
            if item.get("evidence"):
                runs.append({"text": f"　依據：{item['evidence']}", "size": T.TYPE["meta"],
                             "color": T.GREY})
            add_para(doc, runs, after=3, line=1.4)
    facts = sp.get("facts") or []
    if facts or sp.get("notice"):
        h2(doc, "網站架構")
        if sp.get("notice"):
            np_ = add_para(doc, [{"text": sp["notice"], "size": T.TYPE["small"], "color": "075985"}],
                           after=6, line=1.45)
            X.set_para_shading(np_, T.FIXBLUE)
            X.set_para_indent(np_, left=120, right=120)
        if facts:
            data_table(doc, ["項目", "內容"], [[f["label"], f["value"]] for f in facts],
                       [2200, 5900])


def _trend_block(doc, s, ch):
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    left, right = table.rows[0].cells
    left.width = Emu(int(3400 * 635))
    right.width = Emu(int(4700 * 635))
    for c in (left, right):
        X.set_cell_vertical_center(c)
    left.text = ""
    add_image(left.paragraphs[0], ch["trend"], 2.3)
    prev = s["previous"]
    curr_score = s["overall_score"]
    delta = curr_score - prev["score"]
    delta_str = f"+{delta} 分" if delta >= 0 else f"{delta} 分"
    delta_color = "15803D" if delta >= 0 else "B91C1C"
    comparable = prev.get("comparable", True)
    if not comparable:
        # 評分規則不同：不用綠／紅暗示進步或退步，與導讀句「不宜直接比較」一致
        delta_str += "（評分規則不同，僅供參考）"
        delta_color = T.GREY
    right.text = ""
    _r0 = right.paragraphs[0]
    add_run(_r0, "前次掃描　", size=10, color=T.GREY)
    add_run(_r0, f'{prev["date"]}　{prev["score"]} 分', size=10, color=T.SLATE, bold=True)
    p2 = right.add_paragraph()
    add_run(p2, "本次掃描　", size=10, color=T.GREY)
    add_run(p2, f'{s["scan_date"]}　{curr_score} 分', size=10, color=T.SLATE, bold=True)
    p3 = right.add_paragraph()
    add_run(p3, "變化　　　", size=10, color=T.GREY)
    add_run(p3, delta_str, size=11, color=delta_color, bold=True)
    if s.get("new_findings"):
        p4 = right.add_paragraph()
        label = "新出現" if comparable else "本次有、前次沒有（可能來自規則更新）"
        add_run(p4, f'{label} {len(s["new_findings"])} 項：{"、".join(s["new_findings"])}',
                size=9, color=T.GREY)
    _clear_table_borders(table)


def _clear_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "none")
        e.set(qn("w:sz"), "0")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "auto")
        borders.append(e)
    tblPr.append(borders)


def _priorities(doc, data):
    h1(doc, "2", "優先處理清單")
    add_para(doc, [{"text": "以下依「嚴重度 × 影響範圍」排序，是本次最值得先處理的項目。編號對應第 4 章的完整說明，可直接跳轉查看「怎麼修」。",
                    "size": 10, "color": T.SLATE}], after=8, line=1.44, keep_next=True)
    rows = []
    for i, pr in enumerate(data.get("priorities", []), 1):
        rows.append([str(i), ("chip", pr["severity"]), pr["problem"],
                     pr.get("category", ""), pr.get("ref", "")])
    if rows:
        data_table(doc, ["#", "嚴重度", "問題", "分類", "詳見"], rows,
                   [600, 1300, 3900, 1300, 1000])
    # 改一處就能一起解決的問題（Argus 在地修改：root_causes.py，與問題分析頁同一套歸類）
    causes = data["summary"].get("root_causes") or []
    if causes:
        h2(doc, "改一處就能一起解決")
        for cause in causes:
            p = add_para(doc, after=1, line=1.4)
            add_run(p, cause["title"], size=T.TYPE["body"], color=T.SLATE, bold=True)
            add_run(p, f'　{len(cause["refs"])} 項：{"、".join(cause["refs"])}',
                    size=T.TYPE["meta"], color=T.GREY)
            add_para(doc, [{"text": f'在哪裡修：{cause["where"]}', "size": T.TYPE["meta"],
                            "color": T.GREY}], after=5)
    if data["summary"].get("priority_note"):
        add_para(doc, [{"text": data["summary"]["priority_note"], "size": 9, "color": T.GREY}],
                 before=6, after=0, line=1.38)


def _why_matters(doc, data):
    items = data.get("why_matters", [])
    h1(doc, "3", "這些分類為什麼重要", page_break=False)
    add_para(doc, [{"text": "在逐項細節之前，先說明本次最弱的面向若不處理會有什麼實際後果，幫助你判斷投入的優先次序。",
                    "size": 10, "color": T.SLATE}], after=8, line=1.44, keep_next=True)
    if not items:
        # 章節固定存在（第 4 章的編號與說明都引用它）；沒有需要說明的分類就寫明
        add_para(doc, [{"text": "本次沒有中風險以上、需要特別說明後果的分類。", "size": 9.5,
                        "color": T.GREY}], after=6)
        return
    rows = [[it["category"], it["consequence"]] for it in items]
    data_table(doc, ["分類", "沒處理的話會怎樣"], rows, [2600, 5500])


def _findings(doc, data):
    h1(doc, "4", "發現項目")
    n = len(data["findings"])
    add_para(doc, [{"text": f"共 {n} 項，依嚴重度由高至低分組排列。每一張卡片獨立完整：問題是什麼、怎麼修、以及當下觀測到的檢測依據。各分類「為什麼重要」見第 3 章，修補後如何驗證見附錄「修補後如何驗證」。",
                    "size": 10, "color": T.SLATE}], after=6, line=1.44)
    # 資安與網站內容改善分開呈現（沒有 group 欄位的舊 payload 全部歸在同一段）
    parts = [
        ("security", "資訊安全", "可能被利用或造成資料外洩的項目。"),
        ("content", "網站內容與體驗（SEO／AEO／GEO／UX）",
         "影響搜尋、AI 理解與使用體驗的改善建議；每一項附有規則依據與適用限制。"),
    ]
    has_groups = any(f.get("group") for f in data["findings"])
    for key, title, intro in parts if has_groups else [(None, None, None)]:
        items = [f for f in data["findings"] if key is None or f.get("group") == key]
        if not items:
            continue
        if title:
            h2(doc, f"{title}（{len(items)} 項）")
            add_para(doc, [{"text": intro, "size": 9, "color": T.GREY}], after=4)
        by_sev = {}
        for f in items:
            by_sev.setdefault(f["severity"], []).append(f)
        for sev in T.SEVERITY_ORDER:
            group = by_sev.get(sev, [])
            if not group:
                continue
            severity_group_header(doc, sev, len(group))
            for f in group:
                finding_card(doc, f)


def _site_metrics(doc, data, ch):
    """第 1 章後段：網站效能、連結、搜尋與拓撲（Argus 在地擴充，2026-10-11）。

    網頁上有、報告原本沒有的資訊：PageSpeed 效能分數、SEO 分析頁的連結檢查、
    Search Console 實際搜尋詞與網站拓撲；與網頁同一份資料、不計入分數。
    沒有資料的段落寫明原因。
    """
    sm = data.get("site_metrics") or {}
    if not sm:
        return
    _performance_section(doc, sm.get("performance") or {}, ch)
    _links_section(doc, sm.get("links") or {}, ch)
    _search_section(doc, sm.get("search") or {}, ch)
    _topology_section(doc, sm.get("topology") or {}, ch)


def _note(doc, text, keep_next=False):
    add_para(doc, [{"text": text, "size": 9.5, "color": T.GREY}], after=6, line=1.4,
             keep_next=keep_next)


def _rating_cell(rating):
    color = {"良好": "15803D", "需改善": "B45309", "不佳": "B91C1C"}.get(rating, T.GREY)
    return [{"text": rating or "—", "size": 9.5, "color": color, "bold": bool(rating)}]


def _performance_section(doc, perf, ch):
    h2(doc, "Google Lighthouse 首頁檢查（PageSpeed Insights）")
    if not perf.get("scores"):
        _note(doc, perf.get("note") or "本次沒有效能量測。")
        return
    _note(doc, f"行動版、首頁{('（' + perf['url'] + '）') if perf.get('url') else ''}，"
               "由 Google Lighthouse 實驗室單次量測；90 分以上為良好、50–89 需改善、50 以下不佳。",
          keep_next=True)
    add_image(doc, ch["perf_gauges"], 6.0).paragraph_format.keep_with_next = True
    pages = f"全部 {perf['pages']} 頁" if perf.get("pages") else "全部頁面"
    add_para(doc, [{"text": f"只看首頁的基本項目；本章開頭的 Argus 分數檢查{pages}，兩者不同是正常的。",
                    "size": 9, "color": T.GREY}], after=6, line=1.4, keep_next=True)
    if perf.get("metrics"):
        data_table(doc, ["實驗室指標", "數值", "評等"],
                   [[m["label"], m["value"] or "—", _rating_cell(m["rating"])]
                    for m in perf["metrics"]], [3800, 2400, 1900])
    if perf.get("lab_note"):
        add_para(doc, [{"text": perf["lab_note"], "size": 9, "color": T.GREY}],
                 before=3, after=4, line=1.4)
    if perf.get("field"):
        add_para(doc, [{"text": f"真實使用者體驗（CrUX，過去 28 天，{perf['field_scope']}）",
                        "size": T.TYPE["label"], "color": T.NAVY, "bold": True}],
                 before=8, after=3, keep_next=True)
        data_table(doc, ["指標", "第 75 百分位", "評等"],
                   [[m["label"], m["value"], _rating_cell(m["rating"])] for m in perf["field"]],
                   [3800, 2400, 1900])
    elif perf.get("field_note"):
        add_para(doc, [{"text": "真實使用者體驗（CrUX）：" + perf["field_note"], "size": 9.5,
                        "color": T.GREY}], before=6, after=6, line=1.4)
    if perf.get("opportunities"):
        add_para(doc, [{"text": "最值得先改善的項目", "size": T.TYPE["label"], "color": T.NAVY,
                        "bold": True}], before=8, after=3, keep_next=True)
        for o in perf["opportunities"]:
            add_para(doc, [{"text": "•  " + o["title"], "size": 9.5, "color": T.SLATE},
                           {"text": f"　{o['saving']}" if o.get("saving") else "", "size": 9,
                            "color": T.GREY}], after=1, line=1.35)


def _links_section(doc, links, ch):
    h2(doc, "連結檢查（站內、子網域與站外）")
    if not links.get("matrix"):
        _note(doc, links.get("note") or "本次沒有連結檢查。")
        return
    when = f"，檢查時間 {links['checked_at']}" if links.get("checked_at") else ""
    _note(doc, f"共 {links['total']} 個不重複的連結目標{when}。「無法確認」是對方拒絕檢查、逾時或無法連線，"
               "不一定是失效；「未檢查」是超過檢查數量或時間上限。", keep_next=True)
    if "link_matrix" in ch:
        add_image(doc, ch["link_matrix"], 5.2)
    if links.get("broken"):
        add_para(doc, [{"text": f"失效連結（{links['broken_total']} 個）", "size": T.TYPE["label"],
                        "color": "B91C1C", "bold": True}], before=6, after=3, keep_next=True)
        data_table(doc, ["網址", "狀態", "類型", "出現在"],
                   [[b["url"], b["status"], b["type"], b["sources"]] for b in links["broken"]],
                   [3600, 1300, 900, 2300])
        if links["broken_total"] > len(links["broken"]):
            _note(doc, f"另有 {links['broken_total'] - len(links['broken'])} 個，完整清單見網頁版「SEO 分析 → 連結」。")
    else:
        _note(doc, "沒有發現失效連結。")
    if links.get("external"):
        add_para(doc, [{"text": f"站外連結（共 {links['external_total']} 個，列出最常出現的 "
                                f"{len(links['external'])} 個）", "size": T.TYPE["label"],
                        "color": T.NAVY, "bold": True}], before=6, after=3, keep_next=True)
        data_table(doc, ["網址", "狀態", "出現在"],
                   [[e["url"], e["status"], e["sources"]] for e in links["external"]],
                   [4200, 1600, 2300])


def _search_section(doc, search, ch):
    h2(doc, "實際搜尋詞（Google Search Console）")
    if not search.get("totals"):
        _note(doc, search.get("note") or "沒有 Search Console 資料。")
        return
    _note(doc, f"資源 {search['property']}・期間 {search['period']}（Search Console 資料約延遲 2–3 天；"
               f"報告產生時取得：{search['fetched_at']}）。", keep_next=True)
    add_image(doc, ch["search_kpis"], 6.2).paragraph_format.keep_with_next = True
    if "search_trend" in ch:
        add_image(doc, ch["search_trend"], 6.2)
    if search.get("queries"):
        add_para(doc, [{"text": f"點擊最多的搜尋詞（前 {len(search['queries'])} 個）",
                        "size": T.TYPE["label"], "color": T.NAVY, "bold": True},],
                 before=6, after=3, keep_next=True)
        data_table(doc, ["搜尋詞", "點擊", "曝光", "CTR", "平均排名", "對應頁面"],
                   [[q["query"], f"{q['clicks']:,}", f"{q['impressions']:,}",
                     f"{q['ctr'] * 100:.1f}%", f"{q['position']:.1f}", q["page"] or "—"]
                    for q in search["queries"]],
                   [1900, 650, 850, 950, 1050, 2700])
        _note(doc, "平均排名是期間內所有曝光的平均統計值，不是某一刻的即時名次。")


def _topology_section(doc, topo, ch):
    h2(doc, "網站拓撲")
    if not topo.get("nodes"):
        _note(doc, topo.get("note") or "沒有可以畫的網站結構。")
        return
    shown = len(topo["nodes"])
    extra = f"，圖中顯示前 {shown} 頁" if topo.get("total", shown) > shown else ""
    first_layer = sum(1 for n in topo["nodes"] if n.get("depth") == 1)
    labels = (
        "標籤只列入口頁與第一層頁面的路徑。" if first_layer <= C.TOPOLOGY_MAX_LABELS
        else f"第一層有 {first_layer} 頁，標籤太多會重疊，圖中只標入口頁；各頁網址見網頁版「網站拓撲」。"
    )
    _note(doc, f"入口頁在中央，越外圈離首頁越多次點擊；節點顏色是該頁最嚴重的問題等級。"
               f"本次共 {topo.get('total', shown)} 頁{extra}，{labels}",
          keep_next=True)
    add_image(doc, ch["topology"], 5.0)


def _aeo_chapter(doc, data, number):
    """AEO 問答檢測逐題結果（2026-10-11 從附錄獨立成章：這是檢測結果，不是參考資料）。"""
    items = data["appendix"]["aeo_items"]
    h1(doc, str(number), "AEO 問答檢測結果")
    add_para(doc, [{"text": "Argus 依網站內容建立訪客可能會問的問題，逐題檢查能否在已掃描的頁面中找到答案，"
                            "並附上答案原文與位置。判定不是「可回答」的題目，也列在第 4 章的發現項目中並附修正建議。",
                    "size": 10, "color": T.SLATE}], after=6, line=1.44, keep_next=True)
    counts = {}
    for item in items:
        label = item["verdict"].split("（")[0]
        counts[label] = counts.get(label, 0) + 1
    add_para(doc, [{"text": f"共 {len(items)} 題：" + "、".join(f"{k} {v} 題" for k, v in counts.items()),
                    "size": T.TYPE["label"], "color": T.NAVY, "bold": True}], after=4, keep_next=True)
    rows = [[i["question"], i["verdict"], i["basis"]] for i in items]
    data_table(doc, ["題目", "判定", "答案原文或理由"], rows, [2300, 1300, 4500])


def _scan_info(doc, data, ch, number=5):
    si = data.get("scan_info", {})
    h1(doc, str(number), "掃描資訊與範圍", page_break=False)
    add_para(doc, [{"text": "本節說明這份報告涵蓋與未涵蓋的範圍，以及掃描當下擷取的網站畫面，供你確認判讀基礎。",
                    "size": 10, "color": T.SLATE}], after=8, line=1.44, keep_next=True)
    h2(doc, "掃描範圍")
    scope = si.get("scope", {})
    rows = [[k, str(v)] for k, v in scope.items()]
    if rows:
        data_table(doc, ["項目", "設定"], rows, [2600, 5500])
    if si.get("warnings"):
        h2(doc, "掃描警示")
        for w in si["warnings"]:
            add_para(doc, [{"text": f"•  {w}", "size": 9.5, "color": T.SLATE}],
                     after=2, line=1.38)
    if si.get("screenshot"):
        # 全頁截圖縮到 2.3 吋寬時字小到看不清，標題、圖、圖說還會各自掉到不同頁：
        # 只取第一屏放大，並把三者綁在一起
        h2(doc, "掃描當下的網站畫面（首屏）")
        shot = _first_screen(si["screenshot"])
        add_image(doc, shot, 4.3).paragraph_format.keep_with_next = True
        add_para(doc, [{"text": si.get("screenshot_caption", ""), "size": 8, "color": T.GREY}],
                 align=WD_ALIGN_PARAGRAPH.CENTER, after=0)


def _first_screen(path):
    """全頁截圖只留頂端一屏（寬高比 4:3）；失敗時用原圖。"""
    try:
        from PIL import Image

        with Image.open(path) as im:
            width, height = im.size
            limit = int(width * 0.75)
            if height <= limit:
                return path
            out = os.path.join(tempfile.mkdtemp(prefix="argus_"), "first-screen.png")
            im.crop((0, 0, width, limit)).save(out)
            return out
    except Exception:  # noqa: BLE001 — 截圖只是輔助，裁切失敗不能讓報告產不出來
        return path


def _appendix(doc, data, number=6):
    """附錄：小節依實際有的內容連續編號；「免責與報告產生方式」固定在整份報告最後。"""
    ap = data.get("appendix", {})
    h1(doc, str(number), "附錄")
    counter = iter(range(1, 20))

    def sub(title):
        h2(doc, f"{number}.{next(counter)}　{title}")

    if ap.get("glossary"):
        sub("名詞解釋")
        add_para(doc, [{"text": "只列出本報告實際用到的專有名詞，方便對照閱讀。", "size": 9, "color": T.GREY}], after=5)
        rows = [[g["term"], g["explanation"]] for g in ap["glossary"]]
        data_table(doc, ["名詞", "白話說明"], rows, [1800, 6300])
    if ap.get("tech_index"):
        sub("技術索引")
        add_para(doc, [{"text": "供工程師與稽核人員對照。OWASP 為國際公認的網站安全風險分類（依 2025 版，括號內為 2021 版代號），CWE 為通用軟體弱點編號；一般讀者可略過。",
                        "size": 9, "color": T.GREY}], after=5)
        rows = [[t["ref"], t["rule_id"], t.get("owasp_cwe", "— / —")] for t in ap["tech_index"]]
        data_table(doc, ["項次", "規則 ID", "OWASP / CWE"], rows, [1000, 3700, 3400])
    api = ap.get("api_surface")
    if api:
        sub("API 端點清單")
        shown = len(api["rows"])
        static_n = api.get("static_discovered", 0)
        total_all = api["total"] + static_n
        more = f"列出前 {shown} 個，有問題的排前面。" if total_all > shown else ""
        static_txt = (
            f"另有 {static_n} 個端點由前端 JS 靜態發現、執行期未實際呼叫（標示「靜態」，僅供參考）。"
            if static_n else ""
        )
        add_para(doc, [{"text": f"掃描時網站前端自己呼叫的同網站 API 共 {api['total']} 個，其中 {api['with_issues']} 個有問題。"
                                f"只分析這些回應，不另外發送請求，也不保存網址參數與回應內容。{static_txt}{more}",
                        "size": 9, "color": T.GREY}], after=5)
        rows = [[r["method"], r["path"], r["status"], r["content_type"], r["issues"]] for r in api["rows"]]
        data_table(doc, ["方法", "路徑", "狀態碼", "內容類型", "發現"], rows, [900, 3300, 900, 1700, 1300])
    sub("修補後如何驗證")
    add_para(doc, [{"text": ap.get("verify_note",
                    "完成修補後，重新執行一次 Argus 掃描，確認對應項目不再出現；下一份報告的摘要會列出這次解決了哪些項目。"),
                    "size": 10, "color": T.SLATE}], after=8, line=1.44)
    # 只逐項列中風險以上；低風險與資訊提示重新掃描即可確認（舊版全列，佔掉 5 頁）
    severity_by_ref = {f["id"]: f["severity"] for f in data.get("findings", [])}
    items = [v for v in ap.get("verify_items") or []
             if severity_by_ref.get(v["ref"]) in _FULL_CARD_SEVERITIES]
    if items:
        rows = [[v["ref"], v["title"], v["how"]] for v in items]
        data_table(doc, ["項次", "項目", "如何確認已修好"], rows, [900, 2500, 4700])
    hidden = len(ap.get("verify_items") or []) - len(items)
    if hidden > 0:
        add_para(doc, [{"text": f"其餘 {hidden} 項低風險與資訊提示：修正後重新掃描，確認該項不再出現即可。",
                        "size": T.TYPE["label"], "color": T.GREY}], before=4, after=6)
    # 逐項扣分（Argus 在地修改：與網頁「分數說明」分頁同一份資料，讀者可自行加總核對）
    score_items = ap.get("score_items") or {}
    if score_items:
        sub("各分類扣分明細")
        add_para(doc, [{"text": "每一項的扣分依嚴重度固定（嚴重 60、高 35、中 12、低 4），同一個問題出現在多頁只扣一次；"
                                "「只修好這項時」是其他問題不變、只修好這一項後的分類分數。",
                        "size": 9, "color": T.GREY}], after=5)
        if score_items.get("note"):
            add_para(doc, [{"text": score_items["note"], "size": 10, "color": T.SLATE}], after=6, line=1.44)
        for cat in score_items.get("categories") or []:
            add_para(doc, [{"text": f'{cat["name"]}　{cat["score"]} 分', "size": T.TYPE["body"],
                            "color": T.SLATE, "bold": True},
                           {"text": f'　{cat["basis"]}', "size": T.TYPE["meta"], "color": T.GREY}],
                     before=6, after=3, keep_next=True)
            if cat["items"]:
                rows = [[i.get("ref") or "—", i["title"], i["severity"], f'−{i["weight"]}',
                         str(i["occurrences"]), f'{i["score_without"]} 分'] for i in cat["items"]]
                data_table(doc, ["項次", "項目", "嚴重度", "扣分", "出現處", "只修好這項時"], rows,
                           [800, 3300, 1100, 800, 900, 1200])
            else:
                add_para(doc, [{"text": "沒有扣分項目。", "size": 9, "color": T.GREY}], after=3)
            if cat.get("notes"):
                add_para(doc, [{"text": cat["notes"] + "。", "size": T.TYPE["meta"], "color": T.GREY}],
                         before=2, after=4)
    if ap.get("authorization"):
        sub("掃描授權聲明")
        auth = ap["authorization"]
        rows = [[k, str(v)] for k, v in auth.items()]
        data_table(doc, ["項目", "內容"], rows, [2600, 5500])
    # 免責與報告產生方式：放在整份報告的最後（2026-10-11 使用者要求）
    sub("免責與報告產生方式")
    add_para(doc, [{"text": "本報告僅反映掃描當下、從網際網路可觀測到的外部特徵，不等同完整滲透測試或原始碼稽核，也不構成法律或合規意見。未列出的項目不代表不存在風險，實際修補請由具備權限的維運人員評估後執行。",
                    "size": 10, "color": T.SLATE}], after=6, line=1.44)
    add_para(doc, [{"text": ap.get("method_note") or "本報告採 Evidence-first 原則：每一項發現都附上掃描當下實際觀測到的內容。",
                    "size": 10, "color": T.SLATE}], after=0, line=1.44)
