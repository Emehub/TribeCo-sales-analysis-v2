"""
TribeCo Ghana -- Sales Ledger Dashboard
Source: Sales ledger data/Sales Ledger 2026 (1).xlsx
Run:    streamlit run dashboard/sales_ledger_app.py
"""
import os
import warnings
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="TribeCo Sales Ledger",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

LEDGER    = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Sales ledger data", "Sales Ledger 2026 (1).xlsx"
)
CHART_CFG = {"displayModeBar": False}
TODAY     = pd.Timestamp.today().normalize()

# ── CSS ──────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
section[data-testid="stSidebar"],
[data-testid="stSidebar"] {
    background-color: #14532d !important;
    padding-top: 0 !important;
    width: 210px !important;
    min-width: 210px !important;
}
[data-testid="stSidebar"] > div:first-child {
    width: 210px !important;
}
[data-testid="stSidebar"],
[data-testid="stSidebar"] * { color: #ffffff !important; }
[data-testid="stSidebar"] .stButton { margin:0 !important; padding:0 !important; }
[data-testid="stSidebar"] .stButton button {
    background:transparent !important; border:none !important;
    box-shadow:none !important; color:#ffffff !important;
    font-size:14px !important; font-weight:500 !important;
    text-align:center !important; padding:11px 16px !important;
    border-radius:8px !important; width:100% !important;
    transition:background 0.15s ease !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background:rgba(255,255,255,0.10) !important;
}
[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background:rgba(74,222,128,0.25) !important;
    border-left:3px solid #4ade80 !important;
    font-weight:700 !important;
    border-radius:0 8px 8px 0 !important;
}
.main .block-container { padding:1.5rem 2rem !important; max-width:100% !important; }
.main { background-color:#f1f5f9 !important; }
.topbar { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }
.topbar-title { font-size:22px; font-weight:800; color:#14532d; }
.badge-date { background:white; color:#374151; font-size:12px; font-weight:600;
    padding:5px 14px; border-radius:20px; border:1px solid #e5e7eb; }
.kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:16px 0; }
.kpi-card { background:white; border-radius:14px; padding:20px 22px;
    box-shadow:0 1px 4px rgba(0,0,0,0.07); border-top:4px solid #16a34a; }
.kpi-label { font-size:11px; font-weight:700; text-transform:uppercase;
    letter-spacing:0.6px; color:#6b7280; margin-bottom:2px; }
.kpi-value { font-size:30px; font-weight:800; color:#111827; margin:8px 0 6px; line-height:1; }
.kpi-sub { font-size:12px; color:#9ca3af; }
.kpi-badge { font-size:11px; font-weight:700; margin-left:6px; padding:1px 6px; border-radius:10px; }
.chart-card { background:white; border-radius:14px; padding:20px 22px;
    box-shadow:0 1px 4px rgba(0,0,0,0.07); margin-bottom:16px; }
.chart-title { font-size:15px; font-weight:700; color:#14532d; margin-bottom:2px; }
.chart-sub   { font-size:12px; color:#9ca3af; margin-bottom:12px; }
hr { border:none; border-top:1px solid #e5e7eb; margin:12px 0; }
#MainMenu { display:none !important; }
footer    { display:none !important; }
[data-testid="stHeader"] { height:0 !important; min-height:0 !important;
    padding:0 !important; overflow:visible !important; }
.stDeployButton { display:none; }
[data-testid="stAppViewContainer"] { padding-top:0 !important; }
</style>
""", unsafe_allow_html=True)


# ── Data loader ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Loading Sales Ledger data...")
def load_all():
    xl = pd.ExcelFile(LEDGER)

    orders = pd.read_excel(xl, "A-Sales Orders",
                           parse_dates=["Order Date", "Fulfillment / Pre-order Date"])
    inv    = pd.read_excel(xl, "B-Invoices",
                           parse_dates=["Invoice Date", "Due Date"])
    pay    = pd.read_excel(xl, "C-Payment Receipts",
                           parse_dates=["Payment Date", "Invoice Date"])
    cust   = pd.read_excel(xl, "Customers")
    weekly = pd.read_excel(xl, "Weekly Sales & Targets")

    # Strip column name whitespace
    for df in [orders, inv, pay, cust, weekly]:
        df.columns = [c.strip() for c in df.columns]

    # ── B-Invoices derived fields ─────────────────────────────────────────────
    inv["Repayment Status"] = "Open"
    inv.loc[inv["Balance"] <= 0,                                         "Repayment Status"] = "Paid"
    inv.loc[(inv["Balance"] > 0) & inv["Due Date"].notna() &
            (inv["Due Date"] < TODAY),                                   "Repayment Status"] = "Overdue"
    inv.loc[(inv["Balance"] > 0) & inv["Due Date"].notna() &
            (inv["Due Date"] >= TODAY) &
            (inv["Due Date"] <= TODAY + pd.Timedelta(days=14)),          "Repayment Status"] = "Due Soon"

    inv["Month"]    = inv["Invoice Date"].dt.to_period("M").astype(str)
    inv["Week"]     = inv["Invoice Date"].dt.to_period("W").astype(str)
    inv["Year"]     = inv["Invoice Date"].dt.year

    # ── A-Sales Orders derived fields ─────────────────────────────────────────
    orders["SubTotal"]   = pd.to_numeric(orders["SubTotal"],    errors="coerce").fillna(0)
    orders["Q'ty in Doses"] = pd.to_numeric(orders["Q'ty in Doses"], errors="coerce").fillna(0)
    orders["Month"]      = orders["Order Date"].dt.to_period("M").astype(str)
    orders["Week"]       = orders["Order Date"].dt.to_period("W").astype(str)

    # ── C-Payment Receipts derived fields ─────────────────────────────────────
    pay["Amount Received"] = pd.to_numeric(pay["Amount Received"], errors="coerce").fillna(0)
    pay["Month"] = pay["Payment Date"].dt.to_period("M").astype(str)

    return orders, inv, pay, cust, weekly


orders, inv, pay, cust, weekly = load_all()

all_years = sorted(inv["Year"].dropna().unique().astype(int).tolist())

GREENS = ["#14532d","#16a34a","#22c55e","#4ade80","#86efac",
          "#065f46","#059669","#34d399","#6ee7b7","#a7f3d0"]


# ── Helpers ──────────────────────────────────────────────────────────────────────
def kpi_card(label, value, subtitle, color="#16a34a", badge="", badge_color=""):
    v_str = str(value)
    if "%" not in v_str:
        v_clean = v_str.replace("GHS","").replace(",","").replace(" ","").strip()
        try:
            if float(v_clean) == 0:
                return ""
        except (ValueError, TypeError):
            pass
    badge_html = (f'<span class="kpi-badge" style="background:{badge_color}22;color:{badge_color}">'
                  f'{badge}</span>') if badge else ""
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
    return f'<div class="kpi-grid" style="grid-template-columns:repeat({min(n,max_cols)},1fr)">{html}</div>'

def chart_wrap(title, subtitle=""):
    sub = f'<div class="chart-sub">{subtitle}</div>' if subtitle else ""
    return f'<div class="chart-card"><div class="chart-title">{title}</div>{sub}'

def year_filter(key="yr"):
    opts    = ["All"] + [str(y) for y in all_years]
    default = opts.index("2026") if "2026" in opts else 0
    col, _  = st.columns([1, 5])
    with col:
        sel = st.selectbox("Year", opts, index=default, key=key)
    yr = sel if sel == "All" else int(sel)
    st.session_state["current_year"] = yr
    return yr

def filter_inv(yr):
    return inv[inv["Year"] == yr] if yr != "All" else inv

def filter_orders(yr):
    return orders[orders["Order Date"].dt.year == yr] if yr != "All" else orders

def filter_pay(yr):
    return pay[pay["Payment Date"].dt.year == yr] if yr != "All" else pay

def filter_weekly(yr):
    w = weekly.copy()
    w["Date"] = pd.to_datetime(w["Date"], errors="coerce")
    for col in ["Orders","Orders Fulfilled","Value GHS","Weekly Targets",
                "% Target Achieved","AOV","Fulfillment Rate"]:
        if col in w.columns:
            w[col] = pd.to_numeric(w[col], errors="coerce")
    w = w.dropna(subset=["Date", "Value GHS"])
    return w[w["Date"].dt.year == yr] if yr != "All" else w

def _num(val, default=0):
    try:
        v = float(val)
        return default if pd.isna(v) else v
    except (TypeError, ValueError):
        return default

def wl(h=300):
    return dict(plot_bgcolor="white", paper_bgcolor="white",
                margin=dict(t=10, b=40, l=10, r=10), height=h,
                font=dict(family="Inter, sans-serif", size=12),
                yaxis=dict(gridcolor="#f3f4f6"),
                xaxis=dict(tickangle=-35))


# ── Sidebar ──────────────────────────────────────────────────────────────────────
if "active_page" not in st.session_state:
    st.session_state["active_page"] = "Overview"

PAGES = ["Overview", "Sales Performance", "Products",
         "Customers", "Payments", "Weekly Scorecard"]

with st.sidebar:
    st.markdown("""
    <div style="padding:20px 16px 14px;border-bottom:1px solid rgba(255,255,255,0.1);margin-bottom:8px">
        <div style="font-size:18px;font-weight:800;color:white">TribeCo Sales Ledger</div>
        <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-top:3px">Ghana Operations 2026</div>
    </div>
    """, unsafe_allow_html=True)

    for p in PAGES:
        is_active = st.session_state["active_page"] == p
        if st.button(p, key=f"nav_{p}",
                     use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state["active_page"] = p
            st.rerun()

    st.markdown(
        '<div style="color:rgba(255,255,255,0.5);font-size:11px;padding:10px 16px;'
        'border-top:1px solid rgba(255,255,255,0.1);margin-top:8px">'
        '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
        'background:#4ade80;margin-right:5px;vertical-align:middle"></span>'
        'Source: Sales Ledger 2026</div>',
        unsafe_allow_html=True,
    )

page = st.session_state["active_page"]

# ── Top bar ──────────────────────────────────────────────────────────────────────
_yr   = st.session_state.get("current_year", 2026)
_inv2 = filter_inv(_yr)
_from = _inv2["Invoice Date"].min().strftime("%b %Y") if len(_inv2) else ""
_to   = _inv2["Invoice Date"].max().strftime("%b %Y") if len(_inv2) else ""
st.markdown(
    f'<div class="topbar">'
    f'<div class="topbar-title">{page}</div>'
    f'<div><span class="badge-date">{_from + " -- " + _to if _from != _to else _from}</span></div>'
    f'</div>',
    unsafe_allow_html=True,
)


# ════════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    yr    = year_filter("yr_ov")
    inv_y = filter_inv(yr)

    total_sales   = inv_y["Total"].sum()
    total_coll    = inv_y["Payment"].sum()
    outstanding   = inv_y[inv_y["Balance"] > 0]["Balance"].sum()
    coll_pct      = total_coll / total_sales * 100 if total_sales else 0
    aov           = inv_y["Total"].mean() if len(inv_y) else 0
    n_inv         = len(inv_y)
    overdue_val   = inv_y[inv_y["Repayment Status"] == "Overdue"]["Balance"].sum()
    n_cust        = inv_y["Customer Name"].nunique()
    paid_count    = (inv_y["Repayment Status"] == "Paid").sum()

    top_cr = inv_y.groupby("Customer Name")["Total"].sum().sort_values(ascending=False)
    top_name = top_cr.index[0]  if len(top_cr) else "-"
    top_val  = top_cr.iloc[0]   if len(top_cr) else 0

    row1 = (kpi_card("Total Sales",    f"GHS {total_sales:,.0f}",  f"{n_inv:,} invoices",              "#14532d") +
            kpi_card("Collected",       f"GHS {total_coll:,.0f}",   f"{coll_pct:.1f}% collection rate", "#16a34a",
                     f"{coll_pct:.0f}%","#16a34a") +
            kpi_card("Outstanding",     f"GHS {outstanding:,.0f}",  "Balance still owed",               "#dc2626") +
            kpi_card("Avg Order Value", f"GHS {aov:,.0f}",          "Per invoice",                      "#f59e0b"))
    st.markdown(kpi_grid(row1), unsafe_allow_html=True)

    row2 = (kpi_card("Ordering Customers", f"{n_cust:,}",          "Unique customers",                 "#8b5cf6") +
            kpi_card("Overdue Balance",     f"GHS {overdue_val:,.0f}", "Past due date",                "#ef4444") +
            kpi_card("Paid Invoices",       f"{paid_count:,}",      f"of {n_inv:,} invoices",          "#16a34a") +
            kpi_card("Top Customer",        top_name,               f"GHS {top_val:,.0f}",             "#14b8a6"))
    st.markdown(kpi_grid(row2), unsafe_allow_html=True)

    # ── Monthly revenue cards (one per month, up to 6) ───────────────────────────
    MONTH_NAMES = {"01":"January","02":"February","03":"March","04":"April",
                   "05":"May","06":"June","07":"July","08":"August",
                   "09":"September","10":"October","11":"November","12":"December"}
    MONTH_COLORS = ["#14532d","#16a34a","#059669","#0d9488","#065f46","#22c55e"]
    m_rev = inv_y.groupby("Month")["Total"].sum().reset_index().sort_values("Month")
    # Pad to current month so all months Jan-Jun always appear even without data yet
    _cur_mo = TODAY.to_period("M").strftime("%Y-%m")
    if len(m_rev) and m_rev["Month"].max() < _cur_mo:
        _gap = pd.period_range(m_rev["Month"].max(), _cur_mo, freq="M")[1:]
        _pad = pd.DataFrame({"Month": _gap.strftime("%Y-%m"), "Total": 0.0})
        m_rev = pd.concat([m_rev, _pad], ignore_index=True)
    m_rev["prev"] = m_rev["Total"].shift(1)
    m_rev["pct"]  = ((m_rev["Total"] - m_rev["prev"]) / m_rev["prev"] * 100).round(1)
    month_cards = ""
    for i, (_, row) in enumerate(m_rev.head(6).iterrows()):
        mo_key  = row["Month"].split("-")[1] if "-" in str(row["Month"]) else ""
        mo_name = MONTH_NAMES.get(mo_key, row["Month"])
        has_data = row["Total"] > 0
        pct_txt = (f"+{row['pct']:.0f}% vs prev month" if has_data and pd.notna(row["pct"]) and row["pct"] >= 0
                   else (f"{row['pct']:.0f}% vs prev month" if has_data and pd.notna(row["pct"])
                   else ("First month" if has_data else "In progress")))
        _color   = MONTH_COLORS[i % 6]
        _val     = f"GHS {row['Total']:,.0f}" if has_data else "In progress"
        _opacity = "" if has_data else "opacity:0.45;"
        month_cards += (
            f'<div class="kpi-card" style="border-top-color:{_color};{_opacity}">'
            f'<div class="kpi-label">{mo_name}</div>'
            f'<div class="kpi-value">{_val}</div>'
            f'<div class="kpi-sub">{pct_txt}</div>'
            f'</div>'
        )
    if month_cards:
        n_months = min(len(m_rev.head(6)), 6)
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:1px;color:#16a34a;margin:16px 0 6px">Monthly Revenue</div>',
            unsafe_allow_html=True)
        st.markdown(
            f'<div class="kpi-grid" style="grid-template-columns:repeat({n_months},1fr)">'
            f'{month_cards}</div>',
            unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(chart_wrap("Monthly Revenue Trend", "GHS invoiced by month"), unsafe_allow_html=True)
        m = inv_y.groupby("Month")["Total"].sum().reset_index()
        m["prev"] = m["Total"].shift(1)
        m["pct"]  = ((m["Total"] - m["prev"]) / m["prev"] * 100).round(1)
        fig = go.Figure()
        fig.add_bar(x=m["Month"], y=m["Total"], marker_color="#16a34a", name="Revenue",
                    text=m["Total"].apply(lambda v: f"{v/1000:.0f}k"),
                    textposition="outside", textfont_size=10)
        fig.add_scatter(x=m["Month"], y=m["Total"], mode="lines+markers",
                        line=dict(color="#f59e0b", width=2.5, dash="dot"),
                        marker=dict(size=6, color="#f59e0b"), name="Trend")
        for _, r in m.dropna(subset=["pct"]).iterrows():
            clr = "#16a34a" if r["pct"] >= 0 else "#dc2626"
            fig.add_annotation(x=r["Month"], y=r["Total"],
                               text=f"{'+' if r['pct']>=0 else ''}{r['pct']:.0f}%",
                               showarrow=False, yshift=28, font=dict(size=10, color=clr))
        fig.update_layout(**wl(300), legend=dict(orientation="h", y=-0.28))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Sales by Warehouse", "Revenue by location"), unsafe_allow_html=True)
        wh = (inv_y.groupby("Warehouse Name")["Total"].sum()
              .reset_index().sort_values("Total", ascending=False))
        fig2 = px.pie(wh, names="Warehouse Name", values="Total", hole=0.5,
                      color_discrete_sequence=GREENS)
        fig2.update_traces(textinfo="percent", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=12, color="white"))
        fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10,b=10,l=10,r=10), height=300,
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown(chart_wrap("Invoice Payment Status"), unsafe_allow_html=True)
        rs = inv_y["Repayment Status"].value_counts().reset_index()
        rs.columns = ["Status","Count"]
        clrs = {"Paid":"#16a34a","Open":"#14532d","Overdue":"#dc2626","Due Soon":"#f59e0b"}
        fig3 = px.bar(rs, x="Status", y="Count", color="Status",
                      color_discrete_map=clrs, text="Count")
        fig3.update_traces(textposition="outside", textfont_size=11)
        fig3.update_layout(**wl(240), showlegend=False, xaxis_tickangle=0)
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown(chart_wrap("Payment Mode", "How customers pay"), unsafe_allow_html=True)
        pm = inv_y["Payment Mode"].value_counts().reset_index()
        pm.columns = ["Mode","Count"]
        fig4 = px.pie(pm, names="Mode", values="Count", hole=0.5,
                      color_discrete_sequence=GREENS)
        fig4.update_traces(textinfo="percent", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=12, color="white"))
        fig4.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10,b=10,l=10,r=10), height=240,
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)))
        st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)


    # ── Monthly Revenue Breakdown table ──────────────────────────────────────────
    st.markdown(chart_wrap("Monthly Revenue Breakdown",
                           "Sales, collected and outstanding by month"), unsafe_allow_html=True)
    monthly_coll = inv_y.groupby("Month")["Payment"].sum().reset_index().rename(columns={"Payment":"Collected"})
    monthly_inv  = inv_y.groupby("Month").agg(
        Revenue  = ("Total", "sum"),
        Invoices = ("Total", "count"),
    ).reset_index()
    monthly_tbl = monthly_inv.merge(monthly_coll, on="Month", how="left").fillna(0)
    monthly_tbl["Outstanding"]  = monthly_tbl["Revenue"] - monthly_tbl["Collected"]
    monthly_tbl["Collection %"] = (monthly_tbl["Collected"] / monthly_tbl["Revenue"] * 100).round(1)
    monthly_tbl["prev"]         = monthly_tbl["Revenue"].shift(1)
    monthly_tbl["MoM Change"]   = ((monthly_tbl["Revenue"] - monthly_tbl["prev"])
                                    / monthly_tbl["prev"] * 100).round(1)
    disp = monthly_tbl.copy()
    disp["Revenue"]      = disp["Revenue"].apply(lambda v: f"GHS {v:,.0f}")
    disp["Collected"]    = disp["Collected"].apply(lambda v: f"GHS {v:,.0f}")
    disp["Outstanding"]  = disp["Outstanding"].apply(lambda v: f"GHS {v:,.0f}")
    disp["Collection %"] = disp["Collection %"].apply(lambda v: f"{v:.1f}%")
    disp["MoM Change"]   = disp["MoM Change"].apply(
        lambda v: f"+{v:.1f}%" if pd.notna(v) and v >= 0 else (f"{v:.1f}%" if pd.notna(v) else "-"))
    st.dataframe(disp[["Month","Invoices","Revenue","Collected","Outstanding","Collection %","MoM Change"]],
                 use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# SALES PERFORMANCE
# ════════════════════════════════════════════════════════════════════════════════
elif page == "Sales Performance":
    yr    = year_filter("yr_sp")
    inv_y = filter_inv(yr)

    months_avail = sorted(inv_y["Month"].dropna().unique())
    sel = st.multiselect("Filter months", months_avail,
                         default=months_avail[-6:] if len(months_avail) >= 6 else months_avail)
    inv_f = inv_y[inv_y["Month"].isin(sel)] if sel else inv_y

    r1 = (kpi_card("Total Sales",    f"GHS {inv_f['Total'].sum():,.0f}",
                   "In selected period", "#14532d") +
          kpi_card("Total Invoices",  f"{len(inv_f):,}",
                   "Invoices raised",  "#16a34a") +
          kpi_card("Avg Sale Value",  f"GHS {inv_f['Total'].mean():,.0f}" if len(inv_f) else "GHS 0",
                   "Per invoice",     "#f59e0b"))
    st.markdown(kpi_grid(r1, max_cols=3), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Monthly Sales vs Previous Month"), unsafe_allow_html=True)
        m = inv_f.groupby("Month")["Total"].sum().reset_index()
        m["Prev"]    = m["Total"].shift(1)
        m["Change%"] = ((m["Total"] - m["Prev"]) / m["Prev"] * 100).round(1)
        fig = go.Figure()
        fig.add_bar(x=m["Month"], y=m["Total"], marker_color="#16a34a",
                    text=m["Total"].apply(lambda v: f"{v/1000:.0f}k"),
                    textposition="outside", textfont_size=10)
        for _, r in m.dropna(subset=["Change%"]).iterrows():
            clr = "#16a34a" if r["Change%"] >= 0 else "#dc2626"
            fig.add_annotation(x=r["Month"], y=r["Total"],
                               text=f"{'+' if r['Change%']>=0 else ''}{r['Change%']:.0f}%",
                               showarrow=False, yshift=28, font=dict(size=10, color=clr))
        fig.update_layout(**wl(300))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Weekly Sales Trend (last 16 weeks)"), unsafe_allow_html=True)
        w = inv_f.groupby("Week")["Total"].sum().reset_index().tail(16)
        fig2 = go.Figure()
        fig2.add_bar(x=w["Week"], y=w["Total"], marker_color="#bbf7d0", name="Sales")
        fig2.add_scatter(x=w["Week"], y=w["Total"], mode="lines+markers",
                         line=dict(color="#16a34a", width=2.5),
                         marker=dict(size=5, color="#16a34a"), name="Trend")
        fig2.update_layout(**wl(300), xaxis_tickangle=-45,
                           legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Monthly Sales Summary"), unsafe_allow_html=True)
    tbl = m.copy()
    tbl["Sales"]      = tbl["Total"].apply(lambda v: f"GHS {v:,.0f}")
    tbl["MoM Change"] = tbl["Change%"].apply(
        lambda v: f"+{v:.1f}%" if pd.notna(v) and v >= 0 else (f"{v:.1f}%" if pd.notna(v) else "-"))
    st.dataframe(tbl[["Month","Sales","MoM Change"]], use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ════════════════════════════════════════════════════════════════════════════════
elif page == "Products":
    yr    = year_filter("yr_prod")
    ord_y = filter_orders(yr)

    total_rev    = ord_y["SubTotal"].sum()
    total_doses  = ord_y["Q'ty in Doses"].sum()
    total_orders = ord_y["Sales Order ID"].nunique()

    prod_rev = ord_y.groupby("Item Name")["SubTotal"].sum().sort_values(ascending=False)
    top_prod = prod_rev.index[0] if len(prod_rev) else "-"

    r1 = (kpi_card("Total Sales Revenue",  f"GHS {total_rev:,.0f}",  "All delivered orders",     "#14532d") +
          kpi_card("Total Doses Sold",      f"{total_doses:,.0f}",    "Vaccine doses distributed","#16a34a") +
          kpi_card("Total Sales Orders",    f"{total_orders:,}",      "Unique order IDs",         "#f59e0b") +
          kpi_card("Top Product",           top_prod,
                   f"GHS {prod_rev.iloc[0]:,.0f}" if len(prod_rev) else "",            "#8b5cf6"))
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Revenue by Product (Top 12)", "GHS from sales orders"), unsafe_allow_html=True)
        t12 = prod_rev.head(12).reset_index()
        t12.columns = ["Product","Revenue"]
        fig = px.bar(t12.sort_values("Revenue"), x="Revenue", y="Product",
                     orientation="h", text="Revenue",
                     color="Revenue", color_continuous_scale=["#dcfce7","#14532d"])
        fig.update_traces(texttemplate="GHS %{text:,.0f}", textposition="inside",
                          insidetextanchor="middle", textfont=dict(color="white", size=9))
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=10,b=10,l=10,r=10), height=420,
                          coloraxis_showscale=False, xaxis=dict(gridcolor="#f3f4f6"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Doses Sold by Product (Top 12)"), unsafe_allow_html=True)
        d12 = (ord_y.groupby("Item Name")["Q'ty in Doses"].sum()
               .sort_values(ascending=False).head(12).reset_index())
        d12.columns = ["Product","Doses"]
        fig2 = px.bar(d12.sort_values("Doses"), x="Doses", y="Product",
                      orientation="h", text="Doses",
                      color="Doses", color_continuous_scale=["#bbf7d0","#065f46"])
        fig2.update_traces(texttemplate="%{text:,.0f}", textposition="inside",
                           insidetextanchor="middle", textfont=dict(color="white", size=9))
        fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10,b=10,l=10,r=10), height=420,
                           coloraxis_showscale=False, xaxis=dict(gridcolor="#f3f4f6"))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown(chart_wrap("Monthly Product Revenue Trend"), unsafe_allow_html=True)
        m_ord = ord_y.groupby("Month")["SubTotal"].sum().reset_index()
        fig3 = go.Figure()
        fig3.add_bar(x=m_ord["Month"], y=m_ord["SubTotal"], marker_color="#16a34a",
                     text=m_ord["SubTotal"].apply(lambda v: f"{v/1000:.0f}k"),
                     textposition="outside", textfont_size=10)
        fig3.update_layout(**wl(260))
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown(chart_wrap("Revenue by Sales Channel"), unsafe_allow_html=True)
        if "Sales Channel" in ord_y.columns:
            sc = ord_y.groupby("Sales Channel")["SubTotal"].sum().reset_index()
            sc.columns = ["Channel","Revenue"]
            fig4 = px.pie(sc, names="Channel", values="Revenue", hole=0.5,
                          color_discrete_sequence=GREENS)
            fig4.update_traces(textinfo="percent+label", textposition="inside",
                               textfont=dict(size=12, color="white"))
            fig4.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                               margin=dict(t=10,b=10,l=10,r=10), height=260, showlegend=False)
            st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Product Performance Summary"), unsafe_allow_html=True)
    prod_tbl = (ord_y.groupby("Item Name").agg(
        Orders=("Sales Order ID","nunique"),
        Revenue=("SubTotal","sum"),
        Doses=("Q'ty in Doses","sum")
    ).sort_values("Revenue", ascending=False).reset_index())
    prod_tbl["Revenue"] = prod_tbl["Revenue"].apply(lambda v: f"GHS {v:,.0f}")
    prod_tbl["Doses"]   = prod_tbl["Doses"].apply(lambda v: f"{v:,.0f}")
    prod_tbl.columns    = ["Product","Orders","Revenue (GHS)","Doses Sold"]
    st.dataframe(prod_tbl, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# CUSTOMERS
# ════════════════════════════════════════════════════════════════════════════════
elif page == "Customers":
    yr    = year_filter("yr_cust")
    inv_y = filter_inv(yr)

    cust_rev  = inv_y.groupby("Customer Name")["Total"].sum().sort_values(ascending=False)
    n_active  = (cust["Status"].str.strip().str.lower() == "active").sum()
    n_total   = len(cust)
    n_ordering= inv_y["Customer Name"].nunique()
    top_name  = cust_rev.index[0] if len(cust_rev) else "-"
    top_val   = cust_rev.iloc[0]  if len(cust_rev) else 0

    r1 = (kpi_card("Registered Customers", f"{n_total:,}",    "In customer registry",              "#14532d") +
          kpi_card("Active Customers",      f"{n_active:,}",
                   f"{n_active/n_total*100:.0f}% of total" if n_total else "",                     "#16a34a") +
          kpi_card("Ordering Customers",    f"{n_ordering:,}", f"Placed invoices in {yr}",         "#f59e0b") +
          kpi_card("Top Customer",          top_name,          f"GHS {top_val:,.0f}",               "#8b5cf6"))
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    top10 = cust_rev.head(10).reset_index()
    top10.columns = ["Customer","Revenue"]
    top10 = top10[top10["Customer"].notna()]

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(chart_wrap("Top 10 Customers by Invoice Value"), unsafe_allow_html=True)
        fig = px.bar(top10.sort_values("Revenue"), x="Revenue", y="Customer",
                     orientation="h", text="Revenue",
                     color="Revenue", color_continuous_scale=["#dcfce7","#14532d"])
        fig.update_traces(texttemplate="GHS %{text:,.0f}", textposition="inside",
                          insidetextanchor="middle", textfont=dict(color="white", size=10))
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=10,b=10,l=10,r=10), height=380,
                          coloraxis_showscale=False, xaxis=dict(gridcolor="#f3f4f6"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Revenue by Sales Zone"), unsafe_allow_html=True)
        zone_map = cust.set_index("Customer Name")["Sales Zone"].to_dict()
        inv_z = inv_y.copy()
        inv_z["Sales Zone"] = inv_z["Customer Name"].map(zone_map).fillna("Unknown")
        zr = inv_z.groupby("Sales Zone")["Total"].sum().reset_index()
        zr.columns = ["Zone","Revenue"]
        fig2 = px.pie(zr, names="Zone", values="Revenue", hole=0.5,
                      color_discrete_sequence=GREENS)
        fig2.update_traces(textinfo="percent", textposition="inside",
                           textfont=dict(size=12, color="white"))
        fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10,b=10,l=10,r=10), height=300,
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown(chart_wrap("Monthly Active Customers"), unsafe_allow_html=True)
        mc = (inv_y.groupby("Month")["Customer Name"].nunique()
              .reset_index().rename(columns={"Customer Name":"Customers"}))
        fig3 = px.bar(mc, x="Month", y="Customers", color_discrete_sequence=["#16a34a"],
                      text="Customers")
        fig3.update_traces(textposition="outside", textfont_size=11)
        fig3.update_layout(**wl(260))
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown(chart_wrap("Revenue by Region"), unsafe_allow_html=True)
        region_map = cust.set_index("Customer Name")["Region"].to_dict()
        inv_y["Region"] = inv_y["Customer Name"].map(region_map).fillna("Unknown")
        rg = inv_y.groupby("Region")["Total"].sum().reset_index()
        rg.columns = ["Region","Revenue"]
        fig4 = px.pie(rg, names="Region", values="Revenue", hole=0.5,
                      color_discrete_sequence=GREENS)
        fig4.update_traces(textinfo="percent", textposition="inside",
                           textfont=dict(size=12, color="white"))
        fig4.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10,b=10,l=10,r=10), height=260,
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)))
        st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Customer Leaderboard"), unsafe_allow_html=True)
    lb = top10.copy()
    lb.insert(0, "Rank", range(1, len(lb)+1))
    lb["Revenue"] = lb["Revenue"].apply(lambda v: f"GHS {v:,.0f}")
    st.dataframe(lb, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# PAYMENTS
# ════════════════════════════════════════════════════════════════════════════════
elif page == "Payments":
    yr    = year_filter("yr_pay")
    inv_y = filter_inv(yr)
    pay_y = filter_pay(yr)

    collected   = inv_y["Payment"].sum()
    outstanding = inv_y[inv_y["Balance"] > 0]["Balance"].sum()
    total_inv   = inv_y["Total"].sum()
    coll_rate   = collected / total_inv * 100 if total_inv else 0
    n_receipts  = len(pay_y)
    avg_receipt = pay_y["Amount Received"].mean() if len(pay_y) else 0

    r1 = (kpi_card("Total Collected",   f"GHS {collected:,.0f}",
                   f"{coll_rate:.1f}% collection rate", "#16a34a",
                   f"{coll_rate:.0f}%","#16a34a") +
          kpi_card("Outstanding",        f"GHS {outstanding:,.0f}", "Balance not yet received", "#dc2626") +
          kpi_card("Payment Receipts",   f"{n_receipts:,}",          "Individual receipts",      "#14532d") +
          kpi_card("Avg Receipt Value",  f"GHS {avg_receipt:,.0f}",  "Per transaction",          "#f59e0b"))
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Monthly Invoiced vs Collected"), unsafe_allow_html=True)
        inv_m  = inv_y.groupby("Month")["Total"].sum().reset_index().rename(columns={"Total":"Invoiced"})
        coll_m = inv_y.groupby("Month")["Payment"].sum().reset_index().rename(columns={"Payment":"Collected"})
        cmp    = inv_m.merge(coll_m, on="Month", how="outer").fillna(0)
        fig    = go.Figure()
        fig.add_bar(x=cmp["Month"], y=cmp["Invoiced"],  name="Invoiced",  marker_color="#bbf7d0")
        fig.add_bar(x=cmp["Month"], y=cmp["Collected"], name="Collected", marker_color="#16a34a")
        fig.update_layout(**wl(300), barmode="overlay",
                          legend=dict(orientation="h", y=-0.28))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Payment Mode Distribution", "By amount received"), unsafe_allow_html=True)
        pm = (pay_y.groupby("Mode of Payment")["Amount Received"].sum()
              .reset_index().rename(columns={"Mode of Payment":"Mode","Amount Received":"Amount"}))
        fig2 = px.pie(pm, names="Mode", values="Amount", hole=0.5,
                      color_discrete_sequence=GREENS)
        fig2.update_traces(textinfo="percent", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=12, color="white"))
        fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10,b=10,l=10,r=10), height=300,
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown(chart_wrap("Payment Terms Split (Cash vs Credit)"), unsafe_allow_html=True)
        pt = inv_y.groupby("Payment Terms")["Total"].sum().reset_index()
        pt.columns = ["Terms","Total"]
        fig3 = px.pie(pt, names="Terms", values="Total", hole=0.5,
                      color_discrete_sequence=["#14532d","#4ade80","#f59e0b"])
        fig3.update_traces(textinfo="percent+label", textposition="inside",
                           textfont=dict(size=12, color="white"))
        fig3.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(t=10,b=10,l=10,r=10), height=260, showlegend=False)
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown(chart_wrap("Payment Method Summary"), unsafe_allow_html=True)
        pm_tbl = (pay_y.groupby("Mode of Payment")["Amount Received"]
                  .agg(Receipts="count", Total="sum", Average="mean").reset_index())
        pm_tbl.columns = ["Mode","Receipts","Total","Avg"]
        pm_tbl["Total"] = pm_tbl["Total"].apply(lambda v: f"GHS {v:,.0f}")
        pm_tbl["Avg"]   = pm_tbl["Avg"].apply(lambda v: f"GHS {v:,.0f}")
        st.dataframe(pm_tbl, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Recent Payment Receipts (last 30)"), unsafe_allow_html=True)
    recent = (pay_y.sort_values("Payment Date", ascending=False).head(30)
              [["Payment Date","Customer Name","Amount Received","Mode of Payment","Invoice Number"]].copy())
    recent["Amount Received"] = recent["Amount Received"].apply(lambda v: f"GHS {v:,.0f}")
    recent["Payment Date"]    = recent["Payment Date"].dt.strftime("%d %b %Y")
    st.dataframe(recent, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# WEEKLY SCORECARD
# ════════════════════════════════════════════════════════════════════════════════
elif page == "Weekly Scorecard":
    yr    = year_filter("yr_ws")
    inv_y = filter_inv(yr)
    wk    = filter_weekly(yr).dropna(subset=["Date"]).sort_values("Date")

    # Latest week KPIs
    last      = wk.iloc[-1] if len(wk) else None
    lw_orders = int(_num(last["Orders"]))           if last is not None else 0
    lw_sales  = _num(last["Value GHS"])              if last is not None else 0
    lw_target = _num(last["Weekly Targets"])         if last is not None else 0
    lw_pct    = _num(last["% Target Achieved"])      if last is not None else 0
    lw_date   = pd.to_datetime(last["Date"]).strftime("%d %b %Y") if last is not None else "-"
    lw_pct_disp = f"{lw_pct*100:.0f}%" if lw_pct <= 2 else f"{lw_pct:.0f}%"

    overdue = inv_y[inv_y["Repayment Status"] == "Overdue"]

    r1 = (kpi_card("Orders This Week",   f"{lw_orders:,}",        f"Week of {lw_date}",   "#14532d") +
          kpi_card("Sales This Week",     f"GHS {lw_sales:,.0f}",  "Invoiced value",       "#16a34a") +
          kpi_card("Weekly Target",       f"GHS {lw_target:,.0f}", "Set target",           "#f59e0b") +
          kpi_card("Target Achievement",  lw_pct_disp,             "vs weekly target",     "#8b5cf6"))
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    fr_mean   = _num(wk["Fulfillment Rate"].mean())
    fr_disp   = f"{fr_mean*100:.0f}%" if fr_mean <= 1 else f"{fr_mean:.0f}%"
    best_idx  = wk["Value GHS"].idxmax() if len(wk) else None
    best_date = wk.loc[best_idx, "Date"].strftime("%d %b") if best_idx is not None else "-"

    r2 = (kpi_card("Overdue Invoices", f"{len(overdue):,}",
                   f"GHS {overdue['Balance'].sum():,.0f} outstanding", "#ef4444") +
          kpi_card("Fulfillment Rate",  fr_disp,
                   "Avg across all weeks", "#16a34a") +
          kpi_card("Best Week Sales",
                   f"GHS {_num(wk['Value GHS'].max()):,.0f}", best_date, "#14532d") +
          kpi_card("Avg Weekly Sales",
                   f"GHS {_num(wk['Value GHS'].mean()):,.0f}",
                   f"Over {len(wk)} weeks", "#f59e0b"))
    st.markdown(kpi_grid(r2), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(chart_wrap("Weekly Sales vs Target"), unsafe_allow_html=True)
        wk_plot = wk.copy()
        wk_plot["Label"] = wk_plot["Date"].dt.strftime("%d %b")
        fig = go.Figure()
        fig.add_bar(x=wk_plot["Label"], y=wk_plot["Value GHS"],
                    marker_color="#16a34a", name="Actual Sales")
        fig.add_scatter(x=wk_plot["Label"], y=wk_plot["Weekly Targets"],
                        mode="lines+markers",
                        line=dict(color="#f59e0b", width=2.5, dash="dash"),
                        marker=dict(size=6, color="#f59e0b"), name="Target")
        fig.update_layout(**wl(300), legend=dict(orientation="h", y=-0.28))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(chart_wrap("Week-over-Week Sales Change (last 10 weeks)"), unsafe_allow_html=True)
        wk2 = wk.copy()
        wk2["Prev"]  = wk2["Value GHS"].shift(1)
        wk2["Chg%"]  = ((wk2["Value GHS"] - wk2["Prev"]) / wk2["Prev"] * 100).round(1)
        wk2 = wk2.dropna(subset=["Chg%"]).tail(10)
        colors = ["#16a34a" if v >= 0 else "#dc2626" for v in wk2["Chg%"]]
        fig2 = go.Figure()
        fig2.add_bar(x=wk2["Date"].dt.strftime("%d %b"), y=wk2["Chg%"],
                     marker_color=colors,
                     text=wk2["Chg%"].apply(lambda v: f"{'+' if v>=0 else ''}{v:.0f}%"),
                     textposition="outside", textfont_size=10)
        fig2.update_layout(**wl(300))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(chart_wrap("Weekly Breakdown Table"), unsafe_allow_html=True)
    wk_tbl = wk.sort_values("Date", ascending=False).copy()
    wk_tbl["Date"]           = wk_tbl["Date"].dt.strftime("%d %b %Y")
    wk_tbl["Value GHS"]      = wk_tbl["Value GHS"].apply(lambda v: f"GHS {v:,.0f}")
    wk_tbl["Weekly Targets"] = wk_tbl["Weekly Targets"].apply(
        lambda v: f"GHS {v:,.0f}" if pd.notna(v) else "-")
    wk_tbl["% Target Achieved"] = wk_tbl["% Target Achieved"].apply(
        lambda v: (f"{v*100:.0f}%" if v <= 2 else f"{v:.0f}%") if pd.notna(v) else "-")
    keep = ["Date","Week Number","Orders","Orders Fulfilled",
            "Value GHS","Weekly Targets","% Target Achieved","AOV"]
    keep = [c for c in keep if c in wk_tbl.columns]
    st.dataframe(wk_tbl[keep], use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if len(overdue) > 0:
        st.markdown(chart_wrap("Overdue Invoices", "Invoices past due date with outstanding balance"),
                    unsafe_allow_html=True)
        ov = overdue[["Invoice Date","Customer Name","Total","Balance","Due Date"]].copy()
        ov = ov.sort_values("Due Date")
        ov["Invoice Date"] = ov["Invoice Date"].dt.strftime("%d %b %Y")
        ov["Due Date"]     = pd.to_datetime(ov["Due Date"]).dt.strftime("%d %b %Y")
        ov["Total"]        = ov["Total"].apply(lambda v: f"GHS {v:,.0f}")
        ov["Balance"]      = ov["Balance"].apply(lambda v: f"GHS {v:,.0f}")
        st.dataframe(ov, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
