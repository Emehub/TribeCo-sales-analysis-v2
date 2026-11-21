# TribeCo Ghana Data Analysis Dashboard

A Streamlit business intelligence dashboard for TribeCo Ghana's vaccine and agricultural input distribution operations. All data is filtered to **Ghana (GH)** only and defaults to **2026 year-to-date**.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Project Structure](#project-structure)
3. [Setup and Installation](#setup-and-installation)
4. [Configuration](#configuration)
5. [Extracting Data](#extracting-data)
6. [Running the Dashboard](#running-the-dashboard)
7. [Dashboard Pages](#dashboard-pages)
8. [Code Walkthrough](#code-walkthrough)
9. [Generating the PDF Report](#generating-the-pdf-report)
10. [Deployment (Streamlit Cloud)](#deployment-streamlit-cloud)
11. [Data Sources](#data-sources)
12. [Key Dependencies](#key-dependencies)

---

## Project Overview

This dashboard connects to the `tribecodb` PostgreSQL database via the Metabase API, exports all tables as CSV files, and serves them through an interactive Streamlit web application. It is designed for the Ghana data analyst to monitor MERL KPIs, sales performance, customer behaviour, payments, reconciliation, and inventory reliability — all scoped to Ghana operations.

---

## Project Structure

```
company-dashboard/
│
├── dashboard/
│   └── app.py                  # Main Streamlit application (all pages and charts)
│
├── scripts/
│   ├── extract_metabase.py     # Pulls all tables from Metabase API into /data
│   ├── extract_postgres.py     # Pulls tables directly from PostgreSQL into /data
│   └── generate_report.py      # Generates the PDF dashboard explanation report
│
├── data/                       # CSV exports from the database (141 files)
│   ├── invoice.csv
│   ├── repayment.csv
│   ├── retail_centre.csv
│   ├── payment.csv
│   ├── product.csv
│   ├── invoice_line.csv
│   ├── inventory_request.csv
│   ├── inventory_balances_view.csv
│   ├── preorder_campaign.csv
│   ├── inventory_request_fulfillment.csv
│   └── ... (131 more tables)
│
├── exports/
│   └── TribeCo_Dashboard_Report.pdf   # Auto-generated PDF report
│
├── .streamlit/
│   └── config.toml             # Streamlit theme configuration (light mode, brand colours)
│
├── config.py                   # Credentials file — NEVER commit this (gitignored)
├── requirements.txt            # Python package dependencies
├── .gitignore                  # Excludes credentials and large files from git
└── README.md                   # This file
```

---

## Setup and Installation

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Access to the Metabase instance at `http://35.241.44.217` or direct PostgreSQL access

### Step 1 — Clone the repository

```bash
git clone https://github.com/Emehub/TribeCo-sales-analysis.git
cd TribeCo-sales-analysis
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Set up credentials

Create a `config.py` file in the root directory (this file is gitignored — never push it):

```python
# Option A: Direct PostgreSQL connection
DB_CONFIG = {
    "host":     "YOUR_HOST",
    "port":     5432,
    "database": "YOUR_DB_NAME",
    "user":     "YOUR_USERNAME",
    "password": "YOUR_PASSWORD",
}

# Option B: Metabase API (recommended)
METABASE_CONFIG = {
    "url":      "http://your-metabase-url",
    "username": "your@email.com",
    "password": "your_password",
    "dbname":   "tribecodb",
}
```

---

## Configuration

### `.streamlit/config.toml`

Controls the visual theme of the dashboard:

```toml
[theme]
base = "light"
primaryColor = "#4f46e5"       # Indigo — used for buttons and highlights
backgroundColor = "#f1f5f9"    # Soft grey page background
secondaryBackgroundColor = "#ffffff"  # White cards
textColor = "#111827"          # Near-black text
font = "sans serif"
```

This file forces **light mode** regardless of the user's OS setting. Without it, the dashboard may appear dark on Windows/Mac systems set to dark mode.

---

## Extracting Data

The data must be extracted before running the dashboard. Choose one of the two scripts below.

### Option A — Extract via Metabase API (recommended)

```bash
python scripts/extract_metabase.py
```

What this script does:
1. Logs into Metabase using credentials from `config.py`
2. Finds the `tribecodb` database
3. Lists all tables in the database
4. Exports each table as a CSV file to `data/`
5. Also exports any saved Metabase questions linked to `tribecodb`

Output: All tables saved as `data/<table_name>.csv`

### Option B — Extract directly from PostgreSQL

```bash
python scripts/extract_postgres.py
```

What this script does:
1. Connects to PostgreSQL using `DB_CONFIG` from `config.py`
2. Lists all tables in the `public` schema
3. Exports every table as a CSV to `data/`

Use this option if you have direct database access and Metabase is unavailable.

---

## Running the Dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard will open in your browser at `http://localhost:8501`

To stop the dashboard press `Ctrl + C` in the terminal.

---

## Dashboard Pages

The sidebar groups pages by purpose: **Dashboards** (Overview, Advanced Analytics, Sales
Performance), **Leadership**, **Commercial**, **Operations** and **Archive**.

### Advanced Analytics
Statistical analysis of FBC invoices from the first month of sustained trading (pilot months
are excluded from trends). Code: `dashboard/advanced_analytics.py` (calculations, plain
pandas/numpy) and `dashboard/advanced_page.py` (layout).

- **Headline KPIs:** 4-week revenue forecast with an 80% range, projected year-end revenue,
  monthly revenue at risk from customers past their reorder rhythm, top-20% customer share
- **Key findings:** sentences generated from the results below
- **Forecast:** Holt damped-trend exponential smoothing on weekly revenue, with 80%/95%
  prediction intervals, a back-test against a simple average (WAPE), and unusual weeks flagged
  (more than 2.5 robust standard deviations from the model). The in-progress week is shown but
  not used to fit the model.
- **Customer segments:** RFM scoring (recency, frequency, spend, each 1–5) into seven
  segments, each with a recommended action
- **Churn risk:** each customer compared against their own median gap between orders; a
  ranked call list of who is overdue and how much monthly revenue is at stake
- **Cohorts:** retention heatmap by first-order month
- **Concentration:** Lorenz curves, Gini and ABC classes for customers and products
- **Growth drivers:** revenue bridges between two periods (30/60/90 days) by customer
  (new, reactivated, grew, shrank, lost) and by product (volume, price, new, dropped)
- **Cross-sell:** product pairs bought together, with support, confidence and lift
- Everything downloads as one Excel file.

### 1. Overview
The home page. Shows 12 KPI cards in three rows followed by four charts.

- **Row 1 — Financials:** Total Sales, Collected, Outstanding, Basket Size (AOV)
- **Row 2 — MERL KPIs:** New Partners Signed, Activation Rate (90d), Repeat Rate (30d), Reconciliation Rate
- **Row 3 — Risk:** Top-5 Revenue Concentration, Top-10 Revenue Concentration, Active Customers, High-Freq Small Orders
- **Charts:** Monthly Revenue Trend, Sales by City, Repayment Status, Payment Mode

### 2. Sales Performance
Month-by-month and week-by-week sales analysis with month-on-month growth labels.
- Filter by specific months using the multiselect dropdown
- Charts: Monthly Sales vs Previous Month, Weekly Sales Trend
- Table: Monthly Sales Summary with MoM change

### 3. Customers
Customer acquisition, engagement and loyalty metrics.
- MERL metrics: Activation Rate, Repeat Rate, New Partner count
- Charts: Top 10 Customers bar chart, Active vs Inactive donut, New Partner Registrations by Month (stacked bar)
- Table: Customer Leaderboard

### 4. Payments
Money collection tracking.
- Charts: Payment Mode Distribution, Monthly Collections vs Invoiced (overlapping bars)
- Tables: Payment Method Summary, Recent Collections (last 30)

### 5. Weekly Scorecard
Designed for Monday morning reviews.
- KPIs: This week's orders, sales, collections, and overdue invoice count
- Charts: Weekly Orders & Sales Trend (16 weeks), Week-over-Week Sales Change (green/red bars)
- Tables: Full weekly breakdown (all weeks in year), Overdue Invoice Exceptions action list

### 6. Reconciliation
Financial control — checks every invoice has a matching payment.
- KPIs: Total Invoices, Reconciled, Unreconciled, Unreconciled Value
- Charts: Reconciliation Status donut, Monthly Reconciliation Trend
- Table: Unreconciled Invoices list

### 7. Data Quality
Checks for missing values, null dates, and incomplete records across key tables.

### 8. Reliability
Inventory fulfilment tracking.
- Chart: Fulfillment Request Status donut (Fulfilled / Pending / Processing / Cancelled / Failed)

### 9. Segmentation
Customer behaviour and revenue distribution analysis.
- Charts: Revenue Concentration Curve (Lorenz curve), Order Value Distribution (histogram)
- Table: Portfolio Segmentation Summary by segment type (Agrovet, Provider, Hatchery)

### 10. Campaigns
Pre-order campaign tracking.
- KPIs: Total, Active, Completed campaigns
- Charts: Campaign Timeline (Gantt chart), Campaign Details table

---

## Code Walkthrough

### `dashboard/app.py`

The entire dashboard lives in this single file (~1,400 lines). Here is how it is organised:

#### 1. Imports and page config (lines 1–17)
```python
import os, streamlit as st, pandas as pd, plotly.express as px, plotly.graph_objects as go
st.set_page_config(layout="wide", menu_items={})
```
`menu_items={}` removes Streamlit's built-in hamburger menu (which includes the "Clear Cache" button that could confuse users).

#### 2. Global CSS (lines 19–161)
Injected via `st.markdown(..., unsafe_allow_html=True)`. Covers:
- Sidebar dark indigo/green background
- Navigation button styles (transparent, with active state highlight)
- KPI card and chart card styles
- Hiding Streamlit's default header bar while keeping the sidebar toggle functional

Key CSS trick — the header is collapsed to zero height rather than hidden, so the sidebar collapse/expand button remains clickable:
```css
[data-testid="stHeader"] {
    height: 0 !important;
    overflow: visible !important;  /* keeps the sidebar toggle accessible */
}
```

#### 3. Data loader — `load_all()` (lines 165–210)
Decorated with `@st.cache_data` so data is only loaded from disk once per session (speeds up page navigation).

```python
@st.cache_data
def load_all():
    pay  = pd.read_csv(f"{DATA}/payment.csv", parse_dates=["Created At"])
    inv  = pd.read_csv(f"{DATA}/invoice.csv", parse_dates=["Created At", "Due Date"])
    ...
    # Filter everything to Ghana (GH) at load time
    inv = inv[inv["Country Code"] == "GH"].copy()
    rep = rep[rep["Country Code"] == "GH"].copy()
    rc  = rc[rc["Country Code"]   == "GH"].copy()
    ...
```

All Ghana filtering happens here — downstream code never needs to re-filter.

`DATA` is set dynamically so the path works both locally and on Streamlit Cloud:
```python
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
```

#### 4. Global metrics (lines 214–243)
Computed once from the full (all-years) loaded data:
```python
total_revenue   = success_pay["Amount"].sum()
total_invoiced  = inv["Total Order Value"].sum()
collection_pct  = (total_repaid / total_invoiced * 100)
active_customers = rc[rc["Status"] == "Active"].shape[0]
```

#### 5. Helper functions (lines 246–280)

```python
def kpi_card(label, value, subtitle, color, badge="", badge_color=""):
    # Returns an HTML string for a styled KPI card

def chart_wrap(title, subtitle=""):
    # Returns opening HTML for a white chart card container

def year_filter(key="year"):
    # Renders a Year selectbox, defaults to 2026
    # Stores selection in st.session_state["current_year"]

def apply_year(df, year, date_col="Created At"):
    # Filters a dataframe to a specific year (or returns all if year == "All")
```

#### 6. Sidebar navigation (lines 283–332)
Uses `st.session_state["active_page"]` to track the current page. Navigation is built with `st.button()` — the active page button gets `type="primary"` for the highlight style.

```python
NAV_GROUPS = {
    "Core Analytics": ["Overview", "Sales Performance"],
    "Business":       ["Customers", "Payments"],
    "Phase 1":        ["Weekly Scorecard", "Reconciliation", "Data Quality"],
    "Phase 2":        ["Reliability", "Segmentation", "Campaigns"],
}

all_pages = [item for items in NAV_GROUPS.values() for item in items]
for item in all_pages:
    if st.button(item, key=f"nav_{item}", type=kind):
        st.session_state["active_page"] = item
        st.rerun()
```

#### 7. Page routing (lines 360 onwards)
A large `if / elif` block routes to the correct page based on `st.session_state["active_page"]`:

```python
if page == "Overview":
    ...
elif page == "Sales Performance":
    ...
elif page == "Customers":
    ...
# etc.
```

#### 8. Charts
All charts use Plotly with `config={"displayModeBar": False}` to hide the Plotly toolbar. Two types are used:
- `plotly.express` (`px`) — quick single-series charts (bar, pie, histogram, timeline)
- `plotly.graph_objects` (`go`) — multi-series charts (combined bar + line, custom annotations)

---

### `scripts/extract_metabase.py`

| Function | What it does |
|---|---|
| `login()` | Posts credentials to `/api/session`, returns the session token |
| `get_headers(token)` | Returns the `X-Metabase-Session` header dict |
| `find_database(token)` | Calls `/api/database` and finds the ID of `tribecodb` |
| `list_tables(token, db_id)` | Calls `/api/database/{id}/metadata` to list all tables |
| `export_table(token, db_id, table)` | Posts to `/api/dataset` to run a full table query, saves result as CSV |
| `export_saved_questions(token, db_id)` | Exports any saved Metabase questions for the database via `/api/card` |

---

### `scripts/extract_postgres.py`

| Function | What it does |
|---|---|
| `connect()` | Creates a SQLAlchemy engine using `DB_CONFIG` credentials |
| `list_tables(engine)` | Queries `information_schema.tables` to list all public tables |
| `export_table(engine, table_name)` | Runs `SELECT * FROM table_name` and saves as CSV |
| `export_custom_query(engine, query, filename)` | Runs any custom SQL and saves as CSV |

---

### `scripts/generate_report.py`

Uses the `fpdf2` library to produce a multi-page PDF report explaining the dashboard in plain English. Key design decisions:
- All unicode characters (em dashes, smart quotes) are converted to ASCII equivalents before writing to PDF because the built-in Helvetica font only supports Latin-1
- A `clean()` function handles all character substitutions
- Custom `PDF` class extends `FPDF` and adds branded `header()`, `footer()`, `section_title()`, `sub_title()`, `body()`, and `kpi_box()` methods for consistent formatting

---

## Generating the PDF Report

```bash
python3 scripts/generate_report.py
```

Output: `exports/TribeCo_Dashboard_Report.pdf`

The report includes 13 pages covering every dashboard page, every chart, every KPI explained in plain language, plus a glossary of terms.

---

## Deployment (Streamlit Cloud)

The app is deployed at: [https://github.com/Emehub/TribeCo-sales-analysis](https://github.com/Emehub/TribeCo-sales-analysis)

### How to redeploy after changes

```bash
git add dashboard/app.py
git commit -m "describe your change"
git push
```

Streamlit Cloud detects the push and automatically redeploys within 1–2 minutes.

### How to deploy a fresh instance

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click **New app**
4. Select repo: `Emehub/TribeCo-sales-analysis`
5. Branch: `master`
6. Main file: `dashboard/app.py`
7. Click **Deploy**

### Important notes for deployment
- `data/` CSV files are included in the repo so Streamlit Cloud can access them
- `config.py` is gitignored — credentials are never pushed
- `requirements.txt` tells Streamlit Cloud which packages to install

---

## Data Sources

| Table | Description | Rows (approx) | Ghana filter |
|---|---|---|---|
| `invoice.csv` | Sales invoices | 2,000 | `Country Code == GH` |
| `repayment.csv` | Customer repayments | 244 | `Country Code == GH` |
| `retail_centre.csv` | Customer/partner registry | 485 | `Country Code == GH` |
| `payment.csv` | Payment transactions | varies | No Country Code — unfiltered |
| `invoice_line.csv` | Line items per invoice | varies | Filtered via GH invoice IDs |
| `inventory_request.csv` | Stock requests | 2,000 | All GH |
| `inventory_balances_view.csv` | Current stock levels | 1,813 | Filtered via GH retail centre IDs |
| `preorder_campaign.csv` | Pre-order campaigns | 3 | All |
| `inventory_request_fulfillment.csv` | Fulfilment records | 2,000 | All |
| `product.csv` | Product catalogue | varies | All |

> **Note:** `invoice_line.csv` only contains data through 2024. No 2025 or 2026 line-level data is currently available, which is why the Products page was removed from the dashboard.

---

## Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `streamlit` | >=1.57.0 | Web dashboard framework |
| `pandas` | >=2.0.0 | Data loading, filtering and transformation |
| `plotly` | >=5.18.0 | Interactive charts (bar, line, pie, histogram, Gantt) |
| `fpdf2` | >=2.8.0 | PDF report generation |
| `requests` | built-in | Metabase API HTTP calls |
| `sqlalchemy` | optional | PostgreSQL direct connection |
| `psycopg2` | optional | PostgreSQL driver for SQLAlchemy |

---

## Notes for Developers

- **Adding a new page:** Add the page name to `NAV_GROUPS` in `app.py`, add an `elif page == "Your Page":` block at the bottom of the routing section, and run the app to verify
- **Refreshing data:** Re-run `extract_metabase.py` to pull the latest data from the database, then push the updated CSVs to GitHub
- **Changing the year default:** In the `year_filter()` function, change `"2026"` to the desired default year
- **Adding a KPI:** Use the `kpi_card(label, value, subtitle, color)` helper function which returns an HTML string — append it to one of the `row` variables and render inside the `.kpi-grid` div
- **Credentials:** Never add `config.py` to git. If deploying to a platform that supports secrets (e.g. Streamlit Cloud), use `st.secrets` and store credentials in the platform's secrets manager

---

*Built for TribeCo Ghana Operations | Data analyst: Ghana team | Dashboard version: 2026 v1*
