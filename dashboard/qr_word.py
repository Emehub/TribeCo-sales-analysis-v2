"""
Word (.docx) writer for the Quarterly Review. Implements the same small interface as the PDF writer
(title_block, section_title, sub_title, tiles, progress, callout, bullets, body, chart, chart_pair,
table, new_page) so one composition function produces both formats with identical content.
"""
import io

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

DEEP, ACCENT, GOLD = "024B30", "1F7A4D", "C9975A"
RED, AMBER, LIGHT, INK, MUTED = "B91C1C", "BF6908", "F1F7F4", "111827", "6B7280"
CONTENT_W = 180  # mm (A4 minus 15 mm margins)


def _hex(t):
    return "%02X%02X%02X" % t if isinstance(t, tuple) else t.lstrip("#").upper()


def _shade(el, fill):
    pr = el._tc.get_or_add_tcPr() if hasattr(el, "_tc") else el._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def _cell_borders(cell, left=None, size=24, others="nil"):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}")
        if side == "left" and left:
            e.set(qn("w:val"), "single"); e.set(qn("w:sz"), str(size)); e.set(qn("w:color"), left)
        else:
            e.set(qn("w:val"), others)
        b.append(e)
    tcPr.append(b)


def _cell_margins(cell, top=60, bottom=60, left=110, right=90):
    tcPr = cell._tc.get_or_add_tcPr()
    m = OxmlElement("w:tcMar")
    for side, v in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:w"), str(v)); e.set(qn("w:type"), "dxa")
        m.append(e)
    tcPr.append(m)


def _no_table_borders(table):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "nil")
        b.append(e)
    tblPr.append(b)


def _widths(table, widths_mm):
    table.autofit = False
    tblPr = table._tbl.tblPr
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblPr.append(lay)
    for row in table.rows:
        for cell, w in zip(row.cells, widths_mm):
            cell.width = Mm(w)
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths_mm):
        gc.set(qn("w:w"), str(int(w / 25.4 * 1440)))


def _no_split(row):
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement("w:cantSplit"); e.set(qn("w:val"), "true")
    trPr.append(e)


def _run(p, text, size=9.5, bold=False, color=INK, italic=False):
    r = p.add_run(str(text).replace(" -- ", " – ").replace("--", "–"))
    r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic
    r.font.color.rgb = RGBColor.from_string(color)
    return r


def _para(container, space_after=2, align=None):
    p = container.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    if align:
        p.alignment = align
    return p


def _keep_with_next(p):
    p.paragraph_format.keep_with_next = True


class ReportDoc:
    _ACCENT, _RED, _AMBER, _GOLD = ACCENT, RED, AMBER, GOLD

    def __init__(self, header_text):
        self.doc = Document()
        st = self.doc.styles["Normal"]
        st.font.name = "Calibri"; st.font.size = Pt(9.5)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Mm(210), Mm(297)
        sec.left_margin = sec.right_margin = Mm(15)
        sec.top_margin, sec.bottom_margin = Mm(18), Mm(15)
        sec.header_distance, sec.footer_distance = Mm(7), Mm(7)
        hp = sec.header.paragraphs[0]
        _run(hp, header_text, size=8, bold=True, color=DEEP)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _run(fp, "Page ", size=8, color=MUTED)
        r = fp.add_run()
        for tag, txt in (("begin", None), (None, "PAGE"), ("end", None)):
            if tag:
                f = OxmlElement("w:fldChar"); f.set(qn("w:fldCharType"), tag); r._r.append(f)
            else:
                it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = txt; r._r.append(it)
        r.font.size = Pt(8)
        self._first = True

    # ── structure ────────────────────────────────────────────────────────────
    def new_page(self, part=None):
        # The break is attached to the next heading (page_break_before) rather than a separate
        # paragraph, so a page that is already full never produces an extra blank page.
        if self._first:            # the document already starts on page 1
            self._first = False
            return
        self._break_next = True

    def title_block(self, title, subtitle, note):
        t = self.doc.add_table(rows=1, cols=1)
        _no_table_borders(t); _widths(t, [CONTENT_W])
        c = t.rows[0].cells[0]
        _shade(c, DEEP); _cell_margins(c, 160, 160, 120, 120)
        p = c.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p, title, size=18, bold=True, color="FFFFFF")
        p = _para(c, 1, WD_ALIGN_PARAGRAPH.CENTER); _run(p, subtitle, size=12, bold=True, color=GOLD)
        p = _para(c, 0, WD_ALIGN_PARAGRAPH.CENTER); _run(p, note, size=8.5, color="FFFFFF")
        _para(self.doc, 4)

    def section_title(self, text):
        p = self.doc.add_paragraph(style="Heading 1")
        p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(5)
        if getattr(self, "_break_next", False):
            p.paragraph_format.page_break_before = True
            self._break_next = False
        _shade(p, ACCENT)
        r = _run(p, f" {text}", size=12, bold=True, color="FFFFFF")
        r.font.name = "Calibri"
        _keep_with_next(p)

    def sub_title(self, text):
        p = self.doc.add_paragraph(style="Heading 2")
        p.paragraph_format.space_before = Pt(6); p.paragraph_format.space_after = Pt(3)
        pPr = p._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr"); bot = OxmlElement("w:bottom")
        for k, v in (("w:val", "single"), ("w:sz", "8"), ("w:space", "1"), ("w:color", GOLD)):
            bot.set(qn(k), v)
        bdr.append(bot); pPr.append(bdr)
        r = _run(p, text, size=10.5, bold=True, color=DEEP); r.font.name = "Calibri"
        _keep_with_next(p)

    def body(self, text):
        p = _para(self.doc, 4)
        p.paragraph_format.line_spacing = 1.1
        _run(p, text, size=9.5)

    # ── content blocks ───────────────────────────────────────────────────────
    def tiles(self, items, cols=3):
        rows = -(-len(items) // cols)
        t = self.doc.add_table(rows=rows, cols=cols)
        _no_table_borders(t); _widths(t, [CONTENT_W / cols] * cols)
        for row in t.rows:
            _no_split(row)
        for i, (label, value, sub, color) in enumerate(items):
            c = t.rows[i // cols].cells[i % cols]
            _shade(c, LIGHT); _cell_borders(c, left=_hex(color), size=30, others="single")
            for side in ("top", "bottom", "right"):
                c._tc.tcPr.find(qn("w:tcBorders")).find(qn(f"w:{side}")).set(qn("w:color"), "FFFFFF")
                c._tc.tcPr.find(qn("w:tcBorders")).find(qn(f"w:{side}")).set(qn("w:sz"), "24")
            _cell_margins(c, 70, 70, 140, 80)
            p = c.paragraphs[0]; p.paragraph_format.space_after = Pt(0)
            _run(p, label.upper(), size=7, bold=True, color=MUTED)
            p = _para(c, 0); _run(p, value, size=13, bold=True)
            p = _para(c, 0); _run(p, sub, size=7.5, color=_hex(color))
        _para(self.doc, 3)

    def progress(self, value, goal, marker, label):
        p = _para(self.doc, 1); _run(p, label, size=8.5, bold=True, color=DEEP); _keep_with_next(p)
        share = max(min(value / goal, 1), 0.02)
        t = self.doc.add_table(rows=1, cols=2)
        _no_table_borders(t); _widths(t, [CONTENT_W * share, CONTENT_W * (1 - share)])
        a, b = t.rows[0].cells
        _shade(a, ACCENT); _shade(b, "E5E7EB")
        _run(a.paragraphs[0], f" {value/goal*100:.1f}% of annual goal", size=8, bold=True, color="FFFFFF")
        p = _para(self.doc, 4)
        _run(p, f"Gold reference: the YTD target is {marker/goal*100:.0f}% of the annual goal, so the bar is "
                f"{(value - marker)/goal*100:+.1f} points ahead of plan.", size=7.5, color=GOLD, italic=True)

    def callout(self, label, text, color=None):
        color = _hex(color or GOLD)
        t = self.doc.add_table(rows=1, cols=1)
        _no_table_borders(t); _widths(t, [CONTENT_W]); _no_split(t.rows[0])
        c = t.rows[0].cells[0]
        _shade(c, LIGHT); _cell_borders(c, left=color, size=24); _cell_margins(c, 60, 60, 130, 90)
        p = c.paragraphs[0]; p.paragraph_format.space_after = Pt(1)
        _run(p, label, size=9, bold=True, color=color)
        p = _para(c, 0); p.paragraph_format.line_spacing = 1.08
        _run(p, text, size=9)
        _para(self.doc, 2).paragraph_format.space_after = Pt(0)

    def bullets(self, items, color=None):
        color = _hex(color or ACCENT)
        for it in items:
            p = self.doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.08
            _run(p, it, size=9.5)
        _para(self.doc, 2)

    def chart(self, img, w=180):
        if img is None:
            return
        p = _para(self.doc, 4, WD_ALIGN_PARAGRAPH.CENTER)
        p.add_run().add_picture(io.BytesIO(img), width=Mm(min(w, CONTENT_W)))

    def chart_pair(self, a, b):
        imgs = [i for i in (a, b) if i is not None]
        if len(imgs) < 2:
            for i in imgs:
                self.chart(i, w=120)
            return
        t = self.doc.add_table(rows=1, cols=2)
        _no_table_borders(t); _widths(t, [CONTENT_W / 2] * 2)
        for c, img in zip(t.rows[0].cells, (a, b)):
            _cell_margins(c, 0, 0, 30, 30)
            c.paragraphs[0].add_run().add_picture(io.BytesIO(img), width=Mm(CONTENT_W / 2 - 3))
        _para(self.doc, 4)

    def table(self, headers, rows, widths):
        scale = CONTENT_W / sum(widths)
        w = [x * scale for x in widths]
        t = self.doc.add_table(rows=1 + len(rows), cols=len(headers))
        _no_table_borders(t); _widths(t, w)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for j, h in enumerate(headers):
            c = t.rows[0].cells[j]
            _shade(c, DEEP); _cell_margins(c, 50, 50, 90, 60)
            _run(c.paragraphs[0], str(h), size=8.5, bold=True, color="FFFFFF")
        trPr = t.rows[0]._tr.get_or_add_trPr()
        hdr = OxmlElement("w:tblHeader"); hdr.set(qn("w:val"), "true"); trPr.append(hdr)
        for i, row in enumerate(rows, start=1):
            _no_split(t.rows[i])
            for j, v in enumerate(row):
                c = t.rows[i].cells[j]
                if i % 2:
                    _shade(c, LIGHT)
                _cell_margins(c, 40, 40, 90, 60)
                c.paragraphs[0].paragraph_format.space_after = Pt(0)
                _run(c.paragraphs[0], str(v), size=8.5)
        _para(self.doc, 4)

    def output(self):
        buf = io.BytesIO()
        self.doc.save(buf)
        return buf.getvalue()
