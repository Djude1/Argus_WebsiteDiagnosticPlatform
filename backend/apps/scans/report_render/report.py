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


def chip_run(paragraph, severity):
    meta = T.SEVERITY[severity]
    add_run(paragraph, f" {severity} ", size=9, color=meta["text"], bold=True,
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


def data_table(doc, headers, rows, widths):
    """rows: list of lists; each cell is str OR list-of-run-dicts OR ('chip',sev)."""
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
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    chip_run(p, severity)
    add_run(p, f"  {severity}項目（{count} 項）", size=11.5, color=T.NAVY, bold=True)


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
    add_run(p, "Argus 網站健檢平台　|　第 ", size=8, color=T.GREY)
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
    _scan_info(doc, data, chart_paths)
    _appendix(doc, data)

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
    h1(doc, "1", "一頁摘要")
    if s.get("headline"):
        add_para(doc, [{"text": s["headline"], "size": T.TYPE["body"], "color": T.SLATE}],
                 after=8, line=1.5)
    # 摘要頁要能直接回答「先做什麼」（2026-10-06 審查）：優先清單前三項提到最前面
    top = (data.get("priorities") or [])[:3]
    if top:
        h2(doc, f"建議先處理這 {len(top)} 件事")
        for i, pr in enumerate(top, 1):
            p = add_para(doc, after=3, line=1.4)
            add_run(p, f"{i}.  ", size=T.TYPE["body"], color=T.SLATE, bold=True)
            chip_run(p, pr["severity"])
            add_run(p, f"  {pr['problem']}", size=T.TYPE["body"], color=T.SLATE, bold=True)
            if pr.get("ref"):
                add_run(p, f"　詳見 {pr['ref']}", size=T.TYPE["meta"], color=T.GREY)
    # 改一處就能一起解決的問題（Argus 在地修改：root_causes.py，與問題分析頁同一套歸類）
    causes = s.get("root_causes") or []
    if causes:
        h2(doc, "改一處就能一起解決")
        for cause in causes:
            p = add_para(doc, after=1, line=1.4)
            add_run(p, cause["title"], size=T.TYPE["body"], color=T.SLATE, bold=True)
            add_run(p, f'　{len(cause["refs"])} 項：{"、".join(cause["refs"])}',
                    size=T.TYPE["meta"], color=T.GREY)
            add_para(doc, [{"text": f'在哪裡修：{cause["where"]}', "size": T.TYPE["meta"],
                            "color": T.GREY}], after=5)
    _site_profile(doc, data.get("site_profile") or {})
    scores_heading = h2(doc, "各分類分數")
    if data.get("site_profile"):
        # 網站概況已佔滿第一頁：分數圖從新頁開始，避免標題孤零零留在頁尾
        scores_heading.paragraph_format.page_break_before = True
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
        add_image(doc, ch["category_share"], 5.5)
        cat_counts = {}
        for f in data["findings"]:
            cat_counts[f["category"]] = cat_counts.get(f["category"], 0) + 1
        legend = add_para(doc, after=8)
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
        add_run(p4, f'新出現 {len(s["new_findings"])} 項：{"、".join(s["new_findings"])}',
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
                    "size": 10, "color": T.SLATE}], after=8, line=1.44)
    rows = []
    for i, pr in enumerate(data.get("priorities", []), 1):
        rows.append([str(i), ("chip", pr["severity"]), pr["problem"],
                     pr.get("category", ""), pr.get("ref", "")])
    if rows:
        data_table(doc, ["#", "嚴重度", "問題", "分類", "詳見"], rows,
                   [600, 1300, 3900, 1300, 1000])
    if data["summary"].get("priority_note"):
        add_para(doc, [{"text": data["summary"]["priority_note"], "size": 9, "color": T.GREY}],
                 before=6, after=0, line=1.38)


def _why_matters(doc, data):
    items = data.get("why_matters", [])
    if not items:
        return
    h1(doc, "3", "這些分類為什麼重要", page_break=False)
    add_para(doc, [{"text": "在逐項細節之前，先說明本次最弱的面向若不處理會有什麼實際後果，幫助你判斷投入的優先次序。",
                    "size": 10, "color": T.SLATE}], after=8, line=1.44)
    rows = [[it["category"], it["consequence"]] for it in items]
    data_table(doc, ["分類", "沒處理的話會怎樣"], rows, [2600, 5500])


def _findings(doc, data):
    h1(doc, "4", "發現項目")
    n = len(data["findings"])
    add_para(doc, [{"text": f"共 {n} 項，依嚴重度由高至低分組排列。每一張卡片獨立完整：問題是什麼、怎麼修、以及當下觀測到的檢測依據。各分類「為什麼重要」見第 3 章，修補後如何驗證見附錄 6.3。",
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


def _scan_info(doc, data, ch):
    si = data.get("scan_info", {})
    h1(doc, "5", "掃描資訊與範圍", page_break=False)
    add_para(doc, [{"text": "本節說明這份報告涵蓋與未涵蓋的範圍，以及掃描當下擷取的網站畫面，供你確認判讀基礎。",
                    "size": 10, "color": T.SLATE}], after=8, line=1.44)
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
        h2(doc, "掃描當下的網站畫面")
        add_image(doc, si["screenshot"], 2.3)
        add_para(doc, [{"text": si.get("screenshot_caption", ""), "size": 8, "color": T.GREY}],
                 align=WD_ALIGN_PARAGRAPH.CENTER, after=0)


def _appendix(doc, data):
    ap = data.get("appendix", {})
    h1(doc, "6", "附錄")
    # glossary
    if ap.get("glossary"):
        h2(doc, "6.1　名詞解釋")
        add_para(doc, [{"text": "只列出本報告實際用到的專有名詞，方便對照閱讀。", "size": 9, "color": T.GREY}], after=5)
        rows = [[g["term"], g["explanation"]] for g in ap["glossary"]]
        data_table(doc, ["名詞", "白話說明"], rows, [1800, 6300])
    # tech index
    if ap.get("tech_index"):
        h2(doc, "6.2　技術索引")
        add_para(doc, [{"text": "供工程師與稽核人員對照。OWASP 為國際公認的網站安全風險分類，CWE 為通用軟體弱點編號；一般讀者可略過。",
                        "size": 9, "color": T.GREY}], after=5)
        rows = [[t["ref"], t["rule_id"], t.get("owasp_cwe", "— / —")] for t in ap["tech_index"]]
        data_table(doc, ["項次", "規則 ID", "OWASP / CWE"], rows, [1200, 4400, 2500])
    # verify
    h2(doc, "6.3　修補後如何驗證")
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
    # authorization
    if ap.get("authorization"):
        h2(doc, "6.4　掃描授權聲明")
        auth = ap["authorization"]
        rows = [[k, str(v)] for k, v in auth.items()]
        data_table(doc, ["項目", "內容"], rows, [2600, 5500])
    # disclaimer
    h2(doc, "6.5　免責與報告產生方式")
    add_para(doc, [{"text": "本報告僅反映掃描當下、從網際網路可觀測到的外部特徵，不等同完整滲透測試或原始碼稽核，也不構成法律或合規意見。未列出的項目不代表不存在風險，實際修補請由具備權限的維運人員評估後執行。",
                    "size": 10, "color": T.SLATE}], after=6, line=1.44)
    add_para(doc, [{"text": ap.get("method_note") or "本報告採 Evidence-first 原則：每一項發現都附上掃描當下實際觀測到的內容。",
                    "size": 10, "color": T.SLATE}], after=0, line=1.44)
    # AEO 逐題結果（Argus 在地修改：可回答性檢測的每一題與原文證據）
    if ap.get("aeo_items"):
        h2(doc, "6.6　AEO 問答檢測逐題結果")
        add_para(doc, [{"text": "Argus 依網站內容建立的問題，以及在已掃描頁面中找到的答案原文與位置；"
                                "判定不是「可回答」的題目也列在發現清單中，附修正建議。",
                        "size": 9, "color": T.GREY}], after=5)
        rows = [[i["question"], i["verdict"], i["basis"]] for i in ap["aeo_items"]]
        data_table(doc, ["題目", "判定", "答案原文或理由"], rows, [2300, 1100, 4700])
    # 逐項扣分（Argus 在地修改：與網頁「分數說明」分頁同一份資料，讀者可自行加總核對）
    score_items = ap.get("score_items") or {}
    if score_items:
        h2(doc, f"6.{7 if ap.get('aeo_items') else 6}　各分類扣分明細")
        add_para(doc, [{"text": "每一項的扣分依嚴重度固定（嚴重 60、高 35、中 12、低 4），同一個問題出現在多頁只扣一次；"
                                "「只修好這項時」是其他問題不變、只修好這一項後的分類分數。",
                        "size": 9, "color": T.GREY}], after=5)
        if score_items.get("note"):
            add_para(doc, [{"text": score_items["note"], "size": 10, "color": T.SLATE}], after=6, line=1.44)
        for cat in score_items.get("categories") or []:
            add_para(doc, [{"text": f'{cat["name"]}　{cat["score"]} 分', "size": T.TYPE["body"],
                            "color": T.SLATE, "bold": True},
                           {"text": f'　{cat["basis"]}', "size": T.TYPE["meta"], "color": T.GREY}],
                     before=6, after=3)
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
