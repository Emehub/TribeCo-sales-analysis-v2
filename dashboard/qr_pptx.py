"""
PowerPoint deck for the Quarterly Review (python-pptx, native editable charts).

Built for a live management presentation: one message per slide, the quarter first, then the year
to date, then focus, data gaps and decisions. Detailed narrative goes in the speaker notes.
`build(ctx)` takes the figures already computed for the dashboard page and returns .pptx bytes.
"""
import io

import numpy as np
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

DEEP, GREEN, GOLD = "024B30", "1F7A4D", "C9975A"
RED, AMBER, INK, MUTED = "B91C1C", "D97706", "111827", "6B7280"
TINT, GRID, WHITE, GREY = "EAF3EE", "E5E7EB", "FFFFFF", "9CA3AF"
FONT = "Calibri"
W, H = 13.333, 7.5
L, R = 0.6, 0.6          # side margins (in)
CW = W - L - R           # content width


def _rgb(h):
    return RGBColor.from_string(h.lstrip("#").upper())


def _k(v):
    return f"{v/1e6:.2f}M" if abs(v) >= 1e6 else f"{v/1e3:,.0f}k"


def _clean(t):
    return str(t).replace(" -- ", " – ").replace("--", "–").replace(" -> ", " → ")


# ── primitives ────────────────────────────────────────────────────────────────────
def _text(slide, x, y, w, h, text, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.TOP, italic=False, name=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    runs = text if isinstance(text, list) else [(text, {})]
    p = tf.paragraphs[0]
    p.alignment = align
    for t, o in runs:
        r = p.add_run()
        r.text = _clean(t)
        f = r.font
        f.name = FONT
        f.size = Pt(o.get("size", size))
        f.bold = o.get("bold", bold)
        f.italic = o.get("italic", italic)
        f.color.rgb = _rgb(o.get("color", color))
    return tb


def _bullets(slide, x, y, w, h, items, size=14, color=INK, marker_color=GREEN, gap=6, name=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.04)
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(Inches(0.22)))
        pPr.set("indent", str(-Inches(0.22)))
        bu = pPr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}buClr", {})
        clr = bu.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr", {"val": marker_color})
        bu.append(clr)
        pPr.append(bu)
        ch = pPr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}buChar", {"char": "●"})
        pPr.append(ch)
        r = p.add_run()
        r.text = _clean(it)
        r.font.name = FONT
        r.font.size = Pt(size)
        r.font.color.rgb = _rgb(color)
    return tb


def _card(slide, x, y, w, h, fill=TINT, name=None, radius=0.08):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.adjustments[0] = radius
    s.fill.solid()
    s.fill.fore_color.rgb = _rgb(fill)
    s.line.fill.background()
    s.shadow.inherit = False
    if name:
        s.name = name
    return s


def _circle(slide, x, y, d, fill, text, size=14, color=WHITE):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    s.fill.solid()
    s.fill.fore_color.rgb = _rgb(fill)
    s.line.fill.background()
    s.shadow.inherit = False
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = p.add_run()
    r.text = text
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = _rgb(color)
    return s


def _bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = _rgb(color)


class Deck:
    def __init__(self, footer):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.blank = self.prs.slide_layouts[6]
        self.footer = footer
        self.n = 0

    def slide(self, kicker=None, title=None, dark=False, notes=None):
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        _bg(s, DEEP if dark else WHITE)
        if not dark:
            if kicker:
                _text(s, L, 0.32, CW, 0.3, kicker.upper(), size=11, bold=True, color=GOLD, name="Kicker")
            if title:
                _text(s, L, 0.58, CW, 0.75, title, size=28, bold=True, color=DEEP, name="Title")
            _text(s, L, H - 0.42, 8, 0.28, self.footer, size=10, color=MUTED, name="Footer")
            _text(s, W - R - 1.0, H - 0.42, 1.0, 0.28, str(self.n), size=10, color=MUTED,
                  align=PP_ALIGN.RIGHT, name="Slide number")
        if notes:
            s.notes_slide.notes_text_frame.text = _clean(notes)
        return s

    def output(self):
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


# ── charts ────────────────────────────────────────────────────────────────────────
def _style_chart(chart, legend=True, size=11, fmt=None, value_axis=True):
    chart.font.name = FONT
    chart.font.size = Pt(size)
    chart.font.color.rgb = _rgb(MUTED)
    chart.has_title = False
    if legend:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(size)
    else:
        chart.has_legend = False
    try:
        va = chart.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = _rgb(GRID)
        va.format.line.fill.background()
        va.tick_labels.font.size = Pt(size - 1)
        if fmt:
            va.tick_labels.number_format = fmt
            va.tick_labels.number_format_is_linked = False
        if not value_axis:
            va.visible = False
        ca = chart.category_axis
        ca.format.line.color.rgb = _rgb(GRID)
        ca.tick_labels.font.size = Pt(size)
        ca.has_major_gridlines = False
    except Exception:
        pass


def _series_fill(series, color):
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = _rgb(color)
    series.format.line.fill.background()


def _series_line(series, color, width=2.5, dash=None, marker=True):
    series.format.line.color.rgb = _rgb(color)
    series.format.line.width = Pt(width)
    if dash:
        series.format.line.dash_style = dash
    series.smooth = False
    from pptx.enum.chart import XL_MARKER_STYLE
    if marker:
        series.marker.style = XL_MARKER_STYLE.CIRCLE
        series.marker.size = 7
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = _rgb(color)
        series.marker.format.line.color.rgb = _rgb(color)
    else:
        series.marker.style = XL_MARKER_STYLE.NONE


def _labels(series, fmt='#,##0', pos=None, size=11, color=INK, bold=False):
    dl = series.data_labels
    dl.show_value = True
    dl.number_format = fmt
    dl.number_format_is_linked = False
    dl.font.size = Pt(size)
    dl.font.bold = bold
    dl.font.color.rgb = _rgb(color)
    if pos is not None:
        dl.position = pos


def _point_label(series, i, text, color=INK, size=11, pos=XL_LABEL_POSITION.CENTER):
    dl = series.points[i].data_label
    dl.has_text_frame = True
    dl.text_frame.text = text
    dl.position = pos
    run = dl.text_frame.paragraphs[0].runs[0]
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = _rgb(color)
    run.font.name = FONT


MONEY_K = '#,##0,"k"'
MONEY_M = '#,##0.00,,"M"'


def chart_q_months(slide, x, y, w, h, m):
    cd = CategoryChartData()
    cd.categories = list(m["Label"])
    cd.add_series("Target", [float(v) for v in m["Target"]])
    cd.add_series("Revenue", [float(v) for v in m["Revenue"]])
    cd.add_series("Cash collected", [float(v) for v in m["Collections"]])
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    gf.name = "Chart: quarter months"
    ch = gf.chart
    _style_chart(ch, fmt=MONEY_K)
    ch.plots[0].gap_width = 70
    ch.plots[0].overlap = -5
    for s, c in zip(ch.series, (GOLD, GREEN, DEEP)):
        _series_fill(s, c)
        _labels(s, MONEY_K, XL_LABEL_POSITION.OUTSIDE_END, size=11)
    return ch


def chart_bridge(slide, x, y, w, h, steps):
    """Native waterfall: stacked columns with an invisible base series."""
    cats, base, down, up, tot = [], [], [], [], []
    run = 0.0
    for name, val, kind in steps:
        cats.append(name if len(name) <= 20 else name[:19] + ".")
        if kind == "total":
            base.append(0); down.append(0); up.append(0); tot.append(float(val)); run = float(val)
        elif val < 0:
            base.append(run + val); down.append(-float(val)); up.append(0); tot.append(0); run += val
        else:
            base.append(run); up.append(float(val)); down.append(0); tot.append(0); run += val
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("base", base)
    cd.add_series("Decrease", down)
    cd.add_series("Increase", up)
    cd.add_series("Quarter revenue", tot)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_STACKED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    gf.name = "Chart: revenue bridge"
    ch = gf.chart
    _style_chart(ch, legend=False, fmt=MONEY_M)
    ch.plots[0].gap_width = 45
    base_s, dn, upp, tt = ch.series
    base_s.format.fill.background()
    base_s.format.line.fill.background()
    for s, c in ((dn, RED), (upp, GREEN), (tt, DEEP)):
        _series_fill(s, c)
    # labels only on non-zero points (a stacked chart forbids outside-end labels)
    for s, vals, sign in ((dn, down, "-"), (upp, up, "+"), (tt, tot, "")):
        for i, v in enumerate(vals):
            if v:
                _point_label(s, i, f"GHS {_k(v)}" if not sign else f"{sign}{_k(v)}", WHITE, 12)
    lo = min(v for v in tot if v) * 0.6
    ch.value_axis.minimum_scale = round(lo, -5)
    ch.category_axis.tick_labels.font.size = Pt(10)
    return ch


def chart_hbar(slide, x, y, w, h, cats, series, colors, fmt, legend=True, point_colors=None, name=None):
    cd = CategoryChartData()
    cd.categories = list(cats)
    for sname, vals in series:
        cd.add_series(sname, [float(v) for v in vals])
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    if name:
        gf.name = name
    ch = gf.chart
    _style_chart(ch, legend=legend, fmt=fmt)
    ch.plots[0].gap_width = 50
    ch.category_axis.reverse_order = True
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    for s, c in zip(ch.series, colors):
        _series_fill(s, c)
        _labels(s, fmt, XL_LABEL_POSITION.OUTSIDE_END, size=11)
    if point_colors:
        for i, c in enumerate(point_colors):
            pt = ch.series[0].points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = _rgb(c)
    return ch


def chart_lines(slide, x, y, w, h, cats, series, fmt, legend=True, name=None, size=11, label_fmt=None):
    """series: (name, values, colour, dash, show_labels[, label_below[, marker]])"""
    from pptx.enum.dml import MSO_LINE_DASH_STYLE as D
    cd = CategoryChartData()
    cd.categories = list(cats)
    for sname, vals, *_ in series:
        cd.add_series(sname, [None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v) for v in vals])
    gf = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    if name:
        gf.name = name
    ch = gf.chart
    _style_chart(ch, legend=legend, fmt=fmt, size=size)
    ch.value_axis.minimum_scale = 0
    for s, spec in zip(ch.series, series):
        sname, vals, color, dash, show = spec[:5]
        below = spec[5] if len(spec) > 5 else False
        marker = spec[6] if len(spec) > 6 else True
        _series_line(s, color, dash={"dash": D.DASH, "dot": D.ROUND_DOT, "dashdot": D.DASH_DOT}.get(dash),
                     marker=marker)
        if show:
            _labels(s, label_fmt or fmt, XL_LABEL_POSITION.BELOW if below else XL_LABEL_POSITION.ABOVE,
                    size=size - 1, color=color, bold=True)
    return ch


def chart_columns(slide, x, y, w, h, cats, series, colors, fmt, legend=True, name=None, label_fmt=None):
    cd = CategoryChartData()
    cd.categories = list(cats)
    for sname, vals in series:
        cd.add_series(sname, [None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v) for v in vals])
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    if name:
        gf.name = name
    ch = gf.chart
    _style_chart(ch, legend=legend, fmt=fmt)
    ch.plots[0].gap_width = 60
    ch.plots[0].overlap = -10
    for s, c in zip(ch.series, colors):
        _series_fill(s, c)
    return ch


def _table(slide, x, y, w, df, col_w, size=12, name=None, row_h=0.33):
    rows, cols = len(df) + 1, len(df.columns)
    gf = slide.shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(row_h * rows))
    if name:
        gf.name = name
    t = gf.table
    tot = sum(col_w)
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(w * cw / tot)
    for i in range(rows):
        t.rows[i].height = Inches(row_h)
        for j in range(cols):
            c = t.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.08)
            c.margin_top = c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            txt = df.columns[j] if i == 0 else df.iat[i - 1, j]
            c.fill.solid()
            c.fill.fore_color.rgb = _rgb(DEEP if i == 0 else (TINT if i % 2 else WHITE))
            p = c.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
            r = p.add_run()
            r.text = _clean(txt)
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.bold = i == 0 or j == 0
            r.font.color.rgb = _rgb(WHITE if i == 0 else INK)
    return t


# ── deck ──────────────────────────────────────────────────────────────────────────
def _stat_card(s, x, y, w, h, label, value, sub, sub_color=GREEN, value_size=26):
    _card(s, x, y, w, h, name=f"Card: {label}")
    _text(s, x + 0.2, y + 0.14, w - 0.4, 0.3, label.upper(), size=11, bold=True, color=MUTED)
    _text(s, x + 0.2, y + 0.42, w - 0.4, 0.55, value, size=value_size, bold=True, color=INK)
    _text(s, x + 0.2, y + 0.42 + value_size / 72 * 1.35, w - 0.4, 0.4, sub, size=13, color=sub_color)


def _tile_color(c):
    c = c.lstrip("#").upper()
    return {"16A34A": GREEN, "DC2626": RED, "F59E0B": AMBER, "14B8A6": GREEN, "0F766E": DEEP,
            "1F7A4D": GREEN, "C9975A": GOLD}.get(c, c)


def _first_sentence(t):
    import re
    t = _clean(t)
    m = re.search(r"(?<!e\.g)(?<!i\.e)\.\s", t)
    return t if not m else t[:m.start() + 1]


def build(ctx):
    import pandas as pd
    import quarterly_review as qrv
    r, q, ql, label = ctx["r"], ctx["q"], ctx["ql"], ctx["label"]
    s_, y_ = r["score"], r["ytd"]
    cur = s_[q]
    prev = s_[q - 1] if q > 1 else None
    m = r["monthly"]
    d = Deck(f"TribeCo Ghana  |  {label} Performance Review")

    # 1. Title
    s = d.slide(dark=True, notes=f"{label} performance review against the annual goals, prepared from live "
                                f"Metabase data as of {ctx['as_of']}. Structure: the quarter on its own, then the "
                                f"year to date, then focus for {ctx['next']}, data gaps and decisions.")
    _text(s, 0.9, 2.2, 11.5, 0.5, "GHANA COMMERCIAL PERFORMANCE", size=16, bold=True, color=GOLD)
    _text(s, 0.9, 2.7, 11.5, 1.2, f"{label} Review", size=54, bold=True, color=WHITE)
    _text(s, 0.9, 3.85, 11.5, 0.6, "Quarter results and year to date against the annual goals", size=22, color="D1E7DD")
    _text(s, 0.9, 6.3, 11.5, 0.4, f"Management meeting  |  Data as of {ctx['as_of']}", size=14, color="A7C4B5")

    # 2. Executive summary
    s = d.slide("Executive summary", "Sales are on plan; converting them to cash is the issue",
                notes=ctx["headline"])
    cards = [
        (f"{ql} revenue vs target", f"{cur['Attainment %']:.1f}%",
         f"GHS {_k(cur['Revenue'])} of GHS {_k(cur['Target'])} target", GREEN if cur["Attainment %"] >= 100 else RED),
        ("Annual goal reached", f"{y_['annual_pct']:.0f}%",
         f"Projected year-end {y_['projected_pct']:.0f}% of goal", GREEN if y_["projected_pct"] >= 100 else RED),
        ("DSO at quarter end", f"{cur['DSO at quarter end']:.0f} days",
         f"vs a {ctx['terms_days']}-day term; receivables GHS {_k(cur['AR at quarter end'])}",
         RED if cur["DSO at quarter end"] > ctx["terms_days"] else GREEN),
    ]
    cw = (CW - 2 * 0.35) / 3
    for i, (lab, val, sub, col) in enumerate(cards):
        x = L + i * (cw + 0.35)
        _card(s, x, 1.65, cw, 2.15, name=f"Card: {lab}")
        _text(s, x + 0.3, 1.85, cw - 0.6, 0.35, lab.upper(), size=12, bold=True, color=MUTED)
        _text(s, x + 0.3, 2.2, cw - 0.6, 1.0, val, size=54, bold=True, color=col)
        _text(s, x + 0.3, 3.2, cw - 0.6, 0.5, sub, size=13, color=INK)
    take = [ctx["q_ahead"][0] if ctx["q_ahead"] else "",
            ctx["ytd_points"][2][1] if len(ctx["ytd_points"]) > 2 else ctx["ytd_points"][-1][1]]
    if prev is not None and cur["AR at quarter end"] > prev["AR at quarter end"]:
        take.append(f"Receivables rose every quarter to GHS {cur['AR at quarter end']:,.0f}; "
                    f"{cur['AR past terms %']:.0f}% is past terms. Collections is the priority for {ctx['next']}.")
    _bullets(s, L, 4.25, CW, 2.5, [t for t in take if t], size=16, gap=8, name="Key takeaways")

    # 3. Section divider: the quarter
    s = d.slide(dark=True)
    _text(s, 0.9, 2.9, 11.5, 0.5, "PART 1", size=16, bold=True, color=GOLD)
    _text(s, 0.9, 3.35, 11.5, 1.0, f"{label}: how the quarter performed", size=40, bold=True, color=WHITE)

    # 4. Q at a glance
    s = d.slide(f"{ql} analysis", f"{ql} at a glance", notes=ctx["headline"])
    cw, chh = (CW - 2 * 0.3) / 3, 1.75
    for i, (lab, val, sub, col) in enumerate(ctx["q_tiles"]):
        x, yy = L + (i % 3) * (cw + 0.3), 1.75 + (i // 3) * (chh + 0.35)
        _stat_card(s, x, yy, cw, chh, lab, val, sub, _tile_color(col), value_size=30)

    # 5. Month by month
    qm = m[m["Q"] == q]
    on_t = int((qm["Attainment %"] >= 100).sum())
    s = d.slide(f"{ql} analysis",
                f"All {len(qm)} months on target; cash lagged sales" if on_t == len(qm) else
                f"{on_t} of {len(qm)} months on target",
                notes="Month by month: " + "; ".join(
                    f"{lab} revenue GHS {rv:,.0f} = {at:.1f}% of target, cash collected GHS {co:,.0f}"
                    for lab, rv, at, co in zip(qm["Label"], qm["Revenue"], qm["Attainment %"], qm["Collections"])))
    chart_q_months(s, L, 1.5, 8.4, 5.3, qm)
    _card(s, L + 8.7, 1.6, CW - 8.7, 5.1, name="Commentary")
    pts = [f"{lab}: {at:.1f}% of target, cash {co / rv * 100:.0f}% of sales"
           for lab, rv, at, co in zip(qm["Label"], qm["Revenue"], qm["Attainment %"], qm["Collections"])]
    pts.append(f"Quarter: cash collected covered {cur['Collection ratio %']:.0f}% of invoiced revenue")
    _text(s, L + 8.95, 1.8, CW - 9.2, 0.4, "What the months show", size=15, bold=True, color=DEEP)
    _bullets(s, L + 8.95, 2.3, CW - 9.2, 4.2, pts, size=14, gap=10)

    # 6. Bridge
    if r["drivers"].get("bridge"):
        b = r["drivers"]["bridge"]
        chg = b[-1][1] - b[0][1]
        s = d.slide(f"{ql} drivers",
                    f"Revenue {'fell' if chg < 0 else 'rose'} GHS {abs(chg)/1e3:,.0f}k vs Q{q-1}, driven by a few large accounts",
                    notes=ctx["cust_note"])
        chart_bridge(s, L, 1.45, CW, 4.35, b)
        _text(s, L, 5.95, CW, 0.9, _clean(ctx["cust_note"]), size=14, color=INK, name="Bridge reading")

    # 7. Went well / needs attention
    s = d.slide(f"{ql} analysis", "What went well, and what needs attention",
                notes="Went well: " + " | ".join(ctx["q_ahead"]) + "\nNeeds attention: " + " | ".join(ctx["q_behind"]))
    cw = (CW - 0.4) / 2
    for i, (title, items, col) in enumerate((("What went well", ctx["q_ahead"], GREEN),
                                              ("Needs attention", ctx["q_behind"], RED))):
        x = L + i * (cw + 0.4)
        _card(s, x, 1.55, cw, 5.25, name=f"Card: {title}")
        _circle(s, x + 0.3, 1.78, 0.5, col, "✓" if i == 0 else "!", size=18)
        _text(s, x + 0.95, 1.82, cw - 1.2, 0.45, title, size=18, bold=True, color=col)
        _bullets(s, x + 0.3, 2.5, cw - 0.55, 4.2, items[:5] or ["Nothing material this quarter."],
                 size=13, gap=7, marker_color=col)

    # 8. Mix and receivables age
    mc = r["drivers"].get("mix_compare")
    ag = r["aging"]
    s = d.slide(f"{ql} drivers", "Product mix is steady; the risk sits in receivables past terms",
                notes=f"Receivables by age at {r['aging_asof']:%d %b %Y}: " + "; ".join(
                    f"{b} GHS {v:,.0f} ({sh:.0f}%)" for b, v, sh in zip(ag.index, ag["Amount"], ag["Share %"])))
    cw = (CW - 0.4) / 2
    if mc is not None and len(mc) and q > 1:
        top = mc.head(6)
        names = [(n.title() if n.isupper() else n)[:18] for n in top.index]
        _text(s, L, 1.5, cw, 0.35, f"Product mix, share of revenue (Q{q-1} vs {ql})", size=14, bold=True, color=DEEP)
        chart_hbar(s, L, 1.9, cw, 4.9, names, [(f"Q{q-1}", top[q - 1] / 100), (ql, top[q] / 100)],
                   (GREY, GREEN), "0%", name="Chart: product mix")
    x2 = L + cw + 0.4
    _text(s, x2, 1.5, cw, 0.35, f"Receivables by age at {r['aging_asof']:%d %b} (GHS)", size=14, bold=True, color=DEEP)
    chart_hbar(s, x2, 1.9, cw, 4.9, list(ag.index), [("Outstanding", ag["Amount"])], (GREEN,), MONEY_K,
               legend=False, point_colors=[GREEN, "84CC16", AMBER, "EA580C", RED][:len(ag)],
               name="Chart: receivables age")

    # 9. Section divider: YTD
    s = d.slide(dark=True)
    _text(s, 0.9, 2.9, 11.5, 0.5, "PART 2", size=16, bold=True, color=GOLD)
    _text(s, 0.9, 3.35, 11.5, 1.0, "Year to date against the annual goal", size=40, bold=True, color=WHITE)

    # 10. YTD progress + cumulative
    done = m["Revenue"].notna().values
    last = int(np.where(done)[0].max())
    proj = [None] * len(m)
    for i in range(last, len(m)):
        proj[i] = float(m["Cum Revenue"].iloc[last] + y_["run_rate"] * (i - last))
    s = d.slide("Year to date",
                f"{y_['annual_pct']:.0f}% of the annual goal reached; on course for about {y_['projected_pct']:.0f}%",
                notes=" ".join(f"{a}: {b}" for a, b, _ in ctx["ytd_points"]))
    cw = 3.2
    for i, (lab, val, sub, col) in enumerate([ctx["y_tiles"][0], ctx["y_tiles"][2], ctx["y_tiles"][3]]):
        _stat_card(s, L, 1.55 + i * 1.75, cw, 1.55, lab, val, sub, _tile_color(col), value_size=24)
    chart_lines(s, L + cw + 0.3, 1.45, CW - cw - 0.3, 5.4, list(m["Label"]), [
        ("Cumulative target", list(m["Cum Target"]), GOLD, "dash", False),
        ("Cumulative revenue", [v if dn else None for v, dn in zip(m["Cum Revenue"], done)], GREEN, None, False),
        (f"Projection at {ql} run-rate", proj, GREEN, "dot", False, False, False),
        ("Annual goal", [float(y_["annual_target"])] * len(m), RED, "dashdot", False, False, False),
    ], MONEY_M, name="Chart: cumulative revenue")

    # 11. Monthly attainment
    s = d.slide("Year to date", f"{y_['months_on_target']} of {y_['months_done']} months at or above target",
                notes="Monthly attainment: " + ", ".join(
                    f"{lab} {a:.1f}%" for lab, a in zip(m["Label"], m["Attainment %"]) if a == a)
                + ". Remaining monthly targets: " + ", ".join(
                    f"{lab} GHS {t:,.0f}" for lab, t, rv in zip(m["Label"], m["Target"], m["Revenue"]) if rv != rv))
    ch = chart_columns(s, L, 1.45, CW, 4.6, list(m["Label"]),
                       [("Revenue", list(m["Revenue"])), ("Target", list(m["Target"]))], (GREEN, GOLD), MONEY_K)
    for i, a in enumerate(m["Attainment %"]):
        if a == a:
            dl = ch.series[0].points[i].data_label
            dl.has_text_frame = True
            dl.text_frame.text = f"{a:.1f}%" if 99 <= a <= 101.5 else f"{a:.0f}%"
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
            dl.text_frame.paragraphs[0].runs[0].font.size = Pt(10)
            dl.text_frame.paragraphs[0].runs[0].font.bold = True
            dl.text_frame.paragraphs[0].runs[0].font.color.rgb = _rgb(INK)
    _text(s, L, 6.15, CW, 0.7, "Labels show attainment. " + _first_sentence(ctx["ytd_points"][0][1]) +
          (" Months landing within 0.5% of target are flagged for validation." if len(r["flags"]["exact_months"]) >= 3 else ""),
          size=13, color=MUTED, name="Caption")

    # 12-13. Quarter-by-quarter trends (small multiples)
    ql_all = [f"Q{c}" for c in s_.columns]
    row = lambda k: [float(v) for v in s_.loc[k]]
    tl = dict(ctx["trends"])
    panels_a = [
        ("Revenue vs target (GHS)", [("Revenue", row("Revenue"), GREEN, None, True), ("Target", row("Target"), GOLD, "dash", False)],
         MONEY_M, "Revenue " + qrv._shape(row("Revenue"), ql_all)),
        ("Orders", [("Orders", row("Orders"), GREEN, None, True)], "#,##0",
         "Orders " + qrv._shape(row("Orders"), ql_all)),
        ("Customers", [("Active", row("Active customers"), GREEN, None, True), ("New", row("New customers"), GOLD, None, True)],
         "#,##0", "New customers " + qrv._shape(row("New customers"), ql_all)),
    ]
    panels_b = [
        ("Collections vs invoiced (GHS)", [("Invoiced", row("Revenue"), GREY, "dash", False),
                                          ("Collected", row("Collections"), GREEN, None, True, True)],
         MONEY_M, "Collection ratio " + qrv._shape(row("Collection ratio %"), ql_all)),
        ("Receivables at quarter end (GHS)", [("Receivables", row("AR at quarter end"), RED, None, True)], MONEY_K,
         "Receivables " + qrv._shape(row("AR at quarter end"), ql_all)
         + "; DSO " + " → ".join(f"{v:.0f}d" for v in row("DSO at quarter end"))),
        ("Multi-SKU orders vs top-5 share", [("Multi-SKU %", [v / 100 for v in row("Multi-SKU %")], GREEN, None, True),
                                             ("Top-5 share %", [v / 100 for v in row("Top-5 share %")], GOLD, None, True, True)],
         "0%", "Multi-SKU " + qrv._shape(row("Multi-SKU %"), ql_all)),
    ]
    for title, panels, keys in ((f"Sales held up; growth came from existing customers", panels_a,
                                 ("Revenue vs target", "Orders and basket size", "Customers")),
                                (f"Cash conversion weakened while basket breadth improved", panels_b,
                                 ("Collections", "Receivables and DSO", "Mix and concentration"))):
        s = d.slide(f"Quarter-by-quarter trends, Q1 to {ql}", title,
                    notes="\n".join(f"{k}: {tl[k]}" for k in keys if k in tl))
        pw = (CW - 2 * 0.3) / 3
        for i, (ptitle, series, fmt, cap) in enumerate(panels):
            x = L + i * (pw + 0.3)
            _text(s, x, 1.5, pw, 0.35, ptitle, size=14, bold=True, color=DEEP)
            chart_lines(s, x, 1.9, pw, 3.7, ql_all, series, fmt, legend=len(series) > 1,
                        name=f"Chart: {ptitle}")
            _card(s, x, 5.75, pw, 1.0, name=f"Caption: {ptitle}")
            _text(s, x + 0.15, 5.82, pw - 0.3, 0.9, cap[0].upper() + cap[1:] + ".", size=13, color=INK,
                  anchor=MSO_ANCHOR.MIDDLE)

    # 14. Scorecard
    tb = ctx["table"]
    keep = ["Revenue", "Attainment %", "Orders", "AOV", "Active customers", "New customers",
            "Multi-SKU %", "Collections", "Collection ratio %", "AR at quarter end", "DSO at quarter end"]
    tb = tb[tb["Metric"].isin(keep)].reset_index(drop=True)
    s = d.slide(f"Quarter-by-quarter trends, Q1 to {ql}", "Quarterly scorecard",
                notes="Full scorecard including targets, median order, top-5 share and share of receivables past "
                      "terms is in the PDF and Word versions of this review.")
    _table(s, L, 1.5, CW, tb, [3] + [2] * (len(tb.columns) - 2) + [1.6], size=13, name="Scorecard", row_h=0.42)

    # 15. Focus
    s = d.slide("Next quarter", f"Suggested focus for {ctx['next']}", notes="\n".join(ctx["focus"]))
    items = ctx["focus"][:5]
    rh = min(1.0, 5.2 / max(len(items), 1))
    for i, it in enumerate(items):
        yy = 1.55 + i * rh
        _circle(s, L, yy + (rh - 0.1 - 0.5) / 2, 0.5, DEEP if i else GOLD, str(i + 1), size=16)
        _text(s, L + 0.75, yy, CW - 0.8, rh - 0.1, it, size=15, color=INK, anchor=MSO_ANCHOR.MIDDLE)

    # 16. Data gaps
    gaps = [g for g in ctx["gaps"] if not g[0].startswith("Data freshness")]
    s = d.slide("Before we rely on these numbers", "Data gaps and figures to validate",
                notes="\n".join(f"{a}: {b}" for a, b in ctx["gaps"]))
    cols = 3
    cw = (CW - (cols - 1) * 0.3) / cols
    rows_n = -(-len(gaps) // cols)
    chh = min(2.45, (5.2 - (rows_n - 1) * 0.3) / rows_n)
    for i, (gt, gx) in enumerate(gaps):
        x, yy = L + (i % cols) * (cw + 0.3), 1.5 + (i // cols) * (chh + 0.3)
        _card(s, x, yy, cw, chh, name=f"Gap: {gt}")
        head = gt.split(": ", 1)
        _text(s, x + 0.2, yy + 0.12, cw - 0.4, 0.3, (head[0] if len(head) > 1 else "Note").upper(),
              size=10, bold=True, color=AMBER)
        _text(s, x + 0.2, yy + 0.4, cw - 0.4, 0.6, head[-1][:1].upper() + head[-1][1:], size=14, bold=True, color=INK)
        _text(s, x + 0.2, yy + 1.0, cw - 0.4, chh - 1.05, _first_sentence(gx), size=12, color=MUTED)

    # 17. Decisions (dark close)
    asks = []
    if prev is not None and cur["AR at quarter end"] > prev["AR at quarter end"]:
        asks.append(f"Agree a {ctx['next']} collections target: DSO back to about {ctx['terms_days']} days, owners for the "
                    f"GHS {cur['AR past terms']/1e3:,.0f}k past terms")
    if cur["New customers"] <= 5:
        asks.append("Set a new-customer acquisition goal for the rest of the year")
    if len(r["flags"]["exact_months"]) >= 3:
        asks.append("Confirm how the April to August monthly targets were set")
    asks.append("Assign owners to recover volume from the accounts that slowed most")
    s = d.slide(dark=True, notes="Decisions requested from this meeting:\n" + "\n".join(asks))
    _text(s, 0.9, 1.0, 11.5, 0.5, "FOR DISCUSSION", size=16, bold=True, color=GOLD)
    _text(s, 0.9, 1.45, 11.5, 0.9, "Decisions we need from this meeting", size=38, bold=True, color=WHITE)
    for i, a in enumerate(asks[:4]):
        yy = 2.75 + i * 1.0
        _circle(s, 0.9, yy, 0.55, GOLD, str(i + 1), size=18, color=DEEP)
        _text(s, 1.7, yy - 0.05, 10.8, 0.7, a, size=20, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)

    return d.output()
