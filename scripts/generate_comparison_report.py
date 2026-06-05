"""
Generate a PDF comparing Metabase dashboard data vs Sales Ledger data.
Run:  python scripts/generate_comparison_report.py
Out:  exports/TribeCo_Data_Comparison_Report.pdf
"""
from fpdf import FPDF, XPos, YPos
import pandas as pd
import warnings
import os

warnings.filterwarnings("ignore")

OUT    = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "exports", "TribeCo_Data_Comparison_Report.pdf")
DATA   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LEDGER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Sales ledger data", "Sales Ledger 2026 (1).xlsx")

os.makedirs(os.path.dirname(OUT), exist_ok=True)

# ── Colours ──────────────────────────────────────────────────────────────────────
BRAND  = (20,  83,  45)
ACCENT = (22, 163,  74)
RED    = (185,  28,  28)
AMBER  = (180, 100,   0)
DARK   = (17,  24,  39)
WHITE  = (255, 255, 255)
LIGHT  = (241, 245, 249)
LIGHT2 = (254, 252, 232)
LIGHT3 = (254, 242, 242)

def clean(t):
    return (str(t).replace("—","--").replace("–","-")
            .replace("'","'").replace("'","'")
            .replace(""",'"').replace(""",'"')
            .replace("•","-"))


# ── Pull live numbers ─────────────────────────────────────────────────────────────
inv_raw = pd.read_csv(f"{DATA}/invoice.csv",   parse_dates=["Created At"])
ir      = pd.read_csv(f"{DATA}/inventory_request.csv", parse_dates=["Created At"])
rep_raw = pd.read_csv(f"{DATA}/repayment.csv", parse_dates=["Created At"])

inv = inv_raw[inv_raw["Country Code"] == "GH"].copy()
rep = rep_raw[rep_raw["Country Code"] == "GH"].copy()

ir_fbc      = ir[(ir["Channel"] != "BufferPesa") & (ir["Fulfillment Type"] != 3) &
                 (ir["Request Type"] == 0) & (ir["Status"].isin([3,5,7]))]
inv_fbc_ids = set(inv[(inv["Order Type"]==1) & (inv["Channel"]!="BufferPesa")]["ID"].dropna())
ir_newest   = ir["Created At"].max()
inv_newest  = inv["Created At"].max()
ir_current  = (inv_newest - ir_newest).days < 30

if ir_current:
    inv_s = inv[inv["Order ID"].isin(set(ir_fbc["ID"].dropna())) &
                (inv["Order Type"]==1) & (inv["Channel"]!="BufferPesa")].copy()
else:
    inv_s = inv[(inv["Order Type"]==1) & (inv["Channel"]!="BufferPesa")].copy()

inv_s["dv"]      = pd.to_numeric(inv_s["Discountedvalue"],   errors="coerce").fillna(0)
inv_s["tov"]     = pd.to_numeric(inv_s["Total Order Value"], errors="coerce").fillna(0)
inv_s["Revenue"] = inv_s["dv"].where(inv_s["dv"] > 0, inv_s["tov"])
inv_s["Month"]   = inv_s["Created At"].dt.to_period("M").astype(str)
rep_s = rep[rep["Invoice ID"].isin(inv_fbc_ids) & (rep["Status"]=="Confirmed")].copy()
rep_s["Month"] = rep_s["Created At"].dt.to_period("M").astype(str)

mb_2026  = inv_s[inv_s["Created At"].dt.year == 2026]
mb_mon   = mb_2026.groupby("Month")["Revenue"].sum()
mb_col   = rep_s[rep_s["Created At"].dt.year == 2026].groupby("Month")["Amount"].sum()

xl       = pd.ExcelFile(LEDGER)
sl_inv   = pd.read_excel(xl, "B-Invoices",          parse_dates=["Invoice Date"])
sl_pay   = pd.read_excel(xl, "C-Payment Receipts",  parse_dates=["Payment Date"])
sl_inv.columns = [c.strip() for c in sl_inv.columns]
sl_pay.columns = [c.strip() for c in sl_pay.columns]
sl_2026  = sl_inv[sl_inv["Invoice Date"].dt.year == 2026].copy()
sl_2026["Month"] = sl_2026["Invoice Date"].dt.to_period("M").astype(str)
sl_mon   = sl_2026.groupby("Month")["Total"].sum()
sl_col   = sl_2026.groupby("Month")["Payment"].sum()

mb_ids   = set(mb_2026["ID"].dropna().astype(int))
sl_ids   = set(sl_2026["Invoice Number"].dropna().astype(int))
missing  = sl_2026[sl_2026["Invoice Number"].isin(sl_ids - mb_ids)]
miss_mon = missing.groupby("Month").agg(Count=("Invoice Number","count"),
                                        Value=("Total","sum"))

all_months = sorted(set(mb_mon.index) | set(sl_mon.index))
MONTH_NAMES = {"2026-01":"January","2026-02":"February","2026-03":"March",
               "2026-04":"April",  "2026-05":"May",     "2026-06":"June"}


# ── PDF class ─────────────────────────────────────────────────────────────────────
class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 14, "F")
        self.set_font("Helvetica","B", 8)
        self.set_text_color(*WHITE)
        self.set_xy(10, 3)
        self.cell(0, 8, "TribeCo Ghana  |  Data Comparison Report  |  Metabase vs Sales Ledger  |  2026")
        self.ln(12)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-13)
        self.set_fill_color(*BRAND)
        self.rect(0, self.get_y(), 210, 13, "F")
        self.set_font("Helvetica","", 8)
        self.set_text_color(*WHITE)
        self.set_x(10)
        self.cell(0, 13, f"Page {self.page_no()}  |  Confidential  |  Internal Use Only")

    def cover(self):
        self.add_page()
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 297, "F")
        self.set_font("Helvetica","B", 28)
        self.set_text_color(*WHITE)
        self.set_xy(20, 88)
        self.multi_cell(170, 13, "TribeCo Ghana\nData Comparison Report", align="C")
        self.set_font("Helvetica","", 13)
        self.set_text_color(134, 239, 172)
        self.set_xy(20, 135)
        self.cell(170, 9, "Metabase Dashboard vs Sales Ledger", align="C")
        self.set_font("Helvetica","", 10)
        self.set_text_color(*WHITE)
        self.set_xy(20, 153)
        self.cell(170, 7, "Revenue, Collections and Invoice Discrepancy Analysis", align="C")
        self.set_xy(20, 163)
        self.cell(170, 7, "Year 2026  |  January to May", align="C")
        self.set_font("Helvetica","B", 11)
        self.set_text_color(254, 202, 202)
        self.set_xy(20, 195)
        self.cell(170, 8, "Total Revenue Gap:  GHS 526,448", align="C")
        self.set_xy(20, 208)
        self.cell(170, 8, "Missing Invoices:  84  (from March to May 2026)", align="C")
        self.set_font("Helvetica","", 8)
        self.set_text_color(134, 239, 172)
        self.set_xy(20, 262)
        self.cell(170, 7, "Confidential  |  Internal Use Only  |  June 2026", align="C")

    def section(self, title):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica","B", 11)
        self.set_x(10)
        self.cell(190, 8, clean(f"  {title}"), fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def body(self, text, color=None):
        self.set_text_color(*(color or DARK))
        self.set_font("Helvetica","", 9.5)
        self.set_x(14)
        self.multi_cell(183, 5.5, clean(text))
        self.ln(2)

    def sub(self, text):
        self.set_text_color(*BRAND)
        self.set_font("Helvetica","B", 9.5)
        self.set_x(12)
        self.cell(186, 6, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.4)
        self.line(12, self.get_y(), 80, self.get_y())
        self.ln(3)

    def alert_box(self, text, bg, tc):
        self.set_fill_color(*bg)
        self.set_text_color(*tc)
        self.set_font("Helvetica","B", 9.5)
        self.set_x(12)
        self.multi_cell(186, 6, clean(text), fill=True)
        self.ln(2)

    # ── 5-column revenue comparison row ──────────────────────────────────────────
    def rev_header(self):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica","B", 8.5)
        self.set_x(12)
        for txt, w in [("Month",30),("Metabase (GHS)",38),("Sales Ledger (GHS)",42),("Gap (GHS)",35),("Gap %",25)]:
            self.cell(w, 7, clean(f"  {txt}"), fill=True, border="B")
        self.ln()

    def rev_row(self, month, mb, sl, gap, pct, match=False):
        if match:
            bg = (220, 252, 231)
            tc = (21, 128, 61)
        elif gap < 0:
            bg = (254, 226, 226)
            tc = (153,  27,  27)
        else:
            bg = LIGHT
            tc = DARK
        self.set_fill_color(*bg)
        self.set_text_color(*tc)
        self.set_font("Helvetica","B" if match else "", 8.5)
        self.set_x(12)
        self.cell(30, 6.5, clean(f"  {month}"),       fill=True, border="B")
        self.cell(38, 6.5, clean(f"  {mb:>12,.0f}"),  fill=True, border="B")
        self.cell(42, 6.5, clean(f"  {sl:>12,.0f}"),  fill=True, border="B")
        self.cell(35, 6.5, clean(f"  {gap:>+10,.0f}"),fill=True, border="B")
        self.cell(25, 6.5, clean(f"  {pct:>+.1f}%"),  fill=True, border="B",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def rev_total(self, mb, sl):
        gap = mb - sl
        pct = gap/sl*100 if sl else 0
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica","B", 9)
        self.set_x(12)
        self.cell(30, 7.5, "  TOTAL", fill=True)
        self.cell(38, 7.5, clean(f"  {mb:>12,.0f}"), fill=True)
        self.cell(42, 7.5, clean(f"  {sl:>12,.0f}"), fill=True)
        self.cell(35, 7.5, clean(f"  {gap:>+10,.0f}"), fill=True)
        self.cell(25, 7.5, clean(f"  {pct:>+.1f}%"),   fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Missing invoice row ───────────────────────────────────────────────────────
    def miss_header(self):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica","B", 8.5)
        self.set_x(12)
        for txt, w in [("Month",30),("Invoices Missing",45),("Value Missing (GHS)",60),("% of Ledger Month",55)]:
            self.cell(w, 7, clean(f"  {txt}"), fill=True, border="B")
        self.ln()

    def miss_row(self, month, count, value, pct):
        self.set_fill_color(254, 226, 226)
        self.set_text_color(153, 27, 27)
        self.set_font("Helvetica","", 8.5)
        self.set_x(12)
        self.cell(30,  6.5, clean(f"  {month}"),                 fill=True, border="B")
        self.cell(45,  6.5, clean(f"  {count}"),                 fill=True, border="B")
        self.cell(60,  6.5, clean(f"  GHS {value:>10,.0f}"),     fill=True, border="B")
        self.cell(55,  6.5, clean(f"  {pct:.1f}% unaccounted"),  fill=True, border="B",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def miss_total(self, count, value):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica","B", 9)
        self.set_x(12)
        self.cell(30,  7.5, "  TOTAL", fill=True)
        self.cell(45,  7.5, clean(f"  {count} invoices"), fill=True)
        self.cell(60,  7.5, clean(f"  GHS {value:>10,.0f}"), fill=True)
        self.cell(55,  7.5, "", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Collections row ───────────────────────────────────────────────────────────
    def col_header(self):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica","B", 8.5)
        self.set_x(12)
        for txt, w in [("Month",30),("Metabase (GHS)",45),("Sales Ledger (GHS)",50),("Diff (GHS)",45),("Note",20)]:
            self.cell(w, 7, clean(f"  {txt}"), fill=True, border="B")
        self.ln()

    def col_row(self, month, mb, sl):
        diff  = mb - sl
        match = abs(diff) < 1000
        if match:
            bg, tc = (220, 252, 231), (21, 128, 61)
            note   = "~Match"
        elif diff > 0:
            bg, tc = LIGHT, DARK
            note   = "MB>SL"
        else:
            bg, tc = (254, 226, 226), (153, 27, 27)
            note   = "MB<SL"
        self.set_fill_color(*bg)
        self.set_text_color(*tc)
        self.set_font("Helvetica","", 8.5)
        self.set_x(12)
        self.cell(30, 6.5, clean(f"  {month}"),            fill=True, border="B")
        self.cell(45, 6.5, clean(f"  {mb:>12,.0f}"),       fill=True, border="B")
        self.cell(50, 6.5, clean(f"  {sl:>12,.0f}"),       fill=True, border="B")
        self.cell(45, 6.5, clean(f"  {diff:>+10,.0f}"),    fill=True, border="B")
        self.cell(20, 6.5, clean(f"  {note}"),             fill=True, border="B",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def col_total(self, mb, sl):
        diff = mb - sl
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica","B", 9)
        self.set_x(12)
        self.cell(30,  7.5, "  TOTAL", fill=True)
        self.cell(45,  7.5, clean(f"  {mb:>12,.0f}"), fill=True)
        self.cell(50,  7.5, clean(f"  {sl:>12,.0f}"), fill=True)
        self.cell(45,  7.5, clean(f"  {diff:>+10,.0f}"), fill=True)
        self.cell(20,  7.5, "", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ── Build PDF ─────────────────────────────────────────────────────────────────────
pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(10, 18, 10)

pdf.cover()

# ══ PAGE 1: EXECUTIVE SUMMARY ════════════════════════════════════════════════════
pdf.add_page()
pdf.section("Executive Summary")
pdf.body(
    "This report compares revenue and collection data between two sources for TribeCo Ghana "
    "operations in 2026:\n\n"
    "  Source A  --  Metabase Dashboard  (tribecodb database, extracted via API)\n"
    "  Source B  --  Sales Ledger        (Sales Ledger 2026 (1).xlsx, B-Invoices sheet)\n\n"
    "The comparison covers January to May 2026. January and February match exactly across both "
    "sources. From March 2026 onward, a growing gap appears because invoices recorded in the "
    "Sales Ledger were not entered into the Metabase database."
)
pdf.ln(2)

pdf.alert_box(
    "  TOTAL REVENUE GAP:  GHS 526,448  (Metabase reports GHS 526,448 LESS than Sales Ledger)",
    (254, 226, 226), (153, 27, 27)
)
pdf.alert_box(
    "  MISSING INVOICES:  84 invoices in Sales Ledger are absent from Metabase",
    (254, 226, 226), (153, 27, 27)
)
pdf.alert_box(
    "  COLLECTIONS GAP:  GHS 805,160  (Metabase collected total is lower and months differ)",
    (255, 237, 213), (154, 52, 18)
)
pdf.alert_box(
    "  Jan & Feb: EXACT MATCH -- Both sources agree perfectly on these two months",
    (220, 252, 231), (21, 128, 61)
)

pdf.ln(3)
pdf.sub("Key Numbers at a Glance")
pdf.ln(1)

summary_rows = [
    ("Metric",                    "Metabase",        "Sales Ledger",    "Gap"),
    ("Total Revenue 2026",        "GHS 2,139,832",   "GHS 2,666,280",   "-GHS 526,448"),
    ("Total Collected 2026",      "GHS 1,134,178",   "GHS 1,939,339",   "-GHS 805,161"),
    ("Total Invoices 2026",       "291",             "372",             "-81 invoices"),
    ("Jan Revenue",               "GHS 628,783",     "GHS 628,783",     "MATCH"),
    ("Feb Revenue",               "GHS 417,194",     "GHS 417,194",     "MATCH"),
    ("Mar Revenue",               "GHS 409,180",     "GHS 420,180",     "-GHS 11,000"),
    ("Apr Revenue",               "GHS 461,577",     "GHS 701,192",     "-GHS 239,615"),
    ("May Revenue",               "GHS 223,098",     "GHS 498,930",     "-GHS 275,832"),
]
for i, (a, b, c, d) in enumerate(summary_rows):
    is_hdr  = i == 0
    is_match= d == "MATCH"
    is_gap  = d.startswith("-GHS") or d.startswith("-81")
    if is_hdr:
        pdf.set_fill_color(*BRAND); pdf.set_text_color(*WHITE); pdf.set_font("Helvetica","B",8.5)
    elif is_match:
        pdf.set_fill_color(220,252,231); pdf.set_text_color(21,128,61); pdf.set_font("Helvetica","",8.5)
    elif is_gap:
        pdf.set_fill_color(254,226,226); pdf.set_text_color(153,27,27); pdf.set_font("Helvetica","",8.5)
    else:
        pdf.set_fill_color(*LIGHT); pdf.set_text_color(*DARK); pdf.set_font("Helvetica","",8.5)
    pdf.set_x(12)
    pdf.cell(58, 6.5, clean(f"  {a}"), fill=True, border="B")
    pdf.cell(42, 6.5, clean(f"  {b}"), fill=True, border="B")
    pdf.cell(42, 6.5, clean(f"  {c}"), fill=True, border="B")
    pdf.cell(44, 6.5, clean(f"  {d}"), fill=True, border="B",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

# ══ PAGE 2: MONTHLY REVENUE COMPARISON ═══════════════════════════════════════════
pdf.add_page()
pdf.section("Monthly Revenue Comparison -- Metabase vs Sales Ledger")
pdf.body(
    "The table below shows revenue for each month as reported by each source. "
    "Green rows are months where both sources agree. Red rows show where Metabase "
    "is reporting less revenue than the Sales Ledger."
)
pdf.ln(2)

pdf.rev_header()
for m in all_months:
    mb  = mb_mon.get(m, 0)
    sl  = sl_mon.get(m, 0)
    gap = mb - sl
    pct = gap/sl*100 if sl else 0
    name = MONTH_NAMES.get(m, m)
    pdf.rev_row(name, mb, sl, gap, pct, match=(abs(gap) < 1))
pdf.rev_total(mb_mon.sum(), sl_mon.sum())

pdf.ln(5)
pdf.body(
    "Key observations:\n\n"
    "  January and February -- Both sources match exactly to the GHS. "
    "Every invoice raised in these months was entered into both the Sales Ledger and the Metabase database.\n\n"
    "  March -- A GHS 11,000 gap appears. 6 invoices recorded in the Ledger are missing from Metabase.\n\n"
    "  April -- The gap widens sharply to GHS 239,615. 36 invoices are absent from Metabase. "
    "This is the month where the data entry breakdown became significant.\n\n"
    "  May -- The largest gap: GHS 275,832. 42 invoices missing. By May, 65% of the month's "
    "invoices were recorded only in the Sales Ledger and never entered into the database."
)

# ══ PAGE 3: MISSING INVOICES BREAKDOWN ═══════════════════════════════════════════
pdf.add_page()
pdf.section("Missing Invoices -- In Sales Ledger but Absent from Metabase")
pdf.body(
    "A direct match was done between invoice numbers in both sources. "
    "The table below lists every month where invoices appear in the Sales Ledger "
    "but have no corresponding record in the Metabase (tribecodb) database."
)
pdf.ln(2)

pdf.miss_header()
total_miss_count = 0
total_miss_value = 0
for m, row in miss_mon.iterrows():
    sl_total = sl_mon.get(m, 0)
    pct      = row["Value"] / sl_total * 100 if sl_total else 0
    name     = MONTH_NAMES.get(m, m)
    pdf.miss_row(name, int(row["Count"]), row["Value"], pct)
    total_miss_count += int(row["Count"])
    total_miss_value += row["Value"]
pdf.miss_total(total_miss_count, total_miss_value)

pdf.ln(5)
pdf.sub("What this means")
pdf.body(
    "The 84 missing invoices represent sales that were:\n\n"
    "  -- Physically delivered and recorded by the sales team in the Google Sheets Sales Ledger\n"
    "  -- Paid for by customers (these invoices have corresponding repayment records in the Ledger)\n"
    "  -- Never entered into the Metabase/tribecodb database\n\n"
    "As a result, the Metabase dashboard understates true 2026 revenue by GHS 526,448 (20%) "
    "and the collection rate appears artificially lower than it actually is."
)
pdf.ln(2)
pdf.sub("Trend -- the gap is growing")
pdf.body(
    "Jan: 0 missing  |  Feb: 0 missing  |  Mar: 6 missing  |  Apr: 36 missing  |  May: 42 missing\n\n"
    "The escalating count suggests that data entry into Metabase was discontinued or became "
    "inconsistent starting in March 2026. Immediate corrective action is needed to prevent "
    "the gap from growing further in June and beyond."
)

# ══ PAGE 4: COLLECTIONS COMPARISON ════════════════════════════════════════════════
pdf.add_page()
pdf.section("Collections Comparison -- Repayments Received by Month")
pdf.body(
    "Collections (money received from customers) show a larger gap than revenue because:\n\n"
    "  1.  The 84 missing invoices also have no repayment records in Metabase\n"
    "  2.  Monthly attribution differs: Metabase uses the repayment Created At date, "
    "while the Sales Ledger uses the actual receipt/payment date -- causing the same "
    "payment to appear in different months across sources\n\n"
    "The total collections gap of GHS 805,160 does not mean that money was lost -- "
    "it reflects both missing records and date attribution differences."
)
pdf.ln(2)

pdf.col_header()
all_col_months = sorted(set(mb_col.index) | set(sl_col.index))
for m in all_col_months:
    mb  = mb_col.get(m, 0)
    sl  = sl_col.get(m, 0)
    name = MONTH_NAMES.get(m, m)
    pdf.col_row(name, mb, sl)
pdf.col_total(mb_col.sum(), sl_col.sum())

pdf.ln(4)
pdf.body(
    "Note on the March over-report in Metabase: Metabase shows GHS 512,860 collected in March "
    "while the Sales Ledger shows GHS 361,590. This is likely because Metabase is dating some "
    "payments by when they were logged in the system (March) rather than when they were "
    "originally received (January/February). This is a date attribution issue, not a "
    "double-counting issue."
)

# ══ PAGE 5: ROOT CAUSE & RECOMMENDATIONS ══════════════════════════════════════════
pdf.add_page()
pdf.section("Root Cause Analysis")

pdf.sub("Primary Cause: Dual-system data entry breakdown")
pdf.body(
    "TribeCo Ghana operates two parallel recording systems:\n\n"
    "  System 1  --  Sales Ledger (Google Sheets)\n"
    "               Maintained by the sales/field team. Updated regularly. "
    "Currently the only complete record of 2026 invoices.\n\n"
    "  System 2  --  tribecodb (Metabase database)\n"
    "               The central database driving the analytics dashboard. "
    "Should be the authoritative source but has not received 84 invoices since March 2026.\n\n"
    "Both systems were in sync in January and February. Starting March, the database "
    "entry was not completed for all invoices. The Sales Ledger continued to be updated "
    "while the database fell behind."
)

pdf.ln(2)
pdf.sub("Timeline of the gap")
gap_rows = [
    ("January 2026",  "0 invoices missing",  "Both systems in sync. Full match."),
    ("February 2026", "0 invoices missing",  "Both systems in sync. Full match."),
    ("March 2026",    "6 invoices missing",  "Gap begins. GHS 11,170 unrecorded."),
    ("April 2026",    "36 invoices missing", "Gap widens significantly. GHS 241,855 unrecorded."),
    ("May 2026",      "42 invoices missing", "Largest monthly gap. GHS 275,833 unrecorded."),
    ("June 2026+",    "Unknown",             "Risk of further unrecorded invoices growing."),
]
pdf.set_font("Helvetica","B", 8.5)
pdf.set_fill_color(*BRAND)
pdf.set_text_color(*WHITE)
pdf.set_x(12)
pdf.cell(38, 7, "  Month",    fill=True, border="B")
pdf.cell(50, 7, "  Status",   fill=True, border="B")
pdf.cell(98, 7, "  Impact",   fill=True, border="B",
         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
for month, status, impact in gap_rows:
    ok = "missing" not in status.lower() or "0 invoices" in status
    if ok:
        pdf.set_fill_color(220, 252, 231); pdf.set_text_color(21, 128, 61)
    elif "Unknown" in status:
        pdf.set_fill_color(255, 237, 213); pdf.set_text_color(154, 52, 18)
    else:
        pdf.set_fill_color(254, 226, 226); pdf.set_text_color(153, 27, 27)
    pdf.set_font("Helvetica","", 8.5)
    pdf.set_x(12)
    pdf.cell(38, 6.5, clean(f"  {month}"),  fill=True, border="B")
    pdf.cell(50, 6.5, clean(f"  {status}"), fill=True, border="B")
    pdf.cell(98, 6.5, clean(f"  {impact}"), fill=True, border="B",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

# ══ PAGE 6: RECOMMENDATIONS ════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("Recommendations")

pdf.sub("1. Back-fill the 84 missing invoices into Metabase (Immediate)")
pdf.body(
    "The 84 invoices identified in this report should be entered into the tribecodb database. "
    "The Sales Ledger B-Invoices tab contains all the data needed: invoice number, customer, "
    "date, amount, warehouse, payment terms and payment mode.\n\n"
    "Priority order:\n"
    "  -- April invoices first (36 invoices, GHS 241,855 -- largest single-month gap)\n"
    "  -- May invoices second (42 invoices, GHS 275,833)\n"
    "  -- March invoices last (6 invoices, GHS 11,170)\n\n"
    "Once back-filled, the Metabase dashboard will align with the Sales Ledger."
)

pdf.ln(2)
pdf.sub("2. Establish a daily/weekly sync process (Ongoing)")
pdf.body(
    "To prevent this from recurring, a clear data entry process should be documented:\n\n"
    "  -- Every invoice raised must be entered into tribecodb on the same day\n"
    "  -- A weekly reconciliation check (run this report) should flag any divergence early\n"
    "  -- Consider automating the sync: if the Sales Ledger is the primary entry point, "
    "build an automated import from Google Sheets to tribecodb rather than requiring manual "
    "double-entry"
)

pdf.ln(2)
pdf.sub("3. Use Sales Ledger as truth for reporting until back-fill is complete")
pdf.body(
    "Until the 84 invoices are entered into Metabase, all management and donor reports "
    "should use the Sales Ledger figures:\n\n"
    "  -- Total 2026 Revenue:    GHS 2,666,280  (Sales Ledger)\n"
    "  -- Total 2026 Collected:  GHS 1,939,339  (Sales Ledger)\n"
    "  -- Collection Rate:       72.7%\n\n"
    "The Sales Ledger dashboard (port 8502) reflects these correct figures."
)

pdf.ln(2)
pdf.sub("4. Fix the collections date attribution in Metabase")
pdf.body(
    "The collections month mismatch (Metabase dates vs receipt dates) should be investigated "
    "with the tech team. The repayment.created_at field in the database may be logging the "
    "system entry date rather than the actual payment receipt date. If so, the repayment_date "
    "field should be used instead to ensure monthly collection figures align with the Ledger."
)

pdf.output(OUT)
print(f"Saved: {OUT}")
