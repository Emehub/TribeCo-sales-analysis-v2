"""
Generate a PDF documenting all queries used to extract and analyse
the TribeCo Ghana dashboard data.

Run:  python scripts/generate_queries_report.py
Out:  exports/TribeCo_Queries_Report.pdf
"""
from fpdf import FPDF, XPos, YPos
import os

OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "exports", "TribeCo_Queries_Report.pdf"
)
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# ── Colour palette ──────────────────────────────────────────────────────────────
BRAND  = (20,  83,  45)
ACCENT = (22, 163,  74)
DARK   = (17,  24,  39)
WHITE  = (255, 255, 255)
LIGHT  = (241, 245, 249)
CODE   = (248, 250, 252)
BORDER = (226, 232, 240)

def clean(t):
    return (t.replace("—","--").replace("–","-")
             .replace("'","'").replace("'","'")
             .replace(""",'"').replace(""",'"')
             .replace("•","-").replace("…","..."))


class PDF(FPDF):
    def header(self):
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 14, "F")
        self.set_font("Courier", "B", 8)
        self.set_text_color(*WHITE)
        self.set_xy(10, 3)
        self.cell(0, 8, "TribeCo Ghana  |  Data Query Reference  |  2026")
        self.ln(12)

    # ── Section banner ────────────────────────────────────────────────────────────
    def section(self, number, title):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*WHITE)
        self.set_font("Courier", "B", 11)
        self.set_x(10)
        self.cell(190, 9, clean(f"  {number}  {title}"), fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    # ── Sub-heading ───────────────────────────────────────────────────────────────
    def sub(self, title):
        self.set_text_color(*BRAND)
        self.set_font("Courier", "B", 9)
        self.set_x(12)
        self.cell(186, 6, clean(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.4)
        self.line(12, self.get_y(), 90, self.get_y())
        self.ln(3)

    # ── Prose body ────────────────────────────────────────────────────────────────
    def body(self, text):
        self.set_text_color(*DARK)
        self.set_font("Courier", "", 9)
        self.set_x(14)
        self.multi_cell(183, 5, clean(text))
        self.ln(2)

    # ── Code block ───────────────────────────────────────────────────────────────
    def code(self, text, label=""):
        if label:
            self.set_font("Courier", "B", 8)
            self.set_text_color(*ACCENT)
            self.set_x(14)
            self.cell(186, 5, clean(f"-- {label}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_fill_color(*CODE)
        self.set_draw_color(*BORDER)
        self.set_line_width(0.3)
        lines = clean(text).strip().split("\n")
        self.set_font("Courier", "", 8.5)
        block_h = len(lines) * 5 + 5
        if self.get_y() + block_h > self.page_break_trigger:
            self.add_page()
        y_start = self.get_y()
        self.rect(12, y_start, 186, block_h, "FD")
        self.set_xy(15, y_start + 2.5)
        for line in lines:
            self.set_text_color(*DARK)
            self.set_x(15)
            self.cell(183, 5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    # ── Two-column table row ──────────────────────────────────────────────────────
    def trow(self, c1, c2, header=False):
        if header:
            self.set_fill_color(*BRAND)
            self.set_text_color(*WHITE)
            self.set_font("Courier", "B", 8.5)
        else:
            self.set_fill_color(*LIGHT)
            self.set_text_color(*DARK)
            self.set_font("Courier", "", 8.5)
        self.set_x(12)
        self.cell(55, 6, clean(f"  {c1}"), fill=True, border="B")
        self.cell(131, 6, clean(f"  {c2}"), fill=False, border="B",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Three-column table row (single-line) ─────────────────────────────────────
    def trow3(self, c1, c2, c3, header=False):
        if header:
            self.set_fill_color(*BRAND)
            self.set_text_color(*WHITE)
            self.set_font("Courier", "B", 8)
        else:
            self.set_fill_color(*LIGHT)
            self.set_text_color(*DARK)
            self.set_font("Courier", "", 8)
        self.set_x(12)
        self.cell(40, 6, clean(f"  {c1}"), fill=True, border="B")
        self.cell(75, 6, clean(f"  {c2}"), fill=False, border="B")
        self.cell(71, 6, clean(f"  {c3}"), fill=False, border="B",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Three-column table row (multi-line, handles \n in any column) ─────────────
    def trow3_multi(self, c1, c2, c3, header=False):
        LH = 5        # line height per text line
        PAD = 2.5     # top/bottom padding inside the cell
        W1, W2, W3 = 42, 82, 62

        lines1 = clean(c1).split("\n")
        lines2 = clean(c2).split("\n")
        lines3 = clean(c3).split("\n")
        max_lines = max(len(lines1), len(lines2), len(lines3))
        row_h = max_lines * LH + PAD * 2

        if self.get_y() + row_h > self.page_break_trigger:
            self.add_page()

        y0 = self.get_y()
        x0 = 12

        fill = BRAND if header else LIGHT
        text = WHITE if header else DARK
        style = "B" if header else ""

        # draw filled background for all three columns
        self.set_fill_color(*fill)
        self.rect(x0,        y0, W1,          row_h, "F")
        self.set_fill_color(*(BRAND if header else (255, 255, 255)))
        self.rect(x0 + W1,   y0, W2 + W3,     row_h, "F")

        # column dividers and bottom border
        self.set_draw_color(*BORDER)
        self.set_line_width(0.3)
        self.line(x0, y0 + row_h, x0 + W1 + W2 + W3, y0 + row_h)   # bottom
        self.line(x0 + W1, y0, x0 + W1, y0 + row_h)                  # div 1-2
        self.line(x0 + W1 + W2, y0, x0 + W1 + W2, y0 + row_h)       # div 2-3

        self.set_font("Courier", style, 8)
        self.set_text_color(*text)

        for i, line in enumerate(lines1):
            self.set_xy(x0 + 2, y0 + PAD + i * LH)
            self.cell(W1 - 3, LH, line)

        # col 2 and 3 get dark text always (they have white/light bg)
        self.set_text_color(*DARK)
        self.set_font("Courier", style if header else "", 8)

        for i, line in enumerate(lines2):
            self.set_xy(x0 + W1 + 2, y0 + PAD + i * LH)
            self.cell(W2 - 3, LH, line)

        for i, line in enumerate(lines3):
            self.set_xy(x0 + W1 + W2 + 2, y0 + PAD + i * LH)
            self.cell(W3 - 3, LH, line)

        self.set_xy(x0, y0 + row_h)


# ── Build PDF ────────────────────────────────────────────────────────────────────
pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.set_margins(10, 18, 10)

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 0 — DOCUMENT OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("0", "Document Overview")
pdf.body(
    "This document records every query made against the TribeCo database to produce the "
    "Ghana Operations Dashboard. It is organised in the order the queries are executed:\n\n"
    "  1.  Authentication & Database Discovery (Metabase API)\n"
    "  2.  Raw Table Extraction (10 core tables via Metabase API)\n"
    "  3.  Data Filtering  --  Ghana (GH) only\n"
    "  4.  Data Transformations  --  status codes, derived columns\n"
    "  5.  Dashboard KPI Queries  --  per page (10 pages)\n"
    "  6.  Summary of All Tables Extracted\n"
    "  7.  Query Execution Order  --  End-to-End Flow\n\n"
    "All data is fetched from Metabase via its REST API. Filtering and aggregation "
    "after extraction is performed in Python/pandas on the exported CSV data."
)
pdf.ln(2)
pdf.body("Database:       tribecodb")
pdf.body("Access method:  Metabase REST API  (http://35.241.44.217)")
pdf.body("Output format:  CSV files, one per table, stored in data/ folder")
pdf.body("Extraction script:  scripts/extract_metabase.py")

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 1 — AUTHENTICATION & DATABASE DISCOVERY
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("1", "Authentication & Database Discovery")

pdf.sub("1.1  Login to Metabase (obtain session token)")
pdf.body(
    "Before any data can be extracted a session token must be requested. "
    "This is a standard POST to the Metabase sessions endpoint."
)
pdf.code("""\
POST http://35.241.44.217/api/session
Content-Type: application/json

{
  "username": "theophilus.asante@cowtribe.com",
  "password": "********"
}

-- Response
{
  "id": "<session_token_uuid>"
}

-- The token is then passed as a header on every subsequent request:
X-Metabase-Session: <session_token_uuid>""", "HTTP Request")

pdf.sub("1.2  List all databases in Metabase")
pdf.body("Find the numeric ID of the target database (tribecodb) so it can be referenced in queries.")
pdf.code("""\
GET http://35.241.44.217/api/database
X-Metabase-Session: <token>

-- Response (array of databases)
[
  { "id": 1, "name": "Sample Database" },
  { "id": 2, "name": "tribecodb" }    <-- target
]

-- Filter: find the entry where name == 'tribecodb'
-- Store: db_id = 2  (used in all subsequent calls)""", "HTTP Request")

pdf.sub("1.3  Retrieve full schema / table list")
pdf.body("Fetch metadata for the target database to get all table names and their IDs.")
pdf.code("""\
GET http://35.241.44.217/api/database/{db_id}/metadata
X-Metabase-Session: <token>

-- Response (abridged)
{
  "tables": [
    { "id": 101, "name": "invoice" },
    { "id": 102, "name": "repayment" },
    { "id": 103, "name": "retail_centre" },
    { "id": 104, "name": "payment" },
    { "id": 105, "name": "product" },
    { "id": 106, "name": "invoice_line" },
    { "id": 107, "name": "inventory_request" },
    { "id": 108, "name": "inventory_balances_view" },
    { "id": 109, "name": "preorder_campaign" },
    { "id": 110, "name": "inventory_request_fulfillment" },
    ... (131 additional tables)
  ]
}

-- Store: tmap = { "invoice": 101, "repayment": 102, ... }""", "HTTP Request")

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RAW TABLE EXTRACTION
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("2", "Raw Table Extraction -- 10 Core Tables")

pdf.body(
    "The dashboard uses 10 tables out of the full 141 available. Each table is fetched in full "
    "with no server-side filtering -- all filtering to Ghana data happens locally after download."
)
pdf.ln(2)

tables = [
    ("invoice",                       "Sales invoices -- primary revenue source"),
    ("repayment",                     "Customer repayments against invoices"),
    ("retail_centre",                 "Customer / partner registry"),
    ("payment",                       "Individual payment transactions"),
    ("product",                       "Product catalogue"),
    ("invoice_line",                  "Line items for each invoice (quantity x price)"),
    ("inventory_request",             "Stock requests from partners"),
    ("inventory_balances_view",       "Current inventory levels by location"),
    ("preorder_campaign",             "Pre-order campaign definitions"),
    ("inventory_request_fulfillment", "Fulfillment outcomes for inventory requests"),
]

pdf.trow("Table Name", "Purpose", header=True)
for tname, purpose in tables:
    pdf.trow(tname, purpose)

pdf.ln(5)
pdf.sub("2.1  Metabase API table extraction")
pdf.body(
    "Each table is fetched via a POST to /api/dataset. "
    "The query body specifies only the source table ID -- no WHERE clause -- returning all rows."
)
pdf.code("""\
-- Repeated for each of the 10 tables above, using the table ID from tmap

POST http://35.241.44.217/api/dataset
X-Metabase-Session: <token>
Content-Type: application/json

{
  "database": <db_id>,
  "type":     "query",
  "query":    { "source-table": <table_id> }
}

-- Response structure
{
  "data": {
    "cols": [ {"display_name": "ID"}, {"display_name": "Country Code"}, ... ],
    "rows": [ [1, "GH", ...], [2, "KE", ...], ... ]
  }
}

-- Result: assembled into a DataFrame and saved as data/<table_name>.csv""", "HTTP Request")

pdf.sub("2.2  Saved Metabase questions (bonus export)")
pdf.body("Any saved questions in Metabase that belong to tribecodb are also exported.")
pdf.code("""\
GET http://35.241.44.217/api/card
X-Metabase-Session: <token>

-- Filter: keep only cards where database_id == db_id

-- For each saved question:
POST http://35.241.44.217/api/card/{card_id}/query/csv
X-Metabase-Session: <token>

-- Result saved as: data/question_{question_name}.csv""", "HTTP Request")

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 3 — DATA FILTERING
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("3", "Data Filtering -- Ghana (GH) Only")

pdf.body(
    "All extracted tables contain multi-country data (Ghana and Kenya). "
    "The first operation after loading is to restrict every table to Ghana rows only. "
    "This happens once at load time and applies globally to all dashboard pages."
)
pdf.ln(2)

pdf.sub("3.1  Filter invoices to Ghana")
pdf.code("""\
inv = inv[inv["Country Code"] == "GH"].copy()""", "Ghana Filter")

pdf.sub("3.2  Filter repayments to Ghana")
pdf.code("""\
rep = rep[rep["Country Code"] == "GH"].copy()""", "Ghana Filter")

pdf.sub("3.3  Filter retail_centre (customers) to Ghana")
pdf.code("""\
rc = rc[rc["Country Code"] == "GH"].copy()""", "Ghana Filter")

pdf.sub("3.4  Filter invoice_line to Ghana invoice IDs only")
pdf.body("invoice_line has no Country Code column -- it is filtered indirectly via the Ghana invoice IDs.")
pdf.code("""\
gh_inv_ids = set(inv["ID"].dropna().astype(int))
il = il[il["Invoice ID"].isin(gh_inv_ids)].copy()""", "Ghana Filter")

pdf.sub("3.5  Filter inventory_balances_view to Ghana retail centres")
pdf.body("inventory_balances_view is filtered via Ghana retail centre IDs.")
pdf.code("""\
gh_rc_ids = set(rc["ID"].dropna())
ibv = ibv[ibv["Retail Centre ID"].isin(gh_rc_ids)].copy()""", "Ghana Filter")

pdf.sub("3.6  Tables NOT filtered by country")
pdf.body(
    "The following tables have no Country Code column and are loaded without a country filter:\n\n"
    "  payment                       -- no Country Code; left unfiltered\n"
    "  inventory_request             -- already Ghana-only in source data\n"
    "  inventory_request_fulfillment -- inherits scope from inventory_request\n"
    "  preorder_campaign             -- global campaigns, no country split\n"
    "  product                       -- global product catalogue"
)

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 4 — DATA TRANSFORMATIONS
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("4", "Data Transformations -- Derived Columns & Status Decoding")

pdf.body(
    "After filtering, several columns are derived or decoded from integer status codes "
    "before the data is used in any chart or KPI calculation."
)
pdf.ln(2)

pdf.sub("4.1  Payment status decode")
pdf.code("""\
-- payment.Status integer code: 0 = Failed, 1 = Success
pay["Payment Status"] = pay["Status"].map({0: "Failed", 1: "Success"})""", "Transformation")

pdf.sub("4.2  Invoice date dimensions")
pdf.code("""\
-- Derive Month and Week period labels from invoice created date
inv["Month"] = inv["Created At"].dt.to_period("M").astype(str)
inv["Week"]  = inv["Created At"].dt.to_period("W").astype(str)""", "Transformation")

pdf.sub("4.3  Inventory request status decode")
pdf.code("""\
-- Status codes: 0=Draft, 1=Pending, 2=Processing, 3=Completed, 4=Cancelled, 5=Failed
ir["Request Status"] = ir["Status"].map({
    0:"Draft", 1:"Pending", 2:"Processing",
    3:"Completed", 4:"Cancelled", 5:"Failed"
})""", "Transformation")

pdf.sub("4.4  Inventory delivery type decode")
pdf.code("""\
-- Delivery Type codes: 0=Direct, 1=Via Hub
ir["Delivery Label"] = ir["Delivery Type"].map({0.0:"Direct", 1.0:"Via Hub"})""", "Transformation")

pdf.sub("4.5  Invoice line revenue")
pdf.code("""\
-- Line-level revenue = Quantity * Price
il["Line Revenue"] = pd.to_numeric(il["Quantity"]) * pd.to_numeric(il["Price"])""", "Transformation")

pdf.sub("4.6  Product name consolidation")
pdf.code("""\
-- Merge product name onto invoice lines; prefer Generic Name, fall back to Brand Name
prod_rev = il.merge(prod[["ID","Generic Name","Brand Name"]],
                    left_on="Product ID", right_on="ID", how="left")
prod_rev["Product Name"] = prod_rev["Generic Name"].fillna(
                           prod_rev["Brand Name"]).str.strip()""", "Transformation")

pdf.sub("4.7  Campaign status decode")
pdf.code("""\
-- Status codes: 1=Active, 2=Completed, 3=Cancelled
camp["Status Label"] = camp["Status"].map({
    1:"Active", 2:"Completed", 3:"Cancelled"
}).fillna("Unknown")""", "Transformation")

pdf.sub("4.8  Fulfillment status decode")
pdf.code("""\
-- Status codes: 0=Pending, 1=Processing, 2=Failed, 3=Fulfilled, 4=Cancelled
irf["Fulfillment Status"] = irf["Status"].map({
    0:"Pending", 1:"Processing", 2:"Failed",
    3:"Fulfilled", 4:"Cancelled"
}).fillna("Unknown")""", "Transformation")

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 5 — DASHBOARD KPI QUERIES
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("5", "Dashboard KPI Queries -- Per Page")

# ── Page 1: Overview ────────────────────────────────────────────────────────────
pdf.sub("PAGE 1 -- Overview")
pdf.body("All queries below apply the optional year filter (inv_y = invoices for selected year).")
pdf.ln(1)

pdf.code("""\
-- 5.1 Total Sales (invoiced value, GH, selected year)
total_invoiced = inv_y["Total Order Value"].sum()""", "KPI: Total Sales")

pdf.code("""\
-- 5.2 Total Collected (repayments received, GH, selected year)
total_repaid = rep_y["Amount"].sum()""", "KPI: Collected")

pdf.code("""\
-- 5.3 Outstanding (billed minus collected)
outstanding_val = total_invoiced - total_repaid
collection_pct  = (total_repaid / total_invoiced) * 100""", "KPI: Outstanding")

pdf.code("""\
-- 5.4 Average Order Value (AOV / Basket Size)
avg_order_value = inv_y["Total Order Value"].mean()""", "KPI: AOV")

pdf.add_page()
pdf.code("""\
-- 5.5 New Partners Signed (retail_centre registrations in selected year)
new_partners_y = rc[rc["Created At"].dt.year == yr]
new_signed     = len(new_partners_y)""", "KPI: New Partners Signed")

pdf.code("""\
-- 5.6 Activation Rate (90d)
-- Partners who placed their FIRST order within 90 days of signing up
first_ord = (inv[inv["Customer ID"].isin(new_ids)]
             .sort_values("Created At")
             .groupby("Customer ID")["Created At"].first()
             .reset_index().rename(columns={"Created At":"first_order"}))
first_ord = first_ord.merge(new_partners_y[["ID","Created At"]]
            .rename(columns={"ID":"Customer ID","Created At":"signed_at"}),
            on="Customer ID", how="left")
first_ord["days"]  = (first_ord["first_order"] - first_ord["signed_at"]).dt.days
activated_90d      = (first_ord["days"].between(0, 90)).sum()
activation_rate    = activated_90d / new_signed * 100""", "KPI: Activation Rate")

pdf.code("""\
-- 5.7 Repeat Rate (30d)
-- Ordering customers who placed a SECOND order within 30 days of their first
first_inv  = (inv_y.sort_values("Created At").groupby("Customer ID")
              ["Created At"].first().reset_index()
              .rename(columns={"Created At":"first_order"}))
all_ord    = inv_y.merge(first_inv, on="Customer ID")
all_ord["days_gap"] = (all_ord["Created At"] - all_ord["first_order"]).dt.days
repeat_custs = all_ord[all_ord["days_gap"].between(1,30)]["Customer ID"].nunique()
active_custs = inv_y["Customer ID"].nunique()
repeat_rate  = repeat_custs / active_custs * 100""", "KPI: Repeat Rate")

pdf.add_page()
pdf.code("""\
-- 5.8 Revenue Concentration (Top 5 and Top 10 customers)
cust_rev  = inv_y.groupby("Customer ID")["Total Order Value"].sum()
             .sort_values(ascending=False)
rev_top5  = cust_rev.head(5).sum()  / total_invoiced * 100
rev_top10 = cust_rev.head(10).sum() / total_invoiced * 100""", "KPI: Revenue Concentration")

pdf.code("""\
-- 5.9 Reconciliation Rate
-- Percentage of GH invoices that have at least one matching repayment record
inv_ids_y  = set(inv_y["ID"].dropna().astype(int))
rep_ids    = set(rep["Invoice ID"].dropna().astype(int))
recon_rate = len(inv_ids_y & rep_ids) / len(inv_ids_y) * 100""", "KPI: Reconciliation Rate")

pdf.code("""\
-- 5.10 Monthly Revenue Trend (bar chart)
monthly = inv_y.groupby("Month")["Total Order Value"].sum().reset_index()
monthly["prev"] = monthly["Total Order Value"].shift(1)
monthly["pct"]  = ((monthly["Total Order Value"] - monthly["prev"])
                   / monthly["prev"] * 100).round(1)""", "Chart: Monthly Revenue Trend")

pdf.code("""\
-- 5.11 Sales by City (donut chart -- top 8 cities)
city_sales = (inv_y.groupby("Customer City")["Total Order Value"]
              .sum().reset_index()
              .sort_values("Total Order Value", ascending=False)
              .head(8))""", "Chart: Sales by City")

pdf.code("""\
-- 5.12 Repayment Status distribution
rs = inv_y["Repayment Status"].value_counts().reset_index()""", "Chart: Repayment Status")

pdf.code("""\
-- 5.13 Payment Mode distribution
pm = rep_y["Payment Method"].value_counts().reset_index()""", "Chart: Payment Mode")

# ── Page 2: Sales Performance ────────────────────────────────────────────────────
pdf.add_page()
pdf.sub("PAGE 2 -- Sales Performance")

pdf.code("""\
-- 5.14 Monthly Sales vs Previous Month (MoM change %)
m = inv_f.groupby("Month")["Total Order Value"].sum().reset_index()
m["Prev"]     = m["Total Order Value"].shift(1)
m["Change %"] = ((m["Total Order Value"] - m["Prev"]) / m["Prev"] * 100).round(1)""",
"KPI + Chart: Monthly Sales")

pdf.code("""\
-- 5.15 Weekly Sales Trend (last 16 weeks)
w = inv_f.groupby("Week")["Total Order Value"].sum().reset_index().tail(16)""",
"Chart: Weekly Sales Trend")

# ── Page 3: Customers ─────────────────────────────────────────────────────────
pdf.sub("PAGE 3 -- Customers")

pdf.code("""\
-- 5.16 Top 10 Customers by Total Order Value
top_cust_y = (inv_y.merge(rc_names, left_on="Customer ID", right_on="ID", how="left")
              .groupby("Name")["Total Order Value"].sum()
              .sort_values(ascending=False).reset_index())
top_cust = top_cust_y.head(10)""", "Chart: Top 10 Customers")

pdf.code("""\
-- 5.17 New Partner Registrations by Month and Segment Type
rc_dated = rc.copy()
rc_dated["Created At"] = pd.to_datetime(rc_dated["Created At"], errors="coerce")
new_partners_y = rc_dated[rc_dated["Created At"].dt.year == yr]
new_partners_y["Month"] = new_partners_y["Created At"].dt.to_period("M").astype(str)
monthly_new = new_partners_y.groupby(["Month","Segment Type"])["ID"].count()""",
"Chart: New Partner Registrations")

# ── Page 4: Payments ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.sub("PAGE 4 -- Payments")

pdf.code("""\
-- 5.18 Monthly Invoiced vs Collected comparison
inv_monthly = inv_y.groupby("Month")["Total Order Value"].sum().reset_index()
rep_monthly = rep_y.groupby("Month")["Amount"].sum().reset_index()
monthly_cmp = inv_monthly.merge(rep_monthly, on="Month", how="outer").fillna(0)""",
"Chart: Monthly Invoiced vs Collected")

pdf.code("""\
-- 5.19 Payment Method Summary (transactions, total, average)
pm_summary = (rep_y.groupby("Payment Method")["Amount"]
              .agg(Transactions="count", Total="sum", Average="mean")
              .reset_index())""", "Table: Payment Method Summary")

# ── Page 5: Weekly Scorecard ────────────────────────────────────────────────
pdf.sub("PAGE 5 -- Weekly Scorecard")

pdf.code("""\
-- 5.20 Weekly Orders and Sales (all weeks in selected year)
weekly = inv_y.groupby("Week").agg(
    Orders=("ID","count"),
    Invoice_Total=("Total Order Value","sum")
).reset_index()""", "Chart + Table: Weekly Scorecard")

pdf.code("""\
-- 5.21 Overdue Invoices (exceptions list)
overdue = inv_y[inv_y["Repayment Status"] == "Overdue"]""", "Table: Overdue Invoices")

# ── Page 6: Reconciliation ───────────────────────────────────────────────────
pdf.add_page()
pdf.sub("PAGE 6 -- Reconciliation")

pdf.code("""\
-- 5.22 Invoice-Repayment Matching
-- An invoice is 'reconciled' if its ID appears in the repayment table
inv_ids_y = set(inv_y["ID"].dropna().astype(int))
rep_ids   = set(rep["Invoice ID"].dropna().astype(int))
matched   = inv_ids_y & rep_ids          -- intersect (reconciled)
unmatched = inv_ids_y - rep_ids          -- difference (unreconciled)
recon_rate = len(matched) / len(inv_ids_y) * 100""", "KPI + Table: Reconciliation")

# ── Page 7: Data Quality ─────────────────────────────────────────────────────
pdf.sub("PAGE 7 -- Data Quality")

pdf.code("""\
-- 5.23 Field completeness (% non-null rows per column per table)
completeness = table[field].notna().mean() * 100""",
"Chart: Data Quality Completeness")

# ── Page 8: Reliability ──────────────────────────────────────────────────────
pdf.sub("PAGE 8 -- Reliability")

pdf.code("""\
-- 5.24 Inventory Request Fulfillment Rate
ir_status        = ir["Request Status"].value_counts().reset_index()
completed_ir     = ir[ir["Request Status"] == "Completed"].shape[0]
total_ir         = len(ir)
fulfillment_rate = completed_ir / total_ir * 100""", "KPI: Fulfillment Rate")

pdf.code("""\
-- 5.25 Fulfillment outcomes (inventory_request_fulfillment)
irf_status = irf["Fulfillment Status"].value_counts().reset_index()""",
"Chart: Fulfillment Status Donut")

pdf.code("""\
-- 5.26 Stockout count (inventory balance = 0)
stockouts = (ibv["Balance"] == 0).sum()""", "KPI: Stockouts")

# ── Page 9: Segmentation ────────────────────────────────────────────────────
pdf.add_page()
pdf.sub("PAGE 9 -- Segmentation")

pdf.code("""\
-- 5.27 Revenue by Customer Segment (Agrovet / Provider / Hatchery)
seg_inv = inv_y.merge(rc[["ID","Segment Type"]], left_on="Customer ID", right_on="ID", how="left")
seg_summary = seg_inv.groupby("Segment Type").agg(
    Customers  = ("Customer ID","nunique"),
    Orders     = ("ID","count"),
    Total_Sales= ("Total Order Value","sum"),
    AOV        = ("Total Order Value","mean")
).reset_index()""", "Table: Segmentation Summary")

pdf.code("""\
-- 5.28 Revenue Concentration Curve (Lorenz curve)
-- Customers ranked from highest to lowest spend; cumulative revenue share plotted
cust_rev = inv_y.groupby("Customer ID")["Total Order Value"].sum().sort_values(ascending=False)
cum_pct  = cust_rev.cumsum() / cust_rev.sum() * 100""", "Chart: Revenue Concentration Curve")

pdf.code("""\
-- 5.29 Order Value Histogram (low-ticket threshold = 25th percentile)
low_thresh = inv_y["Total Order Value"].quantile(0.25)
hfso_rate  = (inv_y["Total Order Value"] <= low_thresh).mean() * 100""",
"Chart: Order Value Distribution")

# ── Page 10: Campaigns ──────────────────────────────────────────────────────
pdf.sub("PAGE 10 -- Campaigns")

pdf.code("""\
-- 5.30 Campaign Status Summary
camp_status = camp["Status Label"].value_counts().reset_index()

-- 5.31 Campaign Timeline (Gantt data)
-- Columns used: Name, Status Label, Start Date, End Date
-- Duration = End Date - Start Date""",
"KPI + Chart: Campaign Overview")

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 6 — FULL TABLE EXTRACTION SUMMARY
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("6", "Summary -- All 10 Core Tables Extracted")

pdf.body(
    "The dashboard extracts exactly 10 tables from the tribecodb database via Metabase API. "
    "The remaining 131 tables in the database are exported to CSV as a backup "
    "but are not used in any dashboard calculation."
)
pdf.ln(3)

pdf.trow3_multi("Table", "Key Columns Used", "Dashboard Pages", header=True)
rows = [
    ("invoice",
     "ID, Country Code, Customer ID,\nTotal Order Value, Created At,\nDue Date, Repayment Status,\nCustomer City, Month, Week",
     "Overview, Sales, Customers,\nPayments, Weekly, Recon,\nData Quality, Segmentation"),
    ("repayment",
     "ID, Invoice ID, Amount,\nCountry Code, Payment Method,\nCreated At, Repayment Route",
     "Overview, Payments,\nWeekly Scorecard,\nReconciliation"),
    ("retail_centre",
     "ID, Country Code, Name,\nStatus, Segment Type,\nCreated At",
     "Overview, Customers,\nSegmentation"),
    ("payment",
     "ID, Status, Amount,\nCreated At, Payment Status",
     "Overview, Payments"),
    ("product",
     "ID, Generic Name, Brand Name",
     "Merged with invoice_line"),
    ("invoice_line",
     "Invoice ID, Product ID,\nQuantity, Price, Line Revenue",
     "Segmentation (product rev)"),
    ("inventory_request",
     "ID, Status, Created At,\nRequest Status, Delivery Type",
     "Reliability"),
    ("inventory_balances_view",
     "Retail Centre ID, Balance",
     "Reliability (stockouts)"),
    ("preorder_campaign",
     "Name, Status, Start Date,\nEnd Date, Status Label",
     "Campaigns"),
    ("inventory_request_fulfillment",
     "Status, Expected At,\nCreated At, Fulfillment Status",
     "Reliability"),
]
for tname, cols, pages in rows:
    pdf.trow3_multi(tname, cols, pages)

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 7 — QUERY EXECUTION ORDER
# ════════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section("7", "Query Execution Order -- End-to-End Flow")

pdf.body("The complete sequence of operations from login to dashboard display:")
pdf.ln(2)

steps = [
    ("Step 1",  "POST /api/session",                     "Authenticate; obtain session token"),
    ("Step 2",  "GET  /api/database",                    "Find tribecodb ID in Metabase"),
    ("Step 3",  "GET  /api/database/{id}/metadata",      "Get all table names and IDs"),
    ("Step 4",  "POST /api/dataset x 10",                "Extract each core table (all rows)"),
    ("Step 5",  "Save to CSV",                           "Write data/{table}.csv"),
    ("Step 6",  "Filter: Country Code = GH",             "Restrict to Ghana data"),
    ("Step 7",  "Filter: Invoice ID join",               "Restrict invoice_line to GH invoices"),
    ("Step 8",  "Filter: Retail Centre ID join",         "Restrict inventory to GH locations"),
    ("Step 9",  "Decode status columns",                 "Integer codes -> readable labels"),
    ("Step 10", "Derive Month/Week columns",             "Date -> period labels for groupby"),
    ("Step 11", "Calc Line Revenue",                     "Quantity * Price per invoice line"),
    ("Step 12", "Merge product names",                   "invoice_line JOIN product"),
    ("Step 13", "Dashboard KPI aggregations (5.1-5.31)", "Groupby, sum, count per page"),
    ("Step 14", "Render charts and tables",              "Plotly/Streamlit display"),
]
pdf.trow("Step", "Operation", header=True)
for step, op, desc in steps:
    pdf.set_font("Courier", "B", 8)
    pdf.set_text_color(*ACCENT)
    pdf.set_fill_color(*LIGHT)
    pdf.set_x(12)
    pdf.cell(22, 7, clean(f"  {step}"), fill=True, border="B")
    pdf.set_font("Courier", "", 8)
    pdf.set_text_color(*DARK)
    pdf.cell(84, 7, clean(f"  {op}"), fill=False, border="B")
    pdf.cell(82, 7, clean(f"  {desc}"), fill=False, border="B",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

pdf.ln(6)
pdf.body(
    "Refresh cycle: data_updater.py runs Steps 1-5 automatically every 5 minutes in the background. "
    "Steps 6-14 run in the Streamlit app on each page load, with a 5-minute client-side cache (TTL=300s)."
)

# ── Save ─────────────────────────────────────────────────────────────────────────
pdf.output(OUT)
print(f"Saved: {OUT}")
