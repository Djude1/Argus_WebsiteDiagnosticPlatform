from pathlib import Path
from copy import deepcopy
from io import BytesIO
import json
import hashlib
import re
from zipfile import ZipFile, ZIP_DEFLATED
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.enum.section import WD_SECTION_START

HERE = Path(__file__).resolve().parents[2] / '本機資料' / 'work' / 'v10'
ROOT = HERE.parents[1]
REF = ROOT / 'Argus_系統手冊_v4.docx'
TECH = ROOT / 'Argus_系統手冊_v9_新版整合修訂版.docx'
FINAL = ROOT / 'Argus_系統手冊_v10_複審精簡版.docx'
ref = Document(REF)
tech = Document(TECH)
doc = Document(REF)
ref_blocks = list(ref.element.body)
tech_blocks = list(tech.element.body)
pages = json.loads((HERE / 'page_map.json').read_text(encoding='utf-8')) if (HERE / 'page_map.json').exists() else {}

def plain(e):
    return ''.join(e.xpath('.//w:t/text()')).replace('\u200b', '')

def assign_text(e, text):
    nodes = e.xpath('.//w:t')
    if nodes:
        nodes[0].text = text
        for n in nodes[1:]:
            n.text = ''

def font(r, size, bold=None):
    r.font.name = 'Times New Roman'
    r.font.size = Pt(size)
    if bold is not None:
        r.font.bold = bold
    r.font.color.rgb = RGBColor(0, 0, 0)
    rf = r._r.get_or_add_rPr().get_or_add_rFonts()
    for k, v in [('ascii', 'Times New Roman'), ('hAnsi', 'Times New Roman'), ('eastAsia', 'DFKai-SB')]:
        rf.set(qn('w:' + k), v)

def reset_font(p, size=14, bold=None):
    for r in p.runs:
        font(r, size, bold)

def strip_legacy(e):
    for x in e.xpath('.//w:bookmarkStart | .//w:bookmarkEnd | .//w:lastRenderedPageBreak'):
        x.getparent().remove(x)
    for x in e.xpath('.//w:sectPr'):
        x.getparent().remove(x)

def import_block(e, source):
    out = deepcopy(e)
    strip_legacy(out)
    if source is tech:
        for node in out.iter():
            for attr in (qn('r:embed'), qn('r:id'), qn('r:link')):
                old = node.get(attr)
                if not old:
                    continue
                rel = source.part.rels[old]
                if rel.reltype.endswith('/image'):
                    new, _ = doc.part.get_or_add_image(BytesIO(rel.target_part.blob))
                elif rel.is_external:
                    new = doc.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
                else:
                    raise ValueError('不支援的匯入關係 ' + rel.reltype)
                node.set(attr, new)
    return out

body = doc.element.body
last_sect = deepcopy(ref.sections[0]._sectPr)
for x in list(body):
    body.remove(x)
for x in last_sect.xpath('./w:headerReference | ./w:footerReference | ./w:pgNumType | ./w:titlePg'):
    last_sect.remove(x)
body.append(last_sect)

for name, size, bold in [('Normal', 14, False), ('Heading 1', 18, True), ('Heading 2', 16, True), ('Heading 3', 14, True), ('FigCap', 14, True), ('TblCap', 14, True), ('Caption', 14, True)]:
    s = doc.styles[name]
    s.font.name = 'Times New Roman'
    s.font.size = Pt(size)
    s.font.bold = bold
    s.font.color.rgb = RGBColor(0, 0, 0)
    s.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), 'DFKai-SB')
    pf = s.paragraph_format
    pf.line_spacing = 1
    pf.space_after = Pt(4 if name == 'Normal' else 5)
    pf.space_before = Pt(8 if name.startswith('Heading') else 0)
    pf.first_line_indent = Pt(28 if name == 'Normal' else 0)
    pf.keep_with_next = name.startswith('Heading') or name == 'TblCap'
    pf.keep_together = True if name != 'Normal' else False
    if name == 'Normal':
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    elif name in ('Heading 1', 'TblCap', 'FigCap', 'Caption'):
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER

def append(e):
    body.insert(len(body) - 1, e)
    return e

def new_p(text, style='Normal'):
    p = doc.add_paragraph(text, style=style)
    reset_font(p, 18 if style == 'Heading 1' else 16 if style == 'Heading 2' else 14, style != 'Normal')
    return p

def setup_section(s, fmt=None):
    s.page_width = Cm(21.59)
    s.page_height = Cm(27.94)
    s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Cm(1.5)
    s.header_distance = s.footer_distance = Cm(1)
    s.header.is_linked_to_previous = False
    s.footer.is_linked_to_previous = False
    for part in (s.header, s.footer):
        for p in part.paragraphs:
            p.clear()
    for x in s._sectPr.xpath('./w:pgNumType'):
        s._sectPr.remove(x)
    if fmt:
        num = OxmlElement('w:pgNumType')
        num.set(qn('w:fmt'), fmt)
        num.set(qn('w:start'), '1')
        s._sectPr.append(num)
        p = s.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Pt(0)
        f = OxmlElement('w:fldSimple')
        f.set(qn('w:instr'), 'PAGE')
        p._p.append(f)

setup_section(doc.sections[0])
for i in range(13):
    e = import_block(ref_blocks[i], ref)
    if i == 12:
        assign_text(e, '中華民國115年10月6日')
    if i == 10:
        assign_text(e, ''.join(Document(FINAL).element.body[10].xpath('.//w:t/text()')))
    append(e)

setup_section(doc.add_section(WD_SECTION_START.NEW_PAGE), 'lowerRoman')
toc_start = len(body) - 1
new_p('目錄', 'Heading 1')
toc_placeholder = doc.add_paragraph()
setup_section(doc.add_section(WD_SECTION_START.NEW_PAGE), 'decimal')

manifest = []
kept_technical = []
source_notes = []
bookmark_id = 1000
OMIT_FIGURES = {'圖12-1-1', '圖12-4-1', '圖12-6-2', '圖12-7-1', '圖12-8-3', '圖12-8-4'}
FIGURE_RENUMBER = {'圖12-1-2': '圖12-1-1', '圖12-4-2': '圖12-4-1', '圖12-4-3': '圖12-4-2', '圖12-6-3': '圖12-6-2', '圖12-6-4': '圖12-6-3', '圖12-7-2': '圖12-7-1', '圖12-7-3': '圖12-7-2'}

def register(e, title, kind, level=1):
    global bookmark_id
    bookmark_id += 1
    name = 'v10b' + str(bookmark_id)
    a = OxmlElement('w:bookmarkStart')
    a.set(qn('w:id'), str(bookmark_id))
    a.set(qn('w:name'), name)
    b = OxmlElement('w:bookmarkEnd')
    b.set(qn('w:id'), str(bookmark_id))
    e.insert(0, a)
    e.append(b)
    manifest.append({'title': title, 'bookmark': name, 'kind': kind, 'level': level})

def format_table(e, original=False, label=''):
    t = Table(e, doc._body)
    n = len(t.columns)
    compact_matrix = original and label.lstrip().startswith('表 2-4-1')
    # 保留參考原有合併格、甘特圖填色及分工符號。
    t.autofit = False
    if not original:
        widths = {2: [4.3, 14.29], 3: [3.0, 4.0, 11.59], 4: [4.7, 2.8, 4.0, 7.09]}.get(n, [18.59 / n] * n)
        if label.startswith('表5-1-'):
            widths = [4.2, 14.39]
        if label.startswith('表8-2-'):
            widths = [4.6, 2.6, 5.4, 5.99]
        if label.startswith('表11-1-'):
            widths = [2.0, 5.1, 5.2, 6.29]
        if label.startswith(('表14-2-', '表A-1 ')):
            widths = [1.2, 3.4, 11.39, 2.6]
        if label.startswith('表B-'):
            widths = [7.7, 10.89]
        for col, w in zip(t.columns, widths):
            col.width = Cm(w)
        for row in t.rows:
            for c, w in zip(row.cells, widths):
                c.width = Cm(w)
        pr = t._tbl.tblPr
        for old in pr.xpath('./w:tblBorders | ./w:tblCellMar'):
            pr.remove(old)
        borders = OxmlElement('w:tblBorders')
        for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            x = OxmlElement('w:' + side)
            x.set(qn('w:val'), 'single')
            x.set(qn('w:sz'), '4')
            x.set(qn('w:color'), '000000')
            borders.append(x)
        pr.append(borders)
        margins = OxmlElement('w:tblCellMar')
        for side, value in [('top', 45), ('bottom', 45), ('left', 80), ('right', 80)]:
            x = OxmlElement('w:' + side)
            x.set(qn('w:w'), str(value))
            x.set(qn('w:type'), 'dxa')
            margins.append(x)
        pr.append(margins)
    for ri, row in enumerate(t.rows):
        trpr = row._tr.get_or_add_trPr()
        for old in trpr.xpath('./w:trHeight'):
            trpr.remove(old)
        if ri == 0 and not trpr.xpath('./w:tblHeader'):
            trpr.append(OxmlElement('w:tblHeader'))
        if not trpr.xpath('./w:cantSplit'):
            trpr.append(OxmlElement('w:cantSplit'))
        seen = set()
        for ci, c in enumerate(row.cells):
            if id(c._tc) in seen:
                continue
            seen.add(id(c._tc))
            if not original:
                cp = c._tc.get_or_add_tcPr()
                for old in cp.xpath('./w:shd'):
                    cp.remove(old)
                sh = OxmlElement('w:shd')
                sh.set(qn('w:fill'), '82B0E4' if ri == 0 else 'C0D7F1' if ci == 0 and n < 4 else 'F2F2F2' if ri % 2 == 0 else 'FFFFFF')
                cp.append(sh)
            for p in c.paragraphs:
                pf = p.paragraph_format
                pf.line_spacing = 1
                pf.space_before = pf.space_after = Pt(0)
                pf.first_line_indent = Pt(0)
                pf.keep_with_next = ri < len(t.rows) - 1 if compact_matrix else ri == 0
                pf.keep_together = True
                pf.widow_control = False
                size = 10.5 if original and label.lstrip().startswith('表 4-1-1') else 11 if not original or compact_matrix else 12
                reset_font(p, size, ri == 0 if not original else None)
                if size == 10.5:
                    pp = p._p.get_or_add_pPr()
                    rp = pp.find(qn('w:rPr'))
                    if rp is None:
                        rp = OxmlElement('w:rPr')
                        pp.append(rp)
                    sz = OxmlElement('w:sz')
                    sz.set(qn('w:val'), '21')
                    rp.append(sz)
                    cm = c._tc.get_or_add_tcPr().find(qn('w:tcMar'))
                    if cm is None:
                        cm = OxmlElement('w:tcMar')
                        c._tc.get_or_add_tcPr().append(cm)
                    for side in ('top', 'bottom'):
                        old = cm.find(qn('w:' + side))
                        if old is None:
                            old = OxmlElement('w:' + side)
                            cm.append(old)
                        old.set(qn('w:w'), '15')
                        old.set(qn('w:type'), 'dxa')
                p._p.get_or_add_pPr().append(OxmlElement('w:snapToGrid'))
                p._p.pPr[-1].set(qn('w:val'), '0')

def prepare(e, source, index, label=''):
    tag = e.tag.rsplit('}', 1)[-1]
    if tag == 'tbl':
        format_table(e, source is ref, label)
        return
    if tag != 'p':
        return
    p = Paragraph(e, doc._body)
    text = p.text.strip()
    # 清理原稿錯用圖表樣式的節標，不搬入旧版橘色序號。
    if source is ref and index == 194:
        p.style = 'Heading 2'
    if source is ref and index == 190:
        assign_text(e, '本專案自 114 年 12 月起始，115 年 6 月完成初評，後續持續開發與準備複審。我們將各工作分為 22 個項目，以下為初審規劃的專案彙整甘特圖：')
    if source is ref and index == 195:
        assign_text(e, text.replace('部屬', '部署').replace('。。', '。'))
    if source is ref and index == 205:
        for box in e.xpath('.//w:txbxContent'):
            for pe in box.findall(qn('w:p')):
                tp = Paragraph(pe, doc._body)
                tp.paragraph_format.first_line_indent = Pt(0)
                tp.paragraph_format.left_indent = Pt(0)
                tp.paragraph_format.right_indent = Pt(0)
                tp.paragraph_format.space_before = tp.paragraph_format.space_after = Pt(0)
                tp.paragraph_format.line_spacing = 1
                tp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        return
    if source is ref and index == 193:
        return
    pf = p.paragraph_format
    pf.page_break_before = p.style.style_id == 'Heading1'
    pf.line_spacing = 1
    pf.space_before = Pt(8 if p.style.style_id.startswith('Heading') else 0)
    pf.space_after = Pt(5 if p.style.style_id.startswith('Heading') else 4)
    pf.keep_with_next = False
    pf.keep_together = False
    pf.widow_control = True
    for x in e.xpath('.//w:br[@w:type="page"]'):
        x.getparent().remove(x)
    is_image = bool(e.xpath('.//w:drawing | .//w:pict'))
    if source is ref and not is_image:
        # 去掉段尾手動換行，讓兩端對齊不會把最後一行撐開。
        for br in e.xpath('.//w:br[not(@w:type)]'):
            if not ''.join(br.xpath('following::w:t/text()')).strip():
                br.getparent().remove(br)
    if p.style.style_id.startswith('Heading'):
        level = int(p.style.style_id[-1])
        pf.keep_with_next = pf.keep_together = True
        pf.first_line_indent = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
        reset_font(p, 18 if level == 1 else 16 if level == 2 else 14, True)
        if level < 3:
            register(e, p.text, 'heading', level)
        if source is tech and index == 858:
            pf.page_break_before = False
    elif re.match(r'^[▼]?\s*表\s*(?:\d+|[AB])-', text):
        label_text = re.sub(r'^▼\s*', '', text)
        assign_text(e, '▼' + label_text)
        p.style = 'TblCap'
        pf.first_line_indent = Pt(0)
        pf.keep_with_next = pf.keep_together = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        reset_font(p, 12 if source is tech and 425 <= index <= 609 else 14, True)
        register(e, label_text, 'table')
    elif re.match(r'^[▲]?\s*圖\s*\d+-', text):
        label_text = re.sub(r'^▲\s*', '', text)
        for old, new in FIGURE_RENUMBER.items():
            if label_text.startswith(old + ' '):
                label_text = label_text.replace(old, new, 1)
                break
        assign_text(e, '▲' + label_text)
        p.style = 'FigCap'
        pf.first_line_indent = Pt(0)
        pf.keep_together = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        reset_font(p, 14, True)
        register(e, label_text, 'figure')
    elif is_image:
        pf.first_line_indent = Pt(0)
        pf.keep_with_next = True
        pf.keep_together = True
        pf.space_after = Pt(3)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for inline in e.xpath('.//wp:inline'):
            ext = inline.find(qn('wp:extent'))
            w, h = int(ext.get('cx')), int(ext.get('cy'))
            caption = plain(tech_blocks[index + 1]) if source is tech else ''
            maxw, maxh = 18.59, 10.8
            if caption.startswith('圖12-') or caption.startswith('圖11-'):
                maxh = 8.5
                if '手機' in caption:
                    maxw, maxh = 7.1, 11.0
                if '範圍與五維' in caption or '管理後台' in caption:
                    maxh = 12.0
                if 'CSP' in caption:
                    maxw, maxh = 14.0, 10.7
            if caption.startswith(('圖5-3-', '圖6-1-', '圖7-1-')):
                maxh = 12.8
            scale = min(Cm(maxw) / w, Cm(maxh) / h)
            nw, nh = int(w * scale), int(h * scale)
            ext.set('cx', str(nw))
            ext.set('cy', str(nh))
            for ae in inline.xpath('.//a:xfrm/a:ext'):
                ae.set('cx', str(nw))
                ae.set('cy', str(nh))
    else:
        reset_font(p, 11 if source is tech and 425 <= index <= 609 else 12 if source is tech and 849 <= index <= 857 else 14)
        if source is tech:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            pf.first_line_indent = Pt(28)
        if source is ref and text in ('Segmentation 市場區隔', 'Targeting 目標市場', 'Positioning 市場定位'):
            pf.keep_with_next = True
        if source is ref and index == 112:
            assign_text(e, '第一階段以「授權式被動健檢」為核心：使用者登入並完成掃描授權確認後，系統以 BFS 廣度優先爬蟲與 Playwright 擷取同網域頁面，保存頁面證據，再進行 SEO、AEO、GEO 與資安四維分析，輸出 0–100 分的綜合評分與 Word 格式健檢報告。AI 說明須對應確定性掃描器保存的證據，協助使用者掌握網站體質並據以改善。')
        if source is ref and index == 115:
            assign_text(e, '我們預期完成一套可完整運作的 Argus 授權式網站健檢 SaaS 平台，包含登入、掃描授權、SSRF 防護、同網域被動爬取、頁面證據保存、四維分析、網站拓樸與 Word 報告。每項 Finding 與 AI 說明可追溯至掃描證據，協助中小企業以低成本、高整合度且責任邊界清楚的方式改善網站，達到「網站健檢不求人，四維把關更安心」的預期效益。')
    text = p.text
    if source is tech and index == 862:
        p.text = '本表說明平台模型及手冊編製所使用的輔助工具；平台模型功能與費用依第5、9、11章說明。'
        reset_font(p)

def add_range(source, blocks, start, end):
    last_label = ''
    for i in range(start, end):
        src = blocks[i]
        if src.tag == qn('w:sectPr'):
            continue
        text = plain(src)
        if source is ref and i == 116:
            source_notes.append({'index': i, 'reason': '刪除與1-3重複的第二階段規劃說明', 'text': text})
            continue
        if source is tech:
            current_fig = re.match(r'^圖\d+-\d+-\d+', text)
            following = plain(blocks[i + 1]) if i + 1 < len(blocks) and src.xpath('.//w:drawing') else ''
            following_fig = re.match(r'^圖\d+-\d+-\d+', following)
            if (current_fig and current_fig.group() in OMIT_FIGURES) or (following_fig and following_fig.group() in OMIT_FIGURES):
                source_notes.append({'index': i, 'reason': '刪除重複介面示例圖；操作文字保留', 'text': text})
                continue
            if 425 <= i <= 609 and src.tag == qn('w:p') and (src.xpath('./w:pPr/w:pStyle[@w:val="Heading3"]') or text.startswith('資料表 ')):
                source_notes.append({'index': i, 'reason': '模型名稱與資料表名稱併入表題', 'text': text})
                continue
        if src.tag == qn('w:p') and not text.strip() and not src.xpath('.//w:drawing | .//w:pict'):
            continue
        e = import_block(src, source)
        if source is tech and i == 858:
            assign_text(e, '附錄一 人工智慧使用說明表')
            Paragraph(e, doc._body).style = 'Heading 1'
        if source is tech and i == 860:
            assign_text(e, '表A-1 人工智慧使用說明表')
        if source is tech and i == 861:
            e = import_block(ref_blocks[335], ref)
            ai = Table(e, doc._body)
            for ri in range(1, 6):
                chapter = [3, 5, 6, 7, 8][ri - 1]
                matches = [x for x in manifest if x['kind'] == 'heading' and x['level'] == 1 and x['title'].strip().startswith('第' + str(chapter) + '章')]
                page = str(pages.get(matches[0]['bookmark'], {}).get('page', '—')) if matches else '—'
                ai.cell(ri, 3).text = page
            for vals in [
                ['6', 'OpenAI Codex', '本版手冊精簡、排版調整、資料字典核對及逐頁版面檢查。', '1～' + str(max((v['page'] for v in pages.values()), default=83))],
                ['7', 'GLM', '前版手冊文稿及排版輔助，沿用既有編製紀錄。', '前版紀錄'],
            ]:
                row = ai.add_row()
                for c, val in zip(row.cells, vals):
                    c.text = val
        if source is tech and i == 863:
            assign_text(e, '附錄二 初評問題回覆')
        if source is tech and i == 864:
            assign_text(e, 'B-1 初評意見與修正情形')
        if source is tech and re.match(r'^表A-1-', text):
            assign_text(e, text.replace('表A-1-', '表B-1-', 1))
        if source is tech and 425 <= i <= 609 and re.match(r'^表8-2-', text):
            model_heading = plain(blocks[i - 2])
            table_name = plain(blocks[i - 1]).removeprefix('資料表 ').rstrip('。')
            assign_text(e, text + '　' + model_heading.split(' ', 1)[-1] + '（' + table_name + '）')
        if source is tech:
            kept_technical.append({'index': i, 'text': plain(src)})
        prepare(e, source, i, last_label)
        append(e)
        if src.tag == qn('w:p') and re.match(r'^▼?\s*表\s*(?:\d+|[AB])-', plain(e)):
            last_label = plain(e).lstrip('▼')
        if source is ref and i == 95:
            new_p('初審規劃以 SEO、AEO、GEO 與資安四維健檢為主，以下前言與營運計畫說明當時的設計目標；現行功能與實作規格見第3章以後。')
        if source is tech and i == 264:
            new_p('系統由初期四維健檢延伸加入 UX，現行採網站專案工作區，提供 PDF 報告、點數與定期定額訂閱、Search Console 及 MCP 接入。以下依目前 Repo 的實作說明。')

add_range(ref, ref_blocks, 94, 149)
# 移除重複的主動資安比較項，保留授權式主動檢測那一列。
for t in doc.tables:
    for row in list(t.rows):
        if row.cells[0].text.startswith('主動弱點探測'):
            t._tbl.remove(row._tr)
add_range(tech, tech_blocks, 263, 279)
add_range(ref, ref_blocks, 188, 208)
add_range(tech, tech_blocks, 306, 872)

# 手機兩幅同尺寸畫面並排，保留各自圖題與書籤。
mobile_captions = [p for p in doc.paragraphs if p.text.startswith(('▲圖12-14-1', '▲圖12-14-2'))]
if len(mobile_captions) == 2:
    a, b = mobile_captions
    image_a, image_b = a._p.getprevious(), b._p.getprevious()
    pa = Paragraph(image_a, doc._body)
    pb = Paragraph(image_b, doc._body)
    pa.add_run('  ')
    for r in list(pb._p.xpath('./w:r')):
        pa._p.append(r)
    body.remove(image_b)
    a._p.addnext(b._p)
    a.paragraph_format.keep_with_next = True

for t in doc.tables:
    for row in t.rows:
        for cell in row.cells:
            if cell.text == '點數計費與商業化模':
                cell.text = '點數計費與商業化模型'
                reset_font(cell.paragraphs[0], 12)
            if cell.text == '系通規劃':
                cell.text = '系統規劃'
                reset_font(cell.paragraphs[0], 12, True)
                cell.paragraphs[0].paragraph_format.first_line_indent = Pt(0)
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    if t.cell(0, 0).text == '序號' and any('OpenAI Codex' in c.text.replace('\u200b', '') for row in t.rows for c in row.cells):
        for row in t.rows[1:]:
            if 'OpenAI Codex' in row.cells[1].text.replace('\u200b', ''):
                row.cells[-1].text = '1～' + str(max((v['page'] for v in pages.values()), default=85))
                reset_font(row.cells[-1].paragraphs[0], 11)

# 舊引用所指營運計費內容已還原為初審商業規劃，將實際費用集中至使用章。
for p in doc.paragraphs:
    if '2-2及11-2' in p.text:
        p.text = p.text.replace('2-2及11-2', '12-10及11-2')
        reset_font(p)
    if p.text.startswith('[7] 第113402組'):
        p.text = '[7] Argus 專題團隊。Argus 系統手冊 v4。初審前言、营運計畫、專案時程、分工、貢獻度及 GitHub 紀錄。'
        p.text = p.text.replace('营', '營')
        reset_font(p)
    if p.text.startswith('第1章的〔AI3〕'):
        p.text = '本表說明平台模型及手冊編製所使用的輔助工具；平台模型功能與費用依第5、9、11章說明。'
        reset_font(p)

# 本次新增參考資料採 v4 的來源，不更改既有技術來源編號。
reference_anchor = next(p for p in doc.paragraphs if p.text.startswith('公開技術文件查閱日期'))
extra_refs = [
    '[9] AHHA。網站健檢與產品方案。https://ahha.com.tw/',
    '[10] GeoWeb。平台介紹。https://geoweb.tw/about',
    '[11] 經濟部中小及新創企業署。2025年中小企業白皮書。https://www.sme.gov.tw/article-tw-2345-13928',
]
for text in extra_refs:
    p = reference_anchor.insert_paragraph_before(text)
    reset_font(p)

in_references = False
for p in doc.paragraphs:
    if p.text == '14-1 技術與文件來源':
        in_references = True
        continue
    if p.text == '附錄一 人工智慧使用說明表':
        in_references = False
    if in_references:
        reset_font(p, 11)
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

# 初評回覆更新為本版实际保留章節；技術結論不改。
for t in doc.tables:
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                if p.text == '2-1列成本項目與記錄方式，2-2列維度計費、Agent附加費及方案價格。':
                    p.text = '第2章保留初審商業規劃；12-5、12-10列維度計費、Agent附加費與點數／訂閱流程，8章列帳務資料記錄。'
                    reset_font(p, 11)
                if p.text.startswith('2-2、6-1、8-1、12-10'):
                    p.text = p.text.replace('2-2、6-1、8-1、12-10', '6-1、8-1、12-5、12-10')
                    reset_font(p, 11)

# 每幅圖的書籤 ID 必須唯一，避免來源文件重複的 docPr。
for i, node in enumerate(doc.element.xpath('.//wp:docPr'), 1):
    node.set('id', str(i))

def catalog(title, entries, anchor, newpage):
    p = Paragraph(OxmlElement('w:p'), doc._body)
    anchor.addprevious(p._p)
    p.style = 'Heading 1'
    p.text = title
    p.paragraph_format.page_break_before = newpage
    reset_font(p, 18, True)
    for item in entries:
        p = Paragraph(OxmlElement('w:p'), doc._body)
        anchor.addprevious(p._p)
        p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.left_indent = Cm(.6 if item['level'] == 2 else 0)
        p.paragraph_format.keep_with_next = False
        p.paragraph_format.tab_stops.add_tab_stop(Cm(18.4), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        link = OxmlElement('w:hyperlink')
        link.set(qn('w:anchor'), item['bookmark'])
        r = OxmlElement('w:r')
        text = OxmlElement('w:t')
        text.text = item['title'].split('　', 1)[0] if item['title'].startswith('表8-2-') else item['title']
        r.append(text)
        link.append(r)
        p._p.append(link)
        from docx.text.run import Run
        font(Run(r, p), 12, item['kind'] == 'heading' and item['level'] == 1)
        font(p.add_run('\t' + str(pages.get(item['bookmark'], {}).get('page', '—'))), 12)

toc_heading = body[toc_start]
body.remove(toc_heading)
catalog('目錄', [x for x in manifest if x['kind'] == 'heading'], toc_placeholder._p, False)
catalog('圖目錄', [x for x in manifest if x['kind'] == 'figure'], toc_placeholder._p, True)
catalog('表目錄', [x for x in manifest if x['kind'] == 'table'], toc_placeholder._p, True)
body.remove(toc_placeholder._p)

doc.core_properties.title = 'Argus AI網站健檢平台 系統手冊'
doc.core_properties.subject = '複審系統手冊'
doc.core_properties.comments = ''
doc.save(FINAL)
# 編號定義沒有新增，保留參考部分原始位元組，避免純序列化差異。
with ZipFile(REF) as original, ZipFile(FINAL) as built:
    entries = [(item, original.read(item.filename) if item.filename == 'word/numbering.xml' else built.read(item.filename)) for item in built.infolist()]
with ZipFile(FINAL, 'w', ZIP_DEFLATED) as output:
    for item, data in entries:
        output.writestr(item, data)
(HERE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
(HERE / 'technical_baseline.json').write_text(json.dumps(kept_technical, ensure_ascii=False, indent=2), encoding='utf-8')
(HERE / 'editorial_changes.json').write_text(json.dumps(source_notes, ensure_ascii=False, indent=2), encoding='utf-8')
print('OUTPUT', FINAL)
print('TABLES', len(doc.tables), 'FIGURES', sum(x['kind'] == 'figure' for x in manifest), 'CATALOG_TARGETS', len(manifest))
print('REF_SHA256', hashlib.sha256(REF.read_bytes()).hexdigest())
