"""
Branded PDF writer for emailed reports (no Streamlit dependency).

Same look as the dashboard's report PDFs: deep-green title banner, green section bars, light
callout boxes, tiles and tables. Implements the writer interface used by the report modules:
new_page, title_block, section_title, sub_title, body, bullets, callout, tiles, table, chart.
"""
import io

from fpdf import FPDF
from PIL import Image

BRAND, ACCENT, GOLD = (2, 75, 48), (31, 122, 77), (201, 151, 90)
RED, AMBER, BLACK, WHITE, LIGHT = (185, 28, 28), (191, 105, 8), (17, 24, 39), (255, 255, 255), (241, 247, 244)


def _clean(t):
    return (str(t).replace("—", "--").replace("–", "-").replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"').replace("·", "*").replace("•", "-")
            .replace("…", "...").replace("÷", "/").replace("×", "x").replace("→", "->"))


def _rgb(h):
    if isinstance(h, tuple):
        return h
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class ReportPDF(FPDF):
    _ACCENT, _RED, _AMBER, _GOLD = ACCENT, RED, AMBER, GOLD

    def __init__(self, header_text):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(10, 16, 10)
        self.header_text = header_text
        self._first = True

    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 12, "F")
        self.set_font("Helvetica", "B", 8.5)
        self.set_text_color(*WHITE)
        self.set_xy(10, 2.5)
        self.cell(0, 7, _clean(self.header_text))
        self.ln(11)

    def footer(self):
        self.set_y(-11)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"Page {self.page_no()}", align="R")

    # ── structure ────────────────────────────────────────────────────────────
    def new_page(self, part=None):
        self.add_page()

    def title_block(self, title, subtitle, note):
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 34, "F")
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*WHITE)
        self.set_xy(10, 6)
        self.cell(190, 9, _clean(title), align="C")
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*GOLD)
        self.set_xy(10, 16)
        self.cell(190, 7, _clean(subtitle), align="C")
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*WHITE)
        self.set_xy(10, 24)
        self.cell(190, 6, _clean(note), align="C")
        self.set_y(39)

    def section_title(self, text, need=30):
        """`need` = mm of content that must fit under the heading (e.g. a chart), else start a new page."""
        if self.get_y() > self.page_break_trigger - need:
            self.add_page()
        self.set_fill_color(*ACCENT)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 11)
        self.set_x(10)
        self.cell(190, 8, _clean(f"  {text}"), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def sub_title(self, text):
        if self.get_y() > self.page_break_trigger - 40:
            self.add_page()
        self.set_text_color(*BRAND)
        self.set_font("Helvetica", "B", 10)
        self.set_x(10)
        self.cell(190, 6, _clean(text), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*GOLD)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 75, self.get_y())
        self.ln(3)

    def body(self, text):
        self.set_text_color(*BLACK)
        self.set_font("Helvetica", "", 9.5)
        self.set_x(14)
        self.multi_cell(183, 5.2, _clean(text))
        self.ln(1.5)

    # ── blocks ───────────────────────────────────────────────────────────────
    def bullets(self, items, color=None):
        for it in items:
            if self.get_y() > self.page_break_trigger - 12:
                self.add_page()
            self.set_x(14)
            self.set_font("Helvetica", "B", 9.5)
            self.set_text_color(*_rgb(color or ACCENT))
            self.cell(5, 5, "-")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*BLACK)
            self.multi_cell(178, 4.8, _clean(it))
            self.ln(0.6)
        self.ln(1.2)

    def callout(self, label, text, color=None):
        est = 5.5 + max(1, -(-len(_clean(text)) // 95)) * 5 + 3
        if self.get_y() + est > self.page_break_trigger:
            self.add_page()
        self.set_fill_color(*LIGHT)
        self.set_x(14)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_rgb(color or GOLD))
        self.cell(183, 5.5, _clean(label), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_x(14)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*BLACK)
        self.multi_cell(183, 5, _clean(text), fill=True)
        self.ln(1.5)

    def tiles(self, items, cols=3):
        gap, h = 3.5, 17
        w = (183 - gap * (cols - 1)) / cols
        rows = -(-len(items) // cols)
        if self.get_y() + rows * (h + gap) > self.page_break_trigger:
            self.add_page()
        y0 = self.get_y()
        for i, (label, value, sub, color) in enumerate(items):
            x, y = 14 + (i % cols) * (w + gap), y0 + (i // cols) * (h + gap)
            self.set_fill_color(*LIGHT)
            self.rect(x, y, w, h, "F")
            self.set_fill_color(*_rgb(color))
            self.rect(x, y, 1.4, h, "F")
            self.set_xy(x + 3.5, y + 1.6)
            self.set_font("Helvetica", "B", 7)
            self.set_text_color(107, 114, 128)
            self.cell(w - 5, 3.5, _clean(label.upper()))
            self.set_xy(x + 3.5, y + 5.6)
            self.set_font("Helvetica", "B", 12.5)
            self.set_text_color(*BLACK)
            self.cell(w - 5, 6, _clean(value))
            self.set_xy(x + 3.5, y + 12)
            self.set_font("Helvetica", "", 7.2)
            self.set_text_color(*_rgb(color))
            self.cell(w - 5, 3.5, _clean(sub))
        self.set_y(y0 + rows * (h + gap) + 1)

    def table(self, headers, rows, widths):
        scale = 183 / sum(widths)
        widths = [w * scale for w in widths]

        def head():
            self.set_fill_color(*BRAND)
            self.set_text_color(*WHITE)
            self.set_font("Helvetica", "B", 8.5)
            self.set_x(14)
            for h, w in zip(headers, widths):
                self.cell(w, 6.5, _clean(f" {h}"), fill=True)
            self.ln()

        if self.get_y() > self.page_break_trigger - 20:
            self.add_page()
        head()
        self.set_font("Helvetica", "", 8.5)
        for i, row in enumerate(rows):
            if self.get_y() > self.page_break_trigger - 6:
                self.add_page()
                head()
                self.set_font("Helvetica", "", 8.5)
            self.set_x(14)
            self.set_fill_color(*(LIGHT if i % 2 == 0 else WHITE))
            self.set_text_color(*BLACK)
            for v, w in zip(row, widths):
                self.cell(w, 6, _clean(f" {v}"), fill=True, border="B")
            self.ln()
        self.ln(2)

    def chart(self, img, w=183):
        if img is None:
            return
        im = Image.open(io.BytesIO(img))
        h = w * im.height / im.width
        if self.get_y() + h > self.page_break_trigger:
            self.add_page()
        self.image(io.BytesIO(img), x=14 + (183 - w) / 2, y=self.get_y(), w=w)
        self.set_y(self.get_y() + h + 2.5)

    def output_bytes(self):
        return bytes(self.output())
