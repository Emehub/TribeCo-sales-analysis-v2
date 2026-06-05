"""
Generate a PDF report explaining the TribeCo Ghana Dashboard.
Run: python3 scripts/generate_report.py
Output: exports/TribeCo_Dashboard_Report.pdf
"""
from fpdf import FPDF, XPos, YPos
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports", "TribeCo_Dashboard_Report.pdf")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

BRAND  = (30, 27, 75)
ACCENT = (79, 70, 229)
BLACK  = (17, 24, 39)
WHITE  = (255, 255, 255)
LIGHT  = (241, 245, 249)

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
        self.cell(0, 8, "TribeCo Ghana Data Analysis  |  Dashboard Report  |  2026 YTD")
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
        self.set_font("Helvetica", "B", 30)
        self.set_text_color(*WHITE)
        self.set_xy(20, 85)
        self.multi_cell(170, 13, "TribeCo Ghana\nData Analysis Dashboard", align="C")
        self.set_font("Helvetica", "", 13)
        self.set_text_color(129, 140, 248)
        self.set_xy(20, 132)
        self.cell(170, 9, "Plain English Guide to Every Page and Chart", align="C")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*WHITE)
        self.set_xy(20, 152)
        self.cell(170, 7, "Ghana Operations  |  Vaccine and Agricultural Input Distribution", align="C")
        self.set_xy(20, 162)
        self.cell(170, 7, "2026 Year-to-Date  |  January to May 2026", align="C")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(129, 140, 248)
        self.set_xy(20, 262)
        self.cell(170, 7, "Confidential  |  Internal Use Only", align="C")

    def section_title(self, text):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 11)
        self.set_x(10)
        self.cell(190, 8, clean(f"  {text}"), fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def sub_title(self, text):
        self.set_text_color(*BRAND)
        self.set_font("Helvetica", "B", 10)
        self.set_x(10)
        self.cell(190, 6, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 75, self.get_y())
        self.ln(3)

    def body(self, text):
        self.set_text_color(*BLACK)
        self.set_font("Helvetica", "", 9.5)
        self.set_x(14)
        self.multi_cell(183, 5.5, clean(text))
        self.ln(2)

    def kpi_box(self, label, description):
        self.set_fill_color(*LIGHT)
        self.set_x(14)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*ACCENT)
        self.cell(183, 5.5, clean(label), fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(14)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*BLACK)
        self.multi_cell(183, 5, clean(description), fill=True)
        self.ln(1.5)

    def table_row(self, col1, col2, header=False):
        if header:
            self.set_fill_color(*BRAND)
            self.set_text_color(*WHITE)
            self.set_font("Helvetica", "B", 9)
        else:
            self.set_fill_color(*LIGHT)
            self.set_text_color(*BLACK)
            self.set_font("Helvetica", "", 9)
        self.set_x(14)
        self.cell(52, 6.5, clean(f"  {col1}"), fill=True, border="B")
        self.cell(138, 6.5, clean(f"  {col2}"), fill=False, border="B",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(10, 16, 10)

# Cover
pdf.cover()

# ── Introduction ──────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("What Is This Dashboard?")
pdf.body(
    "The TribeCo Ghana Data Analysis Dashboard is a live business intelligence tool built to track "
    "how TribeCo's Ghana operations are performing day-to-day. It connects directly to the company "
    "database and displays numbers, charts and tables that update automatically whenever new data is loaded.\n\n"
    "Everything shown in the dashboard is Ghana (GH) data only -- Kenya data is excluded. "
    "The default view covers the current year 2026, from January to May. "
    "You can change the year using the Year filter at the top of each page.\n\n"
    "The dashboard is divided into 10 pages, each answering a different business question. "
    "This report walks through every page and every chart in plain, simple language."
)

pdf.ln(3)
pdf.section_title("Quick Reference -- What Each Page Answers")
pdf.ln(2)
pdf.table_row("Page", "What It Answers", header=True)
rows = [
    ("Overview",          "How is the Ghana business doing overall right now?"),
    ("Sales Performance", "Are we selling more or less compared to previous months?"),
    ("Customers",         "Who is buying from us and are they coming back?"),
    ("Payments",          "Is money being collected? How are customers paying?"),
    ("Weekly Scorecard",  "How did this week go? What invoices need urgent follow-up?"),
    ("Reconciliation",    "Do our invoices match our payment records?"),
    ("Data Quality",      "Can we trust the data? Are there gaps or errors?"),
    ("Reliability",       "Are we fulfilling inventory orders successfully?"),
    ("Segmentation",      "What types of buyers do we have? How is revenue spread?"),
    ("Campaigns",         "How are our pre-order campaigns performing?"),
]
for page, what in rows:
    pdf.table_row(page, what)

# ── Overview ──────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 1  --  Overview")
pdf.body(
    "The Overview is the home page of the dashboard. It gives you the entire business picture "
    "in a single screen -- 12 key numbers arranged in three rows, followed by four charts."
)

pdf.sub_title("Row 1 -- Core Financial Numbers")
pdf.kpi_box("Total Sales (GHS)",
    "The total value of all goods invoiced to customers in Ghana Cedis (GHS). "
    "Think of this as the total amount TribeCo billed out. It includes both paid and unpaid invoices.")
pdf.kpi_box("Collected (GHS)",
    "How much money has actually been received back from customers as repayments. "
    "The percentage shown is the collection rate -- e.g. 65% means 65 out of every 100 cedis billed has been paid.")
pdf.kpi_box("Outstanding (GHS)",
    "The gap between what was billed and what was collected. This is money still owed by customers. "
    "A large outstanding balance is a key risk to watch.")
pdf.kpi_box("Basket Size / AOV (Average Order Value)",
    "The average value of a single order in GHS. If this number is growing, customers are buying more per visit. "
    "If it is shrinking, orders are getting smaller.")

pdf.sub_title("Row 2 -- MERL Performance Indicators")
pdf.body("MERL stands for Monitoring, Evaluation, Research and Learning -- the indicators used in donor and management reports.")
pdf.kpi_box("New Partners Signed",
    "How many new Agrovets or Providers registered on the TribeCo platform this year. "
    "Measures growth in the distribution network.")
pdf.kpi_box("Activation Rate (90 days)",
    "Of all the new partners who signed up this year, what percentage placed their very first order "
    "within 90 days of signing. A low rate means most people sign up but do not buy -- "
    "a sign that onboarding or follow-up needs improvement.")
pdf.kpi_box("Repeat Rate (30 days)",
    "Of all active customers, what percentage came back and placed a second order within 30 days of their first. "
    "A high repeat rate means customers are loyal and the product is meeting their needs.")
pdf.kpi_box("Reconciliation Rate",
    "What percentage of invoices have a matching payment record. "
    "100% means every invoice is accounted for. Anything below 100% means some invoices have no "
    "corresponding payment -- a financial tracking gap.")

pdf.sub_title("Row 3 -- Risk and Customer Concentration")
pdf.kpi_box("Top-5 Revenue Concentration",
    "What percentage of total sales comes from just the top 5 customers. "
    "If this is very high (e.g. 80%), the business is heavily dependent on a handful of buyers -- "
    "losing one of them would have a large impact.")
pdf.kpi_box("Top-10 Revenue Concentration",
    "Same idea as above but expanded to the top 10 customers. "
    "Comparing Top-5 vs Top-10 shows how spread out or concentrated the customer base is.")
pdf.kpi_box("Active Customers",
    "How many of all registered Ghana customers currently have an active status. "
    "The percentage shows the activation ratio across the whole base.")
pdf.kpi_box("High-Frequency Small Orders",
    "The percentage of orders that are very small in value -- those in the bottom 25% by order size. "
    "Many tiny orders can mean high delivery and admin cost with low revenue return.")

# ── Overview Charts ───────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 1  --  Overview Charts")

pdf.sub_title("Monthly Revenue Trend")
pdf.body(
    "A bar chart showing total sales (in GHS) for each month of the year. A dotted yellow line runs "
    "across the top showing the overall trend direction.\n\n"
    "Green or red percentage labels appear above each bar showing month-on-month growth. "
    "For example, +12% in green means that month had 12% more sales than the month before. "
    "-8% in red means sales dropped 8% compared to the previous month.\n\n"
    "What to look for: Are the bars generally getting taller over time? Is the trend line pointing upward? "
    "Consistent green labels are a healthy sign."
)

pdf.sub_title("Sales by City")
pdf.body(
    "A donut chart where each coloured slice represents a Ghana city. "
    "The bigger the slice, the more that city contributes to total sales.\n\n"
    "What to look for: Is revenue too concentrated in one city? Are smaller cities growing their slice? "
    "This chart helps decide where to focus sales effort or distribution resources."
)

pdf.sub_title("Repayment Status")
pdf.body(
    "A bar chart showing how invoices are split across four payment statuses:\n"
    "  Open     -- Invoice raised, payment not yet due\n"
    "  Repaid   -- Invoice fully paid by the customer\n"
    "  Overdue  -- Past the due date with no payment received\n"
    "  Due Soon -- Payment deadline is approaching\n\n"
    "What to look for: A tall Overdue bar is a warning sign. "
    "It means customers are not paying on time and the collections team needs to act."
)

pdf.sub_title("Payment Mode")
pdf.body(
    "A donut chart showing how customers pay their invoices -- Mobile Money, Bank Transfer, Cash, etc. "
    "Each slice shows what percentage of payments came through that method.\n\n"
    "What to look for: Which payment channel is most popular? If Cash is dominant, "
    "there may be reconciliation challenges. Mobile Money dominance suggests digital payments are working well."
)

# ── Sales Performance ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 2  --  Sales Performance")
pdf.body(
    "A deeper look into sales trends over time. You can filter by specific months using the "
    "dropdown at the top -- useful for comparing two specific periods or zooming into a quarter."
)
pdf.kpi_box("Headline Numbers",
    "Three summary boxes: Total Sales for the period, Total Orders count, "
    "and Average Sale Value (how much each order is worth on average).")
pdf.sub_title("Monthly Sales vs Previous Month")
pdf.body(
    "A bar chart where each bar is one month's total sales. "
    "Green or red percentage labels above each bar show whether that month grew or shrank versus the month before.\n\n"
    "This is the clearest chart for answering: 'Are we growing month over month?'"
)
pdf.sub_title("Weekly Sales Trend")
pdf.body(
    "A bar and line chart showing sales for each week over the last 16 weeks. "
    "The bars give the weekly sales value; the line shows the direction of change.\n\n"
    "What to look for: Regular dips at certain weeks? A spike that can be explained by a campaign? "
    "Consistent upward movement of the line is positive."
)
pdf.sub_title("Monthly Sales Summary Table")
pdf.body(
    "A plain table listing every month with the total sales figure in GHS "
    "and the month-on-month percentage change. Good for copying into management reports."
)

# ── Customers ─────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 3  --  Customers")
pdf.body("Everything about who is buying from TribeCo Ghana -- how many, how active, how loyal, and who the biggest buyers are.")

pdf.sub_title("Headline Numbers (8 KPIs in two rows)")
pdf.body(
    "Row 1: New Partners Signed, Activation Rate (90d), Repeat Rate (30d), Avg Orders per Customer.\n\n"
    "Row 2: Total Registered customers, Active count, Inactive count, "
    "Ordering Customers (those who actually placed at least one order in the year)."
)
pdf.sub_title("Top 10 Customers by Order Value")
pdf.body(
    "A horizontal bar chart ranking the 10 biggest customers by total spend. "
    "The longest bar is the highest-spending customer. Each bar shows the GHS amount spent.\n\n"
    "What to look for: Is one customer's bar much longer than all others? That suggests high dependency. "
    "Healthy businesses have several customers with similar bar lengths."
)
pdf.sub_title("Active vs Inactive Donut")
pdf.body(
    "A simple donut chart split between Active (dark colour) and Inactive (light colour) customers. "
    "Ideally, most of the donut should be the active colour."
)
pdf.sub_title("New Partner Registrations by Month")
pdf.body(
    "A stacked bar chart showing how many new partners joined each month, broken down by type: "
    "Providers (blue), Agrovets (teal), and Hatcheries (amber). Stacked bars let you see the total "
    "AND the breakdown at the same time.\n\n"
    "What to look for: Is new partner sign-up growing each month? Are certain partner types dropping off?"
)
pdf.sub_title("Customer Leaderboard Table")
pdf.body(
    "A ranked table of the top 10 customers with their total spending in GHS. "
    "Useful for the sales team to know who their most important relationships are."
)

# ── Payments ──────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 4  --  Payments")
pdf.body("Payments tracks money coming in -- repayments from customers, collection rates, and payment methods.")

pdf.kpi_box("Headline Numbers",
    "Total Collected (GHS received), Outstanding (GHS still owed), "
    "Number of Successful Payment Transactions, and Average Payment size per transaction.")
pdf.sub_title("Payment Mode Distribution")
pdf.body(
    "A donut chart showing how customers pay -- Mobile Money, Bank Transfer, Cash, etc. "
    "Each slice is one payment method.\n\n"
    "Why it matters: If most payments come via Mobile Money, the finance team should ensure MoMo "
    "reconciliation is tight. Cash-heavy businesses need more field reconciliation effort."
)
pdf.sub_title("Monthly Collections vs Invoiced")
pdf.body(
    "Two overlapping bars for each month. The light bar shows what was invoiced (billed). "
    "The dark bar shows what was actually collected.\n\n"
    "When the dark bar is almost as tall as the light bar -- collections are keeping up with invoicing. "
    "When the light bar is much taller -- a backlog is building up and outstanding debt is growing."
)
pdf.sub_title("Payment Method Summary Table")
pdf.body(
    "A table showing for each payment method: how many transactions, total collected, and average per transaction. "
    "Good for understanding which channels move the most money."
)
pdf.sub_title("Recent Collections Table")
pdf.body(
    "The 30 most recent repayments, showing date, amount, payment method, and repayment route. "
    "A live audit trail for the finance team."
)

# ── Weekly Scorecard ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 5  --  Weekly Scorecard")
pdf.body(
    "The Weekly Scorecard is designed for Monday morning check-ins and weekly management reviews. "
    "It focuses on the most recent week and flags any invoices that are overdue."
)
pdf.kpi_box("Headline Numbers (most recent week)",
    "Orders This Week (invoice count), Sales This Week (GHS), "
    "Collected This Week (GHS received in repayments), and Overdue Invoices (red alert -- invoices past due date).")
pdf.sub_title("Weekly Orders and Sales Trend")
pdf.body(
    "A combination chart for the last 16 weeks. Light blue bars show the total sales value each week. "
    "A dark blue line tracks the number of orders.\n\n"
    "By showing both on the same chart you can spot patterns -- for example, "
    "if orders stay high but sales drop, it means order sizes are getting smaller. "
    "If orders drop but sales stay the same, customers are buying bigger but less often."
)
pdf.sub_title("Week-over-Week Sales Change")
pdf.body(
    "A simple bar chart for the last 8 weeks. Each bar is either:\n"
    "  Green -- That week had MORE sales than the week before\n"
    "  Red   -- That week had LESS sales than the week before\n\n"
    "The percentage on each bar tells you by how much. "
    "This is the quickest way to answer: 'Did this week do better than last week?'"
)
pdf.sub_title("Weekly Breakdown Table")
pdf.body(
    "A full table of every week in 2026, most recent week at the top. Columns:\n"
    "  Week            -- The week period (e.g. 2026-W18)\n"
    "  Orders          -- Number of invoices raised that week\n"
    "  Invoice Total   -- GHS value of invoices raised\n"
    "  Sales Collected -- GHS received in repayments that week\n"
    "  Collection Rate -- Percentage of that week's invoices that were paid\n\n"
    "This table is the best summary for a weekly finance report."
)
pdf.sub_title("Overdue Invoice Exceptions Table")
pdf.body(
    "A list of every invoice that has passed its due date without full payment. "
    "Columns show the customer name, amount owed, invoice date, and due date.\n\n"
    "This is an action list -- the collections team should use this table to prioritise follow-up calls. "
    "If this table is empty, all invoices are either paid or not yet due -- the best outcome."
)

# ── Reconciliation ────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 6  --  Reconciliation")
pdf.body(
    "Reconciliation checks whether every invoice raised has a matching payment record. "
    "It is a financial control -- if an invoice exists but no payment is recorded against it, "
    "either the customer has not paid or the payment was not captured correctly."
)
pdf.kpi_box("Headline Numbers",
    "Total Invoices in the period, Reconciled count (match rate %), "
    "Unreconciled count (no payment found), and Unreconciled Value (total GHS exposure).")
pdf.sub_title("Reconciliation Status Chart")
pdf.body(
    "A donut chart split between Matched and Unmatched invoices. "
    "The goal is for the Matched slice to be as large as possible.\n\n"
    "A large Unmatched slice is a financial risk -- money is unaccounted for."
)
pdf.sub_title("Monthly Reconciliation Trend")
pdf.body(
    "A line or bar chart showing the reconciliation rate each month. "
    "If the rate is falling, the gap between invoices and payments is growing -- "
    "an early warning that collections or data capture needs attention."
)
pdf.sub_title("Unreconciled Invoices Table")
pdf.body(
    "A detailed list of every invoice with no matching payment. "
    "The finance team uses this to either chase the customer for payment "
    "or investigate whether a payment was made but not recorded in the system."
)

# ── Data Quality ──────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 7  --  Data Quality")
pdf.body(
    "This page is for the data and analytics team. It checks how complete and clean the underlying data is.\n\n"
    "It flags missing values, empty columns, and incomplete records across the key data tables "
    "(invoices, repayments, customers, inventory). Before trusting any number in the dashboard, "
    "the data quality page tells you whether the underlying data is reliable.\n\n"
    "Common issues flagged here:\n"
    "  - Customer records with no city or region recorded\n"
    "  - Invoices with missing amounts\n"
    "  - Payments with no payment method captured\n"
    "  - Records with null (empty) dates\n\n"
    "If the data quality score is high, the dashboard numbers can be trusted. "
    "If it is low, some numbers may be understated or misleading and should be interpreted with caution."
)

# ── Reliability ───────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 8  --  Reliability")
pdf.body(
    "The Reliability page tracks inventory fulfilment -- whether orders placed for stock "
    "are actually being delivered successfully."
)
pdf.kpi_box("Headline Numbers",
    "Total inventory requests, how many were fulfilled, the fulfilment rate percentage, "
    "and how many are still pending or have failed.")
pdf.sub_title("Fulfillment Request Status")
pdf.body(
    "A donut chart showing the outcome of all inventory requests, split into:\n"
    "  Fulfilled   -- Delivered successfully (green)\n"
    "  Pending     -- Waiting to be processed (amber)\n"
    "  Processing  -- Currently being handled (blue)\n"
    "  Cancelled   -- Order was cancelled before delivery (red)\n"
    "  Failed      -- Could not be fulfilled (dark red)\n\n"
    "What to look for: The green Fulfilled slice should be the largest. "
    "A growing Cancelled or Failed slice signals a supply chain or logistics problem "
    "that could be hurting customer satisfaction."
)

# ── Segmentation ──────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 9  --  Segmentation")
pdf.body(
    "Segmentation groups customers by their buying behaviour so TribeCo can understand "
    "the different types of buyers in its network and tailor its approach accordingly."
)
pdf.sub_title("Revenue Concentration Curve")
pdf.body(
    "This line chart ranks all customers from the biggest buyer (rank 1) to the smallest. "
    "The vertical axis shows the cumulative percentage of total revenue.\n\n"
    "How to read it: If the line shoots steeply upward on the left side, a small number of customers "
    "account for most of the revenue. Two reference lines mark the Top-5 and Top-10 thresholds.\n\n"
    "A perfectly equal customer base would be a straight diagonal line. "
    "The more curved it is, the more concentrated the revenue risk."
)
pdf.sub_title("Order Value Distribution")
pdf.body(
    "A histogram -- a chart of vertical bars where each bar represents a price range. "
    "The height of each bar tells you how many orders fell in that price bracket.\n\n"
    "A vertical red line marks the low-ticket threshold (bottom 25% of order values). "
    "Orders to the left of the line are small orders. A large cluster on the left means the business "
    "is processing many low-value transactions.\n\n"
    "What to look for: Is there a big hump on the left (many tiny orders)? "
    "Or is the distribution spread out, suggesting a healthy mix of order sizes?"
)
pdf.sub_title("Portfolio Segmentation Summary Table")
pdf.body(
    "A table breaking down business metrics by customer type (Agrovet, Provider, Hatchery):\n"
    "  Segment       -- The customer type\n"
    "  Orders        -- Total orders placed by that segment\n"
    "  Total Sales   -- GHS revenue from that segment\n"
    "  Customers     -- Number of customers in the segment\n"
    "  Rev/Purchase  -- Average revenue per order for that segment (AOV)\n\n"
    "This answers: Which segment is most valuable? Which has the biggest average order size?"
)

# ── Campaigns ─────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Page 10  --  Campaigns")
pdf.body(
    "The Campaigns page tracks pre-order campaigns run through the TribeCo platform. "
    "Pre-order campaigns allow customers to commit to buying a product before it is in stock, "
    "helping TribeCo plan procurement and reduce waste."
)
pdf.kpi_box("Headline Numbers",
    "Total Campaigns created, Active (currently open for pre-orders), "
    "Completed (closed and fulfilled), and the overall Campaign Span date range.")
pdf.sub_title("Campaign Timeline Chart")
pdf.body(
    "A Gantt-style horizontal chart where each campaign appears as a bar. "
    "The left edge is the start date; the right edge is the end date. "
    "The length shows how long the campaign ran. Active and completed campaigns are shown in different colours.\n\n"
    "This makes it easy to see which campaigns are running now and which have finished."
)
pdf.sub_title("Campaign Details Table")
pdf.body(
    "A full table listing every campaign with its name, status (Active / Completed / Cancelled), "
    "start date, end date, and duration in days."
)

# ── Glossary ──────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("Glossary of Terms")
pdf.body("Common terms used throughout the dashboard explained in plain language.")
pdf.ln(2)

terms = [
    ("GHS", "Ghana Cedis -- the currency used for all financial figures in this dashboard."),
    ("Invoice", "A bill raised when goods are sold to a customer. States what was sold, the quantity, and the amount owed."),
    ("Repayment", "A payment made by a customer against an invoice -- money coming back to TribeCo."),
    ("AOV", "Average Order Value -- total sales divided by number of orders. The average size of one purchase."),
    ("MERL", "Monitoring, Evaluation, Research and Learning -- the framework for tracking programme impact for donors and management."),
    ("Activation Rate", "Percentage of newly registered partners who placed their first order within 90 days of signing up."),
    ("Repeat Rate", "Percentage of ordering customers who placed a second order within 30 days of their first."),
    ("Reconciliation", "The process of matching every invoice to a payment record to confirm all money is accounted for."),
    ("Reconciliation Rate", "Percentage of invoices that have a matched payment record."),
    ("Revenue Concentration", "How much of total revenue comes from a small number of top customers. High concentration = high dependency risk."),
    ("Lorenz Curve", "A line chart visualising how evenly (or unevenly) revenue is spread across customers."),
    ("High-Freq Small Orders", "Orders in the bottom 25% by value -- many tiny transactions relative to total revenue."),
    ("Agrovet", "An agricultural retail shop selling veterinary and farm input products."),
    ("Provider", "A field agent or distributor in the TribeCo network."),
    ("Fulfillment", "The process of delivering an inventory request, from approval through to physical delivery."),
    ("Overdue", "An invoice whose repayment due date has passed without full payment being received."),
    ("YTD", "Year-to-Date -- data from 1st January of the current year up to today."),
    ("KPI", "Key Performance Indicator -- a specific number used to measure how well a business is doing."),
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

# Save
pdf.output(OUT)
print(f"Report saved: {OUT}")
