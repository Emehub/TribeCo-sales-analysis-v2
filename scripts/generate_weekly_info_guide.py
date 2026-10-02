"""
Generate a plain-English PDF explaining the Weekly Info page and every calculation on it.
Run: python3 scripts/generate_weekly_info_guide.py
Output: exports/Weekly_Info_Explained.pdf
"""
from fpdf import FPDF, XPos, YPos
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports", "Weekly_Info_Explained.pdf")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

BRAND  = (2, 75, 48)      # TribeCo deep green
ACCENT = (31, 122, 77)    # TribeCo mid green
GOLD   = (201, 151, 90)   # TribeCo gold
BLACK  = (17, 24, 39)
WHITE  = (255, 255, 255)
LIGHT  = (241, 247, 244)

def clean(text):
    return (text
        .replace("—", "--")
        .replace("–", "-")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("·", "*")
        .replace("•", "-")
        .replace("…", "...")
        .replace("÷", "/")
        .replace("×", "x")
    )

class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 14, "F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*WHITE)
        self.set_xy(10, 3)
        self.cell(0, 8, "TribeCo Ghana  |  Weekly Info -- Explained")
        self.ln(12)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-13)
        self.set_fill_color(*BRAND)
        self.rect(0, self.get_y(), 210, 13, "F")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*WHITE)
        self.set_x(10)
        self.cell(0, 13, f"Page {self.page_no()}  |  TribeCo Ghana  |  Confidential")

    def cover(self):
        self.add_page()
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 297, "F")
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(*WHITE)
        self.set_xy(20, 90)
        self.multi_cell(170, 12, "Weekly Info -- Explained", align="C")
        self.set_font("Helvetica", "", 13)
        self.set_text_color(*GOLD)
        self.set_xy(20, 118)
        self.cell(170, 9, "A Plain-English Guide to Every Number and Its Formula", align="C")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*WHITE)
        self.set_xy(20, 140)
        self.cell(170, 7, "TribeCo Ghana  |  Weekly Info Page", align="C")
        self.set_xy(20, 262)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GOLD)
        self.cell(170, 7, "Confidential  |  Internal Use Only", align="C")

    def section_title(self, text):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 11)
        self.set_x(10)
        self.cell(190, 8, clean(f"  {text}"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def sub_title(self, text):
        self.set_text_color(*BRAND)
        self.set_font("Helvetica", "B", 10)
        self.set_x(10)
        self.cell(190, 6, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*GOLD)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 75, self.get_y())
        self.ln(3)

    def body(self, text):
        self.set_text_color(*BLACK)
        self.set_font("Helvetica", "", 9.5)
        self.set_x(14)
        self.multi_cell(183, 5.5, clean(text))
        self.ln(2)

    def formula_box(self, formula, worked=""):
        self.set_fill_color(*LIGHT)
        self.set_x(14)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*ACCENT)
        self.multi_cell(183, 6.5, clean(formula), fill=True)
        if worked:
            self.set_x(14)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*BLACK)
            self.multi_cell(183, 5.5, clean(worked), fill=True)
        self.ln(2)

    def kpi_box(self, label, description):
        self.set_fill_color(*LIGHT)
        self.set_x(14)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*ACCENT)
        self.cell(183, 5.5, clean(label), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(14)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*BLACK)
        self.multi_cell(183, 5, clean(description), fill=True)
        self.ln(1.5)

    def table_header(self, *cols_widths):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 9)
        self.set_x(14)
        for text, w in cols_widths[:-1]:
            self.cell(w, 6.5, clean(f"  {text}"), fill=True)
        text, w = cols_widths[-1]
        self.cell(w, 6.5, clean(f"  {text}"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def table_row(self, *cols_widths):
        self.set_fill_color(*LIGHT)
        self.set_text_color(*BLACK)
        self.set_font("Helvetica", "", 9)
        self.set_x(14)
        for text, w in cols_widths[:-1]:
            self.cell(w, 6.5, clean(f"  {text}"), fill=True, border="B")
        text, w = cols_widths[-1]
        self.cell(w, 6.5, clean(f"  {text}"), fill=False, border="B", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(10, 16, 10)
pdf.cover()

# ── Introduction ──────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("What Is the Weekly Info Page?")
pdf.body(
    "Weekly Info is the dashboard page that answers one question in depth: how did a specific week "
    "actually perform, and what's really behind each number? Pick any week from Week 1 up to the "
    "current week using the selector at the top of the page, and every figure below recalculates "
    "for that week specifically.\n\n"
    "This guide walks through every metric on the page -- what it means, the exact formula behind it, "
    "and a worked example using real Week 33 (10-16 Aug 2026) figures so the calculation is concrete, "
    "not abstract."
)

pdf.sub_title("A note on how 'this week' is scoped")
pdf.body(
    "All figures are scoped to Ghana (GH) invoices only, excluding cancelled orders and BufferPesa "
    "channel orders -- the same scoping used everywhere else in the dashboard. Weeks run Monday to "
    "Sunday. Selecting a week filters every calculation on the page to that seven-day window, except "
    "where a metric is explicitly built on a longer trailing window (DSO uses 28 days of sales, "
    "explained below) -- that's called out wherever it applies."
)

# ── Revenue vs Target ────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("1. Revenue vs Target")
pdf.body(
    "The total value TribeCo actually invoiced customers during the selected week, compared against "
    "that week's sales target."
)
pdf.formula_box(
    "Revenue This Week = sum of Discountedvalue across every invoice created that week",
    "Discountedvalue is the amount actually billed after any discount is applied -- it's the same "
    "figure used as 'Revenue' everywhere else in the dashboard, so it's always comparable."
)
pdf.body(
    "The small badge next to the figure shows attainment: Revenue divided by that week's target, as "
    "a percentage. Week 33's target was GHS 169,834.00; actual revenue came in at GHS 170,847.50, "
    "for 100.6% attainment -- essentially on target."
)
pdf.body(
    "Weekly targets come from a fixed target sheet (data/weekly_revenue_target.csv), matched to each "
    "week by its Monday-to-Sunday date range. If a week has no target on file, the badge is left off "
    "rather than showing a misleading 0%."
)

# ── Collections % ─────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("2. Collections %")
pdf.body(
    "What share of this week's invoiced revenue was collected back in cash within that same week. "
    "This is a narrow, same-week efficiency measure -- not a running total of all money ever "
    "collected against this week's invoices."
)
pdf.formula_box(
    "Collections % = (repayments received this week) / (revenue invoiced this week) x 100",
)
pdf.body(
    "Important: this can legitimately read 0% even in a healthy week. If a customer is invoiced on "
    "Wednesday and pays two weeks later, that payment counts toward the week it was actually paid, "
    "not the week it was invoiced. A low Collections % does not necessarily mean money is being "
    "lost -- it may simply mean it hasn't arrived yet. DSO (below) is the metric built to answer "
    "the longer-term 'how much is still owed overall' question."
)

# ── DSO ───────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("3. DSO -- Days Sales Outstanding")
pdf.body(
    "DSO answers: if TribeCo stopped selling today, roughly how many days would it take to collect "
    "everything customers currently owe, based on recent sales volume? Lower is better -- it means "
    "cash is coming in faster."
)
pdf.formula_box(
    "DSO = (Outstanding AR as of week-end / Sales in the trailing 28 days) x 28",
    "Outstanding AR as of week-end: for every invoice created on or before that week's end date, "
    "subtract whatever had actually been paid against it by that same date (later payments don't "
    "count -- they hadn't happened yet at that point in time). Add up what's left over, unpaid, "
    "across every invoice.\n\n"
    "Sales, trailing 28 days: total revenue invoiced in the 28 days immediately before and including "
    "the week-end date -- a rolling four-week window, not a calendar month. A single week's sales is "
    "too small and volatile a number to divide by, so four weeks smooths that out. If the data stops "
    "part-way through the selected week, the 28 days are counted back from the last day of data "
    "instead, so empty days don't shrink the sales figure and inflate DSO."
)
pdf.sub_title("Worked example -- Week 33 (week-end 16 Aug 2026)")
pdf.table_header(("Component", 70), ("Value", 113))
pdf.table_row(("Outstanding AR as of 16 Aug 2026", 70), ("GHS 1,824,083.50", 113))
pdf.table_row(("Sales, trailing 28 days (20 Jul - 16 Aug 2026)", 70), ("GHS 642,207.50", 113))
pdf.table_row(("DSO", 70), ("(1,824,083.50 / 642,207.50) x 28 = 79.5 days", 113))
pdf.ln(3)
pdf.body(
    "DSO is then compared against the standard 28-day payment term given to credit customers: "
    "79.5 - 28 = +51.5 days beyond terms. A positive number means customers are, on average, paying "
    "slower than agreed."
)
pdf.body(
    "A common mistake: using each invoice's running 'total repaid' field for the 'outstanding' side "
    "of this formula. That field reflects payments received right up to today, not up to the week "
    "being measured -- so a payment received today would incorrectly reduce a past week's DSO, even "
    "though that money hadn't been collected yet as of that week. The calculation above deliberately "
    "rebuilds the repaid amount from individual repayment dates instead, so DSO for a given week "
    "stays fixed once that week has passed, rather than quietly drifting as new payments come in."
)

# ── Gross Margin ──────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("4. Gross Margin %")
pdf.body(
    "How much of this week's revenue is profit after subtracting the direct cost of the products "
    "sold -- before overhead, salaries, or any other business cost."
)
pdf.formula_box(
    "Gross Margin % = (Revenue - Cost of Goods Sold) / Revenue x 100",
    "Revenue and cost are both built from individual invoice lines (one row per product per order), "
    "not the invoice total -- so margin can be measured product by product. Cost per line = that "
    "SKU's Purchase Price (from the product catalogue) x quantity sold."
)
pdf.sub_title("Worked example -- Week 33")
pdf.table_header(("Component", 70), ("Value", 113))
pdf.table_row(("Revenue (line-item basis, 53 lines / 7 SKUs)", 70), ("GHS 178,240.00", 113))
pdf.table_row(("Cost of goods sold", 70), ("GHS 133,215.60", 113))
pdf.table_row(("Gross profit", 70), ("GHS 45,024.40", 113))
pdf.table_row(("Gross Margin %", 70), ("45,024.40 / 178,240.00 = 25.3%", 113))
pdf.ln(3)
pdf.kpi_box("The coverage caveat",
    "Purchase Price is only filled in for about 18% of all products in the catalogue. Margin can "
    "only be calculated for SKUs that have it -- so a 'coverage %' is always shown next to the "
    "margin figure (e.g. '100% of this week's revenue has cost data on file'). Coverage varies week "
    "to week depending on which SKUs happened to sell. A margin shown with low coverage should be "
    "read with caution -- it's based on a small, possibly unrepresentative slice of that week's sales.")
pdf.kpi_box("Why this differs from the 'Revenue This Week' figure above",
    "Gross margin is measured on the pre-discount, line-item revenue (GHS 178,240.00 in this "
    "example), while the KPI at the top of the page shows the post-discount invoiced revenue "
    "(GHS 170,847.50). See section 6, the Revenue Bridge, for why these two figures differ.")

# ── Agrovets & Multi-SKU ──────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("5. Active / Repeat Agrovets and Multi-SKU Adoption")
pdf.sub_title("Active Agrovets")
pdf.formula_box(
    "Active Agrovets = count of distinct customers tagged Segment Type = 'Agrovet' who placed "
    "at least one order this week",
)
pdf.kpi_box("Segment tagging coverage",
    "Only a subset of Ghana retail centres are tagged 'Agrovet' in the system -- most customer "
    "records currently have no segment tag at all. Agrovet-specific figures only ever cover the "
    "tagged subset, not the full customer base.")
pdf.sub_title("Repeat Agrovets")
pdf.formula_box(
    "Repeat Agrovets % = (Agrovets active this week who also ordered before this week) "
    "/ (Agrovets active this week) x 100",
)
pdf.sub_title("Multi-SKU Adoption")
pdf.body(
    "What share of this week's orders included more than one distinct product, rather than just "
    "one item repeated or a single SKU."
)
pdf.formula_box(
    "Multi-SKU Adoption % = (orders this week with 2+ distinct SKUs) / (orders this week with "
    "any line-item data) x 100",
)

# ── Behind the Numbers ────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("6. Behind the Numbers -- Revenue Bridge")
pdf.body(
    "Explains the gap between the pre-discount value of everything sold and the actual amount "
    "invoiced, in three figures side by side."
)
pdf.table_header(("Figure", 60), ("What it is", 123))
pdf.table_row(("Pre-Discount Value", 60), ("List-price total of every product line sold this week (Price x Quantity, before any discount)", 123))
pdf.table_row(("Discounts Given", 60), ("Pre-Discount Value minus Net Revenue -- the total GHS given away in discounts", 123))
pdf.table_row(("Net Revenue (Invoiced)", 60), ("What's actually billed to the customer -- matches Revenue This Week at the top of the page", 123))
pdf.ln(3)
pdf.body(
    "Worked example, Week 33: Pre-Discount Value GHS 178,240.00, minus GHS 7,392.50 in discounts "
    "(5 of that week's 23 invoices carried a 5% or 10% discount), equals Net Revenue of "
    "GHS 170,847.50 -- exactly the figure shown as Revenue This Week."
)

pdf.sub_title("Gross Margin and DSO, side by side")
pdf.body(
    "Directly below the revenue bridge, two panels re-state the Gross Margin and DSO calculations "
    "from sections 3 and 4 as a plain list of inputs and the resulting figure -- so the formula is "
    "always visible on the page itself, not just in this guide. The same numbers can also be reached "
    "by clicking 'View formula' on the DSO and Gross Margin % cards at the top of the page."
)

# ── AR Aging ───────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("7. AR Aging -- Collections Chase List")
pdf.body(
    "Turns the single DSO number into an actionable list: every invoice still unpaid as of the "
    "selected week's end, grouped by how overdue it is, with the worst offenders listed individually."
)
pdf.formula_box(
    "Days Overdue = week-end date - invoice Due Date",
    "A negative number means the invoice isn't due yet."
)
pdf.table_header(("Bucket", 55), ("Meaning", 128))
pdf.table_row(("Not yet due", 55), ("Due date is after the selected week-end -- no action needed yet", 128))
pdf.table_row(("0-30 days overdue", 55), ("Just past due -- normal follow-up territory", 128))
pdf.table_row(("31-60 days overdue", 55), ("Meaningfully late -- worth a direct follow-up", 128))
pdf.table_row(("61-90 days overdue", 55), ("Seriously overdue -- collections priority", 128))
pdf.table_row(("90+ days overdue", 55), ("At high risk of never being collected", 128))
pdf.ln(3)
pdf.body(
    "Below the bucket chart, a sortable table lists individual overdue invoices -- customer name, "
    "invoice ID, due date, days overdue, and amount outstanding -- sorted worst-first. This is the "
    "list a collections team would work from directly, rather than starting from the single DSO "
    "figure and having to go find out which invoices are actually driving it."
)

# ── SKU Performance & Discounts ───────────────────────────────────────────────
pdf.add_page()
pdf.section_title("8. SKU Performance and Discounts Given")
pdf.sub_title("SKU Performance This Week")
pdf.body(
    "Every distinct product (SKU) sold that week, with units sold, revenue, cost (where cost data "
    "exists), gross profit, and margin %. The bar chart above the table is colour-coded by margin: "
    "green for 25% or higher, gold for 15-25%, red for under 15%, grey where there's no cost data "
    "to judge margin at all."
)
pdf.sub_title("Discounts Given This Week")
pdf.body(
    "Every invoice that carried a discount that week, showing the pre-discount value, the discount "
    "percentage applied, the GHS amount given away, and the net amount actually invoiced. Invoices "
    "with no discount don't appear in this table -- only the ones where a discount was actually applied."
)

# ── Formula popovers ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("9. Click-to-Reveal Formulas on the Page Itself")
pdf.body(
    "The DSO and Gross Margin % cards at the top of the Weekly Info page each have a 'View formula' "
    "button beneath them. Clicking it opens a small panel showing the exact formula for that metric "
    "with that week's real numbers plugged in -- the same worked examples as sections 3 and 4 of "
    "this guide, available on demand without leaving the page."
)

# ── Glossary ──────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Glossary of Terms")
pdf.ln(2)
terms = [
    ("AR", "Accounts Receivable -- money owed to TribeCo by customers that hasn't been collected yet."),
    ("DSO", "Days Sales Outstanding -- on average, how many days it takes to collect payment after a sale."),
    ("COGS", "Cost of Goods Sold -- the direct cost of the products sold, before overhead or other business costs."),
    ("SKU", "Stock Keeping Unit -- the unique code a business assigns to each distinct product it sells or stocks."),
    ("Gross Margin", "Revenue minus COGS, shown as a percentage of revenue -- profit before overhead."),
    ("Agrovet", "An agricultural retail shop selling veterinary and farm input products."),
    ("Discountedvalue", "The invoice field used throughout the dashboard as 'Revenue' -- the amount actually billed after any discount."),
    ("Total Order Value", "An invoice's pre-discount, list-price total -- before any discount is subtracted."),
    ("Week-end", "The Sunday that closes out the selected Monday-to-Sunday week."),
    ("Trailing 28 days", "A rolling 28-day (four-week) look-back window ending on a given date, not a fixed calendar period like a month."),
    ("Attainment", "Actual revenue as a percentage of target -- 100% means the target was hit exactly."),
    ("Aging bucket", "A group of overdue invoices bounded by how many days overdue they are, e.g. '31-60 days overdue'."),
]
pdf.set_font("Helvetica", "B", 9)
pdf.set_text_color(*WHITE)
pdf.set_fill_color(*BRAND)
pdf.set_x(14)
pdf.cell(45, 6.5, "  Term", fill=True)
pdf.cell(145, 6.5, "  Definition", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
for term, definition in terms:
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*ACCENT)
    pdf.set_fill_color(*LIGHT)
    pdf.cell(45, 5.5, clean(f"  {term}"), fill=True, border="B")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*BLACK)
    pdf.multi_cell(145, 5.5, clean(f"  {definition}"), fill=False, border="B")

pdf.output(OUT)
print(f"Report saved: {OUT}")
