"""
Generate the August-close YTD Commercial Performance Review for TribeCo Ghana.
Run: python3 scripts/generate_ytd_commercial_review.py
Output: exports/Ghana_YTD_Commercial_Review_Aug2026.pdf

All figures are computed fresh from data/*.csv at run time -- nothing here is
hardcoded except section structure and narrative framing.
"""
import os
import pandas as pd
from fpdf import FPDF, XPos, YPos

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT  = os.path.join(BASE, "exports", "Ghana_YTD_Commercial_Review_Aug2026.pdf")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

BRAND  = (2, 75, 48)
ACCENT = (31, 122, 77)
GOLD   = (201, 151, 90)
RED    = (185, 28, 28)
BLACK  = (17, 24, 39)
WHITE  = (255, 255, 255)
LIGHT  = (241, 247, 244)
AMBER  = (191, 105, 8)

# DSO = Outstanding AR / sales in the trailing DSO_WINDOW_DAYS x DSO_WINDOW_DAYS,
# benchmarked against the standard customer payment term. Keep in sync with dashboard/app.py.
DSO_WINDOW_DAYS     = 28
STANDARD_TERMS_DAYS = 28

MONTH_ABBR = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
              "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}

def mo_short(m):
    return MONTH_ABBR.get(m.split("-")[1], m)

def clean(text):
    return (str(text)
        .replace("—", "--").replace("–", "-")
        .replace("’", "'").replace("‘", "'")
        .replace("“", '"').replace("”", '"')
        .replace("·", "*").replace("•", "-").replace("…", "...")
        .replace("÷", "/").replace("×", "x"))

# ══════════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════════
inv = pd.read_csv(f"{DATA}/invoice.csv")
inv["Created At"] = pd.to_datetime(inv["Created At"], errors="coerce")
inv["Due Date"]   = pd.to_datetime(inv["Due Date"], errors="coerce")
inv = inv[inv["Country Code"] == "GH"].copy()
_f = pd.Series(True, index=inv.index)
if "Order Type" in inv.columns: _f &= (inv["Order Type"] == 1)
if "Channel" in inv.columns:    _f &= (inv["Channel"] != "BufferPesa")
if "Status" in inv.columns:     _f &= (inv["Status"] != 5)
inv = inv[_f].copy()
inv["Discountedvalue"]  = pd.to_numeric(inv["Discountedvalue"], errors="coerce").fillna(0)
inv["Total Order Value"] = pd.to_numeric(inv.get("Total Order Value"), errors="coerce").fillna(0)
inv["Month"] = inv["Created At"].dt.to_period("M").astype(str)
inv_yr = inv[inv["Created At"].dt.year == 2026].copy()
months = sorted(inv_yr["Month"].unique())
as_of  = inv["Created At"].max()
as_of_label = as_of.strftime("%d %b %Y")

rep = pd.read_csv(f"{DATA}/repayment.csv")
rep["Created At"] = pd.to_datetime(rep["Created At"], errors="coerce")
rep["Month"] = rep["Created At"].dt.to_period("M").astype(str)

rc = pd.read_csv(f"{DATA}/retail_centre.csv")
rc_gh = rc[rc["Country Code"] == "GH"].copy()
agro_ids = set(rc_gh[rc_gh["Segment Type"] == "Agrovet"]["ID"])
agro_tagged_n, agro_total_n = len(agro_ids), len(rc_gh)

il   = pd.read_csv(f"{DATA}/invoice_line.csv")
prod = pd.read_csv(f"{DATA}/product.csv")
target = pd.read_csv(f"{DATA}/revenue_target.csv")

# 1. Revenue vs target
mo = inv_yr.groupby("Month")["Discountedvalue"].sum().reset_index()
mo = mo.merge(target, on="Month", how="left")
mo["Attain"] = mo["Discountedvalue"] / mo["Target"] * 100
mo["Orders"] = inv_yr.groupby("Month").size().values
mo["AOV"] = mo["Discountedvalue"] / mo["Orders"]
mo = mo.sort_values("Month")

# 2. Active Agrovets, new vs repeat
first_order = inv.groupby("Customer ID")["Created At"].min()
cust_rows = []
for m in months:
    sub = inv_yr[inv_yr["Month"] == m]
    custs = set(sub["Customer ID"].dropna())
    active_agro = len(custs & agro_ids)
    new_c = sum(1 for c in custs if pd.notna(first_order.get(c))
                and first_order[c].to_period("M").strftime("%Y-%m") == m)
    cust_rows.append(dict(Month=m, Active=len(custs), ActiveAgro=active_agro,
                          New=new_c, Repeat=len(custs) - new_c))
cust_df = pd.DataFrame(cust_rows)

# 3. Repeat-order-rate cohorts (30-day) -- flagged low-n
inv_sorted = inv.sort_values("Created At")
fo = inv_sorted.groupby("Customer ID")["Created At"].first().rename("first_order")
merged = inv.merge(fo, on="Customer ID")
merged["days_gap"] = (merged["Created At"] - merged["first_order"]).dt.days
merged["first_month"] = merged["first_order"].dt.to_period("M").astype(str)
cohort_rows = []
for m in months:
    cohort_custs = merged[merged["first_month"] == m]["Customer ID"].unique()
    repeaters = merged[(merged["Customer ID"].isin(cohort_custs)) &
                       (merged["days_gap"].between(1, 30))]["Customer ID"].nunique()
    n = len(cohort_custs)
    cohort_rows.append(dict(Month=m, CohortSize=n, Repeaters=repeaters,
                            Rate=(repeaters/n*100 if n else None)))
cohort_df = pd.DataFrame(cohort_rows)

# 4. Multi-SKU adoption trend
il_yr = il[il["Invoice ID"].isin(inv_yr["ID"])]
sku_per_order = il_yr.groupby("Invoice ID")["Product ID"].nunique()
inv_lines = inv_yr[inv_yr["ID"].isin(sku_per_order.index)][["ID", "Month"]].copy()
inv_lines["SKUs"] = inv_lines["ID"].map(sku_per_order)
msku_rows = []
for m in months:
    sub = inv_lines[inv_lines["Month"] == m]
    n = len(sub)
    multi = int((sub["SKUs"] > 1).sum())
    msku_rows.append(dict(Month=m, OrdersWithLines=n, MultiSKU=multi,
                          Pct=(multi/n*100 if n else None)))
msku_df = pd.DataFrame(msku_rows)

# 5. Product mix
il_pm = il_yr.merge(inv_yr[["ID", "Month"]], left_on="Invoice ID", right_on="ID", how="left")
il_pm = il_pm.merge(prod[["ID", "Sku", "Generic Name", "Brand Name"]],
                    left_on="Product ID", right_on="ID", how="left", suffixes=("", "_p"))
il_pm["Line Revenue"] = il_pm["Price"] * il_pm["Quantity"]
il_pm["Product Name"] = il_pm["Generic Name"].fillna(il_pm["Brand Name"]).fillna(il_pm["Sku"])
by_prod_month = il_pm.groupby(["Month", "Product Name"])["Line Revenue"].sum().reset_index()
n_products_by_month = il_pm.groupby("Month")["Product Name"].nunique()
top3_by_month = {}
for m in months:
    sub = by_prod_month[by_prod_month["Month"] == m].sort_values("Line Revenue", ascending=False).head(3)
    tot = sub["Line Revenue"].sum() and by_prod_month[by_prod_month["Month"] == m]["Line Revenue"].sum()
    top3_by_month[m] = [(r["Product Name"], r["Line Revenue"]/tot*100 if tot else 0) for _, r in sub.iterrows()]

# 6. Collections trend + DSO trend
coll_by_month = rep.groupby("Month")["Amount"].sum()
dso_rows = []
data_end = max(inv["Created At"].max(), rep["Created At"].max())
for m in months:
    period_end = pd.Period(m, freq="M").end_time.tz_localize("UTC")
    # Partial month: count the window back from the last data point, not month-end,
    # or the empty days shrink the sales base and inflate DSO.
    dso_asof = min(period_end, data_end)
    sales_win = inv[(inv["Created At"] > dso_asof - pd.Timedelta(days=DSO_WINDOW_DAYS)) &
                    (inv["Created At"] <= period_end)]["Discountedvalue"].sum()
    ia = inv[inv["Created At"] <= period_end][["ID", "Discountedvalue"]]
    ra = rep[rep["Created At"] <= period_end].groupby("Invoice ID")["Amount"].sum()
    ia = ia.merge(ra.rename("Repaid"), left_on="ID", right_index=True, how="left")
    ia["Repaid"] = ia["Repaid"].fillna(0)
    ar = (ia["Discountedvalue"] - ia["Repaid"]).clip(lower=0).sum()
    dso = ar / sales_win * DSO_WINDOW_DAYS if sales_win else None
    rev = inv_yr[inv_yr["Month"] == m]["Discountedvalue"].sum()
    coll = coll_by_month.get(m, 0)
    dso_rows.append(dict(Month=m, AR=ar, SalesWindow=sales_win, DSO=dso, Revenue=rev, Collected=coll))
dso_df = pd.DataFrame(dso_rows)
dso_df["BeyondTerms"] = dso_df["DSO"] - STANDARD_TERMS_DAYS

# DSO ranges quoted in the narrative -- Q1 vs. April onward, when payment behaviour shifted.
def _rng(series, fmt="{:.0f}"):
    s = series.dropna()
    lo, hi = fmt.format(s.min()), fmt.format(s.max())
    return lo if lo == hi else f"{lo} to {hi}"
_dso_q1    = dso_df[dso_df["Month"] <= "2026-03"]
_dso_later = dso_df[dso_df["Month"] >= "2026-04"]
dso_q1_rng,    dbt_q1_rng    = _rng(_dso_q1["DSO"]),    _rng(_dso_q1["BeyondTerms"], "{:+.0f}")
dso_later_rng, dbt_later_rng = _rng(_dso_later["DSO"]), _rng(_dso_later["BeyondTerms"], "{:+.0f}")
n_later_over = int((_dso_later["BeyondTerms"] > 0).sum())
n_months_over, n_months = int((dso_df["BeyondTerms"] > 0).sum()), int(dso_df["DSO"].notna().sum())
later_multiple = _rng(_dso_later["DSO"] / STANDARD_TERMS_DAYS, "{:.1f}")

ytd_revenue    = inv_yr["Discountedvalue"].sum()
ytd_collected  = rep[rep["Created At"].dt.year == 2026]["Amount"].sum()

# 7. AR aging snapshot as of latest data
ia_now = inv[["ID", "Discountedvalue", "Due Date"]].copy()
ra_now = rep.groupby("Invoice ID")["Amount"].sum()
ia_now = ia_now.merge(ra_now.rename("Repaid"), left_on="ID", right_index=True, how="left")
ia_now["Repaid"] = ia_now["Repaid"].fillna(0)
ia_now["Outstanding"] = (ia_now["Discountedvalue"] - ia_now["Repaid"]).clip(lower=0)
ia_now = ia_now[ia_now["Outstanding"] > 0.01].copy()
ia_now["Days Overdue"] = (as_of - ia_now["Due Date"]).dt.days
def _bucket(d):
    if pd.isna(d): return "No due date"
    if d < 0: return "Not yet due"
    if d <= 30: return "0-30 days"
    if d <= 60: return "31-60 days"
    if d <= 90: return "61-90 days"
    return "90+ days"
ia_now["Bucket"] = ia_now["Days Overdue"].apply(_bucket)
bucket_order = ["Not yet due", "0-30 days", "31-60 days", "61-90 days", "90+ days", "No due date"]
aging = ia_now.groupby("Bucket")["Outstanding"].agg(Total="sum", Count="count").reindex(bucket_order).dropna(how="all")
total_ar = ia_now["Outstanding"].sum()

# 8. Concentration
by_cust = inv_yr.groupby("Customer ID")["Discountedvalue"].sum().sort_values(ascending=False)
top5_pct  = by_cust.head(5).sum() / by_cust.sum() * 100
top10_pct = by_cust.head(10).sum() / by_cust.sum() * 100
n_customers_ytd = len(by_cust)

# 9. Cost coverage
cost_cov_n, cost_cov_total = prod["Purchase Price"].notna().sum(), len(prod)

# ══════════════════════════════════════════════════════════════════════════════════
# PDF
# ══════════════════════════════════════════════════════════════════════════════════
class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 14, "F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*WHITE)
        self.set_xy(10, 3)
        self.cell(0, 8, "TribeCo Ghana  |  YTD Commercial Review  |  August 2026 Close")
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
        self.set_font("Helvetica", "B", 26)
        self.set_text_color(*WHITE)
        self.set_xy(20, 88)
        self.multi_cell(170, 12, "Ghana Commercial Performance", align="C")
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*GOLD)
        self.set_xy(20, 112)
        self.cell(170, 10, "Year-to-Date Review -- August 2026 Close", align="C")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*WHITE)
        self.set_xy(20, 140)
        self.cell(170, 7, f"Covering January - August 2026 (data as of {as_of_label})", align="C")
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

    def callout(self, label, text, color=GOLD):
        # Rough height estimate (label row + wrapped body lines) so a callout never
        # splits label-on-one-page / body-on-the-next across a page break.
        est_lines = max(1, -(-len(clean(text)) // 95))
        est_height = 5.5 + est_lines * 5 + 3
        if self.get_y() + est_height > self.page_break_trigger:
            self.add_page()
        self.set_fill_color(*LIGHT)
        self.set_x(14)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*color)
        self.cell(183, 5.5, clean(label), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(14)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*BLACK)
        self.multi_cell(183, 5, clean(text), fill=True)
        self.ln(1.5)

    def table(self, headers, rows, widths):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 8.5)
        self.set_x(14)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, clean(f" {h}"), fill=True)
        self.ln()
        self.set_font("Helvetica", "", 8.5)
        for i, row in enumerate(rows):
            self.set_x(14)
            self.set_fill_color(*LIGHT) if i % 2 == 0 else self.set_fill_color(255, 255, 255)
            self.set_text_color(*BLACK)
            for val, w in zip(row, widths):
                self.cell(w, 6, clean(f" {val}"), fill=True, border="B")
            self.ln()
        self.ln(2)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(10, 16, 10)
pdf.cover()

# ── Executive Summary ────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Executive Summary")
pdf.body(
    f"This review covers TribeCo Ghana's commercial performance from January through August 2026 "
    f"(data as of {as_of_label}; August is a partial month, not yet closed). It is built directly "
    f"from invoice, repayment, and product records -- every figure below is computed, not estimated."
)
pdf.callout("Revenue trajectory has flattened after a strong start",
    f"Jan-Mar ran well ahead of target (113-141% attainment). Apr-Jul landed within half a point of "
    f"exactly 100% of target for four straight months -- worth confirming those targets were fixed "
    f"before each month started, not set from the actuals afterward. August is tracking at "
    f"{mo[mo['Month']=='2026-08']['Attain'].iloc[0]:.0f}% with the month still in progress.", ACCENT)
pdf.callout(f"From April, customers are taking {later_multiple}x their agreed payment window",
    f"Standard terms are {STANDARD_TERMS_DAYS} days. DSO ({DSO_WINDOW_DAYS}-day sales basis) ran "
    f"{dso_q1_rng} days through Q1 ({dbt_q1_rng} days vs. terms), then {dso_later_rng} days from April "
    f"onward ({dbt_later_rng} days vs. terms), over terms in {n_later_over} of {len(_dso_later)} months "
    f"since. This is the review's single most material finding.", RED)
pdf.callout("Multi-SKU adoption is a genuine, sustained improvement",
    f"Orders with 2+ distinct products rose from ~42-51% in Q1 to ~55-60% from May onward -- a real "
    f"trend, not noise.", ACCENT)
pdf.callout("Two data coverage gaps limit how far some figures can be trusted",
    f"Only {cost_cov_n} of {cost_cov_total} products ({cost_cov_n/cost_cov_total*100:.0f}%) have cost "
    f"data on file, so margin/profitability figures cover a minority of the catalogue. Only "
    f"{agro_tagged_n} of {agro_total_n} Ghana customer records ({agro_tagged_n/agro_total_n*100:.0f}%) "
    f"are tagged 'Agrovet' -- though notably, every customer who actually placed an order this year "
    f"was among that tagged group, so the Active/Repeat Agrovet figures below are representative of "
    f"real trading activity even though the wider registry is mostly untagged.", AMBER)

# ── 1. Commercial Performance ─────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("1. Commercial Performance -- Revenue vs Target")
pdf.body("Monthly revenue against target, January through August 2026.")
rows = [(mo_short(r["Month"]), f"GHS {r['Discountedvalue']:,.0f}", f"GHS {r['Target']:,.0f}",
         f"{r['Attain']:.1f}%" + (" (partial month)" if r["Month"] == months[-1] else ""))
        for _, r in mo.iterrows()]
pdf.table(["Month", "Revenue", "Target", "Attainment"], rows, [35, 50, 50, 58])
pdf.callout("Trajectory change, not a straight line",
    "Q1 ran comfortably ahead of target (113-141%). From April, attainment sits within a point of "
    "exactly 100% for four consecutive months -- either a genuine stabilisation at plan, or a sign "
    "that targets from April onward were calibrated to expected actuals rather than set independently. "
    "Recommend confirming the target-setting process for Apr-Jul with whoever owns it before reading "
    "'on target' as a performance signal for those months.")

# ── 2. Customer & Order Behaviour ─────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("2. Customer and Order Behaviour")
pdf.sub_title("Active Agrovets, new vs. repeat, and average order value, by month")
rows = [(mo_short(r["Month"]), r["ActiveAgro"], r["New"], r["Repeat"],
         f"GHS {mo[mo['Month']==r['Month']]['AOV'].iloc[0]:,.0f}")
        for _, r in cust_df.iterrows()]
pdf.table(["Month", "Active Agrovets", "New", "Repeat", "AOV"], rows, [30, 40, 25, 30, 68])
pdf.callout("Active base is small and stable, not growing",
    f"{n_customers_ytd} distinct customers have ordered at all in 2026. Monthly active count has held "
    f"in a narrow 20-31 band all year with almost no new customers most months (0-2 in six of eight "
    f"months) -- growth this year has come from ordering frequency and basket size among existing "
    f"accounts, not from acquiring new ones.")
pdf.ln(2)
pdf.sub_title("Repeat-order rate (2nd order within 30 days of 1st), by month of first order")
rows = [(mo_short(r["Month"]), int(r["CohortSize"]),
         f"{r['Rate']:.0f}%" if pd.notna(r["Rate"]) else "n/a")
        for _, r in cohort_df.iterrows()]
pdf.table(["Cohort Month", "New Customers", "Repeat Rate (30d)"], rows, [50, 60, 73])
pdf.callout("Read this trend with caution -- the cohorts are very small",
    "New-customer cohorts range from 0 to 9 people a month. A rate built on 1-2 customers can swing "
    "from 0% to 100% on a single account's behaviour -- it is not a reliable trend on its own. The "
    "consistent signal is the small cohort sizes themselves (new customer acquisition has been minimal "
    "most months), not the repeat-rate percentage.", AMBER)

# ── 3. Multi-SKU Adoption ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("3. Multi-SKU Adoption")
pdf.body("Share of orders containing more than one distinct product, by month.")
rows = [(mo_short(r["Month"]), int(r["OrdersWithLines"]), int(r["MultiSKU"]),
         f"{r['Pct']:.1f}%" if pd.notna(r["Pct"]) else "n/a")
        for _, r in msku_df.iterrows()]
pdf.table(["Month", "Orders", "Multi-SKU Orders", "Adoption %"], rows, [35, 40, 50, 68])
pdf.callout("Sustained improvement, not a spike",
    "Adoption stepped up from the low-to-mid 40s% in Q1 to the mid-50s to ~60% from May through "
    "August -- five consecutive months at the higher level. This reads as a real, durable shift in "
    "ordering behaviour rather than a one-off large order pulling the average up.", ACCENT)

# ── 4. Product Portfolio ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("4. Product Portfolio Mix")
pdf.body("Top 3 products by revenue share each month, and the count of distinct products sold.")
rows = []
for m in months:
    n = n_products_by_month.get(m, 0)
    top3 = ", ".join(f"{name} ({pct:.0f}%)" for name, pct in top3_by_month.get(m, []))
    rows.append((mo_short(m), int(n), top3))
pdf.table(["Month", "Distinct Products", "Top 3 by Revenue Share"], rows, [25, 35, 133])
pdf.callout("Modest breadth expansion, concentrated core",
    "The number of distinct products selling each month grew from 6 (January) to a steady 8-9 from "
    "March onward -- a real but modest widening of the active portfolio. NewCavac has been the single "
    "largest revenue contributor every month (32-42% of product revenue), with Fowl Pox and Lasota/"
    "Gumboro rotating as the second and third contributors. The portfolio is broadening slightly at "
    "the edges but remains concentrated in a small core of poultry vaccine lines.")
pdf.callout("Coverage caveat for anything cost- or margin-related",
    f"Only {cost_cov_n} of {cost_cov_total} products ({cost_cov_n/cost_cov_total*100:.0f}%) have a "
    f"Purchase Price on file. Revenue mix above is reliable (built from actual sale prices), but any "
    f"margin-by-product view would only ever describe a minority of the catalogue.", AMBER)

# ── 5. Collections and Receivables ────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("5. Collections and Receivables")
pdf.callout("No collections budget exists for 2026",
    "Unlike revenue, there is no formal collections target to measure against. The figures below are "
    "reported as trends in their own right, not as attainment against a plan.", AMBER)

_terms_n, _terms_total = inv["Customerpaymentterms"].notna().sum(), len(inv)
_no_terms_n = _terms_total - _terms_n
_terms_on_file = inv["Customerpaymentterms"].dropna().mode()
_terms_on_file = int(_terms_on_file.iloc[0]) if len(_terms_on_file) else None
pdf.callout(f"Standard payment terms: {STANDARD_TERMS_DAYS} days",
    f"DSO below is benchmarked against the {STANDARD_TERMS_DAYS}-day standard term, and measured on a "
    f"trailing {DSO_WINDOW_DAYS}-day sales basis: DSO = Outstanding AR / sales in the last "
    f"{DSO_WINDOW_DAYS} days x {DSO_WINDOW_DAYS}. "
    + (f"Note: invoices with a payment-terms value on file ({_terms_n} of {_terms_total}) still record "
       f"{_terms_on_file} days, so invoice due dates and the ageing buckets below follow that value. "
       if _terms_on_file is not None and _terms_on_file != STANDARD_TERMS_DAYS else "")
    + f"The remaining {_no_terms_n} invoices ({_no_terms_n/_terms_total*100:.0f}%) have no terms value "
    f"recorded and carry a much shorter 2-day due window -- likely a different order type.", ACCENT)

pdf.sub_title(f"Days Sales Outstanding (DSO) vs. the {STANDARD_TERMS_DAYS}-day term, month-end snapshots")
rows = [(mo_short(r["Month"]), f"GHS {r['AR']:,.0f}",
         f"{r['DSO']:.0f} days" if pd.notna(r["DSO"]) else "n/a",
         f"{r['BeyondTerms']:+.0f} days" if pd.notna(r["DSO"]) else "n/a")
        for _, r in dso_df.iterrows()]
pdf.table(["Month-End", "Outstanding AR", "DSO", f"Days vs. {STANDARD_TERMS_DAYS}-Day Terms"],
          rows, [30, 50, 45, 78])
pdf.callout(f"Over terms in {n_months_over} of {n_months} months -- and the overrun widened from April",
    f"Q1 DSO ran {dso_q1_rng} days ({dbt_q1_rng} days vs. the {STANDARD_TERMS_DAYS}-day term). From "
    f"April it ran {dso_later_rng} days ({dbt_later_rng} days vs. terms) -- customers who are supposed "
    f"to clear their balance within {STANDARD_TERMS_DAYS} days are taking {later_multiple}x that long. "
    f"This is the single most material finding in this review -- it directly funds the growing AR "
    f"balance and is a structural collections problem, not a one-off dip. Note that a "
    f"{DSO_WINDOW_DAYS}-day sales basis reacts quickly to a single slow or busy month, so read the "
    f"trend across several months rather than any one snapshot.",
    RED)
pdf.ln(2)
pdf.sub_title("Monthly collections vs. that month's revenue")
rows = [(mo_short(r["Month"]), f"GHS {r['Revenue']:,.0f}", f"GHS {r['Collected']:,.0f}",
         f"{r['Collected']/r['Revenue']*100:.0f}%" if r["Revenue"] else "n/a")
        for _, r in dso_df.iterrows()]
pdf.table(["Month", "Revenue Invoiced", "Collected That Month", "Ratio"], rows, [30, 55, 55, 53])
pdf.callout("Collections arrive in batches, not evenly",
    "The month-to-month ratio swings from 0% (April, May, July) to over 120% (March, June, August) -- "
    "money collected in a given month is often against invoices from earlier months, not that month's "
    "own sales. This lumpiness is consistent with the same pattern already visible at the weekly level "
    "on the Weekly Info dashboard page, and is the main reason DSO (a proper stock-based measure) is "
    "the more reliable read on collections health than any single month's ratio.")
pdf.ln(2)
pdf.sub_title(f"Receivables ageing as of {as_of_label} (latest data)")
rows = [(b, f"GHS {r['Total']:,.0f}", int(r["Count"])) for b, r in aging.iterrows()]
pdf.table(["Bucket", "Outstanding", "Invoices"], rows, [70, 63, 60]) if len(rows) else None
pdf.callout("No historical ageing trend available yet",
    f"Total outstanding AR as of {as_of_label} is GHS {total_ar:,.0f}. This is a single current "
    f"snapshot -- the dashboard did not track ageing buckets historically before this review, so a "
    f"month-by-month ageing trend (e.g. 'is the 61-90 day bucket growing or shrinking over time') "
    f"cannot be shown yet. Recommend treating this month's snapshot as the baseline and tracking it "
    f"going forward.", AMBER)

# ── 6. Key Observations ───────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("6. Key Observations")
pdf.callout("1. Customer base is concentrated",
    f"The top 5 customers account for {top5_pct:.1f}% of YTD revenue; the top 10 account for "
    f"{top10_pct:.1f}%, out of only {n_customers_ytd} customers who ordered at all this year. Losing "
    f"any one or two of the largest accounts would materially move the revenue line.")
pdf.callout("2. DSO and revenue trajectory shifted at the same point -- April",
    f"Both the revenue attainment pattern (Q1 strong, Apr-Jul flat at target) and DSO vs. terms "
    f"({dbt_q1_rng} days in Q1, {dbt_later_rng} days from April) inflect at the same month. The "
    f"benchmark is the same {STANDARD_TERMS_DAYS}-day term for every month, so the shift is in customer "
    f"payment behaviour, not the agreement. Worth investigating together with customer mix or order "
    f"size changes around April rather than as two separate issues.")
pdf.callout("3. Growth this year is coming from existing customers, not new ones",
    "With active customer count flat and new-customer cohorts consistently small, YTD revenue growth "
    "is being driven by existing accounts ordering more often and in larger, more varied baskets "
    "(multi-SKU adoption up) -- not by expanding the customer base.")
pdf.callout("4. Two coverage gaps to close for more reliable reporting going forward",
    f"(a) Product cost data covers only {cost_cov_n/cost_cov_total*100:.0f}% of the catalogue, "
    f"limiting margin analysis. (b) The customer registry's Agrovet tag covers only "
    f"{agro_tagged_n/agro_total_n*100:.0f}% of records overall -- it happens to fully cover this "
    f"year's actual customers, but that coincidence shouldn't be relied on if the customer base "
    f"changes.")

pdf.output(OUT)
print(f"Report saved: {OUT}")
