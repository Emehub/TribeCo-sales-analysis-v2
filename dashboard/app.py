"""
CowTribe Sales Dashboard
Run: python -m streamlit run d:/company-dashboard/dashboard/app.py
"""
import os
import time
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="CowTribe Sales Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

DATA      = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CHART_CFG = {"displayModeBar": False}

# ── Metabase connection ──────────────────────────────────────────────────────────
_MB_CFG     = st.secrets["metabase"]
_MB_BASE    = _MB_CFG["url"]
_MB_DB_NAME = _MB_CFG.get("dbname", "tribecodb")

def _mb_login():
    r = requests.post(
        f"{_MB_BASE}/api/session",
        json={"username": _MB_CFG["username"], "password": _MB_CFG["password"]},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["id"]

_MB_PAGE = 2000  # Metabase API hard limit per request

def _mb_fetch(token, db_id, table_id, parse_dates=None):
    """Fetch all rows from a Metabase table using paginated requests."""
    hdrs     = {"X-Metabase-Session": token}
    all_rows = []
    cols     = None
    offset   = 0

    while True:
        r = requests.post(
            f"{_MB_BASE}/api/dataset",
            headers=hdrs,
            json={"database": db_id, "type": "query",
                  "query": {"source-table": table_id,
                             "limit": _MB_PAGE, "offset": offset}},
            timeout=120,
        )
        if r.status_code != 202:
            raise RuntimeError(f"Metabase {r.status_code}")
        data      = r.json().get("data", {})
        page_rows = data.get("rows", [])
        if cols is None:
            cols = [c.get("display_name", c.get("name")) for c in data.get("cols", [])]
        all_rows.extend(page_rows)
        if len(page_rows) < _MB_PAGE:
            break
        offset += _MB_PAGE

    df = pd.DataFrame(all_rows, columns=cols or [])
    if parse_dates:
        for col in parse_dates:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df

# ── Global CSS ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Sidebar background ── */
[data-testid="stSidebar"] {
    background-color: #14532d !important;
    padding-top: 0 !important;
}

/* ── Force ALL sidebar text white ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] *,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] label {
    color: #ffffff !important;
}

/* ── Nav buttons ── */
[data-testid="stSidebar"] .stButton { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] .stButton button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
    color: #ffffff !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    text-align: center !important;
    justify-content: center !important;
    padding: 11px 16px !important;
    border-radius: 8px !important;
    width: 100% !important;
    cursor: pointer !important;
    letter-spacing: 0.2px !important;
    transition: background 0.15s ease !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: rgba(255,255,255,0.10) !important;
    color: #ffffff !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton button:focus {
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background: rgba(74,222,128,0.25) !important;
    border-left: 3px solid #4ade80 !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    border-radius: 0 8px 8px 0 !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {
    background: rgba(74,222,128,0.35) !important;
}

/* ── Main layout ── */
.main .block-container { padding: 1.5rem 2rem !important; max-width: 100% !important; }
.main { background-color: #f1f5f9 !important; }

/* ── Top bar ── */
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 6px;
}
.topbar-title { font-size: 22px; font-weight: 800; color: #1e1b4b; }
.topbar-right { display: flex; align-items: center; gap: 10px; }
.badge-date {
    background: white; color: #374151; font-size: 12px; font-weight: 600;
    padding: 5px 14px; border-radius: 20px; border: 1px solid #e5e7eb;
}

/* ── KPI cards ── */
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 16px 0; }
.kpi-card {
    background: white; border-radius: 14px; padding: 20px 22px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    border-top: 4px solid #4f46e5;
    position: relative;
}
.kpi-label {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.6px; color: #6b7280; margin-bottom: 2px;
}
.kpi-badge {
    font-size: 11px; font-weight: 700; margin-left: 6px;
    padding: 1px 6px; border-radius: 10px;
}
.kpi-value {
    font-size: 30px; font-weight: 800; color: #111827;
    margin: 8px 0 6px; line-height: 1;
}
.kpi-sub { font-size: 12px; color: #9ca3af; }

/* ── Chart card ── */
.chart-card {
    background: white; border-radius: 14px; padding: 20px 22px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07); margin-bottom: 16px;
}
.chart-title { font-size: 15px; font-weight: 700; color: #1e1b4b; margin-bottom: 2px; }
.chart-sub   { font-size: 12px; color: #9ca3af; margin-bottom: 12px; }

/* ── Divider ── */
hr { border: none; border-top: 1px solid #e5e7eb; margin: 12px 0; }

/* ── Hide Streamlit chrome ── */
#MainMenu { display: none !important; }
footer { display: none !important; }
/* Collapse the header bar height to zero, do NOT use visibility/display
   so the sidebar toggle button inside it stays functional */
[data-testid="stHeader"] {
    height: 0 !important;
    min-height: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
}
.stDeployButton { display: none; }
/* Push the app body up to reclaim the space */
[data-testid="stAppViewContainer"] {
    padding-top: 0 !important;
}
/* Sidebar expand tab — style it to match the dark sidebar */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] {
    background-color: #e5e7eb !important;
    border-radius: 0 8px 8px 0 !important;
    top: 48px !important;
}
[data-testid="collapsedControl"] svg,
[data-testid="stSidebarCollapsedControl"] svg {
    fill: #374151 !important;
}
</style>
""", unsafe_allow_html=True)


# ── Data loader ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Loading dashboard data...")
def load_all():
    # Load directly from pre-extracted CSVs (run scripts/extract_core_tables.py to refresh)
    pay  = pd.read_csv(f"{DATA}/payment.csv",                    parse_dates=["Created At"])
    inv  = pd.read_csv(f"{DATA}/invoice.csv",                    parse_dates=["Created At", "Due Date"])
    rep  = pd.read_csv(f"{DATA}/repayment.csv",                  parse_dates=["Created At"])
    rc   = pd.read_csv(f"{DATA}/retail_centre.csv")
    prod = pd.read_csv(f"{DATA}/product.csv")
    il   = pd.read_csv(f"{DATA}/invoice_line.csv")
    ir   = pd.read_csv(f"{DATA}/inventory_request.csv",          parse_dates=["Created At"])
    ibv  = pd.read_csv(f"{DATA}/inventory_balances_view.csv")
    camp = pd.read_csv(f"{DATA}/preorder_campaign.csv")
    irf  = pd.read_csv(f"{DATA}/inventory_request_fulfillment.csv")

    # ── Filter everything to Ghana (GH) ──────────────────────────────────────────
    inv  = inv[inv["Country Code"] == "GH"].copy()
    rep  = rep[rep["Country Code"] == "GH"].copy()
    rc   = rc[rc["Country Code"]   == "GH"].copy()
    # inventory_request is already all GH
    # invoice_line: keep only lines for GH invoices
    gh_inv_ids = set(inv["ID"].dropna().astype(int))
    il   = il[il["Invoice ID"].isin(gh_inv_ids)].copy()
    # inventory_balances_view: keep only GH retail centre locations
    gh_rc_ids  = set(rc["ID"].dropna())
    ibv  = ibv[ibv["Retail Centre ID"].isin(gh_rc_ids)].copy()
    # payment has no Country Code — left unfiltered

    pay["Payment Status"] = pay["Status"].map({0: "Failed", 1: "Success"})
    inv["Month"]          = inv["Created At"].dt.to_period("M").astype(str)
    inv["Week"]           = inv["Created At"].dt.to_period("W").astype(str)
    ir["Request Status"]  = ir["Status"].map({0:"Draft",1:"Pending",2:"Processing",3:"Completed",4:"Cancelled",5:"Failed"})
    ir["Delivery Label"]  = ir["Delivery Type"].map({0.0:"Direct",1.0:"Via Hub"})

    il["Line Revenue"] = pd.to_numeric(il["Quantity"], errors="coerce") * pd.to_numeric(il["Price"], errors="coerce")
    prod_rev = il.merge(prod[["ID","Generic Name","Brand Name"]], left_on="Product ID", right_on="ID", how="left")
    prod_rev["Product Name"] = prod_rev["Generic Name"].fillna(prod_rev["Brand Name"]).str.strip()

    for col in ["Start Date","End Date","Created At"]:
        camp[col] = pd.to_datetime(camp[col], format="ISO8601", utc=True).dt.tz_convert(None)
    camp["Status Label"] = camp["Status"].map({1:"Active",2:"Completed",3:"Cancelled"}).fillna("Unknown")

    for col in ["Expected At","Created At"]:
        irf[col] = pd.to_datetime(irf[col], format="ISO8601", utc=True).dt.tz_convert(None)
    irf["Fulfillment Status"] = irf["Status"].map({0:"Pending",1:"Processing",2:"Failed",3:"Fulfilled",4:"Cancelled"}).fillna("Unknown")

    rc_names = rc[["ID","Name","Status","Country Code"]].copy()

    # ── Canonical base filter — FBC stock orders, status 3/5/7, not BufferPesa ────
    ir_fbc = ir[
        (ir["Channel"] != "BufferPesa") &
        (ir["Fulfillment Type"] != 3) &
        (ir["Request Type"] == 0) &
        (ir["Status"].isin([3, 5, 7]))
    ].copy()

    valid_ir_ids = set(ir_fbc["ID"].dropna())

    # Revenue scope: invoice.order_type=1 (InventoryOrder) + channel!='BufferPesa'
    # is sufficient to identify all FBC stock orders. Do NOT join to IR status —
    # an invoice can be valid and paid even if its IR is still in progress.
    inv_fbc_ids = set(inv[
        (inv["Order Type"] == 1) &
        (inv["Channel"] != "BufferPesa")
    ]["ID"].dropna())

    inv_scoped = inv[
        (inv["Order Type"] == 1) &
        (inv["Channel"] != "BufferPesa") &
        (inv["Status"] != 5)   # exclude cancelled invoices
    ].copy()

    # Revenue: use Discountedvalue when populated, fall back to Total Order Value
    inv_scoped["Discountedvalue"] = pd.to_numeric(inv_scoped["Discountedvalue"], errors="coerce").fillna(0)
    _tov = pd.to_numeric(inv_scoped["Total Order Value"], errors="coerce").fillna(0)
    inv_scoped["Discountedvalue"] = inv_scoped["Discountedvalue"].where(
        inv_scoped["Discountedvalue"] > 0, _tov
    )
    inv_scoped["Totalrepaid"] = pd.to_numeric(inv_scoped["Totalrepaid"], errors="coerce").fillna(0)
    inv_scoped["Outstanding"] = (inv_scoped["Discountedvalue"] - inv_scoped["Totalrepaid"]).clip(lower=0)
    # Hide incomplete 2025 data — only show 2026 onwards
    inv_scoped = inv_scoped[inv_scoped["Created At"].dt.year >= 2026].copy()

    inv_scoped["Month"] = inv_scoped["Created At"].dt.to_period("M").astype(str)
    inv_scoped["Week"]  = inv_scoped["Created At"].dt.to_period("W").astype(str)

    # Repayments: scope to all FBC GH invoice IDs + Confirmed status
    rep_scoped = rep[
        rep["Invoice ID"].isin(inv_fbc_ids) &
        (rep["Status"] == "Confirmed")
    ].copy()

    # ir_all_fbc: FBC-scoped ir with all non-cancelled statuses (for reliability page)
    ir_all_fbc = ir[
        (ir["Channel"] != "BufferPesa") &
        (ir["Fulfillment Type"] != 3) &
        (ir["Request Type"] == 0) &
        (ir["Status"] != 4)
    ].copy()
    ir_all_fbc["Fulfillment Label"] = ir_all_fbc["Status"].map({
        0: "Not Started", 1: "Scheduled", 2: "In Progress",
        3: "Completed",   5: "Completed", 7: "Completed",
    }).fillna("Unknown")

    return pay, inv, rep, rc, prod, il, ir, prod_rev, rc_names, ibv, camp, irf, inv_scoped, rep_scoped, ir_all_fbc

pay, inv, rep, rc, prod, il, ir, prod_rev, rc_names, ibv, camp, irf, inv_scoped, rep_scoped, ir_all_fbc = load_all()

# ── Metrics ──────────────────────────────────────────────────────────────────────
total_invoiced   = inv_scoped["Discountedvalue"].sum()
total_revenue    = total_invoiced
total_repaid     = rep_scoped["Amount"].sum()
collection_pct   = (total_repaid / total_invoiced * 100) if total_invoiced > 0 else 0
outstanding_pct  = 100 - collection_pct
outstanding_val  = inv_scoped["Outstanding"].sum()
avg_order_value  = inv_scoped["Discountedvalue"].mean()
total_orders     = len(inv_scoped)
active_customers = rc[rc["Status"] == "Active"].shape[0]
total_customers  = len(rc)
active_pct       = active_customers / total_customers * 100 if total_customers else 0
completed_ir     = ir_all_fbc[ir_all_fbc["Status"].isin([3, 5, 7])].shape[0]
total_ir         = len(ir_all_fbc)
fulfillment_rate = completed_ir / total_ir * 100 if total_ir > 0 else 0
inactive         = total_customers - active_customers

top_cust_row = (inv.merge(rc_names, left_on="Customer ID", right_on="ID", how="left")
                   .groupby("Name")["Discountedvalue"].sum()
                   .sort_values(ascending=False).reset_index())
top_cust_name = top_cust_row.iloc[0]["Name"] if len(top_cust_row) else ","
top_cust_val  = top_cust_row.iloc[0]["Discountedvalue"] if len(top_cust_row) else 0

latest_date   = inv["Created At"].max()
date_label    = latest_date.strftime("%b %Y") if pd.notna(latest_date) else "N/A"
oldest_date   = inv["Created At"].min()
date_range    = f"{oldest_date.strftime('%b %Y')}, {latest_date.strftime('%b %Y')}" if pd.notna(oldest_date) else date_label

all_years     = sorted(inv_scoped["Created At"].dt.year.dropna().unique().astype(int).tolist())


# ── Helpers ──────────────────────────────────────────────────────────────────────
def kpi_card(label, value, subtitle, color, badge="", badge_color=""):
    v_str = str(value)
    # Hide cards whose value is a plain zero (skip percentage cards — 0% is meaningful)
    if "%" not in v_str:
        v_clean = v_str.replace("GHS", "").replace(",", "").replace(" ", "").strip()
        try:
            if float(v_clean) == 0:
                return ""
        except (ValueError, TypeError):
            pass
    badge_html = f'<span class="kpi-badge" style="background:{badge_color}22;color:{badge_color}">{badge}</span>' if badge else ""
    return f"""
    <div class="kpi-card" style="border-top-color:{color}">
        <div class="kpi-label">{label}{badge_html}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{subtitle}</div>
    </div>"""

def kpi_grid(html, max_cols=4):
    n = html.count('class="kpi-card"')
    if n == 0:
        return ""
    cols = min(n, max_cols)
    return f'<div class="kpi-grid" style="grid-template-columns:repeat({cols},1fr)">{html}</div>'

def chart_wrap(title, subtitle=""):
    sub = f'<div class="chart-sub">{subtitle}</div>' if subtitle else ""
    return f'<div class="chart-card"><div class="chart-title">{title}</div>{sub}'

def year_filter(key="year"):
    options = ["All"] + [str(y) for y in all_years]
    default_idx = options.index("2026") if "2026" in options else 0
    col_y, _ = st.columns([1, 5])
    with col_y:
        selected = st.selectbox("Year", options, index=default_idx, key=key)
    yr = selected if selected == "All" else int(selected) if selected is not None else "All"
    st.session_state["current_year"] = yr
    return yr

def apply_year(df, year, date_col="Created At"):
    if year == "All":
        return df
    return df[df[date_col].dt.year == year]

def white_layout(height=300):
    return dict(plot_bgcolor="white", paper_bgcolor="white",
                margin=dict(t=10, b=40, l=10, r=10), height=height,
                font=dict(family="Inter, sans-serif", size=12),
                yaxis=dict(gridcolor="#f3f4f6", gridwidth=1),
                xaxis=dict(tickangle=-35))


# ── Sidebar ──────────────────────────────────────────────────────────────────────
# ── Sidebar nav state ────────────────────────────────────────────────────────────
if "active_page" not in st.session_state:
    st.session_state["active_page"] = "Overview"

NAV_GROUPS = {
    "Core Analytics": ["Overview", "Sales Performance"],
    "Business":       ["Customers", "Payments"],
    "Phase 1":        ["Weekly Scorecard", "Reconciliation", "Data Quality"],
    "Phase 2":        ["Reliability", "Segmentation", "Campaigns"],
}

NAV_ICONS = {
    "Overview":          "🏠",
    "Sales Performance": "📈",
    "Products":          "📦",
    "Customers":         "👥",
    "Payments":          "💳",
    "Weekly Scorecard":  "📋",
    "Reconciliation":    "⚖️",
    "Data Quality":      "🔍",
    "Reliability":       "🛡️",
    "Segmentation":      "🎯",
    "Campaigns":         "📣",
}

with st.sidebar:
    st.markdown("""
    <div style="padding:20px 16px 14px;border-bottom:1px solid rgba(255,255,255,0.1);margin-bottom:8px">
        <div style="font-size:18px;font-weight:800;color:white">TribeCo Ghana Data Analysis</div>
    </div>
    """, unsafe_allow_html=True)

    all_pages = [item for items in NAV_GROUPS.values() for item in items]
    for item in all_pages:
        is_active = st.session_state["active_page"] == item
        kind      = "primary" if is_active else "secondary"
        if st.button(item, key=f"nav_{item}", use_container_width=True, type=kind):
            st.session_state["active_page"] = item
            st.rerun()

    # ── Auto-refresh: re-fetches data from disk every 5 minutes ─────────────────
    @st.fragment(run_every=300)
    def _auto_refresh():
        ts_file = os.path.join(DATA, "last_updated.txt")
        ts_text = ""
        if os.path.exists(ts_file):
            try:
                with open(ts_file, encoding="utf-8") as f:
                    ts_text = f.read().strip()
            except Exception:
                pass
        label = f"Live · updated {ts_text}" if ts_text else "Live · auto-refresh on"
        st.markdown(
            f'<div style="color:rgba(255,255,255,0.55);font-size:11px;'
            f'padding:10px 16px 6px;border-top:1px solid rgba(255,255,255,0.1);margin-top:6px">'
            f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
            f'background:#4ade80;margin-right:5px;vertical-align:middle"></span>'
            f'{label}</div>',
            unsafe_allow_html=True,
        )
        # On the initial page render, just record the baseline — don't trigger a rerun.
        if not st.session_state.get("_refresh_initialized"):
            st.session_state["_refresh_initialized"] = True
            return
        # On the full-page rerun we ourselves triggered, skip to avoid a loop.
        if st.session_state.pop("_refresh_triggered", False):
            return
        # Timer-fired run: clear the data cache and reload the page.
        st.session_state["_refresh_triggered"] = True
        st.cache_data.clear()
        st.rerun()

    _auto_refresh()


page = st.session_state["active_page"]

# ── Compute date range label based on the last selected year ─────────────────────
_yr = st.session_state.get("current_year", "All")
if _yr == "All":
    _inv_yr = inv
else:
    _inv_yr = inv[inv["Created At"].dt.year == _yr]
if len(_inv_yr):
    _from = _inv_yr["Created At"].min().strftime("%b %Y")
    _to   = _inv_yr["Created At"].max().strftime("%b %Y")
    _date_range = f"{_from}, {_to}"
else:
    _date_range = str(_yr)

# ── Top bar ──────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="topbar">
    <div class="topbar-title">{page}</div>
    <div class="topbar-right">
        <span class="badge-date">{_date_range}</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    yr    = year_filter("yr_overview")
    inv_y = apply_year(inv_scoped, yr)
    pay_y = apply_year(pay, yr)
    rep_y = apply_year(rep_scoped, yr)

    total_invoiced   = inv_y["Discountedvalue"].sum()
    total_revenue    = total_invoiced
    total_repaid     = rep_y["Amount"].sum()
    collection_pct   = (total_repaid / total_invoiced * 100) if total_invoiced > 0 else 0
    outstanding_pct  = 100 - collection_pct
    outstanding_val  = inv_y["Outstanding"].sum()
    avg_order_value  = inv_y["Discountedvalue"].mean() if len(inv_y) else 0
    total_orders     = len(inv_y)
    top_cust_y       = (inv_y.merge(rc_names, left_on="Customer ID", right_on="ID", how="left")
                              .groupby("Name")["Discountedvalue"].sum()
                              .sort_values(ascending=False).reset_index())
    top_cust_name    = top_cust_y.iloc[0]["Name"] if len(top_cust_y) else ","
    top_cust_val     = top_cust_y.iloc[0]["Discountedvalue"] if len(top_cust_y) else 0

    # ── MERL KPIs ────────────────────────────────────────────────────────────────
    rc_all = rc.copy()
    rc_all["Created At"] = pd.to_datetime(rc_all["Created At"], errors="coerce")
    new_partners_y = rc_all[rc_all["Created At"].dt.year == yr] if yr != "All" else rc_all
    new_signed     = len(new_partners_y)

    # Activation Rate (90d): new partners who placed first order within 90 days
    new_ids = set(new_partners_y["ID"].dropna())
    if new_ids and len(new_partners_y):
        first_ord = (inv_scoped[inv_scoped["Customer ID"].isin(new_ids)]
                     .sort_values("Created At")
                     .groupby("Customer ID")["Created At"].first().reset_index()
                     .rename(columns={"Created At":"first_order"}))
        first_ord = first_ord.merge(
            new_partners_y[["ID","Created At"]].rename(columns={"ID":"Customer ID","Created At":"signed_at"}),
            on="Customer ID", how="left")
        first_ord["days"] = (first_ord["first_order"] - first_ord["signed_at"]).dt.days
        activated_90d  = (first_ord["days"].between(0, 90)).sum()
        activation_rate = activated_90d / new_signed * 100 if new_signed else 0
    else:
        activated_90d, activation_rate = 0, 0

    # Repeat Rate (30d): ordering customers with a second order within 30 days of first
    if len(inv_y) > 0:
        first_inv = (inv_y.sort_values("Created At")
                          .groupby("Customer ID")["Created At"].first()
                          .reset_index().rename(columns={"Created At":"first_order"}))
        all_ord = inv_y.merge(first_inv, on="Customer ID")
        all_ord["days_gap"] = (all_ord["Created At"] - all_ord["first_order"]).dt.days
        repeat_custs  = all_ord[all_ord["days_gap"].between(1, 30)]["Customer ID"].nunique()
        active_custs  = inv_y["Customer ID"].nunique()
        repeat_rate   = repeat_custs / active_custs * 100 if active_custs else 0
    else:
        repeat_custs, active_custs, repeat_rate = 0, 0, 0

    # Revenue concentration
    cust_rev   = inv_y.groupby("Customer ID")["Discountedvalue"].sum().sort_values(ascending=False)
    rev_top5   = cust_rev.head(5).sum()  / total_invoiced * 100 if total_invoiced else 0
    rev_top10  = cust_rev.head(10).sum() / total_invoiced * 100 if total_invoiced else 0

    # Reconciliation rate
    inv_ids_y  = set(inv_y["ID"].dropna().astype(int))
    rep_ids    = set(rep_scoped["Invoice ID"].dropna().astype(int))
    recon_rate = len(inv_ids_y & rep_ids) / len(inv_ids_y) * 100 if inv_ids_y else 0

    # High-frequency small orders (<= 25th percentile AOV)
    low_thresh = inv_y["Discountedvalue"].quantile(0.25) if len(inv_y) else 0
    hfso_rate  = (inv_y["Discountedvalue"] <= low_thresh).mean() * 100 if len(inv_y) else 0


    # Row 1 — Core financials
    row1 = kpi_card("Total Sales",    f"GHS {total_revenue:,.0f}",   f"{total_orders:,} orders",            "#4f46e5") + \
           kpi_card("Collected",      f"GHS {total_repaid:,.0f}",    f"{collection_pct:.1f}% collection rate","#16a34a",
                    f"{collection_pct:.1f}%","#16a34a") + \
           kpi_card("Outstanding",    f"GHS {outstanding_val:,.0f}", f"{outstanding_pct:.1f}% outstanding",  "#dc2626",
                    f"{outstanding_pct:.1f}%","#dc2626") + \
           kpi_card("Basket Size (AOV)",f"GHS {avg_order_value:,.0f}","Avg order value",                    "#f59e0b")
    st.markdown(kpi_grid(row1), unsafe_allow_html=True)

    # Row 2 — MERL KPIs
    st.markdown("<div style='font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#6366f1;margin:16px 0 6px'>MERL Performance Indicators</div>", unsafe_allow_html=True)
    row2 = kpi_card("New Partners Signed", f"{new_signed:,}",
                    "Agrovets/Providers registered", "#8b5cf6") + \
           kpi_card("Activation Rate (90d)", f"{activation_rate:.1f}%",
                    f"{activated_90d} of {new_signed} placed first order", "#14b8a6",
                    f"{activation_rate:.0f}%","#14b8a6") + \
           kpi_card("Repeat Rate (30d)", f"{repeat_rate:.1f}%",
                    f"{repeat_custs} of {active_custs} customers reordered", "#16a34a",
                    f"{repeat_rate:.0f}%","#16a34a") + \
           kpi_card("Reconciliation Rate", f"{recon_rate:.1f}%",
                    "Orders matched to payments", "#4f46e5",
                    f"{recon_rate:.0f}%","#4f46e5")
    st.markdown(kpi_grid(row2), unsafe_allow_html=True)

    row3 = kpi_card("Top-5 Revenue Conc.", f"{rev_top5:.1f}%",
                    f"GHS {rev_top5/100*total_invoiced:,.0f} from top 5", "#f97316") + \
           kpi_card("Top-10 Revenue Conc.", f"{rev_top10:.1f}%",
                    f"GHS {rev_top10/100*total_invoiced:,.0f} from top 10","#dc2626") + \
           kpi_card("Active Customers",    f"{active_customers}",
                    f"of {total_customers} registered", "#3b82f6",
                    f"{active_pct:.0f}%","#3b82f6") + \
           kpi_card("High-Freq Small Orders", f"{hfso_rate:.1f}%",
                    f"Orders ≤ GHS {low_thresh:,.0f}", "#9ca3af")
    st.markdown(kpi_grid(row3), unsafe_allow_html=True)

    # ── Monthly revenue scorecard ─────────────────────────────────────────────────
    _MO_ABBR   = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                  "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}
    _MONTH_COLORS = ["#4f46e5","#6366f1","#8b5cf6","#3b82f6","#0ea5e9","#14b8a6"]
    _m_rev = inv_y.groupby("Month")["Discountedvalue"].sum().reset_index().sort_values("Month")
    _m_rev["prev"] = _m_rev["Discountedvalue"].shift(1)
    _m_rev["pct"]  = ((_m_rev["Discountedvalue"] - _m_rev["prev"]) / _m_rev["prev"] * 100).round(1)
    _month_html = ""
    for _i, (_, _r) in enumerate(_m_rev.iterrows()):
        _parts = str(_r["Month"]).split("-")
        _yr_lbl = _parts[0] if len(_parts) == 2 else ""
        _mo_lbl = _MO_ABBR.get(_parts[1], _parts[1]) if len(_parts) == 2 else _r["Month"]
        _label  = f"{_mo_lbl} {_yr_lbl}"
        _sub    = (f"+{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) and _r["pct"] >= 0
                   else (f"{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) else "First month"))
        _month_html += kpi_card(_label, f"GHS {_r['Discountedvalue']:,.0f}", _sub,
                                _MONTH_COLORS[_i % 6])
    if _month_html:
        st.markdown(
            "<div style='font-size:11px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:1px;color:#6366f1;margin:16px 0 6px'>Monthly Revenue</div>",
            unsafe_allow_html=True)
        st.markdown(
            f'<div class="kpi-grid" style="grid-template-columns:repeat(6,1fr)">'
            f'{_month_html}</div>',
            unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown(chart_wrap("Monthly Revenue Trend", f"GHS revenue by month ({date_range})"), unsafe_allow_html=True)
        monthly = inv_y.groupby("Month")["Discountedvalue"].sum().reset_index()
        monthly["prev"] = monthly["Discountedvalue"].shift(1)
        monthly["pct"]  = (((monthly["Discountedvalue"] - monthly["prev"]) / monthly["prev"]).astype(float) * 100).round(1)

        fig = go.Figure()
        fig.add_bar(x=monthly["Month"], y=monthly["Discountedvalue"],
                    marker_color="#4f46e5", name="Revenue (GHS)",
                    text=monthly["Discountedvalue"].apply(lambda x: f"{x/1000:.0f}k"),
                    textposition="outside", textfont=dict(size=10))
        fig.add_scatter(x=monthly["Month"], y=monthly["Discountedvalue"],
                        mode="lines+markers", line=dict(color="#f59e0b", width=2.5, dash="dot"),
                        marker=dict(size=6, color="#f59e0b"), name="Trend")
        for _, row in monthly.dropna(subset=["pct"]).iterrows():
            clr = "#16a34a" if row["pct"] >= 0 else "#dc2626"
            fig.add_annotation(x=row["Month"], y=row["Discountedvalue"],
                               text=f"{'+' if row['pct']>=0 else ''}{row['pct']:.0f}%",
                               showarrow=False, yshift=32, font=dict(size=10, color=clr))
        fig.update_layout(**white_layout(300),
                          legend=dict(orientation="h", y=-0.28, x=0))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Sales by City", "Top Ghana cities by order value"), unsafe_allow_html=True)
        city_sales = (inv_y.groupby("Customer City")["Discountedvalue"]
                           .sum().reset_index()
                           .rename(columns={"Customer City":"City","Discountedvalue":"Sales"})
                           .sort_values("Sales", ascending=False).head(8))
        city_sales = city_sales[city_sales["City"].notna() & (city_sales["City"] != "")]
        fig2 = px.pie(city_sales, names="City", values="Sales", hole=0.5,
                      color_discrete_sequence=["#4f46e5","#14b8a6","#f59e0b","#f97316","#8b5cf6","#ec4899","#16a34a","#dc2626"])
        fig2.update_traces(textinfo="percent", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=12, color="white"))
        fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10, b=10, l=10, r=10), height=300,
                           showlegend=True,
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11)))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown(chart_wrap("Repayment Status", "Invoice repayment breakdown"), unsafe_allow_html=True)
        rs = inv_y["Repayment Status"].value_counts().reset_index()
        rs.columns = ["Status", "Count"]
        clrs = {"Open":"#4f46e5","Repaid":"#16a34a","Overdue":"#dc2626","Due Soon":"#f59e0b"}
        fig3 = px.bar(rs, x="Status", y="Count", color="Status",
                      color_discrete_map=clrs, text="Count")
        fig3.update_traces(textposition="outside", textfont=dict(size=11))
        fig3.update_layout(**white_layout(240))
        fig3.update_layout(showlegend=False, xaxis=dict(tickangle=0))
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown(chart_wrap("Payment Mode", "Collection method split"), unsafe_allow_html=True)
        pm = rep_y["Payment Method"].value_counts().reset_index()
        pm.columns = ["Method", "Count"]
        pm_clrs = {"Mobile Money":"#4f46e5","Bank Transfer":"#16a34a","Cash":"#f59e0b","Mpesa":"#8b5cf6"}
        fig4 = px.pie(pm, names="Method", values="Count", hole=0.5,
                      color="Method", color_discrete_map=pm_clrs)
        fig4.update_traces(textinfo="percent", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=12, color="white"))
        fig4.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10, b=10, l=10, r=10), height=240,
                           showlegend=True,
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11)))
        st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Monthly Revenue Breakdown table ──────────────────────────────────────────
    st.markdown(chart_wrap("Monthly Revenue Breakdown",
                           "Sales, collected and outstanding by month"), unsafe_allow_html=True)
    _rep_y_m  = rep_y.copy()
    _rep_y_m["Month"] = _rep_y_m["Created At"].dt.to_period("M").astype(str)
    _mb_coll  = _rep_y_m.groupby("Month")["Amount"].sum().reset_index().rename(columns={"Amount":"Collected"})
    _mb_inv   = inv_y.groupby("Month").agg(
        Revenue  = ("Discountedvalue", "sum"),
        Invoices = ("Discountedvalue", "count"),
    ).reset_index()
    _mb_tbl   = _mb_inv.merge(_mb_coll, on="Month", how="left").fillna(0)
    _mb_tbl["Outstanding"]  = inv_y.groupby("Month")["Outstanding"].sum().reindex(_mb_tbl["Month"]).values
    _mb_tbl["Collection %"] = (_mb_tbl["Collected"] / _mb_tbl["Revenue"] * 100).round(1)
    _mb_tbl["prev"]         = _mb_tbl["Revenue"].shift(1)
    _mb_tbl["MoM Change"]   = ((_mb_tbl["Revenue"] - _mb_tbl["prev"]) / _mb_tbl["prev"] * 100).round(1)
    _disp = _mb_tbl.copy()
    _disp["Revenue"]      = _disp["Revenue"].apply(lambda v: f"GHS {v:,.0f}")
    _disp["Collected"]    = _disp["Collected"].apply(lambda v: f"GHS {v:,.0f}")
    _disp["Outstanding"]  = _disp["Outstanding"].apply(lambda v: f"GHS {v:,.0f}")
    _disp["Collection %"] = _disp["Collection %"].apply(lambda v: f"{v:.1f}%")
    _disp["MoM Change"]   = _disp["MoM Change"].apply(
        lambda v: f"+{v:.1f}%" if pd.notna(v) and v >= 0 else (f"{v:.1f}%" if pd.notna(v) else "-"))
    st.dataframe(_disp[["Month","Invoices","Revenue","Collected","Outstanding","Collection %","MoM Change"]],
                 use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Vaccines Delivered by Disease ─────────────────────────────────────────────
    st.markdown(chart_wrap("Vaccines Delivered by Disease",
                           "Monthly doses distributed by disease — Poultry · Goats & Sheep · Cattle"),
                unsafe_allow_html=True)

    # Disease mapping (product generic name → disease label)
    _DISEASE_MAP = {
        "LASOTA":            "Newcastle",
        "NewCavac":          "Newcastle",
        "HB1":               "Newcastle",
        "I-2 Vaccine":       "Newcastle",
        "Lasota + IB":       "Newcastle",
        "ND+IB+EDS":         "Newcastle",
        "GUMBORO INTER":     "Gumboro",
        "FOWL POX":          "Fowlpox",
        "Infectious Coryza": "Other Poultry",
    }
    _DISEASE_COLORS = {
        "Newcastle":     "#4f46e5",
        "Gumboro":       "#06b6d4",
        "Fowlpox":       "#f59e0b",
        "AI":            "#ef4444",
        "PPR":           "#16a34a",
        "CBPP":          "#8b5cf6",
        "Other Poultry": "#9ca3af",
    }

    # Join invoice lines → products → disease, filtered to current year
    _il_v = il[il["Invoice ID"].isin(set(inv_y["ID"].dropna().astype(int)))].copy()
    _il_v = _il_v.merge(prod[["ID", "Generic Name", "Brand Name"]],
                        left_on="Product ID", right_on="ID", how="left")
    _il_v["Product"]  = _il_v["Generic Name"].fillna(_il_v["Brand Name"])
    _il_v["Disease"]  = _il_v["Product"].map(_DISEASE_MAP).fillna("Other")
    _il_v["Quantity"] = pd.to_numeric(_il_v["Quantity"], errors="coerce").fillna(0)

    # Attach month from inv_y
    _inv_mo = inv_y[["ID", "Month"]].rename(columns={"ID": "Invoice ID"})
    _il_v   = _il_v.merge(_inv_mo, on="Invoice ID", how="left")

    _vax = (_il_v[_il_v["Disease"] != "Other"]
            .groupby(["Month", "Disease"])["Quantity"]
            .sum().reset_index())

    if len(_vax):
        _disease_order = ["Newcastle", "Gumboro", "Fowlpox", "AI", "PPR", "CBPP", "Other Poultry"]
        _diseases_present = [d for d in _disease_order if d in _vax["Disease"].unique()]

        col_vax1, col_vax2 = st.columns([3, 2])
        with col_vax1:
            fig_vax = px.bar(
                _vax, x="Month", y="Quantity", color="Disease",
                barmode="stack",
                color_discrete_map=_DISEASE_COLORS,
                category_orders={"Disease": _diseases_present},
                labels={"Quantity": "Doses", "Month": ""},
                text_auto=False,
            )
            fig_vax.update_layout(
                **white_layout(320),
                legend=dict(orientation="h", y=-0.25, font=dict(size=11)),
                yaxis_title="Doses Delivered",
            )
            st.plotly_chart(fig_vax, use_container_width=True, config=CHART_CFG)

        with col_vax2:
            # Summary table: disease totals + % share
            _vax_sum = (_il_v[_il_v["Disease"] != "Other"]
                        .groupby("Disease")["Quantity"].sum()
                        .reset_index().sort_values("Quantity", ascending=False))
            _total_doses = _vax_sum["Quantity"].sum()
            _vax_sum["Share"] = (_vax_sum["Quantity"] / _total_doses * 100).round(1)
            _vax_sum["Doses"] = _vax_sum["Quantity"].apply(lambda v: f"{v:,.0f}")
            _vax_sum["Share"] = _vax_sum["Share"].apply(lambda v: f"{v:.1f}%")
            st.dataframe(
                _vax_sum[["Disease", "Doses", "Share"]],
                use_container_width=True, hide_index=True
            )
            st.markdown(
                f"<div style='font-size:12px;color:#6b7280;margin-top:8px'>"
                f"Total doses: <b>{_total_doses:,.0f}</b></div>",
                unsafe_allow_html=True
            )
    else:
        st.info("No vaccine delivery data found for the selected period.")
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — SALES PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Sales Performance":
    yr    = year_filter("yr_sales")
    inv_y = apply_year(inv_scoped, yr)
    months_available = sorted(inv_y["Month"].dropna().unique())
    selected = st.multiselect("Filter by Month", months_available,
                              default=months_available[-6:] if len(months_available) >= 6 else months_available)
    inv_f = inv_y[inv_y["Month"].isin(selected)] if selected else inv_y

    r1 = kpi_card("Total Sales", f"GHS {inv_f['Discountedvalue'].sum():,.0f}", "Sales in period", "#4f46e5") + \
         kpi_card("Total Orders", f"{len(inv_f):,}", "In selected period", "#14b8a6") + \
         kpi_card("Avg Sale Value", f"GHS {inv_f['Discountedvalue'].mean():,.0f}", "Per order", "#f59e0b")
    st.markdown(kpi_grid(r1, max_cols=3), unsafe_allow_html=True)

    # ── Monthly revenue scorecard ─────────────────────────────────────────────────
    _SP_ABBR   = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                  "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}
    _SP_COLORS = ["#4f46e5","#6366f1","#8b5cf6","#3b82f6","#0ea5e9","#14b8a6"]
    _sp_rev = inv_f.groupby("Month")["Discountedvalue"].sum().reset_index().sort_values("Month")
    _sp_rev["prev"] = _sp_rev["Discountedvalue"].shift(1)
    _sp_rev["pct"]  = ((_sp_rev["Discountedvalue"] - _sp_rev["prev"]) / _sp_rev["prev"] * 100).round(1)
    _sp_html = ""
    for _i, (_, _r) in enumerate(_sp_rev.iterrows()):
        _parts  = str(_r["Month"]).split("-")
        _yr_lbl = _parts[0] if len(_parts) == 2 else ""
        _mo_lbl = _SP_ABBR.get(_parts[1], _parts[1]) if len(_parts) == 2 else _r["Month"]
        _label  = f"{_mo_lbl} {_yr_lbl}"
        _sub    = (f"+{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) and _r["pct"] >= 0
                   else (f"{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) else "First month"))
        _sp_html += kpi_card(_label, f"GHS {_r['Discountedvalue']:,.0f}", _sub,
                             _SP_COLORS[_i % 6])
    if _sp_html:
        st.markdown(
            "<div style='font-size:11px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:1px;color:#6366f1;margin:16px 0 6px'>Monthly Revenue</div>",
            unsafe_allow_html=True)
        st.markdown(
            f'<div class="kpi-grid" style="grid-template-columns:repeat(6,1fr)">'
            f'{_sp_html}</div>',
            unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Monthly Sales vs Previous Month"), unsafe_allow_html=True)
        m = inv_f.groupby("Month")["Discountedvalue"].sum().reset_index()
        m["Prev"]     = m["Discountedvalue"].shift(1)
        m["Change %"] = (((m["Discountedvalue"] - m["Prev"]) / m["Prev"]).astype(float) * 100).round(1)
        fig = go.Figure()
        fig.add_bar(x=m["Month"], y=m["Discountedvalue"], marker_color="#4f46e5",
                    name="Sales (GHS)", text=m["Discountedvalue"].apply(lambda x: f"{x/1000:.0f}k"),
                    textposition="outside", textfont=dict(size=10))
        for _, row in m.dropna(subset=["Change %"]).iterrows():
            clr = "#16a34a" if row["Change %"] >= 0 else "#dc2626"
            fig.add_annotation(x=row["Month"], y=row["Discountedvalue"],
                               text=f"{'+' if row['Change %']>=0 else ''}{row['Change %']:.0f}%",
                               showarrow=False, yshift=30, font=dict(size=10, color=clr))
        fig.update_layout(**white_layout(300))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Weekly Sales Trend"), unsafe_allow_html=True)
        w = inv_f.groupby("Week")["Discountedvalue"].sum().reset_index().tail(16)
        fig2 = go.Figure()
        fig2.add_bar(x=w["Week"], y=w["Discountedvalue"], marker_color="#e0e7ff", name="Weekly Sales")
        fig2.add_scatter(x=w["Week"], y=w["Discountedvalue"],
                         mode="lines+markers", line=dict(color="#4f46e5", width=2.5),
                         marker=dict(size=5, color="#4f46e5"), name="Trend")
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(xaxis=dict(tickangle=-45, nticks=8),
                           legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Monthly Sales Summary"), unsafe_allow_html=True)
    summary = m.copy()
    summary["Sales"]      = summary["Discountedvalue"].apply(lambda x: f"GHS {x:,.0f}")
    summary["MoM Change"] = summary["Change %"].apply(
        lambda x: f"+{x:.1f}%" if pd.notna(x) and x >= 0 else (f"{x:.1f}%" if pd.notna(x) else ","))
    st.dataframe(summary[["Month","Sales","MoM Change"]], use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Customers":
    yr     = year_filter("yr_customers")
    inv_y  = apply_year(inv_scoped, yr)
    top_cust_y = (inv_y.merge(rc_names, left_on="Customer ID", right_on="ID", how="left")
                       .groupby("Name")["Discountedvalue"].sum()
                       .sort_values(ascending=False).reset_index())

    # MERL: new partners signed in selected year
    rc_dated = rc.copy()
    rc_dated["Created At"] = pd.to_datetime(rc_dated["Created At"], errors="coerce")
    new_partners_y = rc_dated[rc_dated["Created At"].dt.year == yr] if yr != "All" else rc_dated
    new_signed_y   = len(new_partners_y)

    # MERL: Activation Rate (90d)
    new_ids_y = set(new_partners_y["ID"].dropna())
    if new_ids_y:
        fo = (inv_scoped[inv_scoped["Customer ID"].isin(new_ids_y)]
              .sort_values("Created At")
              .groupby("Customer ID")["Created At"].first().reset_index()
              .rename(columns={"Created At":"first_order"}))
        fo = fo.merge(new_partners_y[["ID","Created At"]].rename(
                      columns={"ID":"Customer ID","Created At":"signed_at"}), on="Customer ID", how="left")
        fo["days"] = (fo["first_order"] - fo["signed_at"]).dt.days
        act_90   = (fo["days"].between(0, 90)).sum()
        act_rate = act_90 / new_signed_y * 100 if new_signed_y else 0
    else:
        act_90, act_rate = 0, 0

    # MERL: Repeat Rate (30d)
    if len(inv_y):
        fi = (inv_y.sort_values("Created At").groupby("Customer ID")["Created At"]
                   .first().reset_index().rename(columns={"Created At":"first_order"}))
        ao = inv_y.merge(fi, on="Customer ID")
        ao["gap"] = (ao["Created At"] - ao["first_order"]).dt.days
        rep_c     = ao[ao["gap"].between(1,30)]["Customer ID"].nunique()
        act_c     = inv_y["Customer ID"].nunique()
        rep_rate  = rep_c / act_c * 100 if act_c else 0
    else:
        rep_c, act_c, rep_rate = 0, 0, 0

    r1 = kpi_card("New Partners Signed", f"{new_signed_y:,}",
                  f"In {yr} · Agrovets & Providers", "#8b5cf6") + \
         kpi_card("Activation Rate (90d)", f"{act_rate:.1f}%",
                  f"{act_90} of {new_signed_y} ordered within 90d", "#14b8a6",
                  f"{act_rate:.0f}%","#14b8a6") + \
         kpi_card("Repeat Rate (30d)", f"{rep_rate:.1f}%",
                  f"{rep_c} of {act_c} reordered within 30d", "#16a34a",
                  f"{rep_rate:.0f}%","#16a34a") + \
         kpi_card("Avg Orders/Customer", f"{len(inv_y)/act_c:.1f}" if act_c else ",",
                  f"{act_c} active ordering customers", "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    r2 = kpi_card("Total Registered",  f"{total_customers:,}", "All customers",  "#4f46e5") + \
         kpi_card("Active (Status)",   f"{active_customers}",  f"{active_pct:.1f}% of total", "#16a34a",
                  f"{active_pct:.0f}%","#16a34a") + \
         kpi_card("Inactive",          f"{inactive}",          f"{100-active_pct:.1f}% of total","#dc2626") + \
         kpi_card("Ordering Customers",f"{act_c}",             f"Placed orders in {yr}", "#3b82f6")
    st.markdown(kpi_grid(r2), unsafe_allow_html=True)

    top_cust = top_cust_y.head(10).copy()
    top_cust.columns = ["Customer", "Total Value"]
    top_cust = top_cust[top_cust["Customer"].notna()]

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(chart_wrap("Top 10 Customers by Order Value"), unsafe_allow_html=True)
        fig = px.bar(top_cust.sort_values("Total Value"), x="Total Value", y="Customer",
                     orientation="h", text="Total Value",
                     color="Total Value", color_continuous_scale=["#e0e7ff","#4f46e5"])
        fig.update_traces(texttemplate="GHS %{text:,.0f}", textposition="inside",
                          insidetextanchor="middle", textfont=dict(color="white", size=10))
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=10, b=10, l=10, r=10), height=360,
                          coloraxis_showscale=False, xaxis=dict(gridcolor="#f3f4f6"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Active vs Inactive"), unsafe_allow_html=True)
        sdf = pd.DataFrame({"Status":["Active","Inactive"],"Count":[active_customers, inactive]})
        fig2 = px.pie(sdf, names="Status", values="Count", hole=0.55,
                      color="Status", color_discrete_map={"Active":"#4f46e5","Inactive":"#e0e7ff"})
        fig2.update_traces(textinfo="percent+label", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=13, color="white"))
        fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10, b=10, l=10, r=10), height=300, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    # New partners timeline
    st.markdown(chart_wrap("New Partner Registrations by Month", "Agrovets & Providers signed per month"), unsafe_allow_html=True)
    rc_dated["Month"] = rc_dated["Created At"].dt.to_period("M").astype(str)
    rc_month = rc_dated[rc_dated["Created At"].dt.year == yr] if yr != "All" else rc_dated
    rc_month_grp = rc_month.groupby(["Month","Segment Type"])["ID"].count().to_frame("Count").reset_index()
    seg_col_map = {"Provider":"#4f46e5","Agrovet":"#14b8a6","Hatchery":"#f59e0b"}
    fig3 = px.bar(rc_month_grp, x="Month", y="Count", color="Segment Type",
                  color_discrete_map=seg_col_map, barmode="stack", text="Count")
    fig3.update_traces(textposition="inside", textfont=dict(color="white", size=10))
    fig3.update_layout(**white_layout(260), legend=dict(orientation="h", y=-0.3))
    fig3.update_layout(xaxis=dict(tickangle=-30))
    st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Customer Leaderboard"), unsafe_allow_html=True)
    lb = top_cust.copy()
    lb.index = pd.RangeIndex(1, len(lb)+1)
    lb["Total Value"] = lb["Total Value"].apply(lambda x: f"GHS {x:,.0f}")
    st.dataframe(lb, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Active Customers Directory", f"All {active_customers} active registered customers"), unsafe_allow_html=True)
    dir_df = rc[rc["Status"] == "Active"][[
        "Name", "Segment Type", "Customer Address → Region",
        "Phone Number", "Created At"
    ]].copy()
    dir_df["Created At"] = pd.to_datetime(dir_df["Created At"], errors="coerce")
    dir_df = dir_df.sort_values("Created At", ascending=True).reset_index(drop=True)
    dir_df["Created At"] = dir_df["Created At"].dt.strftime("%d %b %Y")
    dir_df = dir_df.rename(columns={
        "Customer Address → Region": "Region",
        "Phone Number":              "Phone",
        "Created At":                "Date Joined",
    })
    dir_df.index = pd.RangeIndex(1, len(dir_df) + 1)
    st.dataframe(dir_df, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Payments":
    yr    = year_filter("yr_payments")
    rep_y = apply_year(rep_scoped, yr)
    inv_y = apply_year(inv_scoped, yr)
    pay_y = apply_year(pay, yr)
    total_repaid_y   = rep_y["Amount"].sum()
    total_invoiced_y = inv_y["Discountedvalue"].sum()
    collection_pct_y = (total_repaid_y / total_invoiced_y * 100) if total_invoiced_y > 0 else 0
    outstanding_y    = inv_y["Outstanding"].sum()
    outstanding_pct_y= outstanding_y / total_invoiced_y * 100 if total_invoiced_y > 0 else 0
    success_pay_y    = pay_y[pay_y["Payment Status"] == "Success"]
    r1 = kpi_card("Total Collected",     f"GHS {total_repaid_y:,.0f}", f"{collection_pct_y:.1f}% rate", "#16a34a",
                  f"{collection_pct_y:.1f}%", "#16a34a") + \
         kpi_card("Outstanding",         f"GHS {outstanding_y:,.0f}", f"{outstanding_pct_y:.1f}% of invoiced",
                  "#dc2626", f"{outstanding_pct_y:.1f}%", "#dc2626") + \
         kpi_card("Successful Payments", f"{success_pay_y.shape[0]:,}", "Transactions", "#4f46e5") + \
         kpi_card("Avg Payment",         f"GHS {rep_y['Amount'].mean():,.0f}", "Per repayment", "#f97316")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Payment Mode Distribution", "By number of transactions"), unsafe_allow_html=True)
        pm = rep_y["Payment Method"].value_counts().reset_index()
        pm.columns = ["Method", "Count"]
        pm_clrs = {"Mobile Money":"#4f46e5","Bank Transfer":"#16a34a","Cash":"#f59e0b","Mpesa":"#8b5cf6"}
        fig = px.pie(pm, names="Method", values="Count", hole=0.5,
                     color="Method", color_discrete_map=pm_clrs)
        fig.update_traces(textinfo="percent", textposition="inside",
                          insidetextorientation="horizontal",
                          textfont=dict(size=13, color="white"))
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=10, b=10, l=10, r=10), height=300,
                          showlegend=True,
                          legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11)))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Monthly Collections vs Invoiced"), unsafe_allow_html=True)
        rep2 = rep_y.copy()
        rep2["Month"] = rep2["Created At"].dt.to_period("M").astype(str)
        monthly_col  = rep2.groupby("Month")["Amount"].sum().reset_index()
        monthly_inv  = inv_y.groupby("Month")["Discountedvalue"].sum().reset_index()
        cmp = monthly_inv.merge(monthly_col, on="Month", how="left").fillna(0)
        fig2 = go.Figure()
        fig2.add_bar(x=cmp["Month"], y=cmp["Discountedvalue"], name="Invoiced", marker_color="#e0e7ff")
        fig2.add_bar(x=cmp["Month"], y=cmp["Amount"],            name="Collected", marker_color="#4f46e5")
        fig2.update_layout(barmode="overlay", **white_layout(300),
                           legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Payment Method Summary"), unsafe_allow_html=True)
    pm_s = rep_y.groupby("Payment Method").agg(
        Transactions=("Amount","count"),
        Total_Collected=("Amount","sum"),
        Avg_Amount=("Amount","mean")
    ).reset_index().sort_values("Total_Collected", ascending=False)
    pm_s["Total_Collected"] = pm_s["Total_Collected"].apply(lambda x: f"GHS {x:,.2f}")
    pm_s["Avg_Amount"]      = pm_s["Avg_Amount"].apply(lambda x: f"GHS {x:,.2f}")
    st.dataframe(pm_s.rename(columns={"Payment Method":"Method","Total_Collected":"Total Collected","Avg_Amount":"Avg per Transaction"}),
                 use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Recent Collections"), unsafe_allow_html=True)
    st.dataframe(rep.sort_values("Created At", ascending=False)
                    [["Created At","Amount","Payment Method","Repayment Route","Country Code"]].head(30),
                 use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — WEEKLY SCORECARD
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Weekly Scorecard":
    yr    = year_filter("yr_weekly")
    inv_y = apply_year(inv_scoped, yr)
    rep_y = apply_year(rep_scoped, yr).copy()
    rep_y["Week"] = rep_y["Created At"].dt.to_period("W").astype(str)

    latest_week  = inv_y["Week"].max() if len(inv_y) else None
    inv_w        = inv_y[inv_y["Week"] == latest_week] if latest_week else inv_y.iloc[:0]
    rep_w        = rep_y[rep_y["Week"] == latest_week] if latest_week else rep_y.iloc[:0]

    weekly_orders    = len(inv_w)
    weekly_sales     = inv_w["Discountedvalue"].sum()
    weekly_collected = rep_w["Amount"].sum()
    overdue_inv      = inv_y[inv_y["Repayment Status"] == "Overdue"]

    r1 = kpi_card("Orders This Week",    f"{weekly_orders:,}",
                  f"Week of {latest_week}", "#4f46e5") + \
         kpi_card("Sales This Week",     f"GHS {weekly_sales:,.0f}",
                  "Total invoiced value", "#14b8a6") + \
         kpi_card("Collected This Week", f"GHS {weekly_collected:,.0f}",
                  "Repayments received", "#16a34a") + \
         kpi_card("Overdue Invoices",    f"{len(overdue_inv):,}",
                  "Requiring follow-up", "#dc2626",
                  f"{len(overdue_inv)}", "#dc2626")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(chart_wrap("Weekly Orders & Sales Trend", "Last 16 weeks"), unsafe_allow_html=True)
        w_trend = (inv_y.groupby("Week")
                        .agg(Orders=("ID","count"), Sales=("Discountedvalue","sum"))
                        .reset_index().tail(16))
        fig = go.Figure()
        fig.add_bar(x=w_trend["Week"], y=w_trend["Sales"],
                    marker_color="#e0e7ff", name="Sales (GHS)", yaxis="y")
        fig.add_scatter(x=w_trend["Week"], y=w_trend["Orders"],
                        mode="lines+markers", line=dict(color="#4f46e5", width=2.5),
                        marker=dict(size=6, color="#4f46e5"), name="Orders", yaxis="y2")
        fig.update_layout(**white_layout(300))
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=-0.3),
            xaxis=dict(tickangle=-45, nticks=8)
        )
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Week-over-Week Sales Change", "Last 8 weeks"), unsafe_allow_html=True)
        ww = (inv_y.groupby("Week")["Discountedvalue"].sum().reset_index().tail(8))
        ww["Prev"]   = ww["Discountedvalue"].shift(1)
        ww["Change"] = ((ww["Discountedvalue"] - ww["Prev"]) / ww["Prev"] * 100).round(1)
        bar_colors   = ["#16a34a" if x >= 0 else "#dc2626" for x in ww["Change"].fillna(0)]
        fig2 = go.Figure(go.Bar(
            x=ww["Week"], y=ww["Change"].fillna(0),
            marker_color=bar_colors,
            text=ww["Change"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else ","),
            textposition="outside"
        ))
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(
            xaxis=dict(tickangle=-45),
            yaxis=dict(title="% Change", gridcolor="#f3f4f6")
        )
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Weekly Breakdown", "Orders, invoiced value and collections per week"), unsafe_allow_html=True)
    weekly_inv = (inv_y.groupby("Week")
                       .agg(Orders=("ID","count"), Invoice_Total=("Discountedvalue","sum"))
                       .reset_index())
    weekly_rep = (rep_y.groupby("Week")
                       .agg(Sales_Collected=("Amount","sum"))
                       .reset_index())
    weekly_tbl = weekly_inv.merge(weekly_rep, on="Week", how="left")
    weekly_tbl["Sales_Collected"] = weekly_tbl["Sales_Collected"].fillna(0)
    weekly_tbl["Collection Rate"] = weekly_tbl.apply(
        lambda r: f"{r['Sales_Collected']/r['Invoice_Total']*100:.1f}%" if r["Invoice_Total"] > 0 else "0.0%", axis=1)
    weekly_tbl["Value GHS"]             = weekly_tbl["Invoice_Total"].apply(lambda x: f"GHS {x:,.0f}")
    weekly_tbl["Sales Collected (GHS)"] = weekly_tbl["Sales_Collected"].apply(lambda x: f"GHS {x:,.0f}")

    # Week start date (e.g. "5-Jan-2026") and ISO week number (continuous across the year)
    _wk_starts = weekly_tbl["Week"].apply(lambda w: pd.Period(w, freq="W").start_time)
    weekly_tbl["Date"]        = _wk_starts.apply(lambda d: f"{d.day}-{d.strftime('%b-%Y')}")
    weekly_tbl["Week Number"] = _wk_starts.apply(lambda d: int(d.isocalendar()[1]))

    weekly_tbl = (weekly_tbl
        .sort_values("Week", ascending=False)
        [["Date", "Week Number", "Orders", "Value GHS", "Sales Collected (GHS)", "Collection Rate"]]
        .reset_index(drop=True))
    st.dataframe(weekly_tbl, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Overdue Invoice Exceptions", "Invoices requiring immediate follow-up"), unsafe_allow_html=True)
    if len(overdue_inv):
        exc = overdue_inv.merge(rc_names[["ID","Name"]], left_on="Customer ID", right_on="ID", how="left")
        exc = exc[["Created At","Name","Discountedvalue","Due Date","Repayment Status"]].copy()
        exc.columns = ["Invoice Date","Customer","Amount (GHS)","Due Date","Status"]
        exc["Amount (GHS)"] = exc["Amount (GHS)"].apply(lambda x: f"GHS {x:,.0f}")
        exc["Invoice Date"] = exc["Invoice Date"].dt.strftime("%Y-%m-%d")
        exc["Due Date"]     = pd.to_datetime(exc["Due Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        exc = exc.sort_values("Due Date")
        exc.index = pd.RangeIndex(1, len(exc)+1)
        st.dataframe(exc, use_container_width=True)
    else:
        st.success("No overdue invoices in the selected period.")
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — RECONCILIATION
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Reconciliation":
    yr    = year_filter("yr_recon")
    inv_y = apply_year(inv_scoped, yr)

    invoiced_ids  = set(inv_y["ID"].dropna().astype(int))
    repaid_ids    = set(rep_scoped["Invoice ID"].dropna().astype(int))

    matched_ids   = invoiced_ids & repaid_ids
    unmatched_ids = invoiced_ids - repaid_ids

    total_invoices  = len(invoiced_ids)
    matched_count   = len(matched_ids)
    unmatched_count = len(unmatched_ids)
    match_rate      = matched_count / total_invoices * 100 if total_invoices else 0
    matched_val     = inv_y[inv_y["ID"].isin(matched_ids)]["Discountedvalue"].sum()
    unmatched_val   = inv_y[inv_y["ID"].isin(unmatched_ids)]["Discountedvalue"].sum()

    r1 = kpi_card("Total Invoices",     f"{total_invoices:,}",
                  "In selected period", "#4f46e5") + \
         kpi_card("Reconciled",         f"{matched_count:,}",
                  f"{match_rate:.1f}% match rate", "#16a34a",
                  f"{match_rate:.0f}%", "#16a34a") + \
         kpi_card("Unreconciled",       f"{unmatched_count:,}",
                  "No repayment record", "#dc2626") + \
         kpi_card("Unreconciled Value", f"GHS {unmatched_val:,.0f}",
                  "Awaiting payment", "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Reconciliation Status", "Invoice match rate"), unsafe_allow_html=True)
        recon_df = pd.DataFrame({
            "Status": ["Reconciled","Unreconciled"],
            "Count":  [matched_count, unmatched_count]
        })
        fig = px.pie(recon_df, names="Status", values="Count", hole=0.55,
                     color="Status",
                     color_discrete_map={"Reconciled":"#16a34a","Unreconciled":"#dc2626"})
        fig.update_traces(textinfo="percent+label", textposition="inside",
                          insidetextorientation="horizontal",
                          textfont=dict(size=13, color="white"))
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=10,b=10,l=10,r=10), height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Value: Reconciled vs Unreconciled"), unsafe_allow_html=True)
        val_df = pd.DataFrame({
            "Category": ["Reconciled","Unreconciled"],
            "Value":    [matched_val, unmatched_val]
        })
        fig2 = px.bar(val_df, x="Category", y="Value", color="Category",
                      color_discrete_map={"Reconciled":"#16a34a","Unreconciled":"#dc2626"},
                      text="Value")
        fig2.update_traces(texttemplate="GHS %{text:,.0f}", textposition="outside",
                           textfont=dict(size=11))
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(showlegend=False, xaxis=dict(tickangle=0))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Repayment Status Breakdown", "Distribution of invoice repayment statuses"), unsafe_allow_html=True)
    rs = inv_y["Repayment Status"].value_counts().reset_index()
    rs.columns = ["Status","Count"]
    clrs = {"Open":"#4f46e5","Repaid":"#16a34a","Overdue":"#dc2626","Due Soon":"#f59e0b"}
    fig3 = px.bar(rs, x="Status", y="Count", color="Status",
                  color_discrete_map=clrs, text="Count")
    fig3.update_traces(textposition="outside", textfont=dict(size=11))
    fig3.update_layout(**white_layout(240))
    fig3.update_layout(showlegend=False, xaxis=dict(tickangle=0))
    st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Unreconciled Invoices", "Top invoices with no repayment record"), unsafe_allow_html=True)
    unmatched_df = inv_y[inv_y["ID"].isin(unmatched_ids)].copy()
    if len(unmatched_df):
        unmatched_df = unmatched_df.merge(rc_names[["ID","Name"]], left_on="Customer ID", right_on="ID", how="left")
        show_cols = unmatched_df[["Created At","Name","Discountedvalue","Repayment Status"]].copy()
        show_cols.columns = ["Invoice Date","Customer","Amount (GHS)","Status"]
        show_cols["Amount (GHS)"] = show_cols["Amount (GHS)"].apply(lambda x: f"GHS {x:,.0f}")
        show_cols["Invoice Date"] = show_cols["Invoice Date"].dt.strftime("%Y-%m-%d")
        show_cols = show_cols.sort_values("Invoice Date", ascending=False).head(30)
        show_cols.index = pd.RangeIndex(1, len(show_cols)+1)
        st.dataframe(show_cols, use_container_width=True)
    else:
        st.success("All invoices in this period are reconciled.")
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — DATA QUALITY
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Data Quality":
    st.markdown("<div style='color:#6b7280;font-size:13px;margin-bottom:16px'>Field completeness analysis across key operational tables</div>", unsafe_allow_html=True)

    inv_fields = {
        "Discounted Value":  inv["Discountedvalue"].notna().mean() * 100,
        "Customer ID":       inv["Customer ID"].notna().mean() * 100,
        "Order ID":          inv["Order ID"].notna().mean() * 100,
        "Order Type":        inv["Order Type"].notna().mean() * 100,
        "Channel":           inv["Channel"].notna().mean() * 100,
        "Repayment Status":  inv["Repayment Status"].notna().mean() * 100,
        "Fulfilment Type":   inv["Fulfilmenttype"].notna().mean() * 100,
        "Customer City":     inv["Customer City"].notna().mean() * 100,
        "Paid At":           inv["Paid At"].notna().mean() * 100,
        "Repayment Route":   inv["Repayment Route"].notna().mean() * 100,
    }
    rc_fields = {
        "Name":         rc["Name"].notna().mean() * 100,
        "Status":       rc["Status"].notna().mean() * 100,
        "Address Region":   rc["Customer Address → Region"].notna().mean() * 100,
        "Segment Type": rc["Segment Type"].notna().mean() * 100,
        "Sales Zone":   rc["Sales Zone"].notna().mean() * 100,
        "Email":        rc["Email"].notna().mean() * 100,
        "Phone Number": rc["Phone Number"].notna().mean() * 100,
    }
    rep_fields = {
        "Amount":              rep["Amount"].notna().mean() * 100,
        "Invoice ID":          rep["Invoice ID"].notna().mean() * 100,
        "Payment Method":      rep["Payment Method"].notna().mean() * 100,
        "Repayment Date":      rep["Repayment Date"].notna().mean() * 100,
        "Reference Trans. ID": rep["Reference Transaction ID"].notna().mean() * 100,
        "Collection Route":    rep["Collection Route"].notna().mean() * 100,
    }

    all_vals         = list(inv_fields.values()) + list(rc_fields.values()) + list(rep_fields.values())
    avg_completeness = sum(all_vals) / len(all_vals)
    critical_fields  = sum(1 for v in all_vals if v < 50)
    good_fields      = sum(1 for v in all_vals if v >= 90)

    r1 = kpi_card("Avg Completeness", f"{avg_completeness:.1f}%",
                  "Across all key fields", "#4f46e5") + \
         kpi_card("Critical Gaps",    f"{critical_fields}",
                  "Fields below 50% complete", "#dc2626") + \
         kpi_card("High Quality",     f"{good_fields}",
                  "Fields above 90% complete", "#16a34a") + \
         kpi_card("Tables Audited",   "3",
                  "Invoice, Customer, Payment", "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    def completeness_bar(fields_dict, height=320):
        df = pd.DataFrame({"Field": list(fields_dict.keys()),
                           "Completeness": list(fields_dict.values())})
        df = df.sort_values("Completeness")
        colors = ["#dc2626" if v < 50 else "#f59e0b" if v < 80 else "#16a34a"
                  for v in df["Completeness"]]
        fig = go.Figure(go.Bar(
            x=df["Completeness"], y=df["Field"], orientation="h",
            marker_color=colors,
            text=df["Completeness"].apply(lambda x: f"{x:.0f}%"),
            textposition="inside", insidetextanchor="start",
            textfont=dict(color="white", size=10)
        ))
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=10,b=10,l=10,r=10), height=height,
                          xaxis=dict(range=[0,108], gridcolor="#f3f4f6", title="% Complete"),
                          yaxis=dict(tickfont=dict(size=11)),
                          font=dict(family="Inter, sans-serif", size=12))
        return fig

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Invoice Table — Field Completeness"), unsafe_allow_html=True)
        st.plotly_chart(completeness_bar(inv_fields, 320), use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Customer Table — Field Completeness"), unsafe_allow_html=True)
        st.plotly_chart(completeness_bar(rc_fields, 320), use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Repayment Table — Field Completeness"), unsafe_allow_html=True)
    st.plotly_chart(completeness_bar(rep_fields, 240), use_container_width=True, config=CHART_CFG)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Data Quality Summary"), unsafe_allow_html=True)
    all_rows = (
        [{"Table":"Invoice",   "Field": k, "Completeness %": round(v,1)} for k, v in inv_fields.items()] +
        [{"Table":"Customer",  "Field": k, "Completeness %": round(v,1)} for k, v in rc_fields.items()] +
        [{"Table":"Repayment", "Field": k, "Completeness %": round(v,1)} for k, v in rep_fields.items()]
    )
    dq_df = pd.DataFrame(all_rows)
    dq_df["Status"] = dq_df["Completeness %"].apply(
        lambda x: "Critical" if x < 50 else ("Warning" if x < 80 else "Good"))
    dq_df["Completeness %"] = dq_df["Completeness %"].apply(lambda x: f"{x:.1f}%")
    dq_df = dq_df.sort_values(["Table","Status"])
    dq_df.index = pd.RangeIndex(1, len(dq_df)+1)
    st.dataframe(dq_df, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — RELIABILITY
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Reliability":
    ibv_num = ibv.copy()
    ibv_num["Balance"] = pd.to_numeric(ibv_num["Balance"], errors="coerce")

    total_sku      = len(ibv_num)
    stockout_count = (ibv_num["Balance"] == 0).sum()
    in_stock_count = total_sku - stockout_count
    stockout_pct   = stockout_count / total_sku * 100 if total_sku else 0

    completed_fbc = ir_all_fbc[ir_all_fbc["Status"].isin([3, 5, 7])].shape[0]
    total_fbc     = len(ir_all_fbc)
    irf_rate      = completed_fbc / total_fbc * 100 if total_fbc else 0

    r1 = kpi_card("Stockout Rate",
                  f"{stockout_pct:.1f}%",
                  f"{stockout_count:,} of {total_sku:,} SKU locations", "#dc2626",
                  f"{stockout_pct:.0f}%", "#dc2626") + \
         kpi_card("In-Stock Rate",
                  f"{100-stockout_pct:.1f}%",
                  f"{in_stock_count:,} locations with stock", "#16a34a") + \
         kpi_card("Fulfillment Rate",
                  f"{irf_rate:.1f}%",
                  f"{completed_fbc:,}/{total_fbc:,} FBC orders fulfilled", "#4f46e5") + \
         kpi_card("Pending / In-Progress",
                  f"{ir_all_fbc[ir_all_fbc['Status'].isin([0,1,2])].shape[0]:,}",
                  "Orders not yet completed", "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    st.markdown(chart_wrap("Fulfillment Status Breakdown", "Derived from FBC order status"), unsafe_allow_html=True)
    irf_s = ir_all_fbc["Fulfillment Label"].value_counts().reset_index()
    irf_s.columns = ["Status","Count"]
    irf_colors = {"Completed":"#16a34a","Not Started":"#f59e0b","Scheduled":"#4f46e5",
                  "In Progress":"#14b8a6","Cancelled":"#dc2626","Unknown":"#9ca3af"}
    fig2 = px.pie(irf_s, names="Status", values="Count", hole=0.5,
                  color="Status", color_discrete_map=irf_colors)
    fig2.update_traces(textinfo="percent", textposition="inside",
                       insidetextorientation="horizontal",
                       textfont=dict(size=13, color="white"))
    fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                       margin=dict(t=10,b=10,l=10,r=10), height=340, showlegend=True,
                       legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11)))
    st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
    st.markdown("</div>", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — SEGMENTATION
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Segmentation":
    yr    = year_filter("yr_seg")
    inv_y = apply_year(inv_scoped, yr)

    rc_seg_info = rc[["ID","Segment Type"]].copy().rename(columns={"ID":"RC_ID"})
    seg_inv     = inv_y.merge(rc_seg_info, left_on="Customer ID", right_on="RC_ID", how="left")
    seg_inv["Segment Type"] = seg_inv["Segment Type"].fillna("Unclassified")

    by_segment = (seg_inv.groupby("Segment Type")
                         .agg(Orders=("ID","count"),
                              Sales=("Discountedvalue","sum"),
                              Customers=("Customer ID","nunique"))
                         .reset_index()
                         .sort_values("Sales", ascending=False))
    by_segment["Rev/Purchase"] = by_segment["Sales"] / by_segment["Orders"]

    seg_counts     = rc["Segment Type"].value_counts()
    total_cls      = rc["Segment Type"].notna().sum()
    classified_pct = total_cls / len(rc) * 100 if len(rc) else 0

    # MERL: SKU Breadth per agrovet/month
    inv_y_map = inv_y.set_index("ID")
    il_y = il[il["Invoice ID"].isin(set(inv_y["ID"].dropna().astype(int)))].copy()
    il_y["Customer ID"] = il_y["Invoice ID"].map(inv_y_map["Customer ID"])
    il_y["Month"]       = il_y["Invoice ID"].map(inv_y_map["Created At"].dt.to_period("M").astype(str))
    if len(il_y):
        sku_month   = il_y.groupby(["Customer ID","Month"])["Product ID"].nunique().reset_index()
        sku_breadth = sku_month.groupby("Customer ID")["Product ID"].mean().mean()
    else:
        sku_breadth = 0

    low_thresh = inv_y["Discountedvalue"].quantile(0.25) if len(inv_y) else 0
    hfso_pct   = (inv_y["Discountedvalue"] <= low_thresh).mean() * 100 if len(inv_y) else 0

    total_sales = inv_y["Discountedvalue"].sum()
    crev = inv_y.groupby("Customer ID")["Discountedvalue"].sum().sort_values(ascending=False)
    top5_pct  = crev.head(5).sum()  / total_sales * 100 if total_sales else 0
    top10_pct = crev.head(10).sum() / total_sales * 100 if total_sales else 0

    r1 = kpi_card("Classified Customers", f"{total_cls:,}",
                  f"{classified_pct:.1f}% of {len(rc):,} registered", "#4f46e5") + \
         kpi_card("SKU Breadth/Agrovet",  f"{sku_breadth:.1f}",
                  "Avg distinct SKUs per customer/month", "#14b8a6") + \
         kpi_card("Top-5 Revenue Conc.",  f"{top5_pct:.1f}%",
                  "Share from top 5 customers", "#f97316") + \
         kpi_card("High-Freq Small Orders",f"{hfso_pct:.1f}%",
                  f"Orders ≤ GHS {low_thresh:,.0f}", "#dc2626")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    seg_colors = {"Provider":"#4f46e5","Agrovet":"#14b8a6","Hatchery":"#f59e0b","Unclassified":"#9ca3af"}

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Sales by Customer Segment", "Total order value per segment"), unsafe_allow_html=True)
        fig = px.bar(by_segment, x="Segment Type", y="Sales", color="Segment Type",
                     color_discrete_map=seg_colors, text="Sales")
        fig.update_traces(texttemplate="GHS %{text:,.0f}", textposition="outside", textfont=dict(size=10))
        fig.update_layout(**white_layout(300))
        fig.update_layout(showlegend=False, xaxis=dict(tickangle=0))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Revenue per Purchase by Segment", "Avg order value per account type"), unsafe_allow_html=True)
        rpp = by_segment[by_segment["Segment Type"] != "Unclassified"].copy()
        fig2 = px.bar(rpp, x="Segment Type", y="Rev/Purchase", color="Segment Type",
                      color_discrete_map=seg_colors, text="Rev/Purchase")
        fig2.update_traces(texttemplate="GHS %{text:,.0f}", textposition="outside", textfont=dict(size=11))
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(showlegend=False, xaxis=dict(tickangle=0),
                           yaxis=dict(title="Avg Rev/Purchase (GHS)", gridcolor="#f3f4f6"))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown(chart_wrap("Revenue Concentration — Top Customers",
                               "Cumulative share of total sales"), unsafe_allow_html=True)
        crev_df = crev.reset_index()
        crev_df.columns = ["Customer ID","Sales"]
        crev_df["Cumulative %"] = crev_df["Sales"].cumsum() / total_sales * 100
        crev_df["Rank"] = range(1, len(crev_df)+1)
        fig3 = go.Figure()
        fig3.add_scatter(x=crev_df["Rank"], y=crev_df["Cumulative %"],
                         mode="lines", line=dict(color="#4f46e5", width=2.5), fill="tozeroy",
                         fillcolor="rgba(79,70,229,0.1)")
        fig3.add_hline(y=top5_pct,  line_dash="dot", line_color="#f97316",
                       annotation_text=f"Top 5: {top5_pct:.0f}%",
                       annotation_position="top left",
                       annotation_font=dict(color="#f97316", size=11))
        fig3.add_hline(y=top10_pct, line_dash="dot", line_color="#dc2626",
                       annotation_text=f"Top 10: {top10_pct:.0f}%",
                       annotation_position="bottom left",
                       annotation_font=dict(color="#dc2626", size=11))
        fig3.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=20, b=50, l=60, r=20), height=300,
                           font=dict(family="Inter, sans-serif", size=12),
                           xaxis=dict(title="Customer Rank", tickangle=0, gridcolor="#f3f4f6"),
                           yaxis=dict(title="Cumulative Revenue %", gridcolor="#f3f4f6"))
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown(chart_wrap("Order Value Distribution", "High-frequency small orders analysis"), unsafe_allow_html=True)
        fig4 = go.Figure()
        fig4.add_histogram(x=inv_y["Discountedvalue"], nbinsx=30,
                           marker_color="#4f46e5", opacity=0.8)
        fig4.add_vline(x=low_thresh, line_dash="dash", line_color="#dc2626",
                       annotation_text=f"Low-ticket<br>≤ GHS {low_thresh:,.0f}",
                       annotation_position="top left",
                       annotation_font=dict(color="#dc2626", size=10))
        fig4.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=20, b=50, l=60, r=20), height=300,
                           font=dict(family="Inter, sans-serif", size=12),
                           xaxis=dict(title="Order Value (GHS)", tickangle=0, gridcolor="#f3f4f6"),
                           yaxis=dict(title="# Orders", gridcolor="#f3f4f6"))
        st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Portfolio Segmentation Summary — MERL"), unsafe_allow_html=True)
    seg_tbl = by_segment.copy()
    seg_tbl["Sales"]        = seg_tbl["Sales"].apply(lambda x: f"GHS {x:,.0f}")
    seg_tbl["Rev/Purchase"] = seg_tbl["Rev/Purchase"].apply(lambda x: f"GHS {x:,.0f}")
    seg_tbl.columns = ["Segment","Orders","Total Sales","Customers","Rev/Purchase (AOV)"]
    seg_tbl.index = pd.RangeIndex(1, len(seg_tbl)+1)
    st.dataframe(seg_tbl, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — CAMPAIGNS
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Campaigns":
    total_campaigns     = len(camp)
    active_campaigns    = (camp["Status Label"] == "Active").sum()
    completed_campaigns = (camp["Status Label"] == "Completed").sum()

    span_days = int((camp["End Date"].max() - camp["Start Date"].min()).days) if total_campaigns else 0
    span_label = (f"{camp['Start Date'].min().strftime('%b %Y')}, "
                  f"{camp['End Date'].max().strftime('%b %Y')}") if total_campaigns else ","

    r1 = kpi_card("Total Campaigns", f"{total_campaigns:,}",
                  "All time", "#4f46e5") + \
         kpi_card("Active",          f"{active_campaigns:,}",
                  "Currently running", "#16a34a",
                  str(active_campaigns), "#16a34a") + \
         kpi_card("Completed",       f"{completed_campaigns:,}",
                  "Finished campaigns", "#14b8a6") + \
         kpi_card("Programme Span",  f"{span_days} days",
                  span_label, "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    st.markdown(chart_wrap("Campaign Timeline", "Pre-order campaign periods and status"), unsafe_allow_html=True)
    camp_colors = {"Active":"#16a34a","Completed":"#4f46e5","Cancelled":"#dc2626","Unknown":"#9ca3af"}
    fig = px.timeline(camp, x_start="Start Date", x_end="End Date", y="Name",
                      color="Status Label", color_discrete_map=camp_colors,
                      hover_data={"Status Label":True,"Start Date":True,"End Date":True,"Name":False})
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                      margin=dict(t=10,b=40,l=10,r=10), height=220,
                      xaxis=dict(gridcolor="#f3f4f6"),
                      legend=dict(orientation="h", y=-0.3, font=dict(size=11)),
                      font=dict(family="Inter, sans-serif", size=12))
    st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Campaign Details"), unsafe_allow_html=True)
    camp_show = camp[["Name","Start Date","End Date","Status Label"]].copy()
    camp_show["Duration (days)"] = (camp["End Date"] - camp["Start Date"]).dt.days
    camp_show["Start Date"] = camp_show["Start Date"].dt.strftime("%Y-%m-%d")
    camp_show["End Date"]   = camp_show["End Date"].dt.strftime("%Y-%m-%d")
    camp_show.columns = ["Campaign Name","Start Date","End Date","Status","Duration (days)"]
    camp_show.index = pd.RangeIndex(1, len(camp_show)+1)
    st.dataframe(camp_show, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Campaign Status Distribution"), unsafe_allow_html=True)
    status_dist = camp["Status Label"].value_counts().reset_index()
    status_dist.columns = ["Status","Count"]
    fig2 = px.bar(status_dist, x="Status", y="Count", color="Status",
                  color_discrete_map=camp_colors, text="Count")
    fig2.update_traces(textposition="outside", textfont=dict(size=12))
    fig2.update_layout(**white_layout(240))
    fig2.update_layout(showlegend=False, xaxis=dict(tickangle=0))
    st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
    st.markdown("</div>", unsafe_allow_html=True)
