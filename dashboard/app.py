"""
CowTribe Sales Dashboard
Run: python -m streamlit run d:/company-dashboard-v2/dashboard/app.py
"""
import os
import io
import time
import base64
import requests
import streamlit as st
from string import Template
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import warnings
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # sibling modules, however the app is launched
import credit_collections_report as ccr
import quarterly_review as qrv
import qr_charts as qrc
import qr_word as qrw
import qr_pptx as qrp
import q_brief as qbf
import admin_store
import admin_page
import product_report as prr
import stock_report as stk
import advanced_page as aap
from types import SimpleNamespace
warnings.filterwarnings("ignore")
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from fpdf import FPDF as _FPDF
    _PDF_AVAIL = True
except ImportError:
    _PDF_AVAIL = False

st.set_page_config(
    page_title="CowTribe Sales Dashboard",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={},
)

DATA      = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CHART_CFG = {"displayModeBar": False}


# ── Sign-in and roles ────────────────────────────────────────────────────────────
# Google sign-in (st.login) is used once an [auth] section exists in the secrets. Until then the
# dashboard works as before, but nobody gets the Admin role -- except on a developer machine whose
# local secrets set [access] dev_admin = true. [access] require_login = true refuses to run without
# [auth], so a misconfigured deployment can never fall back to an open dashboard.
def _secrets_dict():
    return {k: (dict(v) if hasattr(v, "keys") else v) for k, v in st.secrets.items()}


@st.cache_resource
def _open_store(code_version):
    return admin_store.open_store(_secrets_dict(), os.path.join(DATA, "admin_store.local.json"))


def _get_store():
    # Keyed on admin_store.py's timestamp so a redeploy never reuses a store object built by older code.
    return _open_store(os.path.getmtime(admin_store.__file__))


@st.cache_data(ttl=60, show_spinner=False)
def _role_for(email, admins):
    return _get_store().role_for(email, admins)


_ACCESS = dict(st.secrets.get("access", {}))
_BOOT_ADMINS = tuple(a.strip().lower() for a in _ACCESS.get("admins", []))
_AUTH_ON = "auth" in st.secrets

if _AUTH_ON:
    if not getattr(st.user, "is_logged_in", False):
        st.markdown("<div style='max-width:420px;margin:12vh auto 0;text-align:center'>"
                    "<div style='font-size:28px;font-weight:800;color:#024b30'>TribeCo Ghana Dashboard</div>"
                    "<div style='color:#6b7280;margin:8px 0 24px'>Sign in with your Cowtribe Google account.</div>"
                    "</div>", unsafe_allow_html=True)
        _c = st.columns([1, 1, 1])[1]
        if _c.button("Sign in with Google", type="primary", use_container_width=True):
            st.login()
        st.stop()
    USER_EMAIL = (getattr(st.user, "email", "") or "").lower()
    USER_ROLE = _role_for(USER_EMAIL, _BOOT_ADMINS)
    if USER_ROLE is None:
        st.error(f"{USER_EMAIL} does not have access to this dashboard yet. Ask an admin to add you.")
        if st.button("Sign out"):
            st.logout()
        st.stop()
elif _ACCESS.get("require_login"):
    st.error("Sign-in is required but Google sign-in ([auth]) is not configured in the app secrets.")
    st.stop()
else:
    USER_EMAIL = _ACCESS.get("dev_user", "")
    USER_ROLE = "Admin" if _ACCESS.get("dev_admin") else "Viewer"
IS_ADMIN = USER_ROLE == "Admin"

# DSO settings, shared by the Weekly Info and YTD Review pages.
# DSO = Outstanding AR ÷ sales in the trailing DSO_WINDOW_DAYS × DSO_WINDOW_DAYS,
# benchmarked against the standard customer payment term (DSO_TERMS_DAYS).
DSO_WINDOW_DAYS = 28
DSO_TERMS_DAYS  = 28   # standard payment term (Metabase invoices still record 30 in Customerpaymentterms)

# ── Device preview switcher ───────────────────────────────────────────────────────
# Streamlit has no client-side way to fake a viewport width, so "previewing" a device
# means rendering the app a second time inside an iframe of that exact pixel width —
# the iframe gets its own real viewport, so our @media breakpoints fire for real.
# `dashboard_frame=1` marks that nested render so it doesn't draw another switcher/iframe.
_IS_PREVIEW_FRAME = st.query_params.get("dashboard_frame") == "1"

# ── Metabase connection & data pipeline (shared with the scheduled email job) ───
import data_layer as dl

# ── Brand & Theme ────────────────────────────────────────────────────────────────
# Colors sampled directly from the TribeCo logo (dashboard/assets/tribeco_logo.png)
BRAND_GREEN_DEEP  = "#024b30"   # exact logo background
BRAND_GREEN       = "#1f7a4d"   # usable mid-green — primary brand accent (replaces old indigo)
BRAND_GREEN_LIGHT = "#3fa873"   # lighter tint
BRAND_GOLD        = "#c9975a"   # sampled from the logo's tree icon
BRAND_GOLD_LIGHT  = "#e0b980"

if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False
THEME = "dark" if st.session_state["dark_mode"] else "light"

_THEME_TOKENS = {
    "light": dict(
        page_grad="linear-gradient(160deg, #f4f8f5 0%, #eef5f0 50%, #f8f4ec 100%)",
        card_bg="rgba(255,255,255,0.86)",
        card_border="rgba(2,75,48,0.09)",
        card_shadow="0 1px 2px rgba(2,75,48,0.05), 0 6px 20px rgba(2,75,48,0.07)",
        kpi_shadow="0 1px 2px rgba(2,75,48,0.05), 0 6px 20px rgba(2,75,48,0.07)",
        kpi_shadow_hover="0 2px 6px rgba(2,75,48,0.08), 0 14px 32px rgba(2,75,48,0.13)",
        text_heading="#0d3b25",
        text_body="#374151",
        text_muted="#6b7280",
        sidebar_bg="linear-gradient(180deg, #035a39 0%, #024b30 55%, #013a25 100%)",
        sidebar_border="rgba(255,255,255,0.14)",
        hr_color="rgba(2,75,48,0.15)",
        badge_bg="#ffffff",
        badge_border="rgba(2,75,48,0.15)",
        dl_bg="rgba(255,255,255,0.55)",
        dl_border="rgba(2,75,48,0.25)",
        dl_text="#0d3b25",
        widget_bg="#ffffff",
        widget_text="#111827",
        collapsed_bg="rgba(255,255,255,0.6)",
        collapsed_fill="#0d3b25",
        color_scheme="light",
        input_border="rgba(2,75,48,0.16)",
        card_bg_solid="#ffffff",
        tab_bg="rgba(255,255,255,0.6)",
        tab_active_bg="#ffffff",
    ),
    "dark": dict(
        page_grad="linear-gradient(135deg, #050f0a 0%, #0a1f14 45%, #17130a 100%)",
        card_bg="rgba(16,36,27,0.82)",
        card_border="rgba(255,255,255,0.08)",
        card_shadow="0 8px 32px rgba(0,0,0,0.45)",
        kpi_shadow="0 1px 2px rgba(0,0,0,0.35), 0 12px 30px rgba(0,0,0,0.55)",
        kpi_shadow_hover="0 4px 10px rgba(0,0,0,0.45), 0 20px 44px rgba(0,0,0,0.65)",
        text_heading="#eef6f0",
        text_body="#d7ded9",
        text_muted="#9fb0a6",
        sidebar_bg="linear-gradient(180deg, #08170f 0%, #050f0a 100%)",
        sidebar_border="rgba(255,255,255,0.08)",
        hr_color="rgba(255,255,255,0.12)",
        badge_bg="rgba(255,255,255,0.06)",
        badge_border="rgba(255,255,255,0.12)",
        dl_bg="rgba(255,255,255,0.06)",
        dl_border="rgba(255,255,255,0.18)",
        dl_text="#eef6f0",
        widget_bg="rgba(255,255,255,0.08)",
        widget_text="#eef6f0",
        collapsed_bg="rgba(255,255,255,0.12)",
        collapsed_fill="#eef6f0",
        color_scheme="dark",
        input_border="rgba(255,255,255,0.14)",
        card_bg_solid="#0f231a",
        tab_bg="rgba(255,255,255,0.04)",
        tab_active_bg="rgba(255,255,255,0.10)",
    ),
}
_T = dict(_THEME_TOKENS[THEME], brand_green=BRAND_GREEN, brand_green_deep=BRAND_GREEN_DEEP,
          brand_green_light=BRAND_GREEN_LIGHT, brand_gold=BRAND_GOLD, brand_gold_light=BRAND_GOLD_LIGHT)

# Shared Plotly canvas tokens — charts render on a transparent glass card, so
# text/gridlines must flip with THEME even for charts that build their own layout dict.
CHART_FONT = _T["text_body"]
CHART_GRID = "rgba(255,255,255,0.12)" if THEME == "dark" else "rgba(2,75,48,0.10)"

# One Plotly look for every chart: charts only override what they need, so anything they
# leave unset (font, palette, hover box, gridlines, legend) now comes out the same everywhere.
import plotly.io as pio
CHART_COLORWAY = [BRAND_GREEN, BRAND_GOLD, "#14b8a6", "#6366f1", "#f97316", "#0ea5e9", "#a855f7", "#84cc16"]
pio.templates["tribeco"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, Segoe UI, sans-serif", size=12, color=CHART_FONT),
    colorway=CHART_COLORWAY,
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=16, b=40, l=12, r=12),
    hoverlabel=dict(font=dict(family="Inter, Segoe UI, sans-serif", size=12,
                              color="#ffffff" if THEME == "light" else "#0d3b25"),
                    bgcolor="#0d3b25" if THEME == "light" else "#eef6f0", bordercolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor=CHART_GRID, zeroline=False, linecolor=CHART_GRID, automargin=True),
    yaxis=dict(gridcolor=CHART_GRID, zeroline=False, linecolor=CHART_GRID, automargin=True),
    legend=dict(font=dict(size=11.5), bgcolor="rgba(0,0,0,0)"),
    bargap=0.28,
))
pio.templates.default = "plotly_white+tribeco"

# ── Global CSS (theme-aware: liquid glass + responsive + brand colors) ───────────
_CSS_TEMPLATE = Template("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ════════════════════════════════════════════════════════════════════════════
   Spacing scale: 4 · 8 · 12 · 16 · 24 · 32. Every gap below uses one of these.
   ════════════════════════════════════════════════════════════════════════════ */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
.stMarkdown, button, input, textarea, select {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif !important;
}
/* Material Symbols must keep their own font, or icons render as words */
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }

/* ── Page backdrop ── */
[data-testid="stAppViewContainer"] {
    background: $page_grad !important;
    background-attachment: fixed !important;
}
[data-testid="stHeader"] { background: transparent !important; }
.main, [data-testid="stMain"] { background: transparent !important; }

/* ── Main layout ── */
.main .block-container, [data-testid="stMainBlockContainer"] {
    padding: 32px 32px 48px !important;
    max-width: 1480px !important;
}
[data-testid="stMain"] [data-testid="stVerticalBlock"] { gap: 16px; }
[data-testid="stMain"] [data-testid="stHorizontalBlock"] { gap: 16px; }
/* Streamlit pulls every markdown block up by 16px (to cancel paragraph margins). Our HTML
   blocks have no paragraph margin, so that pull made KPI rows and labels collide. */
[data-testid="stMarkdownContainer"]:has(> div, > span) { margin-bottom: 0 !important; }
/* helpers that return "" (e.g. an all-zero KPI row) must not leave a 16px hole */
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"]:empty) { display: none; }

/* ════════════════════════════ Sidebar ════════════════════════════ */
[data-testid="stSidebar"] {
    background: $sidebar_bg !important;
    border-right: 1px solid $sidebar_border !important;
    width: 248px !important; min-width: 248px !important; max-width: 248px !important;
}
[data-testid="stSidebar"] > div:first-child { width: 248px !important; }
[data-testid="stSidebarContent"] { padding: 0 12px 16px !important; }
[data-testid="stSidebarHeader"] { height: 40px !important; min-height: 0 !important; padding: 8px 4px 0 !important; margin: 0 !important; }
[data-testid="stSidebarUserContent"] { padding: 0 !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 2px !important; }
[data-testid="stSidebar"], [data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] div, [data-testid="stSidebar"] label { color: #ffffff; }

.brand {
    display: flex; align-items: center; gap: 12px;
    padding: 0 8px 16px; margin-bottom: 4px;
    border-bottom: 1px solid rgba(255,255,255,0.12);
}
.brand-logo { width: 38px; height: 42px; border-radius: 8px; flex-shrink: 0; }
.brand-name { font-size: 16px; font-weight: 800; letter-spacing: -0.2px; line-height: 1.2; color: #fff; }
.brand-sub  { font-size: 11.5px; font-weight: 500; color: rgba(255,255,255,0.68) !important; line-height: 1.3; }

.nav-group {
    font-size: 10.5px; font-weight: 700; letter-spacing: 0.9px; text-transform: uppercase;
    color: rgba(255,255,255,0.50) !important;
    padding: 20px 10px 8px;
}
.nav-sep { border-top: 1px solid rgba(255,255,255,0.12); margin: 16px 0 12px; }
.nav-user { font-size: 11.5px; line-height: 1.5; color: rgba(255,255,255,0.75) !important; padding: 8px 10px; }
.nav-status { font-size: 11px; color: rgba(255,255,255,0.6) !important; padding: 8px 10px 2px; display: flex; align-items: center; gap: 8px; }
.nav-status-note { font-size: 10.5px; padding-top: 0; }
.nav-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

[data-testid="stSidebar"] .stButton { margin: 0 !important; }
[data-testid="stSidebar"] .stButton button {
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: rgba(255,255,255,0.86) !important;
    justify-content: flex-start !important; text-align: left !important;
    min-height: 36px !important; height: 36px; padding: 0 10px !important;
    border-radius: 8px !important; width: 100% !important;
    transition: background 0.15s ease, color 0.15s ease !important;
}
[data-testid="stSidebar"] .stButton button > div { justify-content: flex-start !important; gap: 10px; width: 100%; }
[data-testid="stSidebar"] .stButton button p {
    font-size: 13.5px !important; font-weight: 500 !important;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
[data-testid="stSidebar"] .stButton button [data-testid="stIconMaterial"] {
    font-size: 19px !important; color: rgba(255,255,255,0.62) !important;
}
[data-testid="stSidebar"] .stButton button:hover { background: rgba(255,255,255,0.08) !important; color: #fff !important; }
[data-testid="stSidebar"] .stButton button:focus:not(:focus-visible) { box-shadow: none !important; }
[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background: rgba(255,255,255,0.14) !important;
    box-shadow: inset 3px 0 0 $brand_gold !important;
    color: #fff !important;
}
[data-testid="stSidebar"] .stButton button[kind="primary"] p { font-weight: 650 !important; }
[data-testid="stSidebar"] .stButton button[kind="primary"] [data-testid="stIconMaterial"] { color: $brand_gold_light !important; }
[data-testid="stSidebar"] [data-testid="stCheckbox"] { padding: 4px 10px; }
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p { color: rgba(255,255,255,0.86) !important; font-size: 13px !important; }
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] span { color: rgba(255,255,255,0.7) !important; }

/* Sidebar expand control (when collapsed) */
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {
    background-color: $collapsed_bg !important; border-radius: 8px !important;
}

/* ════════════════════════════ Top bar ════════════════════════════ */
.topbar { padding: 0 0 4px; }
.topbar-crumb {
    font-size: 11px; font-weight: 700; letter-spacing: 0.9px; text-transform: uppercase;
    color: $brand_green_light; margin-bottom: 4px;
}
.topbar-title { font-size: 28px; font-weight: 800; letter-spacing: -0.5px; line-height: 1.15; color: $text_heading; }
.topbar-desc  { font-size: 13.5px; color: $text_muted; margin-top: 6px; }
.topbar-right { display: flex; justify-content: flex-end; }
.badge-date {
    display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
    background: $badge_bg; color: $text_body; font-size: 12.5px; font-weight: 600;
    padding: 7px 14px; border-radius: 999px; border: 1px solid $badge_border;
}
.st-key-device_preview [data-testid="stButtonGroup"] { display: flex; justify-content: flex-end; }
.device-frame-wrap { display: flex; justify-content: center; padding: 8px 0 32px; }
.device-frame { border: 3px solid #a8d9bf; border-radius: 30px; box-shadow: 0 24px 60px rgba(0,0,0,0.25); overflow: hidden; line-height: 0; }
.device-frame iframe { border: none; display: block; }

/* ════════════════════════════ Section labels ════════════════════════════ */
.section-label {
    display: flex; align-items: center; gap: 12px;
    font-size: 11.5px; font-weight: 700; letter-spacing: 0.9px; text-transform: uppercase;
    color: $brand_green_light; margin: 8px 0 -6px;
}
.section-label::after { content: ""; flex: 1; height: 1px; background: $hr_color; }

/* ════════════════════════════ Cards ════════════════════════════ */
/* card_open() containers: one surface, one padding, one radius everywhere */
[class*="st-key-card_"] {
    background: $card_bg;
    border: 1px solid $card_border;
    border-radius: 14px;
    box-shadow: $card_shadow;
    padding: 20px 22px !important;
    gap: 12px !important;
}
[class*="st-key-card_"] [class*="st-key-card_"] { box-shadow: none; padding: 16px !important; }
.card-head { margin-bottom: 0; }
.chart-title { font-size: 15px; font-weight: 700; color: $text_heading; letter-spacing: -0.1px; }
.chart-sub   { font-size: 12.5px; color: $text_muted; margin-top: 2px; }

/* ════════════════════════════ KPI cards ════════════════════════════ */
.kpi-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 16px; margin: 0;
}
.kpi-card {
    position: relative; overflow: hidden;
    background: $card_bg; border: 1px solid $card_border; border-radius: 14px;
    padding: 18px 20px 18px 22px; box-shadow: $kpi_shadow;
    container-type: inline-size;
    transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.kpi-card::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
    background: var(--accent, $brand_green);
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: $kpi_shadow_hover; }
@media (prefers-reduced-motion: reduce) { .kpi-card { transition: none; } .kpi-card:hover { transform: none; } }
.kpi-label {
    display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: $text_muted;
}
.kpi-badge { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px; letter-spacing: 0; margin-left: 0; }
.kpi-value {
    font-size: clamp(16px, 8.5cqi, 28px); font-weight: 800; letter-spacing: -0.4px;
    color: $text_heading; margin: 10px 0 4px; line-height: 1.15; white-space: nowrap;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 12.5px; color: $text_muted; }

/* ════════════════════════════ Insight cards (Advanced Analytics) ════════════════════════════ */
.insight-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.insight {
    background: $card_bg; border: 1px solid $card_border; border-radius: 14px; padding: 16px 18px;
    box-shadow: $card_shadow; display: flex; gap: 12px; align-items: flex-start;
}
.insight-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.insight-title { font-size: 13.5px; font-weight: 700; color: $text_heading; margin-bottom: 4px; }
.insight-text { font-size: 13px; line-height: 1.55; color: $text_body; }
.method-note { font-size: 12px; color: $text_muted; line-height: 1.6; }
.method-note b { color: $text_body; }

hr { border: none; border-top: 1px solid $hr_color; margin: 12px 0; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }

/* ════════════════════════════ Buttons & downloads ════════════════════════════ */
[data-testid="stMain"] .stButton button, [data-testid="stDownloadButton"] button {
    border-radius: 10px !important; min-height: 38px;
}
[data-testid="stMain"] .stButton button p, [data-testid="stDownloadButton"] button p { font-weight: 600 !important; font-size: 13px !important; }
[data-testid="stDownloadButton"] button {
    background: $dl_bg !important; border: 1px solid $dl_border !important; color: $dl_text !important;
    padding: 6px 16px !important; width: auto !important; box-shadow: none !important;
    transition: background 0.15s ease, color 0.15s ease !important;
}
[data-testid="stDownloadButton"] button:hover { background: $brand_green !important; border-color: $brand_green !important; color: #fff !important; }
[data-testid="stDownloadButton"] button:hover p { color: #fff !important; }

/* ════════════════════════════ Inputs ════════════════════════════ */
[data-testid="stMain"] [data-testid="stWidgetLabel"] p { font-size: 12.5px !important; font-weight: 600 !important; color: $text_body !important; }
[data-testid="stMultiSelect"] > div > div, [data-testid="stSelectbox"] > div > div,
[data-testid="stDateInput"] > div > div, [data-testid="stTextInput"] > div > div, [data-testid="stNumberInput"] > div > div {
    background: $widget_bg !important; color: $widget_text !important;
    border-color: $input_border !important; border-radius: 10px !important;
}
div[data-baseweb="popover"] li, div[data-baseweb="popover"] div { color: $widget_text !important; }
div[data-baseweb="popover"] ul { background: $card_bg_solid !important; }
div[data-baseweb="popover"][data-testid="stPopoverBody"] { color: #111827 !important; }
div[data-baseweb="popover"][data-testid="stPopoverBody"] * { color: #111827 !important; background: transparent !important; }
[data-baseweb="tag"] { background: $brand_green !important; color: #fff !important; border-color: $brand_green !important; border-radius: 6px !important; }
[data-testid="stCheckbox"] [role="switch"] { background: $brand_green !important; }
[data-testid="stMain"] [data-testid="stButtonGroup"] button { border-color: $input_border !important; background: $widget_bg; }
[data-testid="stMain"] [data-testid="stButtonGroup"] button p { color: $text_body !important; font-size: 13px !important; font-weight: 600 !important; }
[data-testid="stMain"] [data-testid="stButtonGroup"] button[kind*="Active"] { background: $brand_green !important; border-color: $brand_green !important; }
[data-testid="stMain"] [data-testid="stButtonGroup"] button[kind*="Active"] p { color: #fff !important; }

/* ════════════════════════════ Tabs ════════════════════════════ */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 4px; background: $tab_bg; padding: 4px; border-radius: 12px; border: 1px solid $card_border;
    width: fit-content; max-width: 100%; overflow-x: auto;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    height: 36px; padding: 0 16px; border-radius: 9px; color: $text_body !important; background: transparent;
}
[data-testid="stTabs"] [data-baseweb="tab"] p { font-size: 13px; font-weight: 600; }
[data-testid="stTabs"] [aria-selected="true"] { background: $tab_active_bg !important; color: $brand_green !important; box-shadow: 0 1px 3px rgba(0,0,0,0.10); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }
[data-testid="stTabs"] [data-baseweb="tab-panel"] { padding-top: 16px; }

/* ════════════════════════════ Tables, expanders, alerts ════════════════════════════ */
[data-testid="stDataFrame"] { color-scheme: $color_scheme; border-radius: 10px; overflow: hidden; border: 1px solid $card_border; }
[data-testid="stExpander"] details {
    background: $card_bg !important; border: 1px solid $card_border !important; border-radius: 12px !important;
}
[data-testid="stExpander"] summary p { font-weight: 600; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] p { color: $text_body !important; }
[data-testid="stAlert"] { border-radius: 12px; }

/* ════════════════════════════ Responsive ════════════════════════════ */
@media (max-width: 1024px) {
    .main .block-container, [data-testid="stMainBlockContainer"] { padding: 24px 16px 40px !important; }
    .topbar-title { font-size: 22px; }
    [class*="st-key-card_"] { padding: 16px !important; }
}
@media (max-width: 640px) {
    .kpi-grid, .insight-grid { grid-template-columns: 1fr !important; }
    .topbar-title { font-size: 20px; }
    .topbar-right { justify-content: flex-start; }
    .chart-title { font-size: 14px; }
}
</style>
""")
st.markdown(_CSS_TEMPLATE.substitute(**_T), unsafe_allow_html=True)


# ── Shared data-processing pipeline (dashboard/data_layer.py) ───────────────────
_process_raw = dl.process_raw


# ── Data loader ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Fetching live data from Metabase...")
def load_all():
    # Live Metabase fetch, falling back to the last saved CSVs if Metabase is unreachable.
    return dl.load(dict(st.secrets["metabase"]), DATA)


@st.cache_data(ttl=300, show_spinner="Fetching product and stock data from Metabase...")
def load_products():
    return dl.load_products(dict(st.secrets["metabase"]), DATA)


# ── Historical Sales Ledger loader (2023-2025 Excel files) ───────────────────────
_HIST_BASE  = os.path.join(os.path.dirname(DATA), "3 years data")
_HIST_FILES = {
    2023: "Sales Ledger 2023.xlsx",
    2024: "Sales Ledger 2024.xlsx",
    2025: "Sales Ledger 2025 (1).xlsx",
}

@st.cache_data(ttl=3600, show_spinner="Loading historical sales ledger...")
def load_hist_data():
    so_list, inv_list, pay_list = [], [], []
    for yr, fname in _HIST_FILES.items():
        path = os.path.join(_HIST_BASE, fname)
        if not os.path.exists(path):
            continue
        xl = pd.ExcelFile(path)

        # ── Sales Orders ──────────────────────────────────────────────────────────
        so = xl.parse("A-Sales Orders")
        so = so.dropna(subset=["Sales Order ID"])
        so["Year"]          = yr
        so["Order Date"]    = pd.to_datetime(so["Order Date"], errors="coerce")
        so["Invoice Total"] = pd.to_numeric(so["Invoice Total"], errors="coerce").fillna(0)
        so["SubTotal"]      = pd.to_numeric(so["SubTotal"],      errors="coerce").fillna(0)
        # Normalise region column (column name differs by year)
        if "Region" not in so.columns and "Sales Location" in so.columns:
            so["Region"] = so["Sales Location"]
        if "Region" not in so.columns and "Sales Location " in so.columns:
            so["Region"] = so["Sales Location "]
        if "Region" not in so.columns and "Region / Location" in so.columns:
            so["Region"] = so["Region / Location"]
        so["Month"]         = so["Order Date"].dt.to_period("M").astype(str)
        so_list.append(so)

        # ── Invoices ──────────────────────────────────────────────────────────────
        inv = xl.parse("B-Invoices")
        inv = inv.dropna(subset=["Invoice Number"])
        inv["Year"]         = yr
        inv["Invoice Date"] = pd.to_datetime(inv.get("Invoice Date"), errors="coerce")
        inv["Total"]        = pd.to_numeric(inv["Total"],   errors="coerce").fillna(0)
        inv["Payment"]      = pd.to_numeric(inv["Payment"], errors="coerce").fillna(0)
        inv["Balance"]      = pd.to_numeric(inv["Balance"], errors="coerce").fillna(0)
        inv_list.append(inv)

        # ── Payments ─────────────────────────────────────────────────────────────
        pay = xl.parse("C-Payment Receipts")
        date_col = "Date" if "Date" in pay.columns else "Payment Date"
        pay = pay.rename(columns={date_col: "Payment Date",
                                  "Mode": "Mode of Payment"})
        pay = pay.dropna(subset=["Payment Date"])
        pay["Year"]            = yr
        pay["Payment Date"]    = pd.to_datetime(pay["Payment Date"], errors="coerce")
        pay["Amount Received"] = pd.to_numeric(pay["Amount Received"], errors="coerce").fillna(0)
        if "Mode of Payment " in pay.columns:
            pay = pay.rename(columns={"Mode of Payment ": "Mode of Payment"})
        pay_list.append(pay)

    so_all  = pd.concat(so_list,  ignore_index=True) if so_list  else pd.DataFrame()
    inv_all = pd.concat(inv_list, ignore_index=True) if inv_list else pd.DataFrame()
    pay_all = pd.concat(pay_list, ignore_index=True) if pay_list else pd.DataFrame()
    return so_all, inv_all, pay_all


(pay, inv, rep, rc, prod, il, ir, prod_rev, rc_names, ibv, camp, irf,
 inv_scoped, rep_scoped, ir_all_fbc, _fetch_ts, _fetch_live, _fetch_error) = load_all()

# Store fetch metadata in session_state so sidebar fragment can read it
st.session_state["_fetch_ts"]    = _fetch_ts
st.session_state["_fetch_live"]  = _fetch_live
st.session_state["_fetch_error"] = _fetch_error

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
    <div class="kpi-card" style="--accent:{color}">
        <div class="kpi-label">{label}{badge_html}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{subtitle}</div>
    </div>"""

def kpi_grid(html, max_cols=4):
    """max_cols is kept for call-site compatibility but no longer forces a fixed column
    count — the .kpi-grid CSS class handles responsive reflow via auto-fit/minmax."""
    if 'class="kpi-card"' not in html:
        return ""
    return f'<div class="kpi-grid">{html}</div>'

def chart_wrap(title, subtitle=""):
    """Card header HTML only. Use card_open()/card_close() to put widgets inside a card."""
    sub = f'<div class="chart-sub">{subtitle}</div>' if subtitle else ""
    return f'<div class="chart-title">{title}</div>{sub}'

# Streamlit renders every st.markdown call in its own element, so an HTML "<div class=card>"
# opened in one call can never wrap the charts and widgets that follow -- it closes itself
# straight away and leaves an empty box with the content spilling out underneath. A real
# st.container does wrap them, so cards are containers styled by their key (.st-key-card_N).
# card_open/card_close are the bracketing pair; they must sit in the same block, like a `with`.
_CARD_STACK = []
_CARD_SEQ = [0]

def card_open(title="", subtitle=""):
    _CARD_SEQ[0] += 1
    box = st.container(key=f"card_{_CARD_SEQ[0]}")
    box.__enter__()
    _CARD_STACK.append(box)
    if title or subtitle:
        st.markdown(f'<div class="card-head">{chart_wrap(title, subtitle)}</div>', unsafe_allow_html=True)
    return box

def card_close():
    if _CARD_STACK:
        _CARD_STACK.pop().__exit__(None, None, None)

def section_label(text):
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)

def year_filter(key="year", inline=False):
    """inline=True draws just the selectbox, for pages that place it inside their own filter row."""
    options = ["All"] + [str(y) for y in all_years]
    default_idx = options.index("2026") if "2026" in options else 0
    if inline:
        selected = st.selectbox("Year", options, index=default_idx, key=key)
    else:
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

def week_label(w):
    """'YYYY-MM-DD/YYYY-MM-DD' week period -> 'Week N' (ISO week number). Concise, no dates."""
    try:
        return f"Week {pd.Period(w, freq='W').start_time.isocalendar()[1]}"
    except Exception:
        return w

def month_label(m):
    """'YYYY-MM' -> short month name, e.g. 'Jan'. Concise, no year/date."""
    try:
        return pd.Period(m, freq="M").strftime("%b")
    except Exception:
        return m

# Rounded, bevelled bar styling -- a Plotly-native "dimensional" finish (rounded data-ends
# plus a light top edge) that reads as premium without the value-distortion of true 3D bars.
def bar_marker(color, line_color="rgba(255,255,255,0.55)"):
    return dict(color=color, cornerradius=6, line=dict(color=line_color, width=1))

def white_layout(height=300):
    """Transparent chart canvas so the glass card shows through; text/gridlines adapt to THEME."""
    return dict(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=10, b=40, l=10, r=10), height=height,
                font=dict(family="Inter, sans-serif", size=12, color=CHART_FONT),
                yaxis=dict(gridcolor=CHART_GRID, gridwidth=1),
                xaxis=dict(tickangle=-35))

def make_excel(sheets: dict) -> bytes:
    """Build a multi-sheet Excel file in memory and return bytes for download."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df = df.copy()
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.tz_localize(None) if df[col].dt.tz is None else df[col].dt.tz_convert(None)
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return buf.getvalue()

def dl_button(sheets: dict, filename: str, label: str = "Download Report"):
    data = make_excel(sheets)
    st.download_button(
        label=f"⬇ {label}",
        data=data,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def dl_row(excel_sheets, excel_file, pdf_bytes, pdf_file, label="Report"):
    """Renders Excel + PDF download buttons side by side."""
    c1, c2, _ = st.columns([1, 1, 5])
    with c1:
        st.download_button(
            f"⬇ Excel",
            data=make_excel(excel_sheets),
            file_name=excel_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with c2:
        if pdf_bytes:
            st.download_button(
                f"⬇ PDF",
                data=pdf_bytes,
                file_name=pdf_file,
                mime="application/pdf",
            )


# ── PDF chart helpers (matplotlib → PNG bytes) ───────────────────────────────────
if _PDF_AVAIL:
    def _bar_png(x, y, title="", color=BRAND_GREEN, xlabel="", ylabel="", label_fmt="{:,.0f}",
                figw=8.5, figh=3.0):
        fig, ax = plt.subplots(figsize=(figw, figh))
        bars = ax.bar(list(x), list(y), color=color, alpha=0.88, zorder=3)
        ax.bar_label(bars, labels=[label_fmt.format(v) for v in y], fontsize=6.5, padding=2, color='#374151')
        if title:
            ax.set_title(title, fontsize=11, fontweight='bold', color='#14532d', pad=6)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=8, color='#6b7280')
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=8, color='#6b7280')
        ax.tick_params(axis='x', rotation=30, labelsize=7)
        ax.tick_params(axis='y', labelsize=7)
        ax.yaxis.grid(True, alpha=0.3, zorder=0)
        ax.set_axisbelow(True)
        ax.margins(y=0.15)
        for sp in ['top','right']:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return buf.getvalue()

    def _hbar_png(x, y, title="", color=BRAND_GREEN, xlabel="", ylabel="", label_fmt="{:,.0f}",
                 figw=8.5, figh=3.2):
        fig, ax = plt.subplots(figsize=(figw, figh))
        bars = ax.barh(list(y), list(x), color=color, alpha=0.88, zorder=3)
        ax.bar_label(bars, labels=[label_fmt.format(v) for v in x], fontsize=6.5, padding=2, color='#374151')
        if title:
            ax.set_title(title, fontsize=11, fontweight='bold', color='#14532d', pad=6)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=8, color='#6b7280')
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=8, color='#6b7280')
        ax.tick_params(axis='y', labelsize=7)
        ax.tick_params(axis='x', labelsize=7)
        ax.xaxis.grid(True, alpha=0.3, zorder=0)
        ax.set_axisbelow(True)
        ax.margins(x=0.15)
        for sp in ['top','right']:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return buf.getvalue()

    def _grouped_bar_png(df, x_col, bars, title="", colors=None, xlabel="", ylabel="",
                         label_fmt="{:,.0f}", figw=8.5, figh=3.0):
        _dc = [BRAND_GREEN_DEEP,'#16a34a','#f59e0b','#dc2626']
        x   = range(len(df))
        w   = 0.8 / len(bars)
        fig, ax = plt.subplots(figsize=(figw, figh))
        for i, (col, lbl) in enumerate(bars):
            offset = (i - len(bars)/2 + 0.5) * w
            b = ax.bar([xi + offset for xi in x], df[col], w, label=lbl,
                      color=(colors[i] if colors else _dc[i % 4]), alpha=0.88, zorder=3)
            ax.bar_label(b, labels=[label_fmt.format(v) for v in df[col]], fontsize=5.5, padding=1,
                        rotation=90, color='#374151')
        ax.set_xticks(list(x))
        ax.set_xticklabels(df[x_col].tolist(), rotation=30, ha='right', fontsize=7)
        if title:
            ax.set_title(title, fontsize=11, fontweight='bold', color='#14532d', pad=6)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=8, color='#6b7280')
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=8, color='#6b7280')
        ax.tick_params(axis='y', labelsize=7)
        ax.yaxis.grid(True, alpha=0.3, zorder=0)
        ax.set_axisbelow(True)
        ax.margins(y=0.2)
        ax.legend(fontsize=7, framealpha=0.7)
        for sp in ['top','right']:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return buf.getvalue()

    def _stacked_bar_png(df, x_col, stack_col, val_col, title="", color_map=None, figw=8.5, figh=3.0):
        pivot = df.pivot_table(index=x_col, columns=stack_col, values=val_col, aggfunc='sum').fillna(0)
        fig, ax = plt.subplots(figsize=(figw, figh))
        _cols = [color_map.get(c, '#9ca3af') for c in pivot.columns] if color_map else None
        pivot.plot(kind='bar', stacked=True, ax=ax, color=_cols, alpha=0.88, zorder=3)
        if title:
            ax.set_title(title, fontsize=11, fontweight='bold', color='#14532d', pad=6)
        ax.tick_params(axis='x', rotation=30, labelsize=7)
        ax.tick_params(axis='y', labelsize=7)
        ax.yaxis.grid(True, alpha=0.3, zorder=0)
        ax.set_axisbelow(True)
        ax.legend(loc='upper right', fontsize=7, framealpha=0.7)
        for sp in ['top','right']:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return buf.getvalue()

    def _pie_png(labels, values, colors=None, title="", figw=6.0, figh=4.2):
        fig, ax = plt.subplots(figsize=(figw, figh))
        _cols = colors or ['#024b30', '#1f7a4d', '#3fa873', '#c9975a', '#e0b980', '#8a9d5e', '#c7d2c2']
        wedges, _, autotexts = ax.pie(
            values, colors=_cols[:len(values)], autopct='%1.0f%%', pctdistance=0.78,
            wedgeprops=dict(width=0.45, edgecolor='white', linewidth=1.5),
            textprops=dict(fontsize=8, color='white', fontweight='bold'))
        if title:
            ax.set_title(title, fontsize=11, fontweight='bold', color='#14532d', pad=6)
        ax.legend(wedges, labels, loc='center left', bbox_to_anchor=(1.0, 0.5), fontsize=7, framealpha=0.7)
        plt.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return buf.getvalue()

    def _bar_with_threshold_png(x, y, threshold, threshold_label="", title="", colors=None,
                                xlabel="", ylabel="", label_fmt="{:,.0f}", figw=8.5, figh=3.0):
        fig, ax = plt.subplots(figsize=(figw, figh))
        _colors = colors if colors is not None else ['#1f7a4d'] * len(list(x))
        bars = ax.bar(list(x), list(y), color=_colors, alpha=0.9, zorder=3)
        ax.bar_label(bars, labels=[label_fmt.format(v) for v in y], fontsize=6.5, padding=2, color='#374151')
        ax.axhline(threshold, color='#c9975a', linestyle=':', linewidth=1.6, zorder=4)
        if threshold_label:
            ax.text(-0.4, threshold, threshold_label, fontsize=7,
                   color='#c9975a', va='bottom', ha='left', fontweight='bold')
        if title:
            ax.set_title(title, fontsize=11, fontweight='bold', color='#14532d', pad=6)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=8, color='#6b7280')
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=8, color='#6b7280')
        ax.tick_params(axis='x', rotation=30, labelsize=7)
        ax.tick_params(axis='y', labelsize=7)
        ax.yaxis.grid(True, alpha=0.3, zorder=0)
        ax.set_axisbelow(True)
        ax.margins(y=0.18)
        for sp in ['top', 'right']:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return buf.getvalue()

    class TribePDF(_FPDF):
        _BRAND = (20, 83, 45)
        _WHITE = (255, 255, 255)
        _DARK  = (17, 24, 39)
        _GRAY  = (107, 114, 128)
        _LGRAY = (243, 244, 246)
        _PALETTE = [
            (79,70,229),(22,163,74),(220,38,38),(245,158,11),
            (139,92,246),(20,184,166),(249,115,22),(59,130,246),
        ]

        def __init__(self):
            super().__init__(orientation='P', unit='mm', format='A4')
            self.set_auto_page_break(auto=True, margin=15)
            self.set_margins(10, 10, 10)

        def add_header(self, title, subtitle="", year=""):
            self.set_fill_color(*self._BRAND)
            self.rect(0, 0, 210, 20, 'F')
            self.set_font('Helvetica', 'B', 13)
            self.set_text_color(*self._WHITE)
            self.set_xy(10, 6)
            self.cell(130, 8, 'TribeCo Ghana Dashboard', ln=False)
            self.set_font('Helvetica', '', 8)
            self.set_xy(10, 14)
            self.cell(190, 5, f'Generated: {pd.Timestamp.today().strftime("%d %b %Y")}',
                      align='R', ln=False)
            self.set_xy(10, 25)
            self.set_font('Helvetica', 'B', 18)
            self.set_text_color(*self._BRAND)
            yr_sfx = f' - {year}' if year and str(year) != 'All' else ''
            self.cell(0, 10, f'{title}{yr_sfx}', ln=True)
            if subtitle:
                self.set_font('Helvetica', '', 9)
                self.set_text_color(*self._GRAY)
                self.cell(0, 5, subtitle, ln=True)
            self.ln(2)
            self.set_text_color(0, 0, 0)

        def add_kpi_row(self, kpis):
            if not kpis:
                return
            n    = min(len(kpis), 4)
            box_w = (190 - (n - 1) * 4) / n
            x0   = 10
            y0   = self.get_y()
            for i, (lbl, val) in enumerate(kpis[:n]):
                x = x0 + i * (box_w + 4)
                self.set_fill_color(*self._PALETTE[i % len(self._PALETTE)])
                self.rect(x, y0, box_w, 18, 'F')
                self.set_text_color(*self._WHITE)
                self.set_font('Helvetica', '', 7)
                self.set_xy(x + 2, y0 + 3)
                self.cell(box_w - 4, 4, str(lbl)[:28], ln=True)
                self.set_font('Helvetica', 'B', 10)
                self.set_xy(x + 2, y0 + 8)
                self.cell(box_w - 4, 7, str(val)[:20])
            self.set_y(y0 + 22)
            self.set_text_color(0, 0, 0)

        def add_chart(self, img_bytes, title="", w=190):
            if title:
                self.set_font('Helvetica', 'B', 10)
                self.set_text_color(*self._BRAND)
                self.cell(0, 6, title, ln=True)
                self.ln(1)
            if self.get_y() > 240:
                self.add_page()
            self.image(io.BytesIO(img_bytes), x=10, w=w)
            self.ln(3)
            self.set_text_color(0, 0, 0)

        def add_table(self, df, title="", max_rows=50):
            if title:
                self.set_font('Helvetica', 'B', 10)
                self.set_text_color(*self._BRAND)
                self.cell(0, 6, title, ln=True)
                self.ln(1)
            df   = df.head(max_rows).reset_index(drop=True)
            cols = list(df.columns)
            cw   = 190 / len(cols)

            def _draw_header():
                self.set_fill_color(*self._BRAND)
                self.set_text_color(*self._WHITE)
                self.set_font('Helvetica', 'B', 7)
                for c in cols:
                    self.cell(cw, 6, str(c)[:22], border=0, fill=True)
                self.ln()

            _draw_header()
            self.set_font('Helvetica', '', 7)
            for ri, (_, row) in enumerate(df.iterrows()):
                if self.get_y() > 275:
                    self.add_page()
                    _draw_header()
                    self.set_font('Helvetica', '', 7)
                fc = self._LGRAY if ri % 2 == 0 else self._WHITE
                self.set_fill_color(*fc)
                self.set_text_color(*self._DARK)
                for c in cols:
                    self.cell(cw, 5, str(row[c])[:22], border=0, fill=True)
                self.ln()
            self.set_text_color(0, 0, 0)
            self.ln(4)

    class YTDReportPDF(_FPDF):
        """Narrative report style (cover page, callout boxes, section structure) --
        distinct from TribePDF's compact per-page KPI/chart/table export."""
        _BRAND = (2, 75, 48)
        _ACCENT = (31, 122, 77)
        _GOLD  = (201, 151, 90)
        _RED   = (185, 28, 28)
        _AMBER = (191, 105, 8)
        _BLACK = (17, 24, 39)
        _WHITE = (255, 255, 255)
        _LIGHT = (241, 247, 244)

        def __init__(self):
            super().__init__(orientation='P', unit='mm', format='A4')
            self.set_auto_page_break(auto=True, margin=18)
            self.set_margins(10, 16, 10)

        @staticmethod
        def _clean(text):
            return (str(text)
                .replace("—", "--").replace("–", "-")
                .replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("·", "*").replace("•", "-").replace("…", "...")
                .replace("÷", "/").replace("×", "x"))

        def header(self):
            if self.page_no() == 1:
                return
            self.set_fill_color(*self._BRAND)
            self.rect(0, 0, 210, 14, "F")
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*self._WHITE)
            self.set_xy(10, 3)
            self.cell(0, 8, self._clean(f"TribeCo Ghana  |  YTD Commercial Review  |  {self.report_month_label} Close"))
            self.ln(12)

        def footer(self):
            pass  # no footer bar -- only section headings carry the brand green

        def title_block(self, as_of_label):
            """Compact title banner at the top of the first content page -- no
            separate cover page, no full-page gap before the report actually starts."""
            self.set_fill_color(*self._BRAND)
            self.rect(0, 0, 210, 40, "F")
            self.set_font("Helvetica", "B", 19)
            self.set_text_color(*self._WHITE)
            self.set_xy(10, 7)
            self.cell(190, 9, "Ghana Commercial Performance", align="C")
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(*self._GOLD)
            self.set_xy(10, 18)
            self.cell(190, 8, self._clean(f"Year-to-Date Review -- {self.report_month_label} Close"), align="C")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*self._WHITE)
            self.set_xy(10, 28)
            self.cell(190, 6, self._clean(f"Covering January - {self.report_month_label} (data as of {as_of_label})"), align="C")
            self.set_text_color(0, 0, 0)
            self.set_y(48)

        def section_title(self, text):
            self.set_fill_color(*self._ACCENT)
            self.set_text_color(*self._WHITE)
            self.set_font("Helvetica", "B", 11)
            self.set_x(10)
            if self.get_y() > self.page_break_trigger - 30:   # never strand a heading at a page foot
                self.add_page()
            self.cell(190, 8, self._clean(f"  {text}"), fill=True, new_x="LMARGIN", new_y="NEXT")
            self.ln(2)

        def sub_title(self, text):
            self.set_text_color(*self._BRAND)
            self.set_font("Helvetica", "B", 10)
            self.set_x(10)
            self.cell(190, 6, self._clean(text), new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*self._GOLD)
            self.set_line_width(0.5)
            self.line(10, self.get_y(), 75, self.get_y())
            self.ln(3)

        def body(self, text):
            self.set_text_color(*self._BLACK)
            self.set_font("Helvetica", "", 9.5)
            self.set_x(14)
            self.multi_cell(183, 5.5, self._clean(text))
            self.ln(2)

        def callout(self, label, text, color=None):
            color = color or self._GOLD
            est_lines = max(1, -(-len(self._clean(text)) // 95))
            est_height = 5.5 + est_lines * 5 + 3
            if self.get_y() + est_height > self.page_break_trigger:
                self.add_page()
            self.set_fill_color(*self._LIGHT)
            self.set_x(14)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*color)
            self.cell(183, 5.5, self._clean(label), fill=True, new_x="LMARGIN", new_y="NEXT")
            self.set_x(14)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*self._BLACK)
            self.multi_cell(183, 5, self._clean(text), fill=True)
            self.ln(1.5)

        def chart(self, img_bytes, w=183):
            if self.get_y() > 230:
                self.add_page()
            self.set_x(14)
            self.image(io.BytesIO(img_bytes), x=14, w=w)
            self.ln(3)

        def table(self, headers, rows, widths):
            def _draw_header():
                self.set_fill_color(*self._BRAND)
                self.set_text_color(*self._WHITE)
                self.set_font("Helvetica", "B", 8.5)
                self.set_x(14)
                for h, w in zip(headers, widths):
                    self.cell(w, 6.5, self._clean(f" {h}"), fill=True)
                self.ln()

            _draw_header()
            self.set_font("Helvetica", "", 8.5)
            for i, row in enumerate(rows):
                # Leave room for at least this row plus the header it would need on a
                # fresh page, so a table never strands its column headers on the page
                # before its data.
                if self.get_y() > self.page_break_trigger - 6:
                    self.add_page()
                    _draw_header()
                    self.set_font("Helvetica", "", 8.5)
                self.set_x(14)
                if i % 2 == 0:
                    self.set_fill_color(*self._LIGHT)
                else:
                    self.set_fill_color(255, 255, 255)
                self.set_text_color(*self._BLACK)
                for val, w in zip(row, widths):
                    self.cell(w, 6, self._clean(f" {val}"), fill=True, border="B")
                self.ln()
            self.ln(2)


# ── Sidebar ──────────────────────────────────────────────────────────────────────
# ── Sidebar nav state ────────────────────────────────────────────────────────────
if "active_page" not in st.session_state:
    st.session_state["active_page"] = "Overview"

# Grouped by what the page is for, so the menu reads top-down from summary to detail.
NAV_GROUPS = {
    "Dashboards":  ["Overview", "Advanced Analytics", "Sales Performance"],
    "Leadership":  ["Weekly Info", "YTD Review", "Quarterly Review", "Credit & Collections"],
    "Commercial":  ["Products", "Customers", "Payments", "Segmentation", "Campaigns"],
    "Operations":  ["Weekly Scorecard", "Reconciliation", "Data Quality", "Reliability"],
    "Archive":     ["Historical Analysis", "Data Export"],
}
if IS_ADMIN:
    NAV_GROUPS["Settings"] = ["Admin"]
if st.session_state.get("active_page") == "Admin" and not IS_ADMIN:
    st.session_state["active_page"] = "Overview"

# One icon family (Material Symbols, rendered by Streamlit) so every menu row lines up.
NAV_ICONS = {
    "Overview":             ":material/space_dashboard:",
    "Advanced Analytics":   ":material/insights:",
    "Sales Performance":    ":material/trending_up:",
    "Weekly Info":          ":material/explore:",
    "YTD Review":           ":material/calendar_month:",
    "Quarterly Review":     ":material/flag:",
    "Credit & Collections": ":material/receipt_long:",
    "Products":             ":material/inventory_2:",
    "Customers":            ":material/groups:",
    "Payments":             ":material/payments:",
    "Segmentation":         ":material/donut_large:",
    "Campaigns":            ":material/campaign:",
    "Weekly Scorecard":     ":material/fact_check:",
    "Reconciliation":       ":material/balance:",
    "Data Quality":         ":material/rule:",
    "Reliability":          ":material/verified:",
    "Historical Analysis":  ":material/history:",
    "Data Export":          ":material/download:",
    "Admin":                ":material/admin_panel_settings:",
}
PAGE_GROUP = {p: g for g, items in NAV_GROUPS.items() for p in items}
if st.session_state["active_page"] not in PAGE_GROUP:
    st.session_state["active_page"] = "Overview"

with st.sidebar:
    _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "tribeco_logo.png")
    _logo_b64  = ""
    if os.path.exists(_logo_path):
        with open(_logo_path, "rb") as _f:
            _logo_b64 = base64.b64encode(_f.read()).decode()
    _logo_img = (f'<img class="brand-logo" src="data:image/png;base64,{_logo_b64}" alt="" />') if _logo_b64 else ""
    st.markdown(f"""
    <div class="brand">
        {_logo_img}
        <div>
            <div class="brand-name">TribeCo</div>
            <div class="brand-sub">Ghana Data Analysis</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    for _group, _items in NAV_GROUPS.items():
        st.markdown(f'<div class="nav-group">{_group}</div>', unsafe_allow_html=True)
        for item in _items:
            is_active = st.session_state["active_page"] == item
            if st.button(item, key=f"nav_{item}", use_container_width=True,
                         type="primary" if is_active else "secondary", icon=NAV_ICONS.get(item)):
                st.session_state["active_page"] = item
                st.rerun()

    st.markdown('<div class="nav-sep"></div>', unsafe_allow_html=True)
    st.toggle("Dark mode", key="dark_mode")
    if USER_EMAIL:
        st.markdown(f'<div class="nav-user">Signed in as <b>{USER_EMAIL}</b><br>Role: {USER_ROLE}</div>',
                    unsafe_allow_html=True)
        if _AUTH_ON and st.button("Sign out", key="nav_signout", use_container_width=True,
                                  icon=":material/logout:"):
            st.logout()

    # ── Auto-refresh: re-fetches data from Metabase every 5 minutes ─────────────
    @st.fragment(run_every=300)
    def _auto_refresh():
        ts    = st.session_state.get("_fetch_ts", "")
        live  = st.session_state.get("_fetch_live", False)
        err   = st.session_state.get("_fetch_error", "")
        dot_color = "#4ade80" if live else "#f59e0b"
        source    = "Metabase" if live else "cached CSV"
        label     = f"Live · {source} · {ts}" if ts else "Live · auto-refresh on"
        st.markdown(
            f'<div class="nav-status"><span class="nav-dot" style="background:{dot_color}"></span>'
            f'{label}</div>',
            unsafe_allow_html=True,
        )
        if err:
            import html as _html
            st.markdown(
                f'<div class="nav-status nav-status-note" title="{_html.escape(err)}">'
                f'Live connection unavailable &mdash; showing the last cached data pull.</div>',
                unsafe_allow_html=True,
            )
        # This fragment body also runs on every ordinary rerun (widget clicks, page nav,
        # etc.), not just its own run_every timer — a boolean "did I just trigger this"
        # flag can't tell those apart. Gate on real elapsed wall-clock time instead, so
        # routine interactions never get treated as a refresh tick.
        now  = time.time()
        last = st.session_state.get("_last_refresh_at")
        if last is None:
            st.session_state["_last_refresh_at"] = now
            return
        if now - last < 290:
            return
        st.session_state["_last_refresh_at"] = now
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
    _date_range = _from if _from == _to else f"{_from} – {_to}"
else:
    _date_range = str(_yr)

# ── Top bar ──────────────────────────────────────────────────────────────────────
PAGE_DESC = {
    "Overview":             "Headline sales, collections and partner KPIs for the selected period.",
    "Advanced Analytics":   "Forecast, customer segments, churn risk, cohorts, concentration and growth drivers.",
    "Sales Performance":    "Sales by month, week, channel and city against targets.",
    "Weekly Info":          "The weekly leadership pack: sales, collections and DSO for one week.",
    "YTD Review":           "Year-to-date performance against plan.",
    "Quarterly Review":     "Quarter results with exportable Word and PowerPoint packs.",
    "Credit & Collections": "Receivables, ageing and collection efficiency.",
    "Products":             "Product sales, margin, stock cover and slow movers.",
    "Customers":            "Who is buying, how often and how much.",
    "Payments":             "Payment volumes, methods and success rates.",
    "Segmentation":         "Partner portfolio segments and their performance.",
    "Campaigns":            "Pre-order campaign results.",
    "Weekly Scorecard":     "Week-by-week operating scorecard.",
    "Reconciliation":       "Orders matched to payments, and the gaps.",
    "Data Quality":         "Missing and inconsistent records to fix at source.",
    "Reliability":          "Inventory request fulfilment reliability.",
    "Historical Analysis":  "2023–2025 sales ledgers.",
    "Data Export":          "Download the underlying tables.",
    "Admin":                "Users, roles and scheduled reports.",
}
_tb_l, _tb_r = st.columns([5, 4], vertical_alignment="center")
with _tb_l:
    st.markdown(f"""
    <div class="topbar">
        <div class="topbar-crumb">{PAGE_GROUP.get(page, "")}</div>
        <div class="topbar-title">{page}</div>
        <div class="topbar-desc">{PAGE_DESC.get(page, "")}</div>
    </div>
    """, unsafe_allow_html=True)
with _tb_r:
    _tb_badge, _tb_dev = st.columns([4, 5], vertical_alignment="center")
    with _tb_badge:
        st.markdown(f'<div class="topbar-right"><span class="badge-date">{_date_range}</span></div>',
                    unsafe_allow_html=True)
    with _tb_dev:
        _device = None
        if not _IS_PREVIEW_FRAME:
            _device = st.segmented_control(
                "Preview as", ["Desktop", "Tablet", "Mobile"],
                default="Desktop", key="device_preview", label_visibility="collapsed",
            )

# Device preview: Streamlit cannot fake a viewport width, so the app is rendered a second
# time inside an iframe of that exact width (dashboard_frame=1 marks the nested render).
if _device and _device != "Desktop":
    _dp_w, _dp_h = {"Tablet": (820, 1180), "Mobile": (390, 844)}[_device]
    st.markdown(f"""
    <div class="device-frame-wrap">
      <div class="device-frame">
        <iframe src="?dashboard_frame=1&embed=true" width="{_dp_w}" height="{_dp_h}"></iframe>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    # ── Filter bar ──────────────────────────────────────────────────────────────
    card_open("Filters", "Refine every KPI, chart and table below")
    _ov_f0, _ov_f1, _ov_f2, _ov_f3 = st.columns([1, 2, 2, 2])
    with _ov_f0:
        yr = year_filter("yr_overview", inline=True)
    inv_y = apply_year(inv_scoped, yr)
    rep_y = apply_year(rep_scoped, yr)
    with _ov_f1:
        _ov_months = sorted(inv_y["Month"].dropna().unique())
        _ov_sel_months = st.multiselect("Month", _ov_months, default=[], key="ov_f_month",
                                         placeholder="All months")
    with _ov_f2:
        _ov_cust_map  = rc_names.set_index("ID")["Name"] if "Name" in rc_names.columns else pd.Series(dtype=str)
        _ov_cust_opts = sorted(inv_y["Customer ID"].map(_ov_cust_map).dropna().unique())
        _ov_sel_custs = st.multiselect("Customer", _ov_cust_opts, default=[], key="ov_f_cust",
                                        placeholder="All customers")
    with _ov_f3:
        _ov_city_opts = sorted(c for c in inv_y["Customer City"].dropna().unique() if c)
        _ov_sel_cities = st.multiselect("City / Region", _ov_city_opts, default=[], key="ov_f_city",
                                         placeholder="All cities")
    card_close()

    if _ov_sel_months:
        inv_y = inv_y[inv_y["Month"].isin(_ov_sel_months)]
    if _ov_sel_custs:
        _ov_sel_cust_ids = set(rc_names[rc_names["Name"].isin(_ov_sel_custs)]["ID"])
        inv_y = inv_y[inv_y["Customer ID"].isin(_ov_sel_cust_ids)]
    if _ov_sel_cities:
        inv_y = inv_y[inv_y["Customer City"].isin(_ov_sel_cities)]
    rep_y = rep_y[rep_y["Invoice ID"].isin(set(inv_y["ID"].dropna().astype(int)))]

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
    row1 = kpi_card("Total Sales",    f"GHS {total_revenue:,.2f}",   f"{total_orders:,} orders",            BRAND_GREEN) + \
           kpi_card("Collected",      f"GHS {total_repaid:,.2f}",    f"{collection_pct:.1f}% collection rate","#16a34a",
                    f"{collection_pct:.1f}%","#16a34a") + \
           kpi_card("Outstanding",    f"GHS {outstanding_val:,.2f}", f"{outstanding_pct:.1f}% outstanding",  "#dc2626",
                    f"{outstanding_pct:.1f}%","#dc2626") + \
           kpi_card("Basket Size (AOV)",f"GHS {avg_order_value:,.2f}","Avg order value",                    "#f59e0b")
    st.markdown(kpi_grid(row1), unsafe_allow_html=True)

    # Row 2 — MERL KPIs
    section_label("MERL Performance Indicators")
    row2 = kpi_card("New Partners Signed", f"{new_signed:,}",
                    "Agrovets/Providers registered", BRAND_GREEN) + \
           kpi_card("Activation Rate (90d)", f"{activation_rate:.1f}%",
                    f"{activated_90d} of {new_signed} placed first order", "#14b8a6",
                    f"{activation_rate:.0f}%","#14b8a6") + \
           kpi_card("Repeat Rate (30d)", f"{repeat_rate:.1f}%",
                    f"{repeat_custs} of {active_custs} customers reordered", "#16a34a",
                    f"{repeat_rate:.0f}%","#16a34a") + \
           kpi_card("Reconciliation Rate", f"{recon_rate:.1f}%",
                    "Orders matched to payments", BRAND_GREEN,
                    f"{recon_rate:.0f}%",BRAND_GREEN)
    st.markdown(kpi_grid(row2), unsafe_allow_html=True)

    row3 = kpi_card("Top-5 Revenue Conc.", f"{rev_top5:.1f}%",
                    f"GHS {rev_top5/100*total_invoiced:,.2f} from top 5", "#f97316") + \
           kpi_card("Top-10 Revenue Conc.", f"{rev_top10:.1f}%",
                    f"GHS {rev_top10/100*total_invoiced:,.2f} from top 10","#dc2626") + \
           kpi_card("Active Customers",    f"{active_customers}",
                    f"of {total_customers} registered", "#3b82f6",
                    f"{active_pct:.0f}%","#3b82f6") + \
           kpi_card("High-Freq Small Orders", f"{hfso_rate:.1f}%",
                    f"Orders ≤ GHS {low_thresh:,.2f}", "#9ca3af")
    st.markdown(kpi_grid(row3), unsafe_allow_html=True)

    # ── Monthly revenue scorecard ─────────────────────────────────────────────────
    _MO_ABBR   = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                  "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}
    _MONTH_COLORS = [BRAND_GREEN_DEEP, BRAND_GREEN, BRAND_GREEN_LIGHT, "#8a9d5e", BRAND_GOLD, BRAND_GOLD_LIGHT]
    _m_rev = inv_y.groupby("Month")["Discountedvalue"].sum().reset_index().sort_values("Month")
    _m_rev["prev"] = _m_rev["Discountedvalue"].shift(1)
    _m_rev["pct"]  = ((_m_rev["Discountedvalue"] - _m_rev["prev"]) / _m_rev["prev"] * 100).round(1)
    _older_html = ""
    _recent_html = ""
    _m_rev_list = list(_m_rev.iterrows())
    for _i, (_, _r) in enumerate(_m_rev_list):
        _parts = str(_r["Month"]).split("-")
        _yr_lbl = _parts[0] if len(_parts) == 2 else ""
        _mo_lbl = _MO_ABBR.get(_parts[1], _parts[1]) if len(_parts) == 2 else _r["Month"]
        _label  = f"{_mo_lbl} {_yr_lbl}"
        _sub    = (f"+{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) and _r["pct"] >= 0
                   else (f"{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) else "First month"))
        _card = kpi_card(_label, f"GHS {_r['Discountedvalue']:,.2f}", _sub, _MONTH_COLORS[_i % 6])
        if _i >= len(_m_rev_list) - 2:
            _recent_html += _card
        else:
            _older_html += _card
    if _recent_html or _older_html:
        section_label("Monthly Revenue")
        if _recent_html:
            st.markdown(
                f'<div class="kpi-grid" style="grid-template-columns:repeat(2,1fr)">'
                f'{_recent_html}</div>',
                unsafe_allow_html=True)
        if _older_html:
            with st.expander("Show previous months"):
                st.markdown(
                    f'<div class="kpi-grid" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr))">'
                    f'{_older_html}</div>',
                    unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])

    with col1:
        card_open("Monthly Revenue Trend", f"GHS revenue by month ({date_range})")
        monthly = inv_y.groupby("Month")["Discountedvalue"].sum().reset_index()
        monthly["prev"] = monthly["Discountedvalue"].shift(1)
        monthly["pct"]  = (((monthly["Discountedvalue"] - monthly["prev"]) / monthly["prev"]).astype(float) * 100).round(1)
        monthly["Month Label"] = monthly["Month"].apply(month_label)

        fig = go.Figure()
        fig.add_bar(x=monthly["Month Label"], y=monthly["Discountedvalue"],
                    marker=bar_marker(BRAND_GREEN), name="Revenue (GHS)",
                    text=monthly["Discountedvalue"].apply(lambda x: f"GHS {x:,.2f}"),
                    textposition="outside", textfont=dict(size=9))
        fig.add_scatter(x=monthly["Month Label"], y=monthly["Discountedvalue"],
                        mode="lines+markers", line=dict(color="#f59e0b", width=2.5, dash="dot"),
                        marker=dict(size=6, color="#f59e0b"), name="Trend")
        for _, row in monthly.dropna(subset=["pct"]).iterrows():
            clr = "#16a34a" if row["pct"] >= 0 else "#dc2626"
            fig.add_annotation(x=row["Month Label"], y=row["Discountedvalue"],
                               text=f"{'+' if row['pct']>=0 else ''}{row['pct']:.0f}%",
                               showarrow=False, yshift=32, font=dict(size=10, color=clr))
        fig.update_layout(**white_layout(300),
                          legend=dict(orientation="h", y=-0.28, x=0))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        card_close()

    with col2:
        card_open("Sales by City", "Top Ghana cities by order value")
        city_sales = (inv_y.groupby("Customer City")["Discountedvalue"]
                           .sum().reset_index()
                           .rename(columns={"Customer City":"City","Discountedvalue":"Sales"})
                           .sort_values("Sales", ascending=False).head(8))
        city_sales = city_sales[city_sales["City"].notna() & (city_sales["City"] != "")]
        fig2 = px.pie(city_sales, names="City", values="Sales", hole=0.5,
                      color_discrete_sequence=[BRAND_GREEN,"#14b8a6","#f59e0b","#f97316","#8b5cf6","#ec4899","#16a34a","#dc2626"])
        fig2.update_traces(textinfo="percent", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=12, color="white"))
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=10, b=10, l=10, r=10), height=300,
                           showlegend=True, font=dict(color=CHART_FONT),
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11, color=CHART_FONT)))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        card_close()

    col3, col4 = st.columns(2)
    with col3:
        card_open("Repayment Status", "Invoice repayment breakdown")
        rs = inv_y["Repayment Status"].value_counts().reset_index()
        rs.columns = ["Status", "Count"]
        clrs = {"Open":BRAND_GOLD,"Repaid":"#16a34a","Overdue":"#dc2626","Due Soon":"#f59e0b"}
        fig3 = px.bar(rs, x="Status", y="Count", color="Status",
                      color_discrete_map=clrs, text="Count")
        fig3.update_traces(textposition="outside", textfont=dict(size=11),
                           marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig3.update_layout(**white_layout(240))
        fig3.update_layout(showlegend=False, xaxis=dict(tickangle=0))
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        card_close()

    with col4:
        card_open("Payment Mode", "Collection method split")
        pm = rep_y["Payment Method"].value_counts().reset_index()
        pm.columns = ["Method", "Count"]
        pm_clrs = {"Mobile Money":BRAND_GOLD,"Bank Transfer":"#16a34a","Cash":"#f59e0b","Mpesa":"#8b5cf6"}
        fig4 = px.pie(pm, names="Method", values="Count", hole=0.5,
                      color="Method", color_discrete_map=pm_clrs)
        fig4.update_traces(textinfo="percent", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=12, color="white"))
        fig4.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=10, b=10, l=10, r=10), height=240,
                           showlegend=True, font=dict(color=CHART_FONT),
                           legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11, color=CHART_FONT)))
        st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)
        card_close()

    # ── Monthly Revenue Breakdown table ──────────────────────────────────────────
    card_open("Monthly Revenue Breakdown",
                           "Sales, collected and outstanding by month")
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
    _disp["Revenue"]      = _disp["Revenue"].apply(lambda v: f"GHS {v:,.2f}")
    _disp["Collected"]    = _disp["Collected"].apply(lambda v: f"GHS {v:,.2f}")
    _disp["Outstanding"]  = _disp["Outstanding"].apply(lambda v: f"GHS {v:,.2f}")
    _disp["Collection %"] = _disp["Collection %"].apply(lambda v: f"{v:.1f}%")
    _disp["MoM Change"]   = _disp["MoM Change"].apply(
        lambda v: f"+{v:.1f}%" if pd.notna(v) and v >= 0 else (f"{v:.1f}%" if pd.notna(v) else "-"))
    st.dataframe(_disp[["Month","Invoices","Revenue","Collected","Outstanding","Collection %","MoM Change"]],
                 use_container_width=True, hide_index=True)
    card_close()

    # ── Vaccines Delivered by Disease ─────────────────────────────────────────────
    card_open("Vaccines Delivered by Disease",
                           "Monthly doses distributed by disease  Poultry · Goats & Sheep · Cattle")

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
        "Newcastle":     BRAND_GOLD,
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
    _vax["Month Label"] = _vax["Month"].apply(month_label)

    if len(_vax):
        _disease_order = ["Newcastle", "Gumboro", "Fowlpox", "AI", "PPR", "CBPP", "Other Poultry"]
        _diseases_present = [d for d in _disease_order if d in _vax["Disease"].unique()]

        col_vax1, col_vax2 = st.columns([3, 2])
        with col_vax1:
            fig_vax = px.bar(
                _vax, x="Month Label", y="Quantity", color="Disease",
                barmode="stack",
                color_discrete_map=_DISEASE_COLORS,
                category_orders={"Disease": _diseases_present},
                labels={"Quantity": "Doses", "Month Label": ""},
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
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _ov_sheets = {
        "Monthly Revenue": _mb_tbl[["Month","Invoices","Revenue","Collected","Outstanding","Collection %","MoM Change"]].copy(),
        "Invoice Detail":  inv_y[["ID","Created At","Month","Customer ID","Channel","Discountedvalue","Outstanding"]].copy(),
        "Vaccine Doses":   _vax.copy() if len(_vax) else pd.DataFrame(columns=["Month","Disease","Quantity"]),
    }
    _ov_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Overview Report", "Ghana Operations  ·  FBC Sales", str(yr))
        _p.add_kpi_row([
            ("Total Sales",    f"GHS {total_revenue:,.2f}"),
            ("Collected",      f"GHS {total_repaid:,.2f}"),
            ("Outstanding",    f"GHS {outstanding_val:,.2f}"),
            ("Avg Order Value",f"GHS {avg_order_value:,.2f}"),
        ])
        _p.add_kpi_row([
            ("New Partners",    f"{new_signed:,}"),
            ("Activation Rate", f"{activation_rate:.1f}%"),
            ("Repeat Rate",     f"{repeat_rate:.1f}%"),
            ("Recon Rate",      f"{recon_rate:.1f}%"),
        ])
        if len(monthly):
            _p.add_chart(_bar_png(monthly["Month"], monthly["Discountedvalue"],
                                  "Monthly Revenue (GHS)", color=BRAND_GREEN, ylabel="GHS"),
                         "Monthly Revenue Trend")
        _t = _mb_tbl.copy()
        for _c in ["Revenue","Collected","Outstanding"]:
            _t[_c] = _t[_c].apply(lambda v: f"GHS {v:,.2f}")
        _t["Collection %"] = _t["Collection %"].apply(lambda v: f"{v:.1f}%")
        _p.add_table(_t[["Month","Invoices","Revenue","Collected","Outstanding","Collection %"]],
                     "Monthly Revenue Breakdown")
        if len(_vax):
            _p.add_chart(_stacked_bar_png(_vax,"Month","Disease","Quantity",
                                          "Vaccine Doses by Disease",color_map=_DISEASE_COLORS),
                         "Vaccines Delivered")
        _ov_pdf = bytes(_p.output())
    dl_row(_ov_sheets, f"Overview_{yr}.xlsx", _ov_pdf, f"Overview_{yr}.pdf", "Overview")


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — ADVANCED ANALYTICS (dashboard/advanced_page.py, maths in advanced_analytics.py)
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Advanced Analytics":
    aap.render(SimpleNamespace(
        inv_fbc=dl.fbc_invoices(inv), rc_names=rc_names, il=il, prod=prod,
        card_open=card_open, card_close=card_close, section_label=section_label,
        kpi_card=kpi_card, kpi_grid=kpi_grid, dl_button=dl_button,
        chart_cfg=CHART_CFG, chart_font=CHART_FONT, chart_grid=CHART_GRID,
        green=BRAND_GREEN, green_light=BRAND_GREEN_LIGHT, gold=BRAND_GOLD,
    ))


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — SALES PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Sales Performance":
    yr    = year_filter("yr_sales")
    inv_y = apply_year(inv_scoped, yr)
    months_available = set(inv_y["Month"].dropna().unique())
    # Also offer months that only have a revenue target set (e.g. the current month
    # before any invoices land) so they don't just vanish from the page.
    _sp_target_path = f"{DATA}/revenue_target.csv"
    if os.path.exists(_sp_target_path):
        _sp_target_months = pd.read_csv(_sp_target_path)["Month"].astype(str)
        if yr != "All":
            _sp_target_months = _sp_target_months[_sp_target_months.str.startswith(str(yr))]
        months_available |= set(_sp_target_months)
    months_available = sorted(months_available)
    selected = st.multiselect("Filter by Month", months_available,
                              default=months_available)
    inv_f = inv_y[inv_y["Month"].isin(selected)] if selected else inv_y

    r1 = kpi_card("Total Sales", f"GHS {inv_f['Discountedvalue'].sum():,.2f}", "Sales in period", BRAND_GREEN) + \
         kpi_card("Total Orders", f"{len(inv_f):,}", "In selected period", "#14b8a6") + \
         kpi_card("Avg Sale Value", f"GHS {inv_f['Discountedvalue'].mean():,.2f}", "Per order", "#f59e0b")
    st.markdown(kpi_grid(r1, max_cols=3), unsafe_allow_html=True)

    # ── Monthly revenue scorecard ─────────────────────────────────────────────────
    _SP_ABBR   = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                  "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}
    _SP_COLORS = [BRAND_GREEN_DEEP, BRAND_GREEN, BRAND_GREEN_LIGHT, "#8a9d5e", BRAND_GOLD, BRAND_GOLD_LIGHT]
    _sp_rev = inv_f.groupby("Month")["Discountedvalue"].sum().reset_index().sort_values("Month")
    _sp_rev["prev"] = _sp_rev["Discountedvalue"].shift(1)
    _sp_rev["pct"]  = ((_sp_rev["Discountedvalue"] - _sp_rev["prev"]) / _sp_rev["prev"] * 100).round(1)
    _sp_older_html = ""
    _sp_recent_html = ""
    _sp_rev_list = list(_sp_rev.iterrows())
    for _i, (_, _r) in enumerate(_sp_rev_list):
        _parts  = str(_r["Month"]).split("-")
        _yr_lbl = _parts[0] if len(_parts) == 2 else ""
        _mo_lbl = _SP_ABBR.get(_parts[1], _parts[1]) if len(_parts) == 2 else _r["Month"]
        _label  = f"{_mo_lbl} {_yr_lbl}"
        _sub    = (f"+{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) and _r["pct"] >= 0
                   else (f"{_r['pct']:.0f}% vs prev" if pd.notna(_r["pct"]) else "First month"))
        _card = kpi_card(_label, f"GHS {_r['Discountedvalue']:,.2f}", _sub, _SP_COLORS[_i % 6])
        if _i >= len(_sp_rev_list) - 2:
            _sp_recent_html += _card
        else:
            _sp_older_html += _card
    if _sp_recent_html or _sp_older_html:
        section_label("Monthly Revenue")
        if _sp_recent_html:
            st.markdown(
                f'<div class="kpi-grid" style="grid-template-columns:repeat(2,1fr)">'
                f'{_sp_recent_html}</div>',
                unsafe_allow_html=True)
        if _sp_older_html:
            with st.expander("Show previous months"):
                st.markdown(
                    f'<div class="kpi-grid" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr))">'
                    f'{_sp_older_html}</div>',
                    unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        card_open("Monthly Revenue")
        # Reindex against every selected month (not just ones with invoices) so a
        # month with a target but no sales yet — e.g. the current month — still
        # shows up as GHS 0 instead of silently dropping off the chart.
        m = (inv_f.groupby("Month")["Discountedvalue"].sum()
                  .reindex(sorted(selected)).fillna(0).reset_index())
        m["Prev"]     = m["Discountedvalue"].shift(1)
        m["Change %"] = (((m["Discountedvalue"] - m["Prev"]) / m["Prev"]).astype(float) * 100).round(1)
        m["Month Label"] = m["Month"].apply(month_label)

        _target_path = f"{DATA}/revenue_target.csv"
        _target = pd.read_csv(_target_path) if os.path.exists(_target_path) else pd.DataFrame(columns=["Month", "Target"])
        m_t = m.merge(_target, on="Month", how="left")

        tab_mom, tab_target = st.tabs(["Vs Previous Month", "Actual vs Target"])

        with tab_mom:
            fig = go.Figure()
            fig.add_bar(x=m["Month Label"], y=m["Discountedvalue"], marker=bar_marker(BRAND_GREEN),
                        name="Sales (GHS)", text=m["Discountedvalue"].apply(lambda x: f"GHS {x:,.2f}"),
                        textposition="outside", textfont=dict(size=9))
            for _, row in m.dropna(subset=["Change %"]).iterrows():
                if row["Discountedvalue"] == 0:
                    continue
                clr = "#16a34a" if row["Change %"] >= 0 else "#dc2626"
                fig.add_annotation(x=row["Month Label"], y=row["Discountedvalue"],
                                   text=f"{'+' if row['Change %']>=0 else ''}{row['Change %']:.0f}%",
                                   showarrow=False, yshift=30, font=dict(size=10, color=clr))
            fig.update_layout(**white_layout(300))
            fig.update_layout(xaxis=dict(type="category", tickmode="linear", dtick=1, tickangle=-35))
            st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

        with tab_target:
            if m_t["Target"].notna().any():
                fig_t = go.Figure()
                fig_t.add_bar(x=m_t["Month Label"], y=m_t["Discountedvalue"], marker=bar_marker(BRAND_GREEN), name="Actual (GHS)")
                fig_t.add_bar(x=m_t["Month Label"], y=m_t["Target"], marker=bar_marker("#eab308"), name="Target (GHS)")
                for _, row in m_t.dropna(subset=["Target"]).iterrows():
                    attain = (row["Discountedvalue"] / row["Target"] * 100) if row["Target"] else 0
                    clr = "#16a34a" if attain >= 100 else "#dc2626"
                    fig_t.add_annotation(x=row["Month Label"], y=max(row["Discountedvalue"], row["Target"]),
                                       text=f"{attain:.1f}%", showarrow=False, yshift=14,
                                       font=dict(size=10, color=clr))
                fig_t.update_layout(**white_layout(300))
                fig_t.update_layout(barmode="group", legend=dict(orientation="h", y=-0.3),
                                    xaxis=dict(type="category", tickmode="linear", dtick=1, tickangle=-35))
                st.plotly_chart(fig_t, use_container_width=True, config=CHART_CFG)
            else:
                st.info("No revenue target set for the selected months.")

        card_close()

    with col2:
        card_open("Weekly Sales Trend")
        w = inv_f.groupby("Week")["Discountedvalue"].sum().reset_index().tail(16)
        w["Week Label"] = w["Week"].apply(week_label)
        fig2 = go.Figure()
        fig2.add_bar(x=w["Week Label"], y=w["Discountedvalue"], marker=bar_marker("#e0e7ff", "rgba(255,255,255,0.9)"), name="Weekly Sales")
        fig2.add_scatter(x=w["Week Label"], y=w["Discountedvalue"],
                         mode="lines+markers", line=dict(color=BRAND_GREEN, width=2.5),
                         marker=dict(size=5, color=BRAND_GREEN), name="Trend")
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(xaxis=dict(tickangle=-45, nticks=8),
                           legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        card_close()

    card_open("Monthly Sales Summary")
    summary = m.copy()
    summary["Sales"]      = summary["Discountedvalue"].apply(lambda x: f"GHS {x:,.2f}")
    summary["MoM Change"] = summary.apply(
        lambda r: "—" if r["Discountedvalue"] == 0 or pd.isna(r["Change %"])
        else (f"+{r['Change %']:.1f}%" if r["Change %"] >= 0 else f"{r['Change %']:.1f}%"),
        axis=1)
    st.dataframe(summary[["Month","Sales","MoM Change"]], use_container_width=True, hide_index=True)
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _sp_monthly = inv_f.groupby("Month")["Discountedvalue"].agg(Invoices="count", Revenue="sum").reset_index()
    _sp_sheets  = {
        "Monthly Summary":  _sp_monthly,
        "Invoice Detail":   inv_f[["ID","Created At","Month","Customer ID","Channel","Discountedvalue","Outstanding"]].copy(),
    }
    _sp_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Sales Performance", "Monthly revenue  ·  weekly trends", str(yr))
        _p.add_kpi_row([
            ("Total Sales",   f"GHS {inv_f['Discountedvalue'].sum():,.2f}"),
            ("Total Orders",  f"{len(inv_f):,}"),
            ("Avg Sale Value",f"GHS {inv_f['Discountedvalue'].mean():,.2f}" if len(inv_f) else "N/A"),
        ])
        if len(m):
            _p.add_chart(_bar_png(m["Month"], m["Discountedvalue"],
                                  "Monthly Sales (GHS)", color=BRAND_GREEN, ylabel="GHS"),
                         "Monthly Sales Trend")
        _t = _sp_monthly.copy()
        _t["Revenue"] = _t["Revenue"].apply(lambda v: f"GHS {v:,.2f}")
        _p.add_table(_t[["Month","Invoices","Revenue"]], "Monthly Summary")
        _sp_pdf = bytes(_p.output())
    dl_row(_sp_sheets, f"Sales_Performance_{yr}.xlsx", _sp_pdf,
           f"Sales_Performance_{yr}.pdf", "Sales Performance")


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
                  f"In {yr} · Agrovets & Providers", BRAND_GREEN) + \
         kpi_card("Activation Rate (90d)", f"{act_rate:.1f}%",
                  f"{act_90} of {new_signed_y} ordered within 90d", "#14b8a6",
                  f"{act_rate:.0f}%","#14b8a6") + \
         kpi_card("Repeat Rate (30d)", f"{rep_rate:.1f}%",
                  f"{rep_c} of {act_c} reordered within 30d", "#16a34a",
                  f"{rep_rate:.0f}%","#16a34a") + \
         kpi_card("Avg Orders/Customer", f"{len(inv_y)/act_c:.1f}" if act_c else ",",
                  f"{act_c} active ordering customers", "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    r2 = kpi_card("Total Registered",  f"{total_customers:,}", "All customers",  BRAND_GREEN) + \
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
        card_open("Top 10 Customers by Order Value")
        fig = px.bar(top_cust.sort_values("Total Value"), x="Total Value", y="Customer",
                     orientation="h", text="Total Value",
                     color="Total Value", color_continuous_scale=["#e3f2e8",BRAND_GREEN])
        fig.update_traces(texttemplate="GHS %{text:,.2f}", textposition="inside",
                          insidetextanchor="middle", textfont=dict(color="white", size=10),
                          marker_cornerradius=6)
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(t=10, b=10, l=10, r=10), height=360, font=dict(color=CHART_FONT),
                          coloraxis_showscale=False,
                          xaxis=dict(gridcolor=CHART_GRID), yaxis=dict(color=CHART_FONT))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        card_close()

    with col2:
        card_open("Active vs Inactive")
        sdf = pd.DataFrame({"Status":["Active","Inactive"],"Count":[active_customers, inactive]})
        fig2 = px.pie(sdf, names="Status", values="Count", hole=0.55,
                      color="Status", color_discrete_map={"Active":BRAND_GREEN,"Inactive":"#e0e7ff"})
        fig2.update_traces(textinfo="percent+label", textposition="inside",
                           insidetextorientation="horizontal",
                           textfont=dict(size=13, color="white"))
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=10, b=10, l=10, r=10), height=300, showlegend=False,
                           font=dict(color=CHART_FONT))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        card_close()

    # New partners timeline
    card_open("New Partner Registrations by Month", "Agrovets & Providers signed per month")
    rc_dated["Month"] = rc_dated["Created At"].dt.to_period("M").astype(str)
    rc_month = rc_dated[rc_dated["Created At"].dt.year == yr] if yr != "All" else rc_dated
    rc_month_grp = rc_month.groupby(["Month","Segment Type"])["ID"].count().to_frame("Count").reset_index()
    rc_month_grp["Month Label"] = rc_month_grp["Month"].apply(month_label)
    seg_col_map = {"Provider":BRAND_GREEN,"Agrovet":"#14b8a6","Hatchery":"#f59e0b"}
    fig3 = px.bar(rc_month_grp, x="Month Label", y="Count", color="Segment Type",
                  color_discrete_map=seg_col_map, barmode="stack", text="Count")
    fig3.update_traces(textposition="inside", textfont=dict(color="white", size=10))
    fig3.update_layout(**white_layout(260), legend=dict(orientation="h", y=-0.3))
    fig3.update_layout(xaxis=dict(tickangle=-30))
    st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
    card_close()

    def _extract_region(val):
        try:
            import json
            return json.loads(val).get("Region", "")
        except Exception:
            return val

    card_open(f"New Customers Onboarded in {yr}",
                           "Agrovets & Providers signed this year, for review")
    new_cust_df = new_partners_y.copy()
    new_cust_df["Region"] = new_cust_df["Customer Address"].apply(_extract_region)
    new_cust_df = new_cust_df.sort_values("Created At", ascending=True)
    new_cust_df["Created At"] = new_cust_df["Created At"].dt.strftime("%d %b %Y")
    new_cust_df = new_cust_df.rename(columns={"Phone Number": "Phone", "Created At": "Date Joined"})
    new_cust_df = new_cust_df[["Name", "Segment Type", "Region", "Phone", "Date Joined"]].reset_index(drop=True)
    new_cust_df.index = pd.RangeIndex(1, len(new_cust_df) + 1)
    st.dataframe(new_cust_df, use_container_width=True)
    card_close()

    card_open("Customer Leaderboard")
    lb = top_cust.copy()
    lb.index = pd.RangeIndex(1, len(lb)+1)
    lb["Total Value"] = lb["Total Value"].apply(lambda x: f"GHS {x:,.2f}")
    st.dataframe(lb, use_container_width=True)
    card_close()

    card_open("Active Customers Directory", f"All {active_customers} active registered customers")
    dir_df = rc[rc["Status"] == "Active"][[
        "Name", "Segment Type", "Customer Address",
        "Phone Number", "Created At"
    ]].copy()
    dir_df["Region"] = dir_df["Customer Address"].apply(_extract_region)
    dir_df = dir_df.drop(columns=["Customer Address"])
    dir_df["Created At"] = pd.to_datetime(dir_df["Created At"], errors="coerce")
    dir_df = dir_df.sort_values("Created At", ascending=True).reset_index(drop=True)
    dir_df["Created At"] = dir_df["Created At"].dt.strftime("%d %b %Y")
    dir_df = dir_df.rename(columns={
        "Phone Number": "Phone",
        "Created At":   "Date Joined",
    })
    dir_df = dir_df[["Name", "Segment Type", "Region", "Phone", "Date Joined"]]
    dir_df.index = pd.RangeIndex(1, len(dir_df) + 1)
    st.dataframe(dir_df, use_container_width=True)
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _cust_revenue = (inv_y.merge(rc_names, left_on="Customer ID", right_on="ID", how="left")
                          .groupby("Name")
                          .agg(Orders=("Customer ID","count"), Revenue=("Discountedvalue","sum"), Outstanding=("Outstanding","sum"))
                          .reset_index().sort_values("Revenue", ascending=False))
    _cust_sheets = {
        "Customer Revenue":    _cust_revenue,
        "Active Directory":    dir_df.reset_index(drop=True),
        "New Customers":       new_cust_df.reset_index(drop=True),
        "Registrations":       rc_month_grp,
    }
    _cust_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Customers", "Partner registrations  ·  revenue leaderboard", str(yr))
        _p.add_kpi_row([
            ("New Partners",     f"{new_signed_y:,}"),
            ("Activation Rate",  f"{act_rate:.1f}%"),
            ("Repeat Rate",      f"{rep_rate:.1f}%"),
            ("Active Customers", f"{act_c:,}"),
        ])
        _tc = top_cust.head(10)
        if len(_tc):
            _p.add_chart(_hbar_png(_tc["Total Value"], _tc["Customer"],
                                   "Top 10 Customers by Order Value (GHS)", color=BRAND_GREEN),
                         "Top Customers")
        _t = _cust_revenue.head(20).copy()
        _t["Revenue"]     = _t["Revenue"].apply(lambda v: f"GHS {v:,.2f}")
        _t["Outstanding"] = _t["Outstanding"].apply(lambda v: f"GHS {v:,.2f}")
        _p.add_table(_t[["Name","Orders","Revenue","Outstanding"]], "Customer Revenue Leaderboard")
        _cust_pdf = bytes(_p.output())
    dl_row(_cust_sheets, f"Customers_{yr}.xlsx", _cust_pdf,
           f"Customers_{yr}.pdf", "Customers")


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
    r1 = kpi_card("Total Collected",     f"GHS {total_repaid_y:,.2f}", f"{collection_pct_y:.1f}% rate", "#16a34a",
                  f"{collection_pct_y:.1f}%", "#16a34a") + \
         kpi_card("Outstanding",         f"GHS {outstanding_y:,.2f}", f"{outstanding_pct_y:.1f}% of invoiced",
                  "#dc2626", f"{outstanding_pct_y:.1f}%", "#dc2626") + \
         kpi_card("Successful Payments", f"{success_pay_y.shape[0]:,}", "Transactions", BRAND_GREEN) + \
         kpi_card("Avg Payment",         f"GHS {rep_y['Amount'].mean():,.2f}", "Per repayment", "#f97316")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        card_open("Payment Mode Distribution", "By number of transactions")
        pm = rep_y["Payment Method"].value_counts().reset_index()
        pm.columns = ["Method", "Count"]
        pm_clrs = {"Mobile Money":BRAND_GOLD,"Bank Transfer":"#16a34a","Cash":"#f59e0b","Mpesa":"#8b5cf6"}
        fig = px.pie(pm, names="Method", values="Count", hole=0.5,
                     color="Method", color_discrete_map=pm_clrs)
        fig.update_traces(textinfo="percent", textposition="inside",
                          insidetextorientation="horizontal",
                          textfont=dict(size=13, color="white"))
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(t=10, b=10, l=10, r=10), height=300,
                          showlegend=True, font=dict(color=CHART_FONT),
                          legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11, color=CHART_FONT)))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        card_close()

    with col2:
        card_open("Monthly Collections vs Invoiced")
        rep2 = rep_y.copy()
        rep2["Month"] = rep2["Created At"].dt.to_period("M").astype(str)
        monthly_col  = rep2.groupby("Month")["Amount"].sum().reset_index()
        monthly_inv  = inv_y.groupby("Month")["Discountedvalue"].sum().reset_index()
        cmp = monthly_inv.merge(monthly_col, on="Month", how="left").fillna(0)
        cmp["Month Label"] = cmp["Month"].apply(month_label)
        fig2 = go.Figure()
        fig2.add_bar(x=cmp["Month Label"], y=cmp["Discountedvalue"], name="Invoiced", marker=bar_marker("#e0e7ff", "rgba(255,255,255,0.9)"))
        fig2.add_bar(x=cmp["Month Label"], y=cmp["Amount"],            name="Collected", marker=bar_marker(BRAND_GREEN))
        fig2.update_layout(barmode="overlay", **white_layout(300),
                           legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        card_close()

    card_open("Payment Method Summary")
    pm_s = rep_y.groupby("Payment Method").agg(
        Transactions=("Amount","count"),
        Total_Collected=("Amount","sum"),
        Avg_Amount=("Amount","mean")
    ).reset_index().sort_values("Total_Collected", ascending=False)
    pm_s["Total_Collected"] = pm_s["Total_Collected"].apply(lambda x: f"GHS {x:,.2f}")
    pm_s["Avg_Amount"]      = pm_s["Avg_Amount"].apply(lambda x: f"GHS {x:,.2f}")
    st.dataframe(pm_s.rename(columns={"Payment Method":"Method","Total_Collected":"Total Collected","Avg_Amount":"Avg per Transaction"}),
                 use_container_width=True, hide_index=True)
    card_close()

    card_open("Recent Collections")
    st.dataframe(rep.sort_values("Created At", ascending=False)
                    [["Created At","Amount","Payment Method","Repayment Route","Country Code"]].head(30),
                 use_container_width=True, hide_index=True)
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _pay_monthly = (rep_y.assign(Month=rep_y["Created At"].dt.to_period("M").astype(str))
                         .groupby("Month")["Amount"].sum().reset_index().rename(columns={"Amount":"Collected"}))
    _pay_monthly = _pay_monthly.merge(
        inv_y.groupby("Month")["Discountedvalue"].sum().reset_index().rename(columns={"Discountedvalue":"Invoiced"}),
        on="Month", how="outer").fillna(0)
    _pay_monthly["Collection %"] = (_pay_monthly["Collected"] / _pay_monthly["Invoiced"] * 100).round(1)
    _pay_sheets = {
        "Monthly Collections": _pay_monthly,
        "Repayment Detail":    rep_y[["ID","Created At","Invoice ID","Amount","Payment Method","Status"]].copy(),
        "Invoice Outstanding": inv_y[["ID","Created At","Month","Discountedvalue","Outstanding"]].copy(),
    }
    _pay_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Payments", "Collections vs invoiced  ·  payment methods", str(yr))
        _p.add_kpi_row([
            ("Total Collected", f"GHS {total_repaid_y:,.2f}"),
            ("Outstanding",     f"GHS {outstanding_y:,.2f}"),
            ("Collection Rate", f"{collection_pct_y:.1f}%"),
            ("Avg Payment",     f"GHS {rep_y['Amount'].mean():,.2f}" if len(rep_y) else "N/A"),
        ])
        if len(cmp):
            _p.add_chart(_grouped_bar_png(cmp, "Month",
                                          [("Discountedvalue","Invoiced"),("Amount","Collected")],
                                          "Monthly: Invoiced vs Collected",
                                          colors=["#a8d9bf",BRAND_GREEN]),
                         "Monthly Collections vs Invoiced")
        _t = _pay_monthly.copy()
        _t["Collected"] = _t["Collected"].apply(lambda v: f"GHS {v:,.2f}")
        _t["Invoiced"]  = _t["Invoiced"].apply(lambda v: f"GHS {v:,.2f}")
        _t["Collection %"] = _t["Collection %"].apply(lambda v: f"{v:.1f}%")
        _p.add_table(_t[["Month","Invoiced","Collected","Collection %"]], "Monthly Collections")
        _pay_pdf = bytes(_p.output())
    dl_row(_pay_sheets, f"Payments_{yr}.xlsx", _pay_pdf,
           f"Payments_{yr}.pdf", "Payments")


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
                  f"Week of {latest_week}", BRAND_GREEN) + \
         kpi_card("Sales This Week",     f"GHS {weekly_sales:,.2f}",
                  "Total invoiced value", "#14b8a6") + \
         kpi_card("Collected This Week", f"GHS {weekly_collected:,.2f}",
                  "Repayments received", "#16a34a") + \
         kpi_card("Overdue Invoices",    f"{len(overdue_inv):,}",
                  "Requiring follow-up", "#dc2626",
                  f"{len(overdue_inv)}", "#dc2626")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])
    with col1:
        card_open("Weekly Orders & Sales Trend", "Last 16 weeks")

        _wk_target_path = f"{DATA}/weekly_revenue_target.csv"
        _wk_target = (pd.read_csv(_wk_target_path)[["Week", "Target"]]
                      if os.path.exists(_wk_target_path) else pd.DataFrame(columns=["Week", "Target"]))
        # Union with target-only weeks (e.g. the current week before any invoices land)
        # so they show up instead of silently dropping off the last-16 window. Anchor the
        # window on today's date rather than the tail of the list — the target file runs
        # all the way to December, which would otherwise push a "last 16" window straight
        # past the real, current data into far-future target-only weeks.
        _wk_all  = sorted(set(inv_y["Week"].dropna().unique()) | set(_wk_target["Week"]))
        _wk_now  = pd.Timestamp.now()
        _wk_recent = sorted(
            w for w in _wk_all if pd.Period(w, freq="W").start_time <= _wk_now + pd.Timedelta(weeks=1)
        )[-16:]

        tab_wk_trend, tab_wk_target = st.tabs(["Trend", "Actual vs Target"])

        with tab_wk_trend:
            w_trend = (inv_y.groupby("Week")
                            .agg(Orders=("ID","count"), Sales=("Discountedvalue","sum"))
                            .reset_index().tail(16))
            w_trend["Week Label"] = w_trend["Week"].apply(week_label)
            fig = go.Figure()
            fig.add_bar(x=w_trend["Week Label"], y=w_trend["Sales"],
                        marker=bar_marker("#e0e7ff", "rgba(255,255,255,0.9)"), name="Sales (GHS)", yaxis="y")
            fig.add_scatter(x=w_trend["Week Label"], y=w_trend["Orders"],
                            mode="lines+markers", line=dict(color=BRAND_GREEN, width=2.5),
                            marker=dict(size=6, color=BRAND_GREEN), name="Orders", yaxis="y2")
            fig.update_layout(**white_layout(300))
            fig.update_layout(
                yaxis2=dict(overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=-0.3),
                xaxis=dict(tickangle=-45, nticks=8)
            )
            st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

        with tab_wk_target:
            if _wk_target["Target"].notna().any():
                w_t = (inv_y.groupby("Week")["Discountedvalue"].sum()
                            .reindex(_wk_recent).fillna(0).reset_index())
                w_t = w_t.merge(_wk_target, on="Week", how="left")
                w_t["Week Label"] = w_t["Week"].apply(week_label)
                fig_wt = go.Figure()
                fig_wt.add_bar(x=w_t["Week Label"], y=w_t["Discountedvalue"], marker=bar_marker(BRAND_GREEN), name="Actual (GHS)")
                fig_wt.add_bar(x=w_t["Week Label"], y=w_t["Target"], marker=bar_marker("#eab308"), name="Target (GHS)")
                for _, row in w_t.dropna(subset=["Target"]).iterrows():
                    attain = (row["Discountedvalue"] / row["Target"] * 100) if row["Target"] else 0
                    clr = "#16a34a" if attain >= 100 else "#dc2626"
                    fig_wt.add_annotation(x=row["Week Label"], y=max(row["Discountedvalue"], row["Target"]),
                                          text=f"{attain:.1f}%", showarrow=False, yshift=12,
                                          font=dict(size=9, color=clr))
                fig_wt.update_layout(**white_layout(300))
                fig_wt.update_layout(barmode="group", legend=dict(orientation="h", y=-0.3),
                                     xaxis=dict(tickangle=-45, nticks=8))
                st.plotly_chart(fig_wt, use_container_width=True, config=CHART_CFG)
            else:
                st.info("No weekly revenue target set.")

        card_close()

    with col2:
        card_open("Week-over-Week Sales Change", "Last 8 weeks")
        ww = (inv_y.groupby("Week")["Discountedvalue"].sum().reset_index().tail(8))
        ww["Prev"]   = ww["Discountedvalue"].shift(1)
        ww["Change"] = ((ww["Discountedvalue"] - ww["Prev"]) / ww["Prev"] * 100).round(1)
        ww["Week Label"] = ww["Week"].apply(week_label)
        bar_colors   = ["#16a34a" if x >= 0 else "#dc2626" for x in ww["Change"].fillna(0)]
        fig2 = go.Figure(go.Bar(
            x=ww["Week Label"], y=ww["Change"].fillna(0),
            marker=dict(color=bar_colors, cornerradius=6, line=dict(color="rgba(255,255,255,0.55)", width=1)),
            text=ww["Change"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else ","),
            textposition="outside"
        ))
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(
            xaxis=dict(tickangle=-45),
            yaxis=dict(title="% Change", gridcolor="#f3f4f6")
        )
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        card_close()

    card_open("Weekly Breakdown", "Orders, invoiced value and collections per week")
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
    weekly_tbl["Value GHS"]             = weekly_tbl["Invoice_Total"].apply(lambda x: f"GHS {x:,.2f}")
    weekly_tbl["Sales Collected (GHS)"] = weekly_tbl["Sales_Collected"].apply(lambda x: f"GHS {x:,.2f}")

    # Week start date (e.g. "5-Jan-2026") and ISO week number (continuous across the year)
    _wk_starts = weekly_tbl["Week"].apply(lambda w: pd.Period(w, freq="W").start_time)
    weekly_tbl["Date"]        = _wk_starts.apply(lambda d: f"{d.day}-{d.strftime('%b-%Y')}")
    weekly_tbl["Week Number"] = _wk_starts.apply(lambda d: int(d.isocalendar()[1]))

    weekly_tbl = (weekly_tbl
        .sort_values("Week", ascending=False)
        [["Date", "Week Number", "Orders", "Value GHS", "Sales Collected (GHS)", "Collection Rate"]]
        .reset_index(drop=True))
    st.dataframe(weekly_tbl, use_container_width=True, hide_index=True)
    card_close()

    card_open("Overdue Invoice Exceptions", "Invoices requiring immediate follow-up")
    if len(overdue_inv):
        exc = overdue_inv.merge(rc_names[["ID","Name"]], left_on="Customer ID", right_on="ID", how="left")
        exc = exc[["Created At","Name","Discountedvalue","Due Date","Repayment Status"]].copy()
        exc.columns = ["Invoice Date","Customer","Amount (GHS)","Due Date","Status"]
        exc["Amount (GHS)"] = exc["Amount (GHS)"].apply(lambda x: f"GHS {x:,.2f}")
        exc["Invoice Date"] = exc["Invoice Date"].dt.strftime("%Y-%m-%d")
        exc["Due Date"]     = pd.to_datetime(exc["Due Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        exc = exc.sort_values("Due Date")
        exc.index = pd.RangeIndex(1, len(exc)+1)
        st.dataframe(exc, use_container_width=True)
    else:
        st.success("No overdue invoices in the selected period.")
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _wk_sheets = {
        "Weekly Summary": weekly_tbl,
        "Overdue Invoices": exc if len(overdue_inv) else pd.DataFrame(columns=["Invoice Date","Customer","Amount (GHS)","Due Date","Status"]),
    }
    _wk_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Weekly Scorecard", "Weekly orders  ·  collections  ·  overdue alerts", str(yr))
        _p.add_kpi_row([
            ("Orders This Week",    f"{weekly_orders:,}"),
            ("Sales This Week",     f"GHS {weekly_sales:,.2f}"),
            ("Collected This Week", f"GHS {weekly_collected:,.2f}"),
            ("Overdue Invoices",    f"{len(overdue_inv):,}"),
        ])
        if len(w_trend):
            _p.add_chart(_bar_png(w_trend["Week"], w_trend["Sales"],
                                  "Weekly Sales (GHS)", color=BRAND_GREEN, ylabel="GHS"),
                         "Weekly Sales Trend")
        _p.add_table(weekly_tbl.head(20), "Weekly Breakdown")
        if len(overdue_inv):
            _p.add_table(exc.head(20), "Overdue Invoice Exceptions")
        _wk_pdf = bytes(_p.output())
    dl_row(_wk_sheets, f"Weekly_Scorecard_{yr}.xlsx", _wk_pdf,
           f"Weekly_Scorecard_{yr}.pdf", "Weekly Scorecard")


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — CEO CLOSEOUT
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Weekly Info":
    _co_all_weeks = sorted(inv_scoped["Week"].dropna().unique())
    if not _co_all_weeks:
        st.info("No invoice data available yet.")
    else:
        _co_week_num = lambda w: pd.Period(w, freq="W").start_time.isocalendar()[1]
        _co_week = st.selectbox("Week", _co_all_weeks, index=len(_co_all_weeks) - 1, key="co_week",
                                format_func=lambda w: f"Week {_co_week_num(w)}")
        _co_wk_start = pd.Period(_co_week, freq="W").start_time.tz_localize("UTC")
        _co_wk_end   = pd.Period(_co_week, freq="W").end_time.tz_localize("UTC")
        st.caption(f"Week {_co_week_num(_co_week)} · {_co_wk_start.strftime('%d %b %Y')}, {_co_wk_end.strftime('%d %b %Y')}")

        inv_wk = inv_scoped[inv_scoped["Week"] == _co_week]
        rep_wk_all = rep_scoped.copy()
        rep_wk_all["Week"] = rep_wk_all["Created At"].dt.to_period("W").astype(str)
        rep_wk = rep_wk_all[rep_wk_all["Week"] == _co_week]

        # ── 1. Revenue vs target ─────────────────────────────────────────────────
        _co_target_path = f"{DATA}/weekly_revenue_target.csv"
        _co_target = (pd.read_csv(_co_target_path) if os.path.exists(_co_target_path)
                      else pd.DataFrame(columns=["Week", "Target"]))
        _co_target_row = _co_target[_co_target["Week"] == _co_week]
        _co_target_val = float(_co_target_row["Target"].iloc[0]) if len(_co_target_row) else None
        _co_revenue = inv_wk["Discountedvalue"].sum()
        _co_attain  = (_co_revenue / _co_target_val * 100) if _co_target_val else None

        # ── 2. Collections % ─────────────────────────────────────────────────────
        _co_collected = rep_wk["Amount"].sum()
        _co_collection_pct = (_co_collected / _co_revenue * 100) if _co_revenue else 0

        # ── 3. DSO — outstanding AR as of week-end over trailing-window sales ────
        # "Outstanding" on inv_scoped is a running total repaid AS OF NOW, not as of
        # week-end — using it here would let repayments received *after* the selected
        # week silently reduce a balance we're claiming to measure at an earlier date.
        # Rebuild the repaid amount per invoice from repayment-level dates instead, so
        # only money actually received by week-end counts.
        # If data stops mid-week, count the window back from the last data point rather
        # than week-end -- otherwise empty days shrink the sales base and inflate DSO.
        _co_dso_asof = min(_co_wk_end, max(inv_scoped["Created At"].max(), rep_scoped["Created At"].max()))
        _co_sales_win = inv_scoped[(inv_scoped["Created At"] > _co_dso_asof - pd.Timedelta(days=DSO_WINDOW_DAYS)) &
                                    (inv_scoped["Created At"] <= _co_wk_end)]["Discountedvalue"].sum()
        _co_inv_asof = inv_scoped[inv_scoped["Created At"] <= _co_wk_end][["ID", "Discountedvalue"]]
        _co_repaid_asof = (rep_scoped[rep_scoped["Created At"] <= _co_wk_end]
                           .groupby("Invoice ID")["Amount"].sum())
        _co_inv_asof = _co_inv_asof.merge(_co_repaid_asof.rename("Repaid"), left_on="ID", right_index=True, how="left")
        _co_inv_asof["Repaid"] = _co_inv_asof["Repaid"].fillna(0)
        _co_ar_asof = (_co_inv_asof["Discountedvalue"] - _co_inv_asof["Repaid"]).clip(lower=0).sum()
        _co_dso = (_co_ar_asof / _co_sales_win * DSO_WINDOW_DAYS) if _co_sales_win else None
        # DSO is only meaningful against the real standard payment term (DSO_TERMS_DAYS),
        # not a generic trade-credit rule of thumb.
        _co_terms_days = DSO_TERMS_DAYS
        _co_days_beyond_terms = (_co_dso - _co_terms_days) if _co_dso is not None else None

        # ── 4. Active / repeat Agrovets ───────────────────────────────────────────
        _co_agro_ids    = set(rc[rc["Segment Type"] == "Agrovet"]["ID"])
        _co_wk_agro_custs = set(inv_wk[inv_wk["Customer ID"].isin(_co_agro_ids)]["Customer ID"])
        _co_active_agro   = len(_co_wk_agro_custs)
        _co_prior_agro_custs = set(
            inv_scoped[(inv_scoped["Created At"] < _co_wk_start) &
                       (inv_scoped["Customer ID"].isin(_co_agro_ids))]["Customer ID"])
        _co_repeat_agro     = len(_co_wk_agro_custs & _co_prior_agro_custs)
        _co_repeat_agro_pct = (_co_repeat_agro / _co_active_agro * 100) if _co_active_agro else 0

        _co_wk_idx    = _co_all_weeks.index(_co_week)
        _co_prev_week = _co_all_weeks[_co_wk_idx - 1] if _co_wk_idx > 0 else None
        if _co_prev_week:
            _co_active_agro_prev = inv_scoped[(inv_scoped["Week"] == _co_prev_week) &
                                               (inv_scoped["Customer ID"].isin(_co_agro_ids))]["Customer ID"].nunique()
            _co_agro_delta = _co_active_agro - _co_active_agro_prev
        else:
            _co_agro_delta = None

        # ── 5. Multi-SKU adoption ─────────────────────────────────────────────────
        _co_il_wk = il[il["Invoice ID"].isin(inv_wk["ID"])]
        _co_sku_per_order    = _co_il_wk.groupby("Invoice ID")["Product ID"].nunique()
        _co_orders_with_lines = len(_co_sku_per_order)
        _co_multi_sku_orders  = int((_co_sku_per_order > 1).sum())
        _co_multi_sku_pct     = (_co_multi_sku_orders / _co_orders_with_lines * 100) if _co_orders_with_lines else None

        # Line-item revenue (no cost/margin here -- gross margin is a monthly figure by
        # agreement, calculated at month-end to properly account for Zipline sales).
        _co_il_cost = _co_il_wk.merge(prod[["ID", "Sku"]], left_on="Product ID", right_on="ID", how="left")
        _co_il_cost["Line Revenue"] = _co_il_cost["Price"] * _co_il_cost["Quantity"]

        _r1c1, _r1c2, _r1c3 = st.columns(3)
        with _r1c1:
            st.markdown(kpi_card("Revenue This Week", f"GHS {_co_revenue:,.2f}",
                        (f"{_co_attain:.1f}% of GHS {_co_target_val:,.2f} target" if _co_target_val is not None
                         else "No target set for this week"),
                        BRAND_GREEN,
                        (f"{_co_attain:.1f}%" if _co_attain is not None else ""),
                        ("#16a34a" if (_co_attain or 0) >= 100 else "#dc2626") if _co_attain is not None else ""),
                        unsafe_allow_html=True)
        with _r1c2:
            st.markdown(kpi_card("Collections %", f"{_co_collection_pct:.1f}%",
                        f"GHS {_co_collected:,.2f} collected", "#16a34a"), unsafe_allow_html=True)
        with _r1c3:
            st.markdown(kpi_card("DSO", f"{_co_dso:.0f} days" if _co_dso is not None else "N/A",
                        (f"vs {_co_terms_days}-day terms" if _co_dso is not None else f"Trailing {DSO_WINDOW_DAYS}-day basis"),
                        "#f59e0b",
                        (f"{_co_days_beyond_terms:+.0f}d" if _co_days_beyond_terms is not None else ""),
                        ("#dc2626" if (_co_days_beyond_terms or 0) > 0 else "#16a34a") if _co_days_beyond_terms is not None else ""),
                        unsafe_allow_html=True)
            with st.popover("🔎 View formula", use_container_width=True):
                st.markdown(f"**DSO = Outstanding AR ÷ Trailing {DSO_WINDOW_DAYS}-day sales × {DSO_WINDOW_DAYS}**")
                st.markdown(
                    f"- Outstanding AR (as of week-end): **GHS {_co_ar_asof:,.2f}**\n"
                    f"- Sales, trailing {DSO_WINDOW_DAYS} days: **GHS {_co_sales_win:,.2f}**\n\n"
                    f"DSO = ({_co_ar_asof:,.2f} ÷ {_co_sales_win:,.2f}) × {DSO_WINDOW_DAYS} = "
                    f"**{_co_dso:.1f} days**\n\n"
                    f"Standard payment terms are **{_co_terms_days} days** -> this week is "
                    f"**{_co_days_beyond_terms:+.1f} days** {'over' if _co_days_beyond_terms >= 0 else 'under'} terms."
                    if _co_dso is not None else "Not enough data to calculate.")

        st.caption("Gross margin is excluded from the weekly closeout by agreement — it's calculated "
                   "at month-end to properly account for Zipline sales, and reported in the monthly review.")

        r2 = kpi_card("Active Agrovets", f"{_co_active_agro}",
                      (f"{'+' if _co_agro_delta >= 0 else ''}{_co_agro_delta} vs last week"
                       if _co_agro_delta is not None else "No prior week to compare"),
                      BRAND_GREEN) + \
             kpi_card("Repeat Agrovets", f"{_co_repeat_agro_pct:.1f}%",
                      f"{_co_repeat_agro} of {_co_active_agro} also ordered before this week", "#14b8a6") + \
             kpi_card("Multi-SKU Adoption", f"{_co_multi_sku_pct:.1f}%" if _co_multi_sku_pct is not None else "N/A",
                      (f"{_co_multi_sku_orders} of {_co_orders_with_lines} orders had 2+ SKUs"
                       if _co_orders_with_lines else "No line-item data for this week"), "#3b82f6")
        st.markdown(kpi_grid(r2, max_cols=3), unsafe_allow_html=True)

        # ── Behind the Numbers — revenue bridge, margin/DSO workings, SKU & discount detail ──
        section_label("Behind the Numbers")

        _co_predisc_rev = inv_wk["Total Order Value"].sum() if "Total Order Value" in inv_wk.columns else _co_revenue
        _co_discount_given = _co_predisc_rev - _co_revenue

        rb = kpi_card("Pre-Discount Value", f"GHS {_co_predisc_rev:,.2f}",
                      "List-price total of everything sold this week", "#64748b") + \
             kpi_card("Discounts Given", f"GHS {_co_discount_given:,.2f}",
                      (f"{_co_discount_given/_co_predisc_rev*100:.1f}% of pre-discount value"
                       if _co_predisc_rev else "No discounts this week"), "#dc2626") + \
             kpi_card("Net Revenue (Invoiced)", f"GHS {_co_revenue:,.2f}",
                      "What's actually billed, matches Revenue This Week above", BRAND_GREEN)
        st.markdown(kpi_grid(rb, max_cols=3), unsafe_allow_html=True)

        def _co_kv_rows(rows):
            return "".join(
                f'<div style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;'
                f'border-bottom:1px solid {_T["hr_color"]};font-size:13px">'
                f'<span style="color:{_T["text_muted"]}">{k}</span>'
                f'<span style="font-weight:700;text-align:right;color:{_T["text_heading"]}">{v}</span></div>'
                for k, v in rows)

        card_open("DSO, How It's Calculated",
                               f"Outstanding AR ÷ trailing {DSO_WINDOW_DAYS}-day sales × {DSO_WINDOW_DAYS}")
        st.markdown(_co_kv_rows([
            ("Outstanding AR as of week-end", f"GHS {_co_ar_asof:,.2f}"),
            (f"Sales, trailing {DSO_WINDOW_DAYS} days", f"GHS {_co_sales_win:,.2f}"),
            ("DSO",                            f"{_co_dso:.1f} days" if _co_dso is not None else "N/A"),
            ("Standard payment terms",         f"{_co_terms_days} days"),
            ("Days beyond terms",              f"{_co_days_beyond_terms:+.1f} days" if _co_days_beyond_terms is not None else "N/A"),
        ]), unsafe_allow_html=True)
        card_close()

        # ── AR Aging — turns the DSO number into an actionable chase list ────────
        card_open("AR Aging, Collections Chase List",
                                f"Every unpaid invoice as of week-end, by how overdue it is")
        _co_ar_detail = _co_inv_asof.merge(inv_scoped[["ID", "Customer ID", "Due Date"]], on="ID", how="left")
        _co_ar_detail["Outstanding"] = (_co_ar_detail["Discountedvalue"] - _co_ar_detail["Repaid"]).clip(lower=0)
        _co_ar_detail = _co_ar_detail[_co_ar_detail["Outstanding"] > 0.01].copy()
        _co_ar_detail["Due Date"]    = pd.to_datetime(_co_ar_detail["Due Date"], errors="coerce")
        _co_ar_detail["Days Overdue"] = (_co_wk_end - _co_ar_detail["Due Date"]).dt.days

        def _co_age_bucket(d):
            if pd.isna(d):  return "No due date"
            if d < 0:       return "Not yet due"
            if d <= 30:     return "0, 30 days overdue"
            if d <= 60:     return "31, 60 days overdue"
            if d <= 90:     return "61, 90 days overdue"
            return "90+ days overdue"

        _co_ar_detail["Bucket"] = _co_ar_detail["Days Overdue"].apply(_co_age_bucket)
        _co_bucket_order  = ["Not yet due", "0, 30 days overdue", "31, 60 days overdue",
                             "61, 90 days overdue", "90+ days overdue", "No due date"]
        _co_bucket_colors = {"Not yet due": "#94a3b8", "0, 30 days overdue": "#16a34a",
                             "31, 60 days overdue": "#eab308", "61, 90 days overdue": "#f97316",
                             "90+ days overdue": "#dc2626", "No due date": "#94a3b8"}

        if len(_co_ar_detail):
            _co_bucket_sum = (_co_ar_detail.groupby("Bucket")["Outstanding"].agg(Total="sum", Invoices="count")
                              .reindex(_co_bucket_order).dropna(how="all"))
            _co_bucket_sum = _co_bucket_sum[_co_bucket_sum["Invoices"].fillna(0) > 0]

            _age_fig = go.Figure(go.Bar(
                x=_co_bucket_sum["Total"], y=_co_bucket_sum.index, orientation="h",
                marker=dict(color=[_co_bucket_colors[b] for b in _co_bucket_sum.index], cornerradius=6,
                           line=dict(color="rgba(255,255,255,0.55)", width=1)),
                text=[f"GHS {t:,.0f} · {int(n)} invoices" for t, n in zip(_co_bucket_sum["Total"], _co_bucket_sum["Invoices"])],
                textposition="outside",
            ))
            _age_fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                   margin=dict(t=10, b=10, l=10, r=120), height=max(140, 44 * len(_co_bucket_sum)),
                                   font=dict(family="Inter, sans-serif", size=12),
                                   xaxis=dict(gridcolor="#f3f4f6", range=[0, _co_bucket_sum["Total"].max() * 1.35]),
                                   yaxis=dict(autorange="reversed"))
            st.plotly_chart(_age_fig, use_container_width=True, config=CHART_CFG)

            _co_chase = _co_ar_detail[_co_ar_detail["Bucket"] != "Not yet due"].sort_values("Days Overdue", ascending=False)
            if len(_co_chase):
                _co_chase = _co_chase.merge(rc_names[["ID", "Name"]], left_on="Customer ID", right_on="ID",
                                            how="left", suffixes=("", "_cust"))
                _co_chase_disp = pd.DataFrame({
                    "Customer":      _co_chase["Name"].fillna("Unknown"),
                    "Invoice ID":    _co_chase["ID"],
                    "Due Date":      _co_chase["Due Date"].dt.strftime("%Y-%m-%d"),
                    "Days Overdue":  _co_chase["Days Overdue"].astype(int),
                    "Outstanding":   _co_chase["Outstanding"].apply(lambda x: f"GHS {x:,.2f}"),
                    "Bucket":        _co_chase["Bucket"],
                }).head(25)
                st.dataframe(_co_chase_disp, use_container_width=True, hide_index=True)
                if len(_co_chase) > 25:
                    st.caption(f"Showing the 25 most overdue of {len(_co_chase)} overdue invoices, "
                               f"totaling GHS {_co_chase['Outstanding'].sum():,.2f} outstanding.")
                else:
                    st.caption(f"{len(_co_chase)} overdue invoices, "
                               f"totaling GHS {_co_chase['Outstanding'].sum():,.2f} outstanding.")
            else:
                st.success("No overdue invoices as of week-end, everything outstanding isn't due yet.")
        else:
            st.success("No outstanding receivables as of week-end.")
        card_close()

        # ── SKU performance ──────────────────────────────────────────────────────
        card_open("SKU Performance This Week",
                                f"{_co_il_cost['Sku'].nunique()} distinct SKUs · "
                                f"{int(_co_il_cost['Quantity'].sum())} units sold")
        # Cost/margin columns intentionally left out here -- gross margin is a monthly
        # figure by agreement (to properly account for Zipline sales), not weekly.
        _sku_tbl = (_co_il_cost.groupby("Sku").agg(
            Units=("Quantity", "sum"), Revenue=("Line Revenue", "sum"),
        ).reset_index())
        if len(_sku_tbl):
            _sku_tbl = _sku_tbl.sort_values("Revenue", ascending=False)

            _sku_fig = go.Figure(go.Bar(
                x=_sku_tbl["Revenue"], y=_sku_tbl["Sku"], orientation="h",
                marker=bar_marker(BRAND_GREEN),
                text=_sku_tbl["Revenue"].apply(lambda v: f"GHS {v:,.0f}"), textposition="outside",
            ))
            _sku_fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                   margin=dict(t=10, b=10, l=10, r=40), height=max(160, 34 * len(_sku_tbl)),
                                   font=dict(family="Inter, sans-serif", size=12),
                                   xaxis=dict(gridcolor="#f3f4f6", range=[0, _sku_tbl["Revenue"].max() * 1.2]),
                                   yaxis=dict(autorange="reversed"))
            st.plotly_chart(_sku_fig, use_container_width=True, config=CHART_CFG)

            _sku_disp = pd.DataFrame({
                "SKU":        _sku_tbl["Sku"],
                "Units Sold": _sku_tbl["Units"].astype(int),
                "Revenue":    _sku_tbl["Revenue"].apply(lambda x: f"GHS {x:,.2f}"),
            })
            st.dataframe(_sku_disp, use_container_width=True, hide_index=True)
        else:
            st.info("No line-item data for this week.")
        card_close()

        # ── Discounts given ──────────────────────────────────────────────────────
        card_open("Discounts Given This Week")
        _disc_tbl = inv_wk[inv_wk["Discount"].fillna(0) > 0][["ID", "Total Order Value", "Discount", "Discountedvalue"]].copy()
        if len(_disc_tbl):
            _disc_tbl["Discount Given"] = _disc_tbl["Total Order Value"] - _disc_tbl["Discountedvalue"]
            _disc_tbl = _disc_tbl.sort_values("Discount Given", ascending=False)
            _disc_disp = pd.DataFrame({
                "Invoice ID":     _disc_tbl["ID"],
                "Pre-Discount":   _disc_tbl["Total Order Value"].apply(lambda x: f"GHS {x:,.2f}"),
                "Discount %":     _disc_tbl["Discount"].apply(lambda x: f"{x:.0f}%"),
                "Discount Given": _disc_tbl["Discount Given"].apply(lambda x: f"GHS {x:,.2f}"),
                "Net Invoiced":   _disc_tbl["Discountedvalue"].apply(lambda x: f"GHS {x:,.2f}"),
            })
            st.dataframe(_disc_disp, use_container_width=True, hide_index=True)
            st.caption(f"{len(_disc_tbl)} of {len(inv_wk)} invoices this week had a discount applied, "
                       f"totaling GHS {_disc_tbl['Discount Given'].sum():,.2f}.")
        else:
            st.success("No discounts were given this week.")
        card_close()

        # ── Business Read — patterns computed from the data, not written commentary ──
        section_label("Business Read")

        _insights = []

        # 1. Monthly attainment landing suspiciously close to exactly 100%, repeatedly
        _mo_target_path = f"{DATA}/revenue_target.csv"
        if os.path.exists(_mo_target_path):
            _mo_target = pd.read_csv(_mo_target_path)
            _mo_rev = inv_scoped.copy()
            _mo_rev["Month"] = _mo_rev["Created At"].dt.to_period("M").astype(str)
            _mo_g = _mo_rev.groupby("Month")["Discountedvalue"].sum().reset_index()
            _mo_m = _mo_g.merge(_mo_target, on="Month", how="inner").sort_values("Month")
            _mo_m["Attain"] = _mo_m["Discountedvalue"] / _mo_m["Target"] * 100
            _mo_m["Near100"] = (_mo_m["Attain"] - 100).abs() <= 1.0
            _cur, _best = [], []
            for _, r in _mo_m.iterrows():
                _cur = _cur + [r["Month"]] if r["Near100"] else []
                _best = _cur if len(_cur) > len(_best) else _best
            if len(_best) >= 3:
                _insights.append(("🎯", "Check how targets are set",
                    f"{len(_best)} months in a row ({_best[0]} to {_best[-1]}) landed within one point of "
                    f"exactly 100% of target. That's an unusual pattern for independently-set targets, worth "
                    f"confirming those months' targets were fixed in advance, not derived from the actuals "
                    f"afterward. If they were, 'hitting target' those months isn't a real performance signal.",
                    "Ask whoever sets monthly targets whether those months' numbers were fixed before the "
                    "month started. If any were adjusted after seeing early results, flag it as a "
                    "target-setting process fix, not a result to report as on-target."))

        # 2. Weekly attainment swinging wildly even when the month closes near 100%
        if len(_co_target):
            _wk_rev_all = inv_scoped.groupby("Week")["Discountedvalue"].sum().reset_index()
            _wk_m = _wk_rev_all.merge(_co_target, on="Week", how="inner")
            _wk_m = _wk_m[_wk_m["Target"] > 0]
            _wk_m["Attain"] = _wk_m["Discountedvalue"] / _wk_m["Target"] * 100
            _wk_recent = _wk_m.sort_values("Week").tail(10)
            if len(_wk_recent) >= 5:
                _wmin, _wmax = _wk_recent["Attain"].min(), _wk_recent["Attain"].max()
                if _wmax - _wmin > 150:
                    _insights.append(("📉", "Weekly volatility is high",
                        f"Over the last {len(_wk_recent)} weeks, attainment ranged from {_wmin:.0f}% to "
                        f"{_wmax:.0f}% of target, even in months that closed near 100%. Revenue is landing "
                        f"unevenly week to week, which makes weekly cash and stock planning harder than the "
                        f"monthly trend alone suggests.",
                        "Check whether a small number of large orders are driving the swings. If so, "
                        "consider staggered restock cycles or standing orders with the largest few "
                        "customers, so revenue lands more evenly week to week instead of in bursts."))

        # 3. AR sitting in the 31-90 day danger zone for the selected week
        if len(_co_ar_detail):
            _danger_total = _co_ar_detail[_co_ar_detail["Bucket"].isin(
                ["31, 60 days overdue", "61, 90 days overdue"])]["Outstanding"].sum()
            if _danger_total > 0:
                _insights.append(("🕒", "Collections danger zone",
                    f"GHS {_danger_total:,.2f} is currently 31, 90 days overdue as of this week, still "
                    f"realistically collectible, but starting to be at risk of aging into the 90+ bucket. "
                    f"This is the priority slice of the AR Aging chase list above.",
                    "Work the 31, 90 day invoices in the AR Aging chase list this week, before they roll "
                    "into the 90+ bucket, where recovery odds drop sharply."))

        # 4. Segment tagging coverage limiting how much the Agrovet KPIs really describe
        _agro_tagged_n, _agro_total_n = len(_co_agro_ids), len(rc)
        _agro_untagged_active_n = rc[rc["Segment Type"].isna() &
                                     rc["ID"].isin(set(inv_scoped["Customer ID"].dropna()))].shape[0]
        if _agro_total_n and _agro_tagged_n / _agro_total_n < 0.5:
            if _agro_untagged_active_n > 0:
                _insights.append(("🏷️", "Segment tagging gap -- smaller than it first looks",
                    f"Only {_agro_tagged_n} of {_agro_total_n} Ghana retail centres "
                    f"({_agro_tagged_n/_agro_total_n*100:.0f}%) are tagged 'Agrovet' in the system. Most of "
                    f"the untagged records have never actually ordered, though -- only "
                    f"{_agro_untagged_active_n} untagged accounts have placed an order this year. Tagging "
                    f"those specific accounts would close most of the real gap.",
                    f"Have whoever manages the retail centre records tag the {_agro_untagged_active_n} "
                    "untagged accounts that have actually ordered -- a short list, not a full registry "
                    "cleanup. The remaining untagged records appear dormant and can wait."))
            else:
                _insights.append(("🏷️", "Segment tagging gap doesn't affect this year's numbers",
                    f"Only {_agro_tagged_n} of {_agro_total_n} Ghana retail centres "
                    f"({_agro_tagged_n/_agro_total_n*100:.0f}%) are tagged 'Agrovet', but every customer "
                    f"who has actually ordered in 2026 is already tagged -- the untagged records are all "
                    f"dormant accounts with no orders this year.",
                    "No action needed for current reporting. Worth tagging the dormant records eventually "
                    "for registry hygiene, but it won't change any Agrovet figure on this page today."))

        if _insights:
            for _icon, _title, _text, _action in _insights:
                st.markdown(
                    f'<div style="background:{_T["card_bg"]};backdrop-filter:blur(14px);'
                    f'border:1px solid {_T["card_border"]};border-left:4px solid {BRAND_GOLD};'
                    f'border-radius:12px;padding:14px 18px;margin-bottom:10px">'
                    f'<div style="font-weight:700;color:{_T["text_heading"]};margin-bottom:4px">{_icon} {_title}</div>'
                    f'<div style="font-size:13px;color:{_T["text_body"]};margin-bottom:10px">{_text}</div>'
                    f'<div style="display:flex;gap:8px;padding-top:10px;border-top:1px solid {_T["hr_color"]}">'
                    f'<span style="font-size:11px;font-weight:700;text-transform:uppercase;'
                    f'letter-spacing:0.5px;color:{BRAND_GOLD};white-space:nowrap">Suggested action</span>'
                    f'<span style="font-size:13px;color:{_T["text_heading"]}">{_action}</span></div>'
                    f'</div>',
                    unsafe_allow_html=True)
        else:
            st.info("No notable patterns flagged for the current data window.")


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — YTD REVIEW
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "YTD Review":
    _yr_terms_days = DSO_TERMS_DAYS
    _yr_inv = inv_scoped.copy()
    _yr_months = sorted(_yr_inv["Month"].dropna().unique())
    # "As of" is today's real date, not the latest invoice's timestamp -- a YTD report
    # reads oddly saying "as of 21 Aug" when it's actually being viewed on the 27th, and
    # AR aging should measure days overdue against today, not against however recently
    # the last invoice happened to land.
    _yr_as_of = pd.Timestamp.now(tz="UTC")
    _yr_as_of_label = _yr_as_of.strftime("%d %b %Y")
    _yr_latest_invoice = _yr_inv["Created At"].max()
    _yr_month_label = month_label(_yr_months[-1]) + " " + _yr_months[-1].split("-")[0] if _yr_months else "N/A"

    def _yr_text(html, muted=True, weight=400, size=13, margin="4px 0 10px"):
        # Plain st.markdown/st.caption use Streamlit's own fixed (light-theme) text
        # color regardless of the in-app dark-mode toggle, which goes invisible on
        # our dark cards -- route this page's prose through theme tokens instead.
        color = _T["text_muted"] if muted else _T["text_heading"]
        st.markdown(f'<div style="font-size:{size}px;color:{color};font-weight:{weight};'
                    f'margin:{margin}">{html}</div>', unsafe_allow_html=True)

    _yr_lag_days = (_yr_as_of.normalize() - _yr_latest_invoice.normalize()).days if pd.notna(_yr_latest_invoice) else None
    _yr_lag_note = (f" (latest invoice on file: {_yr_latest_invoice.strftime('%d %b %Y')})"
                    if _yr_lag_days and _yr_lag_days >= 2 else "")
    _yr_text(f"Covering January – {_yr_month_label} · data as of {_yr_as_of_label}{_yr_lag_note} · "
             f"refreshes automatically as new data comes in, no manual regeneration needed")

    if not _yr_months:
        st.info("No invoice data available yet.")
    else:
        # ── 1. Revenue vs target ─────────────────────────────────────────────────
        _yr_mo_target_path = f"{DATA}/revenue_target.csv"
        _yr_mo_target = (pd.read_csv(_yr_mo_target_path) if os.path.exists(_yr_mo_target_path)
                         else pd.DataFrame(columns=["Month", "Target"]))
        _yr_mo = _yr_inv.groupby("Month")["Discountedvalue"].sum().reset_index()
        _yr_mo = _yr_mo.merge(_yr_mo_target, on="Month", how="left").sort_values("Month")
        _yr_mo["Attain"] = _yr_mo["Discountedvalue"] / _yr_mo["Target"] * 100
        _yr_mo["Orders"] = _yr_inv.groupby("Month").size().reindex(_yr_mo["Month"]).values
        _yr_mo["AOV"] = _yr_mo["Discountedvalue"] / _yr_mo["Orders"]
        _yr_mo["Month Label"] = _yr_mo["Month"].apply(month_label)
        _yr_is_partial_month = _yr_months[-1] == _yr_as_of.to_period("M").strftime("%Y-%m")

        # ── 2. Active Agrovets, new vs repeat ────────────────────────────────────
        # inv_scoped (and therefore _yr_inv) only holds 2026-onward rows -- computing
        # "first order" from it alone would wrongly call every January customer "new"
        # even if they'd been ordering since 2025. Pull full history just to establish
        # each customer's true first-ever order date.
        _yr_full_hist = pd.read_csv(f"{DATA}/invoice.csv")
        _yr_full_hist["Created At"] = pd.to_datetime(_yr_full_hist["Created At"], errors="coerce")
        _yr_full_hist = _yr_full_hist[_yr_full_hist["Country Code"] == "GH"].copy()
        _yr_full_f = pd.Series(True, index=_yr_full_hist.index)
        if "Order Type" in _yr_full_hist.columns: _yr_full_f &= (_yr_full_hist["Order Type"] == 1)
        if "Channel" in _yr_full_hist.columns: _yr_full_f &= (_yr_full_hist["Channel"] != "BufferPesa")
        if "Status" in _yr_full_hist.columns: _yr_full_f &= (_yr_full_hist["Status"] != 5)
        _yr_full_hist = _yr_full_hist[_yr_full_f].copy()
        _yr_true_first_order = _yr_full_hist.groupby("Customer ID")["Created At"].min()

        _yr_agro_ids = set(rc[rc["Segment Type"] == "Agrovet"]["ID"])
        _yr_cust_rows = []
        for m in _yr_months:
            sub = _yr_inv[_yr_inv["Month"] == m]
            custs = set(sub["Customer ID"].dropna())
            active_agro = len(custs & _yr_agro_ids)
            new_c = sum(1 for c in custs if pd.notna(_yr_true_first_order.get(c))
                        and _yr_true_first_order[c].to_period("M").strftime("%Y-%m") == m)
            _yr_cust_rows.append(dict(Month=m, Active=len(custs), ActiveAgro=active_agro,
                                      New=new_c, Repeat=len(custs) - new_c))
        _yr_cust_df = pd.DataFrame(_yr_cust_rows)
        _yr_cust_df["Month Label"] = _yr_cust_df["Month"].apply(month_label)
        _yr_n_customers_ytd = _yr_inv["Customer ID"].nunique()

        # ── 3. Repeat-order-rate cohorts (30-day) ────────────────────────────────
        _yr_fo = _yr_true_first_order.rename("first_order")
        _yr_merged = _yr_inv.merge(_yr_fo, on="Customer ID")
        _yr_merged["days_gap"] = (_yr_merged["Created At"] - _yr_merged["first_order"]).dt.days
        _yr_merged["first_month"] = _yr_merged["first_order"].dt.to_period("M").astype(str)
        _yr_cohort_rows = []
        for m in _yr_months:
            cohort_custs = _yr_merged[_yr_merged["first_month"] == m]["Customer ID"].unique()
            repeaters = _yr_merged[(_yr_merged["Customer ID"].isin(cohort_custs)) &
                                   (_yr_merged["days_gap"].between(1, 30))]["Customer ID"].nunique()
            n = len(cohort_custs)
            _yr_cohort_rows.append(dict(Month=m, CohortSize=n, Rate=(repeaters/n*100 if n else None)))
        _yr_cohort_df = pd.DataFrame(_yr_cohort_rows)
        _yr_cohort_df["Month Label"] = _yr_cohort_df["Month"].apply(month_label)

        # ── 4. Multi-SKU adoption trend ──────────────────────────────────────────
        _yr_il = il[il["Invoice ID"].isin(_yr_inv["ID"])]
        _yr_sku_per_order = _yr_il.groupby("Invoice ID")["Product ID"].nunique()
        _yr_inv_lines = _yr_inv[_yr_inv["ID"].isin(_yr_sku_per_order.index)][["ID", "Month"]].copy()
        _yr_inv_lines["SKUs"] = _yr_inv_lines["ID"].map(_yr_sku_per_order)
        _yr_msku_rows = []
        for m in _yr_months:
            sub = _yr_inv_lines[_yr_inv_lines["Month"] == m]
            n = len(sub)
            multi = int((sub["SKUs"] > 1).sum())
            _yr_msku_rows.append(dict(Month=m, Pct=(multi/n*100 if n else None)))
        _yr_msku_df = pd.DataFrame(_yr_msku_rows)
        _yr_msku_df["Month Label"] = _yr_msku_df["Month"].apply(month_label)

        # ── 5. Product mix ────────────────────────────────────────────────────────
        _yr_il_pm = _yr_il.merge(_yr_inv[["ID", "Month"]], left_on="Invoice ID", right_on="ID", how="left")
        _yr_il_pm = _yr_il_pm.merge(prod[["ID", "Sku", "Generic Name", "Brand Name"]],
                                    left_on="Product ID", right_on="ID", how="left", suffixes=("", "_p"))
        _yr_il_pm["Line Revenue"] = _yr_il_pm["Price"] * _yr_il_pm["Quantity"]
        _yr_il_pm["Product Name"] = _yr_il_pm["Generic Name"].fillna(_yr_il_pm["Brand Name"]).fillna(_yr_il_pm["Sku"])
        _yr_by_prod_month = _yr_il_pm.groupby(["Month", "Product Name"])["Line Revenue"].sum().reset_index()
        _yr_n_products_by_month = _yr_il_pm.groupby("Month")["Product Name"].nunique()
        _yr_top3_by_month = {}
        for m in _yr_months:
            sub = _yr_by_prod_month[_yr_by_prod_month["Month"] == m].sort_values("Line Revenue", ascending=False).head(3)
            tot = _yr_by_prod_month[_yr_by_prod_month["Month"] == m]["Line Revenue"].sum()
            _yr_top3_by_month[m] = [(r["Product Name"], r["Line Revenue"]/tot*100 if tot else 0) for _, r in sub.iterrows()]
        _yr_by_prod_ytd = _yr_il_pm.groupby("Product Name")["Line Revenue"].sum().sort_values(ascending=False)
        _yr_cost_cov_n, _yr_cost_cov_total = prod["Purchase Price"].notna().sum(), len(prod)
        # The catalogue-wide % above is dominated by SKUs that have never actually sold --
        # what matters for margin reliability is coverage among products that generated
        # real revenue this year.
        _yr_sold_ids = set(_yr_il_pm["Product ID"].dropna().unique())
        _yr_cost_cov_sold_total = len(_yr_sold_ids)
        _yr_cost_cov_sold_n = prod[prod["ID"].isin(_yr_sold_ids) & prod["Purchase Price"].notna()].shape[0]
        # Same logic for Agrovet tagging -- most untagged records have never ordered at all,
        # so the real gap is only the untagged accounts that are actually transacting.
        _yr_ordered_ids = set(_yr_inv["Customer ID"].dropna())
        _yr_agro_untagged = rc[rc["Segment Type"].isna()]
        _yr_agro_untagged_active_n = _yr_agro_untagged["ID"].isin(_yr_ordered_ids).sum()
        _yr_agro_note = (f"only {_yr_agro_untagged_active_n} untagged records have actually ordered this "
                        f"year, tagging those would close most of the real gap"
                        if _yr_agro_untagged_active_n > 0 else
                        "every customer who has actually ordered this year is already tagged, the "
                        "untagged records are all dormant, with no orders this year")
        _yr_agro_note_short = (f"missing on only {_yr_agro_untagged_active_n} customer records that have "
                              f"actually ordered, out of {len(rc)} total records on file"
                              if _yr_agro_untagged_active_n > 0 else
                              f"not missing on any customer that has actually ordered this year, all "
                              f"{len(_yr_agro_untagged)} untagged records are dormant, with no orders "
                              f"this year")

        # ── 6. Collections trend + DSO trend + AR aging ──────────────────────────
        _yr_coll_by_month = rep_scoped.groupby(rep_scoped["Created At"].dt.to_period("M").astype(str))["Amount"].sum()
        _yr_dso_rows = []
        _yr_data_end = max(inv_scoped["Created At"].max(), rep_scoped["Created At"].max())
        for m in _yr_months:
            period_end = pd.Period(m, freq="M").end_time.tz_localize("UTC")
            # Partial month: count the window back from the last data point, not month-end,
            # or the empty days shrink the sales base and inflate DSO.
            dso_asof = min(period_end, _yr_data_end)
            sales_win = inv_scoped[(inv_scoped["Created At"] > dso_asof - pd.Timedelta(days=DSO_WINDOW_DAYS)) &
                                 (inv_scoped["Created At"] <= period_end)]["Discountedvalue"].sum()
            ia = inv_scoped[inv_scoped["Created At"] <= period_end][["ID", "Discountedvalue"]]
            ra = rep_scoped[rep_scoped["Created At"] <= period_end].groupby("Invoice ID")["Amount"].sum()
            ia = ia.merge(ra.rename("Repaid"), left_on="ID", right_index=True, how="left")
            ia["Repaid"] = ia["Repaid"].fillna(0)
            ar = (ia["Discountedvalue"] - ia["Repaid"]).clip(lower=0).sum()
            dso = ar / sales_win * DSO_WINDOW_DAYS if sales_win else None
            rev = _yr_mo[_yr_mo["Month"] == m]["Discountedvalue"].iloc[0]
            coll = _yr_coll_by_month.get(m, 0)
            _yr_dso_rows.append(dict(Month=m, AR=ar, DSO=dso, Revenue=rev, Collected=coll))
        _yr_dso_df = pd.DataFrame(_yr_dso_rows)
        _yr_dso_df["Month Label"] = _yr_dso_df["Month"].apply(month_label)
        _yr_dso_df["DaysBeyondTerms"] = _yr_dso_df["DSO"] - _yr_terms_days

        _yr_ia_now = inv_scoped[["ID", "Discountedvalue", "Due Date"]].copy()
        _yr_ra_now = rep_scoped.groupby("Invoice ID")["Amount"].sum()
        _yr_ia_now = _yr_ia_now.merge(_yr_ra_now.rename("Repaid"), left_on="ID", right_index=True, how="left")
        _yr_ia_now["Repaid"] = _yr_ia_now["Repaid"].fillna(0)
        _yr_ia_now["Outstanding"] = (_yr_ia_now["Discountedvalue"] - _yr_ia_now["Repaid"]).clip(lower=0)
        _yr_ia_now = _yr_ia_now[_yr_ia_now["Outstanding"] > 0.01].copy()
        _yr_ia_now["Days Overdue"] = (_yr_as_of - _yr_ia_now["Due Date"]).dt.days
        def _yr_bucket(d):
            if pd.isna(d): return "No due date"
            if d < 0: return "Not yet due"
            if d <= 30: return "0–30 days"
            if d <= 60: return "31–60 days"
            if d <= 90: return "61–90 days"
            return "90+ days"
        _yr_ia_now["Bucket"] = _yr_ia_now["Days Overdue"].apply(_yr_bucket)
        _yr_bucket_order = ["Not yet due", "0–30 days", "31–60 days", "61–90 days", "90+ days", "No due date"]
        _yr_aging = (_yr_ia_now.groupby("Bucket")["Outstanding"].agg(Total="sum", Count="count")
                     .reindex(_yr_bucket_order).dropna(how="all"))
        _yr_aging = _yr_aging[_yr_aging["Count"].fillna(0) > 0]
        _yr_total_ar = _yr_ia_now["Outstanding"].sum()

        # ── 7. Concentration ──────────────────────────────────────────────────────
        _yr_by_cust = _yr_inv.groupby("Customer ID")["Discountedvalue"].sum().sort_values(ascending=False)
        _yr_top5_pct = _yr_by_cust.head(5).sum() / _yr_by_cust.sum() * 100 if len(_yr_by_cust) else 0
        _yr_top10_pct = _yr_by_cust.head(10).sum() / _yr_by_cust.sum() * 100 if len(_yr_by_cust) else 0

        # ══════════════════════════════════════════════════════════════════════
        # ON-SCREEN RENDER
        # ══════════════════════════════════════════════════════════════════════

        # ── Download ─────────────────────────────────────────────────────────
        if _PDF_AVAIL:
            def _build_ytd_pdf():
                pdf = YTDReportPDF()
                pdf.report_month_label = _yr_month_label
                pdf.add_page()
                pdf.title_block(_yr_as_of_label)
                pdf.section_title("Executive Summary")
                pdf.body(f"This review covers TribeCo Ghana's commercial performance from January through "
                         f"{_yr_month_label} (data as of {_yr_as_of_label}{_yr_lag_note}"
                         f"{'; latest month is partial, not yet closed' if _yr_is_partial_month else ''}). "
                         f"Generated on demand from the live dashboard, every figure is computed, not estimated.")
                _last_attain = _yr_mo["Attain"].iloc[-1] if pd.notna(_yr_mo["Attain"].iloc[-1]) else None
                pdf.callout("Revenue trajectory",
                    f"Attainment across the year: " +
                    ", ".join(f"{r['Month Label']} {r['Attain']:.0f}%" for _, r in _yr_mo.iterrows() if pd.notna(r["Attain"])) + ".")
                _last_dso = _yr_dso_df["DSO"].iloc[-1] if len(_yr_dso_df) else None
                _last_dbt = _yr_dso_df["DaysBeyondTerms"].iloc[-1] if len(_yr_dso_df) else None
                if _last_dso is not None:
                    pdf.callout(f"Collections speed vs. the {_yr_terms_days}-day term",
                        f"Standard terms are {_yr_terms_days} days. Latest DSO is {_last_dso:.0f} days "
                        f"({_last_dbt:+.0f} days beyond terms). Full month-by-month detail is in Section 5.",
                        pdf._RED)
                pdf.callout("Two data gaps, smaller in practice than they first look",
                    f"Cost data covers {_yr_cost_cov_n} of {_yr_cost_cov_total} catalogue entries "
                    f"({_yr_cost_cov_n/_yr_cost_cov_total*100:.0f}%), but most of the catalogue has never "
                    f"sold, among the {_yr_cost_cov_sold_total} products actually sold this year, "
                    f"{_yr_cost_cov_sold_n} have cost data ({_yr_cost_cov_sold_n/_yr_cost_cov_sold_total*100:.0f}%). "
                    f"Similarly, {len(_yr_agro_ids)} of {len(rc)} Ghana customer records "
                    f"({len(_yr_agro_ids)/len(rc)*100:.0f}%) are tagged 'Agrovet', but {_yr_agro_note}.",
                    pdf._AMBER)

                pdf.section_title("1. Commercial Performance, Revenue vs Target")
                _rows = [(r["Month Label"], f"GHS {r['Discountedvalue']:,.0f}",
                         f"GHS {r['Target']:,.0f}" if pd.notna(r["Target"]) else "n/a",
                         (f"{r['Attain']:.1f}%" if pd.notna(r["Attain"]) else "n/a") +
                         (" (partial)" if r["Month"] == _yr_months[-1] and _yr_is_partial_month else ""))
                        for _, r in _yr_mo.iterrows()]
                pdf.table(["Month", "Revenue", "Target", "Attainment"], _rows, [35, 50, 50, 58])
                pdf.chart(_grouped_bar_png(_yr_mo, "Month Label",
                    [("Discountedvalue", "Revenue"), ("Target", "Target")],
                    title="Revenue vs Target", colors=["#1f7a4d", "#eab308"],
                    xlabel="Month", ylabel="GHS", label_fmt="{:,.0f}"))

                pdf.section_title("2. Customer and Order Behaviour")
                pdf.sub_title("Active Agrovets, new vs. repeat, AOV")
                _rows = [(month_label(r["Month"]), r["ActiveAgro"], r["New"], r["Repeat"],
                         f"GHS {_yr_mo[_yr_mo['Month']==r['Month']]['AOV'].iloc[0]:,.0f}")
                        for _, r in _yr_cust_df.iterrows()]
                pdf.table(["Month", "Active Agrovets", "New", "Repeat", "AOV"], _rows, [30, 40, 25, 30, 68])
                pdf.chart(_grouped_bar_png(_yr_cust_df, "Month Label",
                    [("New", "New"), ("Repeat", "Repeat")],
                    title="New vs Repeat Customers", colors=["#c9975a", "#1f7a4d"],
                    xlabel="Month", ylabel="Customers", label_fmt="{:,.0f}"))
                pdf.sub_title("Repeat-order rate (30-day), by cohort month")
                _rows = [(month_label(r["Month"]), int(r["CohortSize"]),
                         f"{r['Rate']:.0f}%" if pd.notna(r["Rate"]) else "n/a")
                        for _, r in _yr_cohort_df.iterrows()]
                pdf.table(["Cohort Month", "New Customers", "Repeat Rate (30d)"], _rows, [50, 60, 73])
                pdf.chart(_bar_png(_yr_cohort_df["Month Label"], _yr_cohort_df["Rate"].fillna(0),
                    title="Repeat Rate by Cohort Month", color="#1f7a4d",
                    xlabel="Cohort Month", ylabel="Repeat Rate (%)", label_fmt="{:.0f}%"))
                pdf.callout("Small cohorts, read with caution",
                    "Some monthly cohorts have very few new customers; a rate built on 1-2 people can "
                    "swing from 0% to 100% on a single account.", pdf._AMBER)

                pdf.section_title("3. Multi-SKU Adoption")
                _rows = [(r["Month Label"], f"{r['Pct']:.1f}%" if pd.notna(r["Pct"]) else "n/a")
                        for _, r in _yr_msku_df.iterrows()]
                pdf.table(["Month", "Adoption %"], _rows, [90, 103])
                pdf.chart(_bar_png(_yr_msku_df["Month Label"], _yr_msku_df["Pct"].fillna(0),
                    title="Multi-SKU Adoption", color="#1f7a4d",
                    xlabel="Month", ylabel="Adoption (%)", label_fmt="{:.0f}%"))

                pdf.section_title("4. Product Portfolio Mix")
                _rows = [(month_label(m), int(_yr_n_products_by_month.get(m, 0)),
                         ", ".join(f"{n} ({p:.0f}%)" for n, p in _yr_top3_by_month.get(m, [])))
                        for m in _yr_months]
                pdf.table(["Month", "Distinct Products", "Top 3 by Revenue Share"], _rows, [25, 35, 133])
                _pdf_top_n = 6
                _pdf_pie_data = _yr_by_prod_ytd.head(_pdf_top_n)
                _pdf_other = _yr_by_prod_ytd.iloc[_pdf_top_n:].sum()
                _pdf_pie_labels = list(_pdf_pie_data.index) + (["Other"] if _pdf_other > 0 else [])
                _pdf_pie_values = list(_pdf_pie_data.values) + ([_pdf_other] if _pdf_other > 0 else [])
                pdf.chart(_pie_png(_pdf_pie_labels, _pdf_pie_values, title="YTD Revenue Share by Product"), w=140)
                pdf.callout("Coverage caveat",
                    f"{_yr_cost_cov_sold_n} of the {_yr_cost_cov_sold_total} products actually sold this "
                    f"year ({_yr_cost_cov_sold_n/_yr_cost_cov_sold_total*100:.0f}%) have cost data, revenue "
                    f"mix above is reliable, margin-by-product would only describe part of it.", pdf._AMBER)

                pdf.section_title("5. Collections and Receivables")
                pdf.callout("No collections budget exists", "Figures below are trends, not attainment "
                            "against a plan.", pdf._AMBER)
                pdf.sub_title(f"DSO vs. the {_yr_terms_days}-day term, month-end snapshots")
                _rows = [(r["Month Label"], f"GHS {r['AR']:,.0f}",
                         f"{r['DSO']:.0f} days" if pd.notna(r["DSO"]) else "n/a",
                         f"{r['DaysBeyondTerms']:+.0f} days" if pd.notna(r["DaysBeyondTerms"]) else "n/a")
                        for _, r in _yr_dso_df.iterrows()]
                pdf.table(["Month-End", "Outstanding AR", "DSO", "Beyond Terms"], _rows, [30, 50, 45, 78])
                pdf.chart(_bar_with_threshold_png(_yr_dso_df["Month Label"], _yr_dso_df["DSO"].fillna(0),
                    _yr_terms_days, threshold_label=f"{_yr_terms_days}-day term", title=f"DSO vs {_yr_terms_days}-Day Term",
                    xlabel="Month", ylabel="Days", label_fmt="{:.0f}d"))
                pdf.sub_title("Monthly collections vs. that month's revenue")
                _rows = [(r["Month Label"], f"GHS {r['Revenue']:,.0f}", f"GHS {r['Collected']:,.0f}",
                         f"{r['Collected']/r['Revenue']*100:.0f}%" if r["Revenue"] else "n/a")
                        for _, r in _yr_dso_df.iterrows()]
                pdf.table(["Month", "Revenue", "Collected", "Ratio"], _rows, [30, 55, 55, 53])
                pdf.chart(_grouped_bar_png(_yr_dso_df, "Month Label",
                    [("Revenue", "Invoiced"), ("Collected", "Collected")],
                    title="Monthly Collections vs Revenue", colors=["#c7d2fe", "#1f7a4d"],
                    xlabel="Month", ylabel="GHS", label_fmt="{:,.0f}"))
                pdf.sub_title(f"Receivables ageing as of {_yr_as_of_label}")
                _rows = [(b, f"GHS {r['Total']:,.0f}", int(r["Count"])) for b, r in _yr_aging.iterrows()]
                pdf.table(["Bucket", "Outstanding", "Invoices"], _rows, [70, 63, 60])
                if len(_yr_aging):
                    pdf.chart(_hbar_png(_yr_aging["Total"], _yr_aging.index,
                        title="Receivables Ageing", color="#1f7a4d",
                        xlabel="Outstanding (GHS)", ylabel="Ageing Bucket", label_fmt="GHS {:,.0f}"))
                pdf.callout("Snapshot only", "This ageing view is a current snapshot; treat it as the "
                            "baseline for tracking the trend going forward.", pdf._AMBER)

                pdf.section_title("6. Key Observations")
                pdf.callout("Customer concentration",
                    f"Top 5 customers = {_yr_top5_pct:.1f}% of YTD revenue; top 10 = {_yr_top10_pct:.1f}%, "
                    f"out of {_yr_n_customers_ytd} customers who ordered at all this year.")
                pdf.callout("Data coverage",
                    f"Cost data covers {_yr_cost_cov_sold_n/_yr_cost_cov_sold_total*100:.0f}% of products "
                    f"actually sold this year ({_yr_cost_cov_n/_yr_cost_cov_total*100:.0f}% of the full, "
                    f"mostly-unsold catalogue). Agrovet tagging is {_yr_agro_note_short}.",
                    pdf._AMBER)
                return bytes(pdf.output())

            _yr_pdf_bytes = _build_ytd_pdf()
            _yr_fname = f"Ghana_YTD_Commercial_Review_{_yr_month_label.replace(' ', '')}.pdf"
            st.download_button("⬇ Download Full YTD Report Here for your review",
                              data=_yr_pdf_bytes, file_name=_yr_fname, mime="application/pdf",
                              type="primary", use_container_width=True)
            _yr_text("This button always reflects the current data, next month, just come back to this "
                     "page and download again. No need to regenerate anything manually.")
        else:
            st.warning("PDF export isn't available in this environment (fpdf2/matplotlib not installed).")

        # ── Executive Summary ────────────────────────────────────────────────────
        section_label("Executive Summary")
        _yr_summary = [
            ("🎯", "Revenue trajectory", BRAND_GOLD,
             f"Attainment: " + ", ".join(f"{r['Month Label']} {r['Attain']:.0f}%"
                                         for _, r in _yr_mo.iterrows() if pd.notna(r["Attain"]))),
        ]
        if len(_yr_dso_df) and pd.notna(_yr_dso_df["DSO"].iloc[-1]):
            _yr_summary.append(("⏱️", f"Collections vs. {_yr_terms_days}-day terms", "#dc2626",
                f"Latest DSO is {_yr_dso_df['DSO'].iloc[-1]:.0f} days "
                f"({_yr_dso_df['DaysBeyondTerms'].iloc[-1]:+.0f} days beyond the standard "
                f"{_yr_terms_days}-day term)."))
        _yr_summary.append(("🏷️", "Two data gaps, smaller in practice than they first look", "#bf6908",
            f"Cost data covers {_yr_cost_cov_n/_yr_cost_cov_total*100:.0f}% of the full catalogue, but most "
            f"of it has never sold, among products actually sold this year, coverage is "
            f"{_yr_cost_cov_sold_n/_yr_cost_cov_sold_total*100:.0f}% ({_yr_cost_cov_sold_n} of "
            f"{_yr_cost_cov_sold_total}). Similarly, {len(_yr_agro_ids)} of {len(rc)} customer records "
            f"({len(_yr_agro_ids)/len(rc)*100:.0f}%) are tagged 'Agrovet', but {_yr_agro_note}."))
        for _icon, _title, _color, _text in _yr_summary:
            st.markdown(
                f'<div style="background:{_T["card_bg"]};backdrop-filter:blur(14px);'
                f'border:1px solid {_T["card_border"]};border-left:4px solid {_color};'
                f'border-radius:12px;padding:14px 18px;margin-bottom:10px">'
                f'<div style="font-weight:700;color:{_T["text_heading"]};margin-bottom:4px">{_icon} {_title}</div>'
                f'<div style="font-size:13px;color:{_T["text_body"]}">{_text}</div></div>',
                unsafe_allow_html=True)

        # ── 1. Revenue vs Target ─────────────────────────────────────────────────
        card_open("1. Commercial Performance, Revenue vs Target",
                                "Monthly revenue against target, January to date")
        _yr_fig1 = go.Figure()
        _yr_fig1.add_bar(x=_yr_mo["Month Label"], y=_yr_mo["Discountedvalue"], marker=bar_marker(BRAND_GREEN), name="Revenue")
        _yr_fig1.add_bar(x=_yr_mo["Month Label"], y=_yr_mo["Target"], marker=bar_marker("#eab308"), name="Target")
        _yr_fig1.update_layout(**white_layout(300))
        _yr_fig1.update_layout(barmode="group", legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(_yr_fig1, use_container_width=True, config=CHART_CFG)
        st.dataframe(pd.DataFrame({
            "Month": _yr_mo["Month Label"],
            "Revenue": _yr_mo["Discountedvalue"].apply(lambda x: f"GHS {x:,.2f}"),
            "Target": _yr_mo["Target"].apply(lambda x: f"GHS {x:,.2f}" if pd.notna(x) else "n/a"),
            "Attainment": _yr_mo["Attain"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "n/a"),
        }), use_container_width=True, hide_index=True)
        card_close()

        # ── 2. Customer & Order Behaviour ─────────────────────────────────────────
        card_open("2. Customer and Order Behaviour",
                                "Active Agrovets, new vs. repeat customers, average order value")
        _yr_fig2 = go.Figure()
        _yr_fig2.add_bar(x=_yr_cust_df["Month Label"], y=_yr_cust_df["New"], marker=bar_marker(BRAND_GOLD), name="New")
        _yr_fig2.add_bar(x=_yr_cust_df["Month Label"], y=_yr_cust_df["Repeat"], marker=bar_marker(BRAND_GREEN), name="Repeat")
        _yr_fig2.update_layout(**white_layout(300))
        _yr_fig2.update_layout(barmode="stack", legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(_yr_fig2, use_container_width=True, config=CHART_CFG)
        st.dataframe(pd.DataFrame({
            "Month": _yr_cust_df["Month Label"], "Active Agrovets": _yr_cust_df["ActiveAgro"],
            "New": _yr_cust_df["New"], "Repeat": _yr_cust_df["Repeat"],
            "AOV": _yr_mo.set_index("Month").loc[_yr_cust_df["Month"], "AOV"].apply(lambda x: f"GHS {x:,.0f}").values,
        }), use_container_width=True, hide_index=True)
        _yr_text(f"{_yr_n_customers_ytd} distinct customers have ordered at all in 2026.")
        with st.expander("Repeat-order rate by cohort month (small samples, read with caution)"):
            st.dataframe(pd.DataFrame({
                "Cohort Month": _yr_cohort_df["Month"].apply(month_label),
                "New Customers": _yr_cohort_df["CohortSize"],
                "Repeat Rate (30d)": _yr_cohort_df["Rate"].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "n/a"),
            }), use_container_width=True, hide_index=True)
        card_close()

        # ── 3. Multi-SKU Adoption ─────────────────────────────────────────────────
        card_open("3. Multi-SKU Adoption", "Share of orders with 2+ distinct products")
        _yr_fig3 = go.Figure(go.Bar(x=_yr_msku_df["Month Label"], y=_yr_msku_df["Pct"], marker=bar_marker(BRAND_GREEN),
                                    text=_yr_msku_df["Pct"].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else ""),
                                    textposition="outside"))
        _yr_fig3.update_layout(**white_layout(280))
        st.plotly_chart(_yr_fig3, use_container_width=True, config=CHART_CFG)
        card_close()

        # ── 4. Product Portfolio Mix ──────────────────────────────────────────────
        card_open("4. Product Portfolio Mix", "Share of YTD revenue by product")
        _yr_pcol1, _yr_pcol2 = st.columns([2, 3])
        with _yr_pcol1:
            _yr_top_n = 6
            _yr_pie_data = _yr_by_prod_ytd.head(_yr_top_n)
            _yr_other = _yr_by_prod_ytd.iloc[_yr_top_n:].sum()
            _yr_pie_labels = list(_yr_pie_data.index) + (["Other"] if _yr_other > 0 else [])
            _yr_pie_values = list(_yr_pie_data.values) + ([_yr_other] if _yr_other > 0 else [])
            _yr_pie = go.Figure(go.Pie(labels=_yr_pie_labels, values=_yr_pie_values, hole=0.5,
                                       marker=dict(colors=[BRAND_GREEN_DEEP, BRAND_GREEN, BRAND_GREEN_LIGHT,
                                                          BRAND_GOLD, BRAND_GOLD_LIGHT, "#8a9d5e", "#c7d2c2"])))
            _yr_pie.update_traces(textposition="inside", textinfo="percent")
            _yr_pie.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  margin=dict(t=10, b=10, l=10, r=10), height=280,
                                  font=dict(family="Inter, sans-serif", size=11, color=CHART_FONT),
                                  legend=dict(orientation="h", y=-0.15, font=dict(size=9)))
            st.plotly_chart(_yr_pie, use_container_width=True, config=CHART_CFG)
        with _yr_pcol2:
            st.dataframe(pd.DataFrame({
                "Month": [month_label(m) for m in _yr_months],
                "Distinct Products": [int(_yr_n_products_by_month.get(m, 0)) for m in _yr_months],
                "Top 3 by Revenue Share": [", ".join(f"{n} ({p:.0f}%)" for n, p in _yr_top3_by_month.get(m, []))
                                          for m in _yr_months],
            }), use_container_width=True, hide_index=True)
        _yr_text(f"Product revenue mix is reliable (built from actual sale prices). Margin-by-product would "
                 f"only cover {_yr_cost_cov_sold_n} of the {_yr_cost_cov_sold_total} products actually sold "
                 f"this year ({_yr_cost_cov_sold_n/_yr_cost_cov_sold_total*100:.0f}%) with cost data on file.")
        card_close()

        # ── 5. Collections and Receivables ────────────────────────────────────────
        card_open("5. Collections and Receivables",
                                "No collections budget exists, shown as trends, not attainment")
        _yr_col_c1, _yr_col_c2 = st.columns(2)
        with _yr_col_c1:
            _yr_text(f"<b>DSO vs. the {_yr_terms_days}-day term</b>", muted=False, size=14, margin="4px 0 8px")
            _yr_fig5 = go.Figure(go.Bar(
                x=_yr_dso_df["Month Label"], y=_yr_dso_df["DSO"],
                marker=bar_marker(BRAND_GREEN),
                text=_yr_dso_df["DSO"].apply(lambda x: f"{x:.0f}d" if pd.notna(x) else ""), textposition="outside"))
            _yr_fig5.add_hline(y=_yr_terms_days, line_dash="dot", line_color=BRAND_GOLD,
                               annotation_text=f"{_yr_terms_days}-day term")
            _yr_fig5.update_layout(**white_layout(280))
            st.plotly_chart(_yr_fig5, use_container_width=True, config=CHART_CFG)
        with _yr_col_c2:
            _yr_text("<b>Monthly collections vs. that month's revenue</b>", muted=False, size=14, margin="4px 0 8px")
            _yr_fig6 = go.Figure()
            _yr_fig6.add_bar(x=_yr_dso_df["Month Label"], y=_yr_dso_df["Revenue"], marker=bar_marker("#e0e7ff", "rgba(255,255,255,0.9)"), name="Invoiced")
            _yr_fig6.add_bar(x=_yr_dso_df["Month Label"], y=_yr_dso_df["Collected"], marker=bar_marker(BRAND_GREEN), name="Collected")
            _yr_fig6.update_layout(barmode="overlay", **white_layout(280), legend=dict(orientation="h", y=-0.3))
            st.plotly_chart(_yr_fig6, use_container_width=True, config=CHART_CFG)
        st.dataframe(pd.DataFrame({
            "Month-End": _yr_dso_df["Month Label"],
            "Outstanding AR": _yr_dso_df["AR"].apply(lambda x: f"GHS {x:,.2f}"),
            "DSO": _yr_dso_df["DSO"].apply(lambda x: f"{x:.1f} days" if pd.notna(x) else "n/a"),
            "Beyond Terms": _yr_dso_df["DaysBeyondTerms"].apply(lambda x: f"{x:+.1f} days" if pd.notna(x) else "n/a"),
        }), use_container_width=True, hide_index=True)
        _yr_text(f"<b>Receivables ageing as of {_yr_as_of_label}</b>, GHS {_yr_total_ar:,.2f} outstanding",
                 muted=False, size=14, margin="4px 0 8px")
        if len(_yr_aging):
            _yr_age_colors = {"Not yet due": "#94a3b8", "0–30 days": "#16a34a", "31–60 days": "#eab308",
                              "61–90 days": "#f97316", "90+ days": "#dc2626", "No due date": "#94a3b8"}
            _yr_fig7 = go.Figure(go.Bar(
                x=_yr_aging["Total"], y=_yr_aging.index, orientation="h",
                marker=dict(color=[_yr_age_colors.get(b, "#94a3b8") for b in _yr_aging.index], cornerradius=6,
                           line=dict(color="rgba(255,255,255,0.55)", width=1)),
                text=[f"GHS {t:,.0f} · {int(n)} invoices" for t, n in zip(_yr_aging["Total"], _yr_aging["Count"])],
                textposition="outside"))
            _yr_fig7.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                   margin=dict(t=10, b=10, l=10, r=120), height=max(140, 40*len(_yr_aging)),
                                   font=dict(family="Inter, sans-serif", size=12),
                                   xaxis=dict(gridcolor="#f3f4f6", range=[0, _yr_aging["Total"].max()*1.35]))
            st.plotly_chart(_yr_fig7, use_container_width=True, config=CHART_CFG)
        _yr_text("This ageing view is a current snapshot, not yet a historical trend, treat it as the "
                 "baseline for tracking going forward.")
        card_close()

        # ── 6. Key Observations ───────────────────────────────────────────────────
        card_open("6. Key Observations")
        _yr_text(f"• <b>Customer concentration:</b> top 5 customers = {_yr_top5_pct:.1f}% of YTD revenue; "
                 f"top 10 = {_yr_top10_pct:.1f}%, out of {_yr_n_customers_ytd} customers who ordered at all this year.",
                 muted=False)
        _yr_text(f"• <b>Data coverage:</b> cost data covers {_yr_cost_cov_sold_n/_yr_cost_cov_sold_total*100:.0f}% "
                 f"of products actually sold this year ({_yr_cost_cov_n/_yr_cost_cov_total*100:.0f}% of the "
                 f"full, mostly-unsold catalogue). Agrovet tagging is {_yr_agro_note_short}.",
                 muted=False)
        card_close()


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — DATA EXPORT
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Quarterly Review":
    _qr_text = lambda html, size=13, muted=True, margin="0 0 14px": st.markdown(
        f'<div style="font-size:{size}px;color:{_T["text_muted"] if muted else _T["text_heading"]};'
        f'margin:{margin}">{html}</div>', unsafe_allow_html=True)
    _qr_text("Management review of a completed quarter: the quarter's own performance first, then the "
             "year to date against the annual goal, quarter-by-quarter trends, suggested focus and the data "
             "gaps to validate. Download it as a PDF for the management meeting.")

    # Completed quarters only (a quarter counts once data runs past its last day).
    _qr_latest = max(ccr._to_naive_date(inv_scoped["Created At"]).max(),
                     ccr._to_naive_date(rep_scoped["Repayment Date"]).dropna().pipe(
                         lambda s: s[s <= pd.Timestamp.now()]).max())
    _qr_year = _qr_latest.year
    _qr_done = [q for q in (1, 2, 3, 4) if qrv.quarter_bounds(_qr_year, q)[1].normalize() <= _qr_latest]
    if not _qr_done:
        st.info(f"No completed quarter yet in {_qr_year}.")
        st.stop()
    _qr_q = st.selectbox("Quarter", _qr_done, index=len(_qr_done) - 1, key="qr_quarter",
                         format_func=lambda q: f"Q{q} {_qr_year}")

    _qr_hist = inv.copy()
    _qr_hf = pd.Series(True, index=_qr_hist.index)
    if "Order Type" in _qr_hist.columns: _qr_hf &= (_qr_hist["Order Type"] == 1)
    if "Channel" in _qr_hist.columns: _qr_hf &= (_qr_hist["Channel"] != "BufferPesa")
    if "Status" in _qr_hist.columns: _qr_hf &= (_qr_hist["Status"] != 5)
    _qr = qrv.build(inv_scoped, rep_scoped, _qr_hist[_qr_hf], rc, il, prod,
                    pd.read_csv(f"{DATA}/revenue_target.csv"), _qr_year, _qr_q,
                    window_days=DSO_WINDOW_DAYS, terms_days=DSO_TERMS_DAYS)
    _qr_qa, _qr_qb, _qr_ytdp, _qr_focus = qrv.insights(_qr)
    _qr_gaps = qrv.data_gaps(_qr)
    _qr_trends = qrv.trend_lines(_qr)
    _qr_s, _qr_y = _qr["score"], _qr["ytd"]
    _qr_cur = _qr_s[_qr_q]
    _qr_prev = _qr_s[_qr_q - 1] if _qr_q > 1 else None
    _qr_ql, _qr_label = f"Q{_qr_q}", f"Q{_qr_q} {_qr_year}"
    _qr_next = f"Q{_qr_q + 1}" if _qr_q < 4 else f"Q1 {_qr_year + 1}"
    _qr_d = _qr["drivers"]

    _qr_money = lambda v: f"GHS {v:,.0f}" if pd.notna(v) else "n/a"
    _qr_pctf = lambda v: f"{v:.1f}%" if pd.notna(v) else "n/a"
    _qr_int = lambda v: f"{int(v):,}" if pd.notna(v) else "n/a"
    _qr_days = lambda v: f"{v:.0f} days" if pd.notna(v) else "n/a"

    def _qr_vs(metric, fmt="pct"):
        """Change vs the previous quarter, as short text."""
        if _qr_prev is None or pd.isna(_qr_prev[metric]):
            return ""
        d = _qr_cur[metric] - _qr_prev[metric]
        if fmt == "pts":
            return f"{d:+.1f} pts vs Q{_qr_q-1}"
        if fmt == "days":
            return f"{d:+.0f} days vs Q{_qr_q-1}"
        if fmt == "abs":
            return f"{d:+,.0f} vs Q{_qr_q-1}"
        return f"{d / _qr_prev[metric] * 100:+.1f}% vs Q{_qr_q-1}" if _qr_prev[metric] else ""

    # Headline tiles: (label, value, sub-line, accent colour)
    _qr_q_tiles = [
        (f"{_qr_ql} revenue", _qr_money(_qr_cur["Revenue"]),
         f"{_qr_cur['Attainment %']:.1f}% of {_qr_money(_qr_cur['Target'])} target",
         "#16a34a" if _qr_cur["Attainment %"] >= 100 else "#dc2626"),
        ("Orders / average order", f"{_qr_int(_qr_cur['Orders'])} / {_qr_money(_qr_cur['AOV'])}",
         _qr_vs("Orders"), BRAND_GREEN),
        ("Active customers", f"{_qr_int(_qr_cur['Active customers'])}",
         f"{_qr_int(_qr_cur['New customers'])} new; {_qr_vs('Active customers', 'abs')}", "#14b8a6"),
        ("Cash collected", _qr_money(_qr_cur["Collections"]),
         f"{_qr_cur['Collection ratio %']:.0f}% of {_qr_ql} revenue", "#0f766e"),
        ("Receivables at quarter end", _qr_money(_qr_cur["AR at quarter end"]),
         f"{_qr_cur['AR past terms %']:.0f}% past terms; {_qr_vs('AR at quarter end')}", "#f59e0b"),
        ("DSO at quarter end", _qr_days(_qr_cur["DSO at quarter end"]),
         f"{_qr_cur['DSO at quarter end'] - DSO_TERMS_DAYS:+.0f} days vs {DSO_TERMS_DAYS}-day term",
         "#dc2626" if _qr_cur["DSO at quarter end"] > DSO_TERMS_DAYS else "#16a34a"),
    ]
    _qr_y_tiles = [
        ("YTD revenue", _qr_money(_qr_y["revenue"]),
         f"{_qr_y['attainment']:.1f}% of {_qr_money(_qr_y['target'])} YTD target",
         "#16a34a" if _qr_y["attainment"] >= 100 else "#dc2626"),
        ("Annual goal reached", f"{_qr_y['annual_pct']:.1f}%",
         f"of {_qr_money(_qr_y['annual_target'])}", BRAND_GOLD),
        ("Still needed this year", _qr_money(_qr_y["remaining"]),
         f"{_qr_y['needed_pct_of_rest_target']:.0f}% of remaining targets" if _qr_y["months_left"] else "year complete",
         BRAND_GREEN),
        ("Projected year-end", _qr_money(_qr_y["projected"]),
         f"{_qr_y['projected_pct']:.0f}% of goal at {_qr_ql} run-rate", "#16a34a" if _qr_y["projected_pct"] >= 100 else "#dc2626"),
        ("Months on target", f"{_qr_y['months_on_target']} of {_qr_y['months_done']}",
         "months at or above monthly target", "#14b8a6"),
        ("YTD cash collected", _qr_money(_qr_y["collections"]),
         f"{_qr_y['collection_ratio']:.0f}% of YTD revenue", "#0f766e"),
    ]

    _q_on = int((_qr["monthly"].query("Q == @_qr_q")["Attainment %"] >= 100).sum())
    _qr_headline = (
        f"{_qr_label} delivered {_qr_money(_qr_cur['Revenue'])}, {_qr_cur['Attainment %']:.1f}% of target, with "
        f"{_q_on} of 3 months on or above target"
        + (f"; revenue was {abs(_qr_cur['Revenue']/_qr_prev['Revenue']-1)*100:.0f}% "
           f"{'below' if _qr_cur['Revenue'] < _qr_prev['Revenue'] else 'above'} Q{_qr_q-1}, against a target that was "
           f"{abs(_qr_cur['Target']/_qr_prev['Target']-1)*100:.0f}% "
           f"{'lower' if _qr_cur['Target'] < _qr_prev['Target'] else 'higher'}" if _qr_prev is not None else "")
        + f". Cash collected covered {_qr_cur['Collection ratio %']:.0f}% of the quarter's sales, and receivables "
          f"ended at {_qr_money(_qr_cur['AR at quarter end'])} (DSO {_qr_cur['DSO at quarter end']:.0f} days vs a "
          f"{DSO_TERMS_DAYS}-day term): sales are on plan, cash conversion is the issue.")

    _QR_ROWS = [("Revenue", _qr_money), ("Target", _qr_money), ("Attainment %", _qr_pctf),
                ("Orders", _qr_int), ("AOV", _qr_money), ("Median order", _qr_money),
                ("Active customers", _qr_int), ("New customers", _qr_int), ("Multi-SKU %", _qr_pctf),
                ("Top-5 share %", _qr_pctf), ("Collections", _qr_money), ("Collection ratio %", _qr_pctf),
                ("AR at quarter end", _qr_money), ("AR past terms %", _qr_pctf), ("DSO at quarter end", _qr_days)]
    _qr_quarters = list(_qr_s.columns)

    def _qr_change(metric):
        if _qr_prev is None or pd.isna(_qr_prev[metric]) or pd.isna(_qr_cur[metric]):
            return "n/a"
        if metric.endswith("%"):
            return f"{_qr_cur[metric] - _qr_prev[metric]:+.1f} pts"
        if metric == "DSO at quarter end":
            return f"{_qr_cur[metric] - _qr_prev[metric]:+.0f} days"
        return f"{(_qr_cur[metric] / _qr_prev[metric] - 1) * 100:+.1f}%" if _qr_prev[metric] else "n/a"

    _qr_table = pd.DataFrame(
        [[m] + [fmt(_qr_s.loc[m, q]) for q in _qr_quarters] + [_qr_change(m)] for m, fmt in _QR_ROWS],
        columns=["Metric"] + [f"Q{q}" for q in _qr_quarters] + ([f"Q{_qr_q} vs Q{_qr_q-1}"] if _qr_q > 1 else ["Change"]))

    # Charts (shared by page and PDF)
    _qr_c = {
        "months": qrc.quarter_months(_qr), "bridge": qrc.bridge(_qr), "mix": qrc.mix_compare(_qr),
        "aging": qrc.aging(_qr), "cum": qrc.cumulative(_qr), "matt": qrc.monthly_attainment(_qr),
        "trends": qrc.trends(_qr, DSO_TERMS_DAYS),
    }
    _qr_movers = None
    if "customers" in _qr_d:
        _m = _qr_d["customers"]
        _qr_movers = pd.concat([_m.head(5), _m.tail(5).iloc[::-1]])
        _qr_movers = _qr_movers[_qr_movers["Change"] != 0]
    _qr_cust_note = ""
    if "bridge" in _qr_d:
        _b = _qr_d["bridge"]
        _start, _end = _b[0][1], _b[-1][1]
        _dec = sum(v for n, v, k in _b if k == "delta" and v < 0 and n != "Stopped ordering")
        _top3 = sum(v for n, v, k in _b[1:4] if k == "delta" and v < 0 and n not in ("Other lower spend", "Stopped ordering"))
        _lost = next((v for n, v, k in _b if n == "Stopped ordering"), 0)
        _grow = next((v for n, v, k in _b if n == "Higher spend, existing"), 0)
        _new = next((v for n, v, k in _b if n == "New / returning"), 0)
        _qr_cust_note = (
            f"Revenue {'fell' if _end < _start else 'rose'} GHS {abs(_end - _start):,.0f} from Q{_qr_q-1}. "
            f"Existing customers spending less took off GHS {abs(_dec):,.0f} (the three largest decliners alone "
            f"GHS {abs(_top3):,.0f}, {abs(_top3) / abs(_dec) * 100 if _dec else 0:.0f}% of it) and customers who "
            f"stopped ordering GHS {abs(_lost):,.0f}; customers spending more added GHS {_grow:,.0f} and new or "
            f"returning customers GHS {_new:,.0f}. {_qr_d['retained']} customers ordered in both quarters, "
            f"{_qr_d['gained']} only in Q{_qr_q}, {len(_qr_d['lapsed'])} only in Q{_qr_q-1}.")

    # ── PDF ──────────────────────────────────────────────────────────────────────
    if _PDF_AVAIL:
        from PIL import Image as _QRImage

        class _QRPdf(YTDReportPDF):
            def header(self):
                if self.page_no() == 1:
                    return
                self.set_fill_color(*self._BRAND)
                self.rect(0, 0, 210, 14, "F")
                self.set_font("Helvetica", "B", 9)
                self.set_text_color(*self._WHITE)
                self.set_xy(10, 3)
                self.cell(0, 8, self._clean(f"TribeCo Ghana  |  {_qr_label} Performance Review  |  {self.part}"))
                self.ln(12)

            def new_page(self, part):
                self.part = part
                self.add_page()

            def title_block(self, title, subtitle, note):
                self.set_fill_color(*self._BRAND)
                self.rect(0, 0, 210, 34, "F")
                self.set_font("Helvetica", "B", 18)
                self.set_text_color(*self._WHITE)
                self.set_xy(10, 6)
                self.cell(190, 9, self._clean(title), align="C")
                self.set_font("Helvetica", "B", 12)
                self.set_text_color(*self._GOLD)
                self.set_xy(10, 16)
                self.cell(190, 7, self._clean(subtitle), align="C")
                self.set_font("Helvetica", "", 8.5)
                self.set_text_color(*self._WHITE)
                self.set_xy(10, 24)
                self.cell(190, 6, self._clean(note), align="C")
                self.set_text_color(0, 0, 0)
                self.set_y(39)

            def sub_title(self, text):
                if self.get_y() > self.page_break_trigger - 45:   # keep a heading with its content
                    self.add_page()
                super().sub_title(text)

            @staticmethod
            def _rgb(h):
                h = h.lstrip("#")
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

            def tiles(self, items, cols=3):
                gap, h = 3.5, 17
                w = (183 - gap * (cols - 1)) / cols
                y0 = self.get_y()
                for i, (label, value, sub, color) in enumerate(items):
                    x, y = 14 + (i % cols) * (w + gap), y0 + (i // cols) * (h + gap)
                    self.set_fill_color(*self._LIGHT)
                    self.rect(x, y, w, h, "F")
                    self.set_fill_color(*self._rgb(color))
                    self.rect(x, y, 1.4, h, "F")
                    self.set_xy(x + 3.5, y + 1.6)
                    self.set_font("Helvetica", "B", 7)
                    self.set_text_color(107, 114, 128)
                    self.cell(w - 5, 3.5, self._clean(label.upper()))
                    self.set_xy(x + 3.5, y + 5.6)
                    self.set_font("Helvetica", "B", 12.5)
                    self.set_text_color(*self._BLACK)
                    self.cell(w - 5, 6, self._clean(value))
                    self.set_xy(x + 3.5, y + 12)
                    self.set_font("Helvetica", "", 7.2)
                    self.set_text_color(*self._rgb(color))
                    self.cell(w - 5, 3.5, self._clean(sub))
                rows = -(-len(items) // cols)
                self.set_y(y0 + rows * (h + gap) + 1)

            def progress(self, value, goal, marker, label):
                y = self.get_y()
                x, w, h = 14, 183, 6
                self.set_font("Helvetica", "B", 8)
                self.set_text_color(*self._BRAND)
                self.set_xy(x, y)
                self.cell(w, 4, self._clean(label))
                y += 5
                self.set_fill_color(229, 231, 235)
                self.rect(x, y, w, h, "F")
                self.set_fill_color(*self._ACCENT)
                self.rect(x, y, w * min(value / goal, 1), h, "F")
                mx = x + w * min(marker / goal, 1)
                self.set_draw_color(*self._GOLD)
                self.set_line_width(0.9)
                self.line(mx, y - 1.2, mx, y + h + 1.2)
                self.set_font("Helvetica", "B", 7.5)
                self.set_text_color(*self._WHITE)
                self.set_xy(x + 2, y + 0.8)
                self.cell(60, 4.4, self._clean(f"{value/goal*100:.1f}% of annual goal"))
                self.set_text_color(*self._GOLD)
                self.set_xy(mx - 40, y + h + 1.2)
                self.cell(80, 3.5, self._clean(f"YTD target {marker/goal*100:.0f}%"), align="C")
                self.set_y(y + h + 6)

            def _img_h(self, img, w):
                im = _QRImage.open(io.BytesIO(img))
                return w * im.height / im.width

            def chart(self, img, w=183):
                if img is None:
                    return
                h = self._img_h(img, w)
                if self.get_y() + h > self.page_break_trigger:
                    self.add_page()
                self.image(io.BytesIO(img), x=14 + (183 - w) / 2, y=self.get_y(), w=w)
                self.set_y(self.get_y() + h + 2.5)

            def chart_pair(self, a, b):
                imgs = [i for i in (a, b) if i is not None]
                if len(imgs) < 2:
                    for i in imgs:
                        self.chart(i, w=120)
                    return
                w = 89.5
                h = max(self._img_h(a, w), self._img_h(b, w))
                if self.get_y() + h > self.page_break_trigger:
                    self.add_page()
                y = self.get_y()
                self.image(io.BytesIO(a), x=14, y=y, w=w)
                self.image(io.BytesIO(b), x=14 + w + 4, y=y, w=w)
                self.set_y(y + h + 2.5)

            def bullets(self, items, color=None):
                for it in items:
                    if self.get_y() > self.page_break_trigger - 12:
                        self.add_page()
                    self.set_x(14)
                    self.set_font("Helvetica", "B", 9.5)
                    self.set_text_color(*(color or self._ACCENT))
                    self.cell(5, 5, "-")
                    self.set_font("Helvetica", "", 9)
                    self.set_text_color(*self._BLACK)
                    self.multi_cell(178, 4.8, self._clean(it))
                    self.ln(0.6)
                self.ln(1.2)

        def _qr_compose(w):
            """Write the whole report through a writer -- the PDF and Word versions share this."""
            tone = {"good": w._ACCENT, "bad": w._RED, "neutral": w._GOLD}

            # Pages 1-2: the quarter on its own
            w.new_page(f"{_qr_ql} analysis")
            w.title_block("Ghana Commercial Performance",
                          f"{_qr_label} Review and Year-to-Date vs Annual Goals",
                          f"Prepared for the management meeting  |  data as of {_qr['flags']['data_end']:%d %b %Y}")
            w.section_title(f"1. {_qr_label} at a glance")
            w.tiles(_qr_q_tiles)
            w.callout("Headline", _qr_headline, w._ACCENT)
            w.chart(_qr_c["months"])
            w.section_title(f"2. {_qr_ql}: what went well")
            w.bullets(_qr_qa or ["Nothing materially ahead of plan this quarter."], w._ACCENT)
            w.section_title(f"3. {_qr_ql}: what needs attention")
            w.bullets(_qr_qb or ["Nothing materially behind plan this quarter."], w._RED)
            if _qr_c["bridge"] is not None or _qr_c["mix"] is not None:
                w.section_title(f"4. {_qr_ql} drivers")
                w.chart(_qr_c["bridge"])
                if _qr_cust_note:
                    w.body(_qr_cust_note)
                w.chart_pair(_qr_c["mix"], _qr_c["aging"])
                if _qr_movers is not None and len(_qr_movers):
                    w.sub_title(f"Largest customer movements, Q{_qr_q-1} to {_qr_ql}")
                    w.table(["Customer", f"Q{_qr_q-1}", _qr_ql, "Change"],
                            [(n[:38], _qr_money(r.Prev), _qr_money(r.Curr), f"{r.Change:+,.0f}")
                             for n, r in _qr_movers.iterrows()], [80, 35, 35, 33])

            # Page 3 onward: year to date
            w.new_page("Year to date")
            w.section_title(f"5. Year to date vs the annual goal (Jan - {_qr['monthly'].dropna(subset=['Revenue'])['Label'].iloc[-1]} {_qr_year})")
            w.tiles(_qr_y_tiles)
            w.progress(_qr_y["revenue"], _qr_y["annual_target"], _qr_y["target"],
                       f"Progress to the GHS {_qr_y['annual_target']:,.0f} annual goal")
            w.chart(_qr_c["cum"])
            w.chart(_qr_c["matt"])
            for lbl, txt, t in _qr_ytdp:
                w.callout(lbl, txt, tone[t])

            w.section_title(f"6. Quarter-by-quarter trends, Q1 to {_qr_ql}")
            w.chart(_qr_c["trends"])
            for title, text in _qr_trends:
                w.callout(title, text, w._ACCENT)
            w.sub_title(f"Quarterly scorecard, Q1 to {_qr_ql}")
            w.table(list(_qr_table.columns), _qr_table.values.tolist(),
                    [48] + [int(110 / len(_qr_quarters))] * len(_qr_quarters) + [25])
            w.section_title(f"7. Suggested focus for {_qr_next}")
            w.bullets(_qr_focus, w._GOLD)
            w.section_title("8. Data gaps and figures to validate")
            for title, text in _qr_gaps:
                w.callout(title, text, w._AMBER)
            w.body("Method: revenue = invoiced value after discount (Ghana FBC orders, excluding cancelled and "
                   "BufferPesa). Collections dated by actual payment date. DSO = receivables at quarter end / "
                   f"last {DSO_WINDOW_DAYS} days of sales x {DSO_WINDOW_DAYS}. Projection = YTD revenue + "
                   f"{_qr_ql} monthly run-rate x months left. Generated live from Metabase.")

        def _qr_build_pdf():
            pdf = _QRPdf()
            _qr_compose(pdf)
            return bytes(pdf.output())

        def _qr_build_docx():
            doc = qrw.ReportDoc(f"TribeCo Ghana  |  {_qr_label} Performance Review")
            _qr_compose(doc)
            return doc.output()

        def _qr_build_pptx():
            return qrp.build(dict(
                r=_qr, q=_qr_q, ql=_qr_ql, label=_qr_label, next=_qr_next,
                as_of=f"{_qr['flags']['data_end']:%d %b %Y}", terms_days=DSO_TERMS_DAYS,
                headline=_qr_headline, q_tiles=_qr_q_tiles, y_tiles=_qr_y_tiles,
                q_ahead=_qr_qa, q_behind=_qr_qb, ytd_points=_qr_ytdp, focus=_qr_focus,
                trends=_qr_trends, gaps=_qr_gaps, table=_qr_table, cust_note=_qr_cust_note))

        _qr_fname = f"Ghana_{_qr_label.replace(' ', '_')}_Review_vs_Annual_Goals"
        _qr_d1, _qr_d2, _qr_d3 = st.columns(3)
        with _qr_d1:
            st.download_button(f"⬇ Download {_qr_label} Review (PDF)", data=_qr_build_pdf(),
                               file_name=f"{_qr_fname}.pdf", mime="application/pdf",
                               type="primary", use_container_width=True)
        with _qr_d2:
            st.download_button(f"⬇ Download {_qr_label} Review (Word)", data=_qr_build_docx(),
                               file_name=f"{_qr_fname}.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               type="primary", use_container_width=True)
        with _qr_d3:
            st.download_button(f"⬇ Download {_qr_label} Presentation (PowerPoint)", data=_qr_build_pptx(),
                               file_name=f"{_qr_fname}.pptx",
                               mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                               type="primary", use_container_width=True)

        # ── Brief report: targets vs actuals, the quarter's weekly trend, vaccines YTD ──
        _qb_end = _qr["flags"]["data_end"]
        _qb_qm = _qr["monthly"][_qr["monthly"]["Q"] == _qr_q]
        _qb_last_m = qrv.quarter_bounds(_qr_year, _qr_q)[1].strftime("%Y-%m")
        _qb_vax, _qb_vials = qbf.vaccine_trend(inv_scoped, il, prod, _qr_year, _qb_last_m)
        _qb_c = {"months": qbf.chart_quarter_months(_qb_qm, _qr_q) if len(_qb_qm) else None,
                 "vax": qbf.chart_vaccines(_qb_vax) if len(_qb_vax) else None}

        def _qb_row(lbl, tgt, act):
            return (lbl, _qr_money(tgt), _qr_money(act), f"{act - tgt:+,.0f}", f"{act / tgt * 100:.1f}%" if tgt else "n/a")

        def _qb_drivers_recs():
            """Analyst read of the quarter: what drove the numbers, and what management should do."""
            drivers, recs = [], []
            prev = _qr_prev
            nq = _qr_next.split()[0]
            # 1. Target vs underlying sales
            if prev is not None and _qr_cur["Target"] < prev["Target"] and _qr_cur["Revenue"] < prev["Revenue"]:
                drivers.append(
                    f"Target beaten on a lower bar: revenue fell {abs(_qr_cur['Revenue'] / prev['Revenue'] - 1) * 100:.0f}% "
                    f"vs Q{_qr_q - 1}, but the {_qr_ql} target was {abs(_qr_cur['Target'] / prev['Target'] - 1) * 100:.0f}% "
                    f"lower, so {_qr_cur['Attainment %']:.1f}% attainment reflects a lighter plan more than stronger sales.")
            # 2. Customer movements (bridge)
            b = _qr_d.get("bridge")
            if b:
                top = [(n, v) for n, v, k in b[1:4] if k == "delta" and v < 0]
                grow = next((v for n, v, k in b if n == "Higher spend, existing"), 0)
                new = next((v for n, v, k in b if n == "New / returning"), 0)
                if top:
                    drivers.append(
                        f"A few large accounts drove the change: {', '.join(n for n, _ in top)} together bought "
                        f"{_qr_money(abs(sum(v for _, v in top)))} less than in Q{_qr_q - 1}; other customers spending more "
                        f"(+{_qr_money(grow)}) and new or returning customers (+{_qr_money(new)}) only partly offset it.")
            # 3. Cash conversion
            if prev is not None and _qr_cur["AR at quarter end"] > prev["AR at quarter end"]:
                ag = _qr["aging"]
                worst = ag.drop(index="Within terms", errors="ignore")["Amount"]
                drivers.append(
                    f"Sales are not turning into cash fast enough: only {_qr_cur['Collection ratio %']:.0f}% of {_qr_ql} sales "
                    f"was collected, receivables rose to {_qr_money(_qr_cur['AR at quarter end'])} "
                    f"(+{(_qr_cur['AR at quarter end'] / prev['AR at quarter end'] - 1) * 100:.0f}%) and DSO reached "
                    f"{_qr_cur['DSO at quarter end']:.0f} days against a {DSO_TERMS_DAYS}-day term"
                    + (f"; the largest overdue block is {worst.idxmax()} ({_qr_money(worst.max())})." if len(worst) and worst.max() > 0 else "."))
            # 4. Vaccine volumes
            if len(_qb_vax):
                vq = _qb_vax.groupby("Q")["Total"].sum()
                cur_q = _qb_vax[_qb_vax["Q"] == _qr_q]["Total"]
                if len(vq) > 1 and vq.iloc[-1] < vq.iloc[-2]:
                    drivers.append(
                        f"Vaccine volumes are softening: {vq.iloc[-1] / 1e6:.1f}M doses in {_qr_ql}, "
                        f"{abs(vq.iloc[-1] / vq.iloc[-2] - 1) * 100:.0f}% below Q{_qr_q - 1}"
                        + (", falling every month of the quarter" if (cur_q.diff().dropna() < 0).all() else "")
                        + (f"; revenue moved in line ({(_qr_cur['Revenue'] / prev['Revenue'] - 1) * 100:+.0f}%), so lower "
                           f"volume, not price, explains the dip."
                           if prev is not None and abs((_qr_cur['Revenue'] / prev['Revenue']) - (vq.iloc[-1] / vq.iloc[-2])) < 0.05
                           else "."))
            # 5. Customer base and basket
            if prev is not None:
                drivers.append(
                    f"Growth is coming from existing customers: only {int(_qr_cur['New customers'])} new customers in "
                    f"{_qr_ql}, while orders with 2+ products rose to {_qr_cur['Multi-SKU %']:.0f}% "
                    f"(from {prev['Multi-SKU %']:.0f}%).")

            # Recommendations
            if prev is not None and _qr_cur["AR at quarter end"] > prev["AR at quarter end"]:
                recs.append(
                    f"Make collections the {nq} priority: work a weekly chase list of the {_qr_money(_qr_cur['AR past terms'])} "
                    f"past terms, oldest first, and set a {nq} DSO target (e.g. from {_qr_cur['DSO at quarter end']:.0f} "
                    f"days back towards the {DSO_TERMS_DAYS}-day term). Consider pausing new credit for accounts over 60 days past terms.")
            if b and top:
                recs.append(
                    f"Run account reviews with the customers that slowed most ({', '.join(n for n, _ in top)}"
                    + (f", and {_qr_d['lapsed'][0][0]}, which stopped ordering" if _qr_d.get("lapsed") and _qr_d["lapsed"][0][1] >= 10000 else "")
                    + "): understand why volume dropped and agree a recovery plan with the account manager.")
            if len(_qb_vax) and len(vq) > 1 and vq.iloc[-1] < vq.iloc[-2]:
                recs.append("Find out why vaccine doses are falling (customer demand, stock availability or seasonality) "
                            "and set a monthly doses target alongside revenue.")
            if _qr_y["months_left"]:
                recs.append(
                    f"Protect the annual goal: {_qr_money(_qr_y['remaining'])} is needed in {nq} "
                    f"({_qr_y['needed_pct_of_rest_target']:.0f}% of the {nq} target). Aim for at least "
                    f"{_qr_money(_qr_y['rest_target'] / _qr_y['months_left'])} per month to finish above goal.")
            if _qr_cur["New customers"] <= 5:
                recs.append(f"Set a new-customer acquisition target for {nq}; the customer base has barely grown since Q1.")
            if len(_qr["flags"]["exact_months"]) >= 3:
                recs.append("Confirm how monthly targets were set: several months landed within 0.5% of target, so "
                            "agree that targets are fixed before each month starts and add targets for collections and doses.")
            return drivers, recs

        _qb_q_rows = [_qb_row(f"{l} {_qr_year}", t, a)
                      for l, t, a in zip(_qb_qm["Label"], _qb_qm["Target"], _qb_qm["Revenue"])]
        _qb_q_rows.append(_qb_row(f"{_qr_ql} total", _qr_cur["Target"], _qr_cur["Revenue"]))
        _qb_y_rows = [_qb_row(f"Q{c}", _qr_s.loc["Target", c], _qr_s.loc["Revenue", c]) for c in _qr_quarters]
        _qb_y_rows.append(_qb_row(f"YTD (Jan - {_qb_qm['Label'].iloc[-1]})", _qr_y["target"], _qr_y["revenue"]))
        _qb_y_rows.append((f"Annual goal {_qr_year}", _qr_money(_qr_y["annual_target"]), _qr_money(_qr_y["revenue"]),
                           f"{_qr_y['revenue'] - _qr_y['annual_target']:+,.0f}", f"{_qr_y['annual_pct']:.1f}% reached"))
        _qb_notes = {}

        def _qb_compose(w):
            qm = _qr["monthly"][_qr["monthly"]["Q"] == _qr_q]
            w.new_page(f"{_qr_ql} brief")
            w.title_block("Ghana Commercial Performance", f"{_qr_label} Brief: Targets vs Actuals",
                          f"Management summary  |  data as of {_qb_end:%d %b %Y}")

            w.section_title(f"1. {_qr_ql} targets vs actuals")
            w.table(["Period", "Target (GHS)", "Actual (GHS)", "Variance (GHS)", "Attainment"], _qb_q_rows,
                    [40, 37, 37, 37, 32])
            _qb_notes["q"] = (f"{_qr_ql} finished {'above' if _qr_cur['Attainment %'] >= 100 else 'below'} target at "
                   f"{_qr_cur['Attainment %']:.1f}% ({_qr_money(_qr_cur['Revenue'] - _qr_cur['Target'])} "
                   f"{'over' if _qr_cur['Revenue'] >= _qr_cur['Target'] else 'under'}), with "
                   f"{int((qm['Attainment %'] >= 100).sum())} of {len(qm)} months on or above target.")
            w.body(_qb_notes["q"])

            w.section_title("2. Year-to-date targets vs actuals")
            w.table(["Period", "Target (GHS)", "Actual (GHS)", "Variance (GHS)", "Attainment"], _qb_y_rows,
                    [40, 37, 37, 37, 32])
            _qb_notes["y"] = (f"The year is {_qr_y['attainment']:.1f}% of the YTD target. {_qr_money(_qr_y['remaining'])} more "
                   f"is needed to reach the annual goal, which is {_qr_y['needed_pct_of_rest_target']:.0f}% of the "
                   f"remaining monthly targets; at the {_qr_ql} pace the year would close near "
                   f"{_qr_money(_qr_y['projected'])} ({_qr_y['projected_pct']:.0f}% of goal)." if _qr_y["months_left"] else
                   f"The year closed at {_qr_y['annual_pct']:.1f}% of the annual goal.")
            w.body(_qb_notes["y"])

            if _qb_c["months"] is not None:
                rv, tg = list(_qb_qm["Revenue"]), list(_qb_qm["Target"])
                lab = list(_qb_qm["Label"])
                w.section_title(f"3. {_qr_ql} trend: month by month")
                w.chart(_qb_c["months"])
                _qb_notes["trend"] = (f"How to read: the green line is revenue each month and the dashed gold line the monthly target; "
                       f"green shading = above target, red = below. Revenue moved "
                       + " -> ".join(f"{l} {_qr_money(v)}" for l, v in zip(lab, rv))
                       + f" ({(rv[-1] / rv[0] - 1) * 100:+.1f}% from {lab[0]} to {lab[-1]}), while the target moved "
                       + f"{(tg[-1] / tg[0] - 1) * 100:+.1f}% over the same months. "
                       + f"{int((_qb_qm['Attainment %'] >= 100).sum())} of {len(rv)} months were on or above target; "
                       + f"the best month against target was {lab[int(_qb_qm['Attainment %'].values.argmax())]} "
                       + f"({_qb_qm['Attainment %'].max():.1f}%).")
                w.body(_qb_notes["trend"])

            if _qb_c["vax"] is not None:
                vq = _qb_vax.groupby("Q")["Total"].sum()
                share = {d: _qb_vax[d].sum() / _qb_vax["Total"].sum() * 100
                         for d in qbf.DISEASE_COLORS if d in _qb_vax.columns}
                w.section_title("4. Vaccines delivered: year-to-date trend")
                w.chart(_qb_c["vax"])
                _qb_notes["vax"] = (f"How to read: each line is doses delivered per month by disease; the dotted line is all vaccines. "
                       f"{_qb_vax['Total'].sum() / 1e6:.1f}M doses delivered year to date ({_qb_vials:,.0f} vials): "
                       + ", ".join(f"Q{k} {v / 1e6:.1f}M" for k, v in vq.items()) + ". "
                       + ", ".join(f"{d} {v:.0f}%" for d, v in sorted(share.items(), key=lambda kv: -kv[1]) if v >= 1)
                       + " of doses. "
                       + (f"Q{_qr_q} doses were {abs(vq.iloc[-1] / vq.iloc[-2] - 1) * 100:.0f}% "
                          f"{'lower' if vq.iloc[-1] < vq.iloc[-2] else 'higher'} than Q{_qr_q - 1}"
                          + ("; monthly doses fell in each month of the quarter. "
                             if (_qb_vax[_qb_vax['Q'] == _qr_q]['Total'].diff().dropna() < 0).all() else ". ")
                          if len(vq) > 1 else "")
                       + "Doses = vials sold x doses per vial (mostly 1,000-dose vials).")
                w.body(_qb_notes["vax"])
            drivers, recs = _qb_drivers_recs()
            if drivers:
                w.section_title(f"5. Key drivers behind the {_qr_ql} numbers")
                w.bullets(drivers, w._ACCENT)
            if recs:
                w.section_title("6. Recommendations to management")
                w.bullets(recs, w._GOLD)
            w.body("Revenue = invoiced value after discount (Ghana FBC orders). Live from Metabase.")

        def _qb_pdf():
            pdf = _QRPdf()
            _qb_compose(pdf)
            return bytes(pdf.output())

        def _qb_docx():
            doc = qrw.ReportDoc(f"TribeCo Ghana  |  {_qr_label} Brief: Targets vs Actuals")
            _qb_compose(doc)
            return doc.output()

        def _qb_pptx():
            if not _qb_notes:                       # notes are filled while composing the document
                _qb_compose(qrw.ReportDoc(""))
            drivers, recs = _qb_drivers_recs()
            return qrp.build_brief(dict(
                q=_qr_q, ql=_qr_ql, label=_qr_label, as_of=f"{_qb_end:%d %b %Y}", qm=_qb_qm, cur=_qr_cur,
                ytd=_qr_y, vax=_qb_vax, vials=_qb_vials, q_rows=_qb_q_rows, y_rows=_qb_y_rows,
                q_note=_qb_notes.get("q", ""), y_note=_qb_notes.get("y", ""),
                trend_note=_qb_notes.get("trend", ""), vax_note=_qb_notes.get("vax", ""),
                drivers=drivers, recs=recs))

        _qb_fname = f"Ghana_{_qr_label.replace(' ', '_')}_Brief_Targets_vs_Actuals"
        _qr_text("<b>Brief version</b>: targets vs actuals for the quarter and year to date, the quarter's "
                 "month-by-month trend, the year-to-date vaccines trend, key drivers and recommendations.",
                 margin="10px 0 6px")
        _qb_d1, _qb_d2, _qb_d3 = st.columns(3)
        with _qb_d1:
            st.download_button(f"⬇ Download {_qr_label} Brief (PDF)", data=_qb_pdf(), file_name=f"{_qb_fname}.pdf",
                               mime="application/pdf", use_container_width=True)
        with _qb_d2:
            st.download_button(f"⬇ Download {_qr_label} Brief (Word)", data=_qb_docx(), file_name=f"{_qb_fname}.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               use_container_width=True)
        with _qb_d3:
            st.download_button(f"⬇ Download {_qr_label} Brief (PowerPoint)", data=_qb_pptx(),
                               file_name=f"{_qb_fname}.pptx",
                               mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                               use_container_width=True)
    else:
        st.warning("PDF export isn't available in this environment (fpdf2/matplotlib not installed).")

    # ── On-screen ────────────────────────────────────────────────────────────────
    def _qr_part(title, sub):
        st.markdown(f'<div style="margin:26px 0 10px;padding:10px 16px;border-radius:10px;'
                    f'background:{BRAND_GREEN_DEEP};color:white"><div style="font-size:17px;font-weight:800">'
                    f'{title}</div><div style="font-size:12px;opacity:.8">{sub}</div></div>',
                    unsafe_allow_html=True)

    def _qr_cards(items):
        html = "".join(kpi_card(l, v, s, c) for l, v, s, c in items)
        st.markdown(kpi_grid(html, max_cols=3), unsafe_allow_html=True)

    def _qr_box(title, items, color):
        body = "".join(f'<li style="margin:0 0 6px">{i}</li>' for i in items) or "<li>None this quarter.</li>"
        st.markdown(f'<div style="border-left:4px solid {color};padding:10px 14px;margin:6px 0 14px;'
                    f'border-radius:8px"><div style="font-weight:700;color:{color};margin-bottom:6px">{title}</div>'
                    f'<ul style="margin:0;padding-left:18px;font-size:13px;color:{_T["text_heading"]}">{body}</ul></div>',
                    unsafe_allow_html=True)

    def _qr_img(img):
        if img is not None:
            st.image(img, use_container_width=True)

    _qr_part(f"{_qr_label} analysis", "How the quarter itself performed")
    _qr_cards(_qr_q_tiles)
    st.info(_qr_headline)
    _qr_img(_qr_c["months"])
    _qr_c1, _qr_c2 = st.columns(2)
    with _qr_c1:
        _qr_box("What went well", _qr_qa, "#16a34a")
    with _qr_c2:
        _qr_box("What needs attention", _qr_qb, "#dc2626")
    _qr_img(_qr_c["bridge"])
    if _qr_cust_note:
        _qr_text(_qr_cust_note)
    _qr_c3, _qr_c4 = st.columns(2)
    with _qr_c3:
        _qr_img(_qr_c["mix"])
    with _qr_c4:
        _qr_img(_qr_c["aging"])
    if _qr_movers is not None and len(_qr_movers):
        with st.expander(f"Largest customer movements, Q{_qr_q-1} to {_qr_ql}"):
            st.dataframe(pd.DataFrame({
                "Customer": _qr_movers.index,
                f"Q{_qr_q-1}": _qr_movers["Prev"].apply(_qr_money).values,
                _qr_ql: _qr_movers["Curr"].apply(_qr_money).values,
                "Change": _qr_movers["Change"].apply(lambda v: f"{v:+,.0f}").values,
            }), use_container_width=True, hide_index=True)

    _qr_part("Year to date vs the annual goal", f"January to the end of {_qr_label}")
    _qr_cards(_qr_y_tiles)
    _qr_img(_qr_c["cum"])
    _tone_c = {"good": "#16a34a", "bad": "#dc2626", "neutral": BRAND_GOLD}
    for _l, _t, _tn in _qr_ytdp:
        st.markdown(f'<div style="border-left:4px solid {_tone_c[_tn]};padding:6px 12px;margin:0 0 8px;'
                    f'font-size:13px;color:{_T["text_heading"]}"><b>{_l}.</b> {_t}</div>', unsafe_allow_html=True)
    _qr_img(_qr_c["matt"])

    _qr_part(f"Quarter-by-quarter trends, Q1 to {_qr_ql}", "How each part of the business moved across the year")
    _qr_img(_qr_c["trends"])
    for _t, _x in _qr_trends:
        st.markdown(f"**{_t}.** {_x}")
    st.dataframe(_qr_table, use_container_width=True, hide_index=True)

    _qr_part(f"Suggested focus for {_qr_next}", "Where the numbers say to act")
    _qr_box("Focus", _qr_focus, BRAND_GOLD)
    card_open("Data Gaps and Figures to Validate", "Flag these before the numbers are presented")
    for _t, _x in _qr_gaps:
        st.markdown(f"**{_t}.** {_x}")
    card_close()

elif page == "Credit & Collections":
    _cc_text = lambda html: st.markdown(
        f'<div style="font-size:13px;color:{_T["text_muted"]};margin:0 0 14px">{html}</div>',
        unsafe_allow_html=True)
    _cc_text("The Sales Credit & Collections Performance workbook, rebuilt from live Metabase data: "
             "invoice aging, receipt detail, customer credit matrix and monthly performance. Choose the "
             "invoice period and the collections cut-off, then download the workbook to review.")

    # Defaults: year-to-date invoices up to the last complete month, collections up to the
    # latest repayment on file -- the same closed-period approach as the original workbook.
    _cc_latest_inv = ccr._to_naive_date(inv_scoped["Created At"]).max()
    _cc_rep_dates  = ccr._to_naive_date(rep_scoped["Repayment Date"]).dropna()
    _cc_latest_rep = min(_cc_rep_dates.max(), pd.Timestamp.now().normalize()) if len(_cc_rep_dates) else _cc_latest_inv
    _cc_def_end    = (_cc_latest_inv + pd.offsets.MonthEnd(0) if _cc_latest_inv.is_month_end
                      else _cc_latest_inv.replace(day=1) - pd.Timedelta(days=1))
    _cc_c1, _cc_c2, _cc_c3 = st.columns(3)
    with _cc_c1:
        _cc_start = st.date_input("Invoices from", _cc_latest_inv.replace(month=1, day=1).date(), key="cc_start")
    with _cc_c2:
        _cc_end = st.date_input("Invoices to", _cc_def_end.date(), key="cc_end")
    with _cc_c3:
        _cc_cutoff = st.date_input("Collections cut-off", _cc_latest_rep.date(), key="cc_cutoff")

    if _cc_end < _cc_start:
        st.warning("'Invoices to' must be on or after 'Invoices from'.")
        st.stop()

    _cc = ccr.prepare_data(inv_scoped, rep_scoped, rc, ir, _cc_start, _cc_end, _cc_cutoff, DSO_TERMS_DAYS)
    _cc_s = ccr.summary(_cc)
    _cc_label = ccr.period_label(_cc["start"], _cc["end"])

    if not _cc_s["invoice_count"]:
        st.info("No invoices in the selected period.")
        st.stop()

    st.download_button(
        "⬇ Download Sales Credit & Collections workbook (.xlsx)",
        data=ccr.build_workbook(_cc),
        file_name=f"Sales_Credit_and_Collections_Performance_{_cc_label.replace(' ', '')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary", use_container_width=True)
    _cc_text(f"{_cc_s['invoice_count']} invoices issued {_cc_label}; collections through "
             f"{_cc['cutoff']:%d %b %Y}. Every summary figure in the workbook is a live Excel formula "
             f"over its Invoice Aging and Receipt Detail sheets.")

    _cc_row1 = kpi_card("Invoice Value", f"GHS {_cc_s['invoice_value']:,.2f}",
                        f"{_cc_s['invoice_count']} invoices", BRAND_GREEN) + \
               kpi_card("Collections to Cut-off", f"GHS {_cc_s['collections']:,.2f}",
                        "Allocated by invoice number", "#16a34a") + \
               kpi_card("Collection Rate", f"{_cc_s['collection_rate']*100:.1f}%",
                        "Collections ÷ invoice value", "#14b8a6")
    _cc_row2 = kpi_card("Gross Outstanding", f"GHS {_cc_s['gross_outstanding']:,.2f}",
                        "Positive invoice balances", "#f59e0b") + \
               kpi_card("Overdue Balance", f"GHS {_cc_s['overdue']:,.2f}",
                        f"Past the {DSO_TERMS_DAYS}-day due date at cut-off", "#dc2626") + \
               kpi_card("Credit Customers", f"{_cc_s['credit_customers']}",
                        "Customers with credit invoices", "#3b82f6")
    st.markdown(kpi_grid(_cc_row1, max_cols=3), unsafe_allow_html=True)
    st.markdown(kpi_grid(_cc_row2, max_cols=3), unsafe_allow_html=True)

    _cc_inv = _cc["invoices"]
    _cc_a, _cc_b = st.columns(2)
    with _cc_a:
        card_open("Aging of Gross Outstanding", f"As of {_cc['cutoff']:%d %b %Y}")
        _cc_age = (_cc_inv.groupby("Aging Bucket")["Gross Outstanding"].agg(["size", "sum"])
                   .reindex(ccr.AGING_ORDER).fillna(0))
        _cc_age_tot = _cc_age["sum"].sum()
        st.dataframe(pd.DataFrame({
            "Aging Bucket": _cc_age.index,
            "Invoices": _cc_age["size"].astype(int).values,
            "Balance": _cc_age["sum"].apply(lambda x: f"GHS {x:,.2f}").values,
            "Share": (_cc_age["sum"] / _cc_age_tot * 100 if _cc_age_tot else _cc_age["sum"] * 0)
                     .apply(lambda x: f"{x:.1f}%").values,
        }), use_container_width=True, hide_index=True)
        card_close()
    with _cc_b:
        card_open("Portfolio Status", "Invoices by payment status")
        _cc_st = (_cc_inv.groupby("Status").agg(n=("Invoice Number", "size"), val=("Invoice Total", "sum"),
                                                 out=("Gross Outstanding", "sum"))
                  .reindex(ccr.STATUS_ORDER).fillna(0))
        st.dataframe(pd.DataFrame({
            "Status": _cc_st.index,
            "Invoices": _cc_st["n"].astype(int).values,
            "Invoice Value": _cc_st["val"].apply(lambda x: f"GHS {x:,.2f}").values,
            "Outstanding": _cc_st["out"].apply(lambda x: f"GHS {x:,.2f}").values,
        }), use_container_width=True, hide_index=True)
        card_close()

    card_open("Top Credit Exposures", "Largest credit customers in the period")
    _cc_top = _cc["customers"].head(10)
    st.dataframe(pd.DataFrame({
        "Customer": _cc_top["Customer Name"],
        "Credit Issued": _cc_top["Credit Issued"].apply(lambda x: f"GHS {x:,.2f}"),
        "Collections": _cc_top["Collections"].apply(lambda x: f"GHS {x:,.2f}"),
        "Outstanding": _cc_top["Gross Outstanding"].apply(lambda x: f"GHS {x:,.2f}"),
        "Collection Rate": (_cc_top["Collection Rate"] * 100).apply(lambda x: f"{x:.1f}%"),
        "Overdue": _cc_top["Overdue Balance"].apply(lambda x: f"GHS {x:,.2f}"),
        "Risk Flag": _cc_top["Risk Flag"],
    }), use_container_width=True, hide_index=True)
    card_close()
    st.caption("Built from Metabase only. An invoice counts as Credit when Metabase records payment terms "
               "on it (every invoice this year carries 30-day terms), so Credit Issued matches total "
               "invoice value. Sales Zone isn't held in Metabase and is left blank in the workbook.")

elif page == "Products":
    _ps_text = lambda html: st.markdown(
        f'<div style="font-size:13px;color:{_T["text_muted"]};margin:0 0 14px">{html}</div>',
        unsafe_allow_html=True)
    _ps_frames, _ps_live, _ps_err = load_products()
    _ps_months = sorted(prr.lines(inv_scoped, _ps_frames.get("lines"))["Month"].dropna().unique())[::-1] \
        if len(_ps_frames.get("lines", [])) else []
    if not _ps_months:
        st.info("No product sales found.")
        st.stop()
    _ps_now_m = pd.Timestamp.now().strftime("%Y-%m")
    _ps_c1, _ = st.columns([1, 3])
    _ps_month = _ps_c1.selectbox(
        "Month", _ps_months, key="ps_month",
        index=1 if len(_ps_months) > 1 and _ps_months[0] == _ps_now_m else 0,
        format_func=lambda m: pd.Period(m, freq="M").strftime("%B %Y") + (" (to date)" if m == _ps_now_m else ""))
    _ps = prr.compute(_ps_month, inv_scoped, _ps_frames)
    _ps_t, _ps_p, _ps_s = _ps["totals"], _ps["products"], _ps["stock_summary"]
    _ps_text("Product sales, gross margin and where products sold for the chosen month; stock received, sold and "
             "remaining as of today. The same figures go into the monthly management email."
             + ("" if _ps_live else " <b>Metabase is unavailable, so this shows the last saved copy.</b>"))

    # Findings first: what the CEO should know
    with st.container(border=True):
        st.markdown(f"**What is happening: {_ps['label']}**")
        for _x in _ps["points"]:
            st.markdown(f"- {_x}")
        if _ps["recs"]:
            st.markdown("**Actions**")
            for _x in _ps["recs"]:
                st.markdown(f"- {_x}")

    _ps_card = lambda label, value, sub, color: (
        f'<div class="kpi-card" style="--accent:{color}"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>')
    _ps_fmt_g = lambda v: f"{v * 100:+.1f}% vs last month" if pd.notna(v) else "no sales last month"
    st.markdown('<div class="kpi-grid">' + "".join([
        _ps_card("Product Revenue", f"GHS {_ps_t['revenue']:,.0f}", _ps_fmt_g(_ps_t["growth"]), BRAND_GREEN),
        _ps_card("Gross Margin", f"{_ps_t['margin_pct'] * 100:.1f}%" if pd.notna(_ps_t["margin_pct"]) else "-",
                 f"GHS {_ps_t['margin']:,.0f} gross profit", "#16a34a"),
        _ps_card("Products Sold", f"{_ps_t['products']}",
                 f"Top 3 = {_ps_t['top3_share'] * 100:.0f}% of revenue" if pd.notna(_ps_t["top3_share"]) else "",
                 "#14b8a6"),
        _ps_card("Cities Reached", f"{_ps_t['cities']}", f"{_ps_t['units']:,.0f} units sold", BRAND_GOLD),
    ]) + "</div>", unsafe_allow_html=True)

    _ps_tab1, _ps_tab2, _ps_tab3, _ps_tab4 = st.tabs(["Sales and margin", "Stock", "Slow movers", "Cities"])

    # ── Sales and margin ──
    with _ps_tab1:
        card_open("Products", f"{_ps['label']}: revenue, margin and growth vs the month before")
        _ps_sales = pd.DataFrame({
            "Product": _ps_p["Product"], "Category": _ps_p["category"], "Units": _ps_p["units"],
            "Revenue (GHS)": _ps_p["revenue"].round(0), "Share %": (_ps_p["share"] * 100).round(1),
            "Margin %": (_ps_p["margin_pct"] * 100).round(1), "Gross Profit (GHS)": _ps_p["margin"].round(0),
            "Growth %": (_ps_p["growth"] * 100).round(0), "Customers": _ps_p["customers"],
            "Cities": _ps_p["cities"], "Top City": _ps_p["top_city"]}) if len(_ps_p) else pd.DataFrame()
        st.dataframe(_ps_sales, use_container_width=True, hide_index=True,
                     column_config={"Revenue (GHS)": st.column_config.NumberColumn(format="localized"),
                                    "Gross Profit (GHS)": st.column_config.NumberColumn(format="localized"),
                                    "Units": st.column_config.NumberColumn(format="localized")})
        card_close()

        _ps_cat = _ps["categories"]
        if len(_ps_cat):
            card_open("By Category")
            st.dataframe(pd.DataFrame({
                "Category": _ps_cat["Category"], "Products": _ps_cat["products"],
                "Revenue (GHS)": _ps_cat["revenue"].round(0), "Share %": (_ps_cat["share"] * 100).round(1),
                "Margin %": (_ps_cat["margin_pct"] * 100).round(1), "Growth %": (_ps_cat["growth"] * 100).round(0)}),
                use_container_width=True, hide_index=True,
                column_config={"Revenue (GHS)": st.column_config.NumberColumn(format="localized")})
            card_close()

        # Revenue and margin trend, month by month
        _ps_L = _ps["lines"]
        _ps_tr = (_ps_L.groupby("Month").agg(rev=("Revenue", "sum"), cost=("Cost", "sum")).tail(12))
        _ps_tr["mp"] = (1 - _ps_tr["cost"] / _ps_tr["rev"]) * 100
        card_open("Revenue and Gross Margin by Month", "Bars = revenue, line = margin %")
        _ps_fig3 = go.Figure()
        _ps_fig3.add_bar(x=[pd.Period(m, freq="M").strftime("%b %y") for m in _ps_tr.index], y=_ps_tr["rev"],
                         name="Revenue", marker=bar_marker(BRAND_GREEN))
        _ps_fig3.add_scatter(x=[pd.Period(m, freq="M").strftime("%b %y") for m in _ps_tr.index], y=_ps_tr["mp"],
                             name="Margin %", yaxis="y2", mode="lines+markers+text",
                             text=[f"{v:.1f}%" for v in _ps_tr["mp"]], textposition="top center",
                             line=dict(color=BRAND_GOLD, width=3))
        _ps_lay3 = white_layout(height=320)
        _ps_lay3.update(yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[0, 50], ticksuffix="%"),
                        legend=dict(orientation="h", y=1.1, x=0), xaxis=dict(tickangle=0))
        _ps_fig3.update_layout(**_ps_lay3)
        st.plotly_chart(_ps_fig3, use_container_width=True, config=CHART_CFG)
        card_close()

    # ── Stock ──
    with _ps_tab2:
        if not _ps_s:
            st.info("No stock batches found for Ghana.")
        else:
            _ps_b, _ps_sp = _ps["batches"], _ps["stock"]
            _ps_sold_pct = _ps_s["sold"] / _ps_s["received"] * 100 if _ps_s["received"] else 0
            st.markdown('<div class="kpi-grid">' + "".join([
                _ps_card("Units Received", f"{_ps_s['received']:,}",
                         f"{_ps_s['products']} products, {len(_ps_b)} batches", BRAND_GREEN),
                _ps_card("Units Sold", f"{_ps_s['sold']:,}", f"{_ps_sold_pct:.1f}% of units received", "#16a34a"),
                _ps_card("Units Remaining", f"{_ps_s['remaining']:,}", f"{_ps_s['in_stock']} products in stock",
                         "#14b8a6"),
                _ps_card("Stock Value", f"GHS {_ps_s['value_price']:,.0f}",
                         f"At selling price (GHS {_ps_s['value_cost']:,.0f} at cost)", BRAND_GOLD),
                _ps_card("Out of Stock", f"{_ps_s['out']}", "Products with nothing left", "#dc2626"),
                _ps_card("Low Stock", f"{_ps_s['low']}", f"Under {stk.LOW_STOCK_WEEKS} weeks of sales left",
                         "#f59e0b"),
                _ps_card("Expiring Soon", f"{_ps_s['expiring_units']:,} units",
                         f"Within {stk.EXPIRY_WARN_DAYS} days (GHS {_ps_s['expiring_value']:,.0f})", "#f97316"),
                _ps_card("Expired", f"{_ps_s['expired_units']:,} units",
                         f"Past expiry, unsold (GHS {_ps_s['expired_value']:,.0f})", "#991b1b"),
            ]) + "</div>", unsafe_allow_html=True)

            _ps_c = _ps_sp.sort_values("received")
            card_open("Sold and Remaining by Product", "Units since each batch was received")
            _ps_fig = go.Figure()
            _ps_fig.add_bar(y=_ps_c["Product"], x=_ps_c["sold"], name="Sold", orientation="h",
                            marker=bar_marker(BRAND_GREEN))
            _ps_fig.add_bar(y=_ps_c["Product"], x=_ps_c["remaining"], name="Remaining", orientation="h",
                            marker=bar_marker(BRAND_GOLD), text=_ps_c["remaining"].map("{:,} left".format),
                            textposition="outside", cliponaxis=False, textfont=dict(size=12, color=CHART_FONT))
            _ps_lay = white_layout(height=max(320, 28 * len(_ps_c) + 80))
            _ps_lay.update(barmode="stack", xaxis=dict(tickangle=0, gridcolor=CHART_GRID, tickformat=",.0f",
                                                       range=[0, _ps_c["received"].max() * 1.25]),
                           yaxis=dict(automargin=True, ticksuffix="  ", tickfont=dict(size=12, color=CHART_FONT)),
                           legend=dict(orientation="h", y=1.04, x=0),
                           margin=dict(t=30, b=30, l=10, r=40))
            _ps_fig.update_layout(**_ps_lay)
            st.plotly_chart(_ps_fig, use_container_width=True, config=CHART_CFG)
            card_close()

            card_open("Stock by Product", "Most urgent first: out of stock, expired, expiring, low stock")
            _ps_tbl = pd.DataFrame({
                "Product": _ps_sp["Product"], "Status": _ps_sp["status"], "Received": _ps_sp["received"],
                "Sold": _ps_sp["sold"], "Remaining": _ps_sp["remaining"], "% Sold": (_ps_sp["sold_pct"] * 100).round(1),
                "Sold / Week": _ps_sp["pace"].round(1), "Weeks Left": _ps_sp["weeks_left"].round(1),
                "Next Expiry": _ps_sp["next_expiry"].dt.strftime("%d %b %Y").fillna(""),
                "Selling Price (GHS)": _ps_sp["price"], "Stock Value (GHS)": _ps_sp["value_price"].round(0)})
            st.dataframe(_ps_tbl, use_container_width=True, hide_index=True,
                         column_config={"% Sold": st.column_config.ProgressColumn("% Sold", min_value=0,
                                                                                  max_value=100, format="%.0f%%"),
                                        "Stock Value (GHS)": st.column_config.NumberColumn(format="localized"),
                                        "Selling Price (GHS)": st.column_config.NumberColumn(format="%.2f")})
            card_close()

            _ps_w = prr.weekly(_ps["lines"])
            _ps_names = dict(zip(_ps_sp["product_id"], _ps_sp["Product"]))
            _ps_pick = st.multiselect("Products in the weekly sales chart (leave empty for all stocked products)",
                                      sorted(_ps_sp["Product"]), key="ps_pick")
            _ps_ids = [i for i, n in _ps_names.items() if not _ps_pick or n in _ps_pick]
            _ps_wk = _ps_w[[c for c in _ps_w.columns if c in _ps_ids]].sum(axis=1)
            card_open("Units Sold per Week", f"Last {len(_ps_wk)} complete weeks (Monday to Sunday)")
            _ps_fig2 = go.Figure(go.Bar(x=[f"{d:%d %b}" for d in _ps_wk.index], y=_ps_wk.values,
                                        marker=bar_marker(BRAND_GREEN), text=[f"{v:,.0f}" for v in _ps_wk.values],
                                        textposition="outside"))
            _ps_fig2.update_layout(**white_layout(height=300))
            st.plotly_chart(_ps_fig2, use_container_width=True, config=CHART_CFG)
            card_close()

            with st.expander(f"Batch detail ({len(_ps_b)} batches)"):
                _ps_only = st.toggle("Only batches with stock remaining", value=True, key="ps_only")
                _ps_bt = _ps_b[_ps_b["Remaining"] > 0] if _ps_only else _ps_b
                st.dataframe(pd.DataFrame({
                    "Product": _ps_bt["Product"], "Batch": _ps_bt["Batch"], "Received": _ps_bt["Received"],
                    "Sold": _ps_bt["Sold"], "Remaining": _ps_bt["Remaining"],
                    "Expiry": _ps_bt["Expiry"].dt.strftime("%d %b %Y"), "Days to Expiry": _ps_bt["Days to Expiry"],
                    "Storage": _ps_bt["Storage"]}).sort_values("Days to Expiry"),
                    use_container_width=True, hide_index=True)

    # ── Slow movers ──
    with _ps_tab3:
        _ps_slow, _ps_stop = _ps["slow"], _ps["stopped"]
        card_open("In Stock but Not Selling",
                               f"Stock left and no sale in the last {prr.SLOW_DAYS} days")
        if len(_ps_slow):
            st.dataframe(pd.DataFrame({
                "Product": _ps_slow["Product"], "Units Left": _ps_slow["remaining"],
                "Stock Value (GHS)": _ps_slow["value_price"].round(0),
                "Last Sold": _ps_slow["last_sale"].dt.strftime("%d %b %Y").fillna("Never"),
                "Days Since Sale": _ps_slow["days_since"]}), use_container_width=True, hide_index=True)
        else:
            st.caption(f"None: every product in stock sold in the last {prr.SLOW_DAYS} days.")
        card_close()
        card_open("Stopped Selling", f"Sold in the {prr.LOOKBACK_DAYS} days before, nothing in the "
                                                   f"last {prr.SLOW_DAYS} days")
        if len(_ps_stop):
            st.dataframe(pd.DataFrame({
                "Product": _ps_stop["Product"], "Revenue Before (GHS)": _ps_stop["revenue"].round(0),
                "Customers Before": _ps_stop["customers"],
                "Last Sold": _ps_stop["last_sale"].dt.strftime("%d %b %Y"),
                "Days Since Sale": _ps_stop["days_since"]}), use_container_width=True, hide_index=True,
                column_config={"Revenue Before (GHS)": st.column_config.NumberColumn(format="localized")})
        else:
            st.caption("None.")
        card_close()

    # ── Cities ──
    with _ps_tab4:
        _ps_ct = _ps["cities"]
        if len(_ps_ct):
            _ps_top = _ps_ct.head(12).iloc[::-1]
            card_open("Revenue by City", f"{_ps['label']}: top {len(_ps_top)} customer cities")
            _ps_fig4 = go.Figure(go.Bar(
                y=_ps_top["City"], x=_ps_top["revenue"], orientation="h", marker=bar_marker(BRAND_GREEN),
                text=[f"GHS {v:,.0f}  ({sh * 100:.0f}%)" for v, sh in zip(_ps_top["revenue"], _ps_top["share"])],
                textposition="outside", cliponaxis=False, textfont=dict(size=13, color=CHART_FONT),
                hovertemplate="%{y}: GHS %{x:,.0f}<extra></extra>"))
            _ps_lay4 = white_layout(height=max(320, 38 * len(_ps_top) + 60))
            _ps_lay4.update(xaxis=dict(tickangle=0, gridcolor=CHART_GRID, range=[0, _ps_top["revenue"].max() * 1.45],
                                       tickformat=",.0f"),
                            yaxis=dict(automargin=True, ticksuffix="  ", tickfont=dict(size=13, color=CHART_FONT)),
                            margin=dict(t=10, b=30, l=10, r=20), bargap=0.25)
            _ps_fig4.update_layout(**_ps_lay4)
            st.plotly_chart(_ps_fig4, use_container_width=True, config=CHART_CFG)
            card_close()
            st.dataframe(pd.DataFrame({
                "City": _ps_ct["City"], "Revenue (GHS)": _ps_ct["revenue"].round(0),
                "Share %": (_ps_ct["share"] * 100).round(1), "Customers": _ps_ct["customers"],
                "Products": _ps_ct["products"], "Margin %": (_ps_ct["margin_pct"] * 100).round(1),
                "Growth %": (_ps_ct["growth"] * 100).round(0)}), use_container_width=True, hide_index=True,
                column_config={"Revenue (GHS)": st.column_config.NumberColumn(format="localized")})
            st.caption("City = the customer city recorded on each invoice.")
        else:
            st.caption("No sales in the month.")

    _ps_sheets = {"Products": _ps_sales, "Categories": _ps["categories"], "Cities": _ps["cities"],
                  "Stock": _ps["stock"], "Batches": _ps["batches"], "Slow Movers": _ps["slow"],
                  "Stopped Selling": _ps["stopped"]}
    st.download_button(
        "Download product report (.xlsx)",
        data=make_excel({k: v for k, v in _ps_sheets.items() if isinstance(v, pd.DataFrame) and len(v)}),
        file_name=f"TribeCo_Ghana_Products_{_ps_month}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption("Sources: Metabase invoice lines (Ghana FBC, not cancelled) with the cost price from each invoice's "
               "order, and stock batches for received / sold / remaining. Margin = (price - cost) / price.")

elif page == "Admin" and IS_ADMIN:
    import mailer as _mailer
    _smtp = _mailer.config_from(_secrets_dict())
    admin_page.render(_get_store(), USER_EMAIL or "admin", list(_BOOT_ADMINS),
                      dict(inv=inv, inv_scoped=inv_scoped, rep_scoped=rep_scoped, rc=rc, il=il, prod=prod,
                           data_dir=DATA, product_frames=load_products()[0]), _smtp)

elif page == "Data Export":
    _de_text = lambda html: st.markdown(
        f'<div style="font-size:13px;color:{_T["text_muted"]};margin:0 0 14px">{html}</div>',
        unsafe_allow_html=True)
    _de_text("Every core TribeCo table, scoped to Ghana only, in one workbook. "
             "For easy reference, all data are live from the Metabase.")

    if st.button("🗂️ Ghana Raw Data sheet", type="primary", use_container_width=True):
        with st.spinner("Pulling and scoping every table to Ghana..."):
            def _de_load(name):
                df = pd.read_csv(f"{DATA}/{name}.csv")
                for col in df.columns:
                    if col in ("Created At", "Updated At", "Due Date", "Repayment Date", "Completed At",
                              "Start Date", "End Date", "Expected At", "Paid At"):
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                return df

            _de_payment = _de_load("payment")
            _de_invoice = _de_load("invoice")
            _de_repayment = _de_load("repayment")
            _de_rc = _de_load("retail_centre")
            _de_product = _de_load("product")
            _de_il = _de_load("invoice_line")
            _de_ir = _de_load("inventory_request")
            _de_ibv = _de_load("inventory_balances_view")
            _de_camp = _de_load("preorder_campaign")
            _de_irf = _de_load("inventory_request_fulfillment")

            _de_invoice_gh = _de_invoice[_de_invoice["Country Code"] == "GH"].copy()
            _de_repayment_gh = _de_repayment[_de_repayment["Country Code"] == "GH"].copy()
            _de_rc_gh = _de_rc[_de_rc["Country Code"] == "GH"].copy()
            _de_ir_gh = _de_ir[_de_ir["Country Code"] == "GH"].copy()

            _de_gh_invoice_ids = set(_de_invoice_gh["ID"].dropna())
            _de_gh_rc_ids = set(_de_rc_gh["ID"].dropna())
            _de_gh_request_ids = set(_de_ir_gh["ID"].dropna())

            _de_il_gh = _de_il[_de_il["Invoice ID"].isin(_de_gh_invoice_ids)].copy()
            _de_ibv_gh = _de_ibv[_de_ibv["Retail Centre ID"].isin(_de_gh_rc_ids)].copy()
            _de_irf_gh = _de_irf[_de_irf["Request ID"].isin(_de_gh_request_ids)].copy()
            _de_gh_sold_product_ids = set(_de_il_gh["Product ID"].dropna())
            _de_product_gh = _de_product[_de_product["ID"].isin(_de_gh_sold_product_ids)].copy()

            # Flag which rows actually feed the dashboard's own KPIs (a narrower slice
            # than "all Ghana" -- excludes cancelled invoices, non-standard order types,
            # and the BufferPesa channel).
            _de_invoice_gh["Included in Dashboard KPIs"] = (
                (_de_invoice_gh["Order Type"] == 1) &
                (_de_invoice_gh["Channel"] != "BufferPesa") &
                (_de_invoice_gh["Status"] != 5))
            _de_qualifying_ids = set(_de_invoice_gh[_de_invoice_gh["Included in Dashboard KPIs"]]["ID"])
            _de_repayment_gh["Included in Dashboard KPIs"] = _de_repayment_gh["Invoice ID"].isin(_de_qualifying_ids)
            _de_il_gh["Included in Dashboard KPIs"] = _de_il_gh["Invoice ID"].isin(_de_qualifying_ids)

            _de_readme = pd.DataFrame([
                ("Generated", pd.Timestamp.now().strftime("%d %b %Y %H:%M")),
                ("", ""),
                ("Sheet", "Ghana scoping applied"),
                ("Invoice", f"Country Code = GH ({len(_de_invoice_gh)} of {len(_de_invoice)} rows). "
                            f"'Included in Dashboard KPIs' column flags the narrower "
                            f"{_de_invoice_gh['Included in Dashboard KPIs'].sum()}-row slice the dashboard "
                            f"itself reports on (excludes cancelled invoices, non-standard order types, "
                            f"and BufferPesa-channel orders)."),
                ("Repayment", f"Country Code = GH ({len(_de_repayment_gh)} of {len(_de_repayment)} rows). "
                              f"Same 'Included in Dashboard KPIs' flag, based on whether its invoice "
                              f"qualifies."),
                ("Retail Centre", f"Country Code = GH ({len(_de_rc_gh)} of {len(_de_rc)} rows)"),
                ("Invoice Line", f"Invoice ID belongs to a GH invoice ({len(_de_il_gh)} of {len(_de_il)} rows)"),
                ("Inventory Request", f"Country Code = GH ({len(_de_ir_gh)} of {len(_de_ir)} rows)"),
                ("Inventory Balances", f"Retail Centre ID belongs to a GH retail centre "
                                       f"({len(_de_ibv_gh)} of {len(_de_ibv)} rows)"),
                ("Inventory Fulfillment", f"Request ID belongs to a GH inventory request "
                                          f"({len(_de_irf_gh)} of {len(_de_irf)} rows)"),
                ("Product", f"Product ID has actually sold on a GH invoice ({len(_de_product_gh)} of "
                            f"{len(_de_product)} rows). NOTE: the catalogue's own 'Country' field mixes "
                            f"manufacturing origin (e.g. CN, NL) with market codes and isn't reliable for "
                            f"Ghana/Kenya scoping, so this sheet is scoped by actual Ghana sales instead."),
                ("Payment", f"NOT scoped -- no country field and no reliable link to Ghana records. "
                            f"Included in full ({len(_de_payment)} rows). Treat as a mixed GH/KE table."),
                ("Preorder Campaign", f"NOT scoped -- no country field and only {len(_de_camp)} rows "
                                      f"total. Included in full."),
            ], columns=["Item", "Detail"])

            _de_sheets = {
                "README": _de_readme,
                "Invoice": _de_invoice_gh,
                "Repayment": _de_repayment_gh,
                "Retail Centre": _de_rc_gh,
                "Invoice Line": _de_il_gh,
                "Inventory Request": _de_ir_gh,
                "Inventory Balances": _de_ibv_gh,
                "Inventory Fulfillment": _de_irf_gh,
                "Product": _de_product_gh,
                "Payment (unfiltered)": _de_payment,
                "Preorder Campaign (unfiltered)": _de_camp,
            }
            st.session_state["_de_workbook"] = make_excel(_de_sheets)
            st.session_state["_de_fname"] = f"TribeCo_Ghana_Data_{pd.Timestamp.now().strftime('%Y-%m-%d')}.xlsx"

    if "_de_workbook" in st.session_state:
        st.success("Workbook ready.")
        st.download_button("⬇ Download Ghana Data Workbook", data=st.session_state["_de_workbook"],
                          file_name=st.session_state["_de_fname"],
                          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          type="primary", use_container_width=True)


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
                  "In selected period", BRAND_GREEN) + \
         kpi_card("Reconciled",         f"{matched_count:,}",
                  f"{match_rate:.1f}% match rate", "#16a34a",
                  f"{match_rate:.0f}%", "#16a34a") + \
         kpi_card("Unreconciled",       f"{unmatched_count:,}",
                  "No repayment record", "#dc2626") + \
         kpi_card("Unreconciled Value", f"GHS {unmatched_val:,.2f}",
                  "Awaiting payment", "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        card_open("Reconciliation Status", "Invoice match rate")
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
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(t=10,b=10,l=10,r=10), height=300, showlegend=False,
                          font=dict(color=CHART_FONT))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        card_close()

    with col2:
        card_open("Value: Reconciled vs Unreconciled")
        val_df = pd.DataFrame({
            "Category": ["Reconciled","Unreconciled"],
            "Value":    [matched_val, unmatched_val]
        })
        fig2 = px.bar(val_df, x="Category", y="Value", color="Category",
                      color_discrete_map={"Reconciled":"#16a34a","Unreconciled":"#dc2626"},
                      text="Value")
        fig2.update_traces(texttemplate="GHS %{text:,.2f}", textposition="outside",
                           textfont=dict(size=11),
                           marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(showlegend=False, xaxis=dict(tickangle=0))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        card_close()

    card_open("Repayment Status Breakdown", "Distribution of invoice repayment statuses")
    rs = inv_y["Repayment Status"].value_counts().reset_index()
    rs.columns = ["Status","Count"]
    clrs = {"Open":BRAND_GREEN,"Repaid":"#16a34a","Overdue":"#dc2626","Due Soon":"#f59e0b"}
    fig3 = px.bar(rs, x="Status", y="Count", color="Status",
                  color_discrete_map=clrs, text="Count")
    fig3.update_traces(textposition="outside", textfont=dict(size=11),
                       marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
    fig3.update_layout(**white_layout(240))
    fig3.update_layout(showlegend=False, xaxis=dict(tickangle=0))
    st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
    card_close()

    card_open("Unreconciled Invoices", "Top invoices with no repayment record")
    unmatched_df = inv_y[inv_y["ID"].isin(unmatched_ids)].copy()
    if len(unmatched_df):
        unmatched_df = unmatched_df.merge(rc_names[["ID","Name"]], left_on="Customer ID", right_on="ID", how="left")
        show_cols = unmatched_df[["Created At","Name","Discountedvalue","Repayment Status"]].copy()
        show_cols.columns = ["Invoice Date","Customer","Amount (GHS)","Status"]
        show_cols["Amount (GHS)"] = show_cols["Amount (GHS)"].apply(lambda x: f"GHS {x:,.2f}")
        show_cols["Invoice Date"] = show_cols["Invoice Date"].dt.strftime("%Y-%m-%d")
        show_cols = show_cols.sort_values("Invoice Date", ascending=False).head(30)
        show_cols.index = pd.RangeIndex(1, len(show_cols)+1)
        st.dataframe(show_cols, use_container_width=True)
    else:
        st.success("All invoices in this period are reconciled.")
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _recon_matched = inv_y[inv_y["ID"].isin(matched_ids)].merge(rc_names[["ID","Name"]], left_on="Customer ID", right_on="ID", how="left")[["Created At","Name","Discountedvalue","Repayment Status"]].copy()
    _recon_matched.columns = ["Invoice Date","Customer","Amount","Status"]
    _recon_unmatched = inv_y[inv_y["ID"].isin(unmatched_ids)].merge(rc_names[["ID","Name"]], left_on="Customer ID", right_on="ID", how="left")[["Created At","Name","Discountedvalue","Repayment Status"]].copy()
    _recon_unmatched.columns = ["Invoice Date","Customer","Amount","Status"]
    _recon_sheets = {
        "Matched (Paid)":   _recon_matched,
        "Unmatched (Unpaid)": _recon_unmatched,
    }
    _recon_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Reconciliation", "Invoice match rates  ·  unreconciled analysis", str(yr))
        _p.add_kpi_row([
            ("Total Invoices",     f"{total_invoices:,}"),
            ("Reconciled",         f"{matched_count:,}  ({match_rate:.1f}%)"),
            ("Unreconciled",       f"{unmatched_count:,}"),
            ("Unreconciled Value", f"GHS {unmatched_val:,.2f}"),
        ])
        _rs_df = inv_y["Repayment Status"].value_counts().reset_index()
        _rs_df.columns = ["Status","Count"]
        if len(_rs_df):
            _p.add_chart(_bar_png(_rs_df["Status"], _rs_df["Count"],
                                  "Repayment Status Distribution", color=BRAND_GREEN),
                         "Status Breakdown")
        if len(_recon_unmatched):
            _t = _recon_unmatched.copy()
            _t["Amount"] = pd.to_numeric(_t["Amount"], errors="coerce").apply(lambda v: f"GHS {v:,.2f}")
            _p.add_table(_t.head(30), "Unreconciled Invoices (Top 30)")
        _recon_pdf = bytes(_p.output())
    dl_row(_recon_sheets, f"Reconciliation_{yr}.xlsx", _recon_pdf,
           f"Reconciliation_{yr}.pdf", "Reconciliation")


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
        "Address Region":   rc["Customer Address"].notna().mean() * 100,
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
                  "Across all key fields", BRAND_GREEN) + \
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
            marker=dict(color=colors, cornerradius=6),
            text=df["Completeness"].apply(lambda x: f"{x:.0f}%"),
            textposition="inside", insidetextanchor="start",
            textfont=dict(color="white", size=10)
        ))
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(t=10,b=10,l=10,r=10), height=height,
                          xaxis=dict(range=[0,108], gridcolor=CHART_GRID, title="% Complete"),
                          yaxis=dict(tickfont=dict(size=11, color=CHART_FONT)),
                          font=dict(family="Inter, sans-serif", size=12, color=CHART_FONT))
        return fig

    col1, col2 = st.columns(2)
    with col1:
        card_open("Invoice Table — Field Completeness")
        st.plotly_chart(completeness_bar(inv_fields, 320), use_container_width=True, config=CHART_CFG)
        card_close()

    with col2:
        card_open("Customer Table — Field Completeness")
        st.plotly_chart(completeness_bar(rc_fields, 320), use_container_width=True, config=CHART_CFG)
        card_close()

    card_open("Repayment Table — Field Completeness")
    st.plotly_chart(completeness_bar(rep_fields, 240), use_container_width=True, config=CHART_CFG)
    card_close()

    card_open("Data Quality Summary")
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
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _dq_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Data Quality", "Field completeness across Invoice  ·  Customer  ·  Repayment")
        _p.add_kpi_row([
            ("Avg Completeness", f"{avg_completeness:.1f}%"),
            ("Critical Gaps",    f"{critical_fields}"),
            ("High Quality",     f"{good_fields}"),
            ("Tables Audited",   "3"),
        ])
        for _tname, _fdict in [("Invoice", inv_fields), ("Customer", rc_fields), ("Repayment", rep_fields)]:
            _df_f = pd.DataFrame({"Field": list(_fdict.keys()), "Completeness %": [f"{v:.1f}%" for v in _fdict.values()]})
            _p.add_table(_df_f, f"{_tname} Table - Field Completeness")
        _dq_pdf = bytes(_p.output())
    dl_row({"Data Quality": dq_df.reset_index(drop=True)}, "Data_Quality.xlsx",
           _dq_pdf, "Data_Quality.pdf", "Data Quality")


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
                  f"{completed_fbc:,}/{total_fbc:,} FBC orders fulfilled", BRAND_GREEN) + \
         kpi_card("Pending / In-Progress",
                  f"{ir_all_fbc[ir_all_fbc['Status'].isin([0,1,2])].shape[0]:,}",
                  "Orders not yet completed", "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    card_open("Fulfillment Status Breakdown", "Derived from FBC order status")
    irf_s = ir_all_fbc["Fulfillment Label"].value_counts().reset_index()
    irf_s.columns = ["Status","Count"]
    irf_colors = {"Completed":"#16a34a","Not Started":"#f59e0b","Scheduled":BRAND_GOLD,
                  "In Progress":"#14b8a6","Cancelled":"#dc2626","Unknown":"#9ca3af"}
    fig2 = px.pie(irf_s, names="Status", values="Count", hole=0.5,
                  color="Status", color_discrete_map=irf_colors)
    fig2.update_traces(textinfo="percent", textposition="inside",
                       insidetextorientation="horizontal",
                       textfont=dict(size=13, color="white"))
    fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                       margin=dict(t=10,b=10,l=10,r=10), height=340, showlegend=True,
                       font=dict(color=CHART_FONT),
                       legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11, color=CHART_FONT)))
    st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _ir_dl = ir_all_fbc[["ID","Created At","Status","Fulfillment Label","Channel","Fulfillment Type"]].copy()
    _ibv_dl = ibv[["Retail Centre ID","Product ID","Balance"]].copy() if len(ibv) else pd.DataFrame()
    _rel_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Reliability", "Stockout rates  ·  FBC fulfillment tracking")
        _p.add_kpi_row([
            ("Stockout Rate",       f"{stockout_pct:.1f}%"),
            ("In-Stock Rate",       f"{100-stockout_pct:.1f}%"),
            ("Fulfillment Rate",    f"{irf_rate:.1f}%"),
            ("Pending/In-Progress", f"{ir_all_fbc[ir_all_fbc['Status'].isin([0,1,2])].shape[0]:,}"),
        ])
        _fs = ir_all_fbc["Fulfillment Label"].value_counts().reset_index()
        _fs.columns = ["Status","Count"]
        if len(_fs):
            _p.add_chart(_bar_png(_fs["Status"], _fs["Count"],
                                  "Fulfillment Status Distribution", color=BRAND_GREEN),
                         "FBC Order Fulfillment Status")
        _t = _ir_dl.copy()
        _t["Created At"] = pd.to_datetime(_t["Created At"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        _p.add_table(_t[["ID","Created At","Fulfillment Label","Channel"]].head(30), "Fulfillment Orders (Top 30)")
        _rel_pdf = bytes(_p.output())
    dl_row({"Fulfillment Status": _ir_dl, "Inventory Balances": _ibv_dl}, "Reliability.xlsx",
           _rel_pdf, "Reliability.pdf", "Reliability")


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
                  f"{classified_pct:.1f}% of {len(rc):,} registered", BRAND_GREEN) + \
         kpi_card("SKU Breadth/Agrovet",  f"{sku_breadth:.1f}",
                  "Avg distinct SKUs per customer/month", "#14b8a6") + \
         kpi_card("Top-5 Revenue Conc.",  f"{top5_pct:.1f}%",
                  "Share from top 5 customers", "#f97316") + \
         kpi_card("High-Freq Small Orders",f"{hfso_pct:.1f}%",
                  f"Orders ≤ GHS {low_thresh:,.2f}", "#dc2626")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    seg_colors = {"Provider":BRAND_GREEN,"Agrovet":"#14b8a6","Hatchery":"#f59e0b","Unclassified":"#9ca3af"}

    col1, col2 = st.columns(2)
    with col1:
        card_open("Sales by Customer Segment", "Total order value per segment")
        fig = px.bar(by_segment, x="Segment Type", y="Sales", color="Segment Type",
                     color_discrete_map=seg_colors, text="Sales")
        fig.update_traces(texttemplate="GHS %{text:,.2f}", textposition="outside", textfont=dict(size=10),
                          marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig.update_layout(**white_layout(300))
        fig.update_layout(showlegend=False, xaxis=dict(tickangle=0))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
        card_close()

    with col2:
        card_open("Revenue per Purchase by Segment", "Avg order value per account type")
        rpp = by_segment[by_segment["Segment Type"] != "Unclassified"].copy()
        fig2 = px.bar(rpp, x="Segment Type", y="Rev/Purchase", color="Segment Type",
                      color_discrete_map=seg_colors, text="Rev/Purchase")
        fig2.update_traces(texttemplate="GHS %{text:,.2f}", textposition="outside", textfont=dict(size=11),
                           marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig2.update_layout(**white_layout(300))
        fig2.update_layout(showlegend=False, xaxis=dict(tickangle=0),
                           yaxis=dict(title="Avg Rev/Purchase (GHS)", gridcolor="#f3f4f6"))
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
        card_close()

    col3, col4 = st.columns(2)
    with col3:
        card_open("Revenue Concentration — Top Customers",
                               "Cumulative share of total sales")
        crev_df = crev.reset_index()
        crev_df.columns = ["Customer ID","Sales"]
        crev_df["Cumulative %"] = crev_df["Sales"].cumsum() / total_sales * 100
        crev_df["Rank"] = range(1, len(crev_df)+1)
        fig3 = go.Figure()
        fig3.add_scatter(x=crev_df["Rank"], y=crev_df["Cumulative %"],
                         mode="lines", line=dict(color=BRAND_GREEN, width=2.5), fill="tozeroy",
                         fillcolor="rgba(79,70,229,0.1)")
        fig3.add_hline(y=top5_pct,  line_dash="dot", line_color="#f97316",
                       annotation_text=f"Top 5: {top5_pct:.0f}%",
                       annotation_position="top left",
                       annotation_font=dict(color="#f97316", size=11))
        fig3.add_hline(y=top10_pct, line_dash="dot", line_color="#dc2626",
                       annotation_text=f"Top 10: {top10_pct:.0f}%",
                       annotation_position="bottom left",
                       annotation_font=dict(color="#dc2626", size=11))
        fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=20, b=50, l=60, r=20), height=300,
                           font=dict(family="Inter, sans-serif", size=12, color=CHART_FONT),
                           xaxis=dict(title="Customer Rank", tickangle=0, gridcolor=CHART_GRID),
                           yaxis=dict(title="Cumulative Revenue %", gridcolor=CHART_GRID))
        st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)
        card_close()

    with col4:
        card_open("Order Value Distribution", "High-frequency small orders analysis")
        fig4 = go.Figure()
        fig4.add_histogram(x=inv_y["Discountedvalue"], nbinsx=30,
                           marker_color=BRAND_GREEN, opacity=0.8)
        fig4.add_vline(x=low_thresh, line_dash="dash", line_color="#dc2626",
                       annotation_text=f"Low-ticket<br>≤ GHS {low_thresh:,.2f}",
                       annotation_position="top left",
                       annotation_font=dict(color="#dc2626", size=10))
        fig4.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=20, b=50, l=60, r=20), height=300,
                           font=dict(family="Inter, sans-serif", size=12, color=CHART_FONT),
                           xaxis=dict(title="Order Value (GHS)", tickangle=0, gridcolor=CHART_GRID),
                           yaxis=dict(title="# Orders", gridcolor=CHART_GRID))
        st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)
        card_close()

    card_open("Portfolio Segmentation Summary — MERL")
    seg_tbl = by_segment.copy()
    seg_tbl["Sales"]        = seg_tbl["Sales"].apply(lambda x: f"GHS {x:,.2f}")
    seg_tbl["Rev/Purchase"] = seg_tbl["Rev/Purchase"].apply(lambda x: f"GHS {x:,.2f}")
    seg_tbl.columns = ["Segment","Orders","Total Sales","Customers","Rev/Purchase (AOV)"]
    seg_tbl.index = pd.RangeIndex(1, len(seg_tbl)+1)
    st.dataframe(seg_tbl, use_container_width=True)
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _seg_detail = seg_inv[["ID","Created At","Month","Customer ID","Segment Type","Discountedvalue"]].copy()
    _seg_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Segmentation", "Portfolio segments  ·  revenue concentration  ·  MERL", str(yr))
        _p.add_kpi_row([
            ("Classified Customers", f"{total_cls:,}"),
            ("SKU Breadth/Agrovet",  f"{sku_breadth:.1f}"),
            ("Top-5 Revenue Conc.",  f"{top5_pct:.1f}%"),
            ("HFSO Rate",            f"{hfso_pct:.1f}%"),
        ])
        if len(by_segment):
            _p.add_chart(_bar_png(by_segment["Segment Type"], by_segment["Sales"],
                                  "Sales by Customer Segment (GHS)", color=BRAND_GREEN, ylabel="GHS"),
                         "Revenue by Segment")
        _t = by_segment.copy()
        _t["Sales"]        = _t["Sales"].apply(lambda v: f"GHS {v:,.2f}")
        _t["Rev/Purchase"] = _t["Rev/Purchase"].apply(lambda v: f"GHS {v:,.2f}")
        _t.columns = ["Segment","Orders","Total Sales","Customers","Rev/Purchase (AOV)"]
        _p.add_table(_t, "Segment Summary")
        _seg_pdf = bytes(_p.output())
    dl_row({"Segment Summary": by_segment, "Segment Detail": _seg_detail},
           f"Segmentation_{yr}.xlsx", _seg_pdf, f"Segmentation_{yr}.pdf", "Segmentation")


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
                  "All time", BRAND_GREEN) + \
         kpi_card("Active",          f"{active_campaigns:,}",
                  "Currently running", "#16a34a",
                  str(active_campaigns), "#16a34a") + \
         kpi_card("Completed",       f"{completed_campaigns:,}",
                  "Finished campaigns", "#14b8a6") + \
         kpi_card("Programme Span",  f"{span_days} days",
                  span_label, "#f59e0b")
    st.markdown(kpi_grid(r1), unsafe_allow_html=True)

    card_open("Campaign Timeline", "Pre-order campaign periods and status")
    camp_colors = {"Active":"#16a34a","Completed":BRAND_GOLD,"Cancelled":"#dc2626","Unknown":"#9ca3af"}
    fig = px.timeline(camp, x_start="Start Date", x_end="End Date", y="Name",
                      color="Status Label", color_discrete_map=camp_colors,
                      hover_data={"Status Label":True,"Start Date":True,"End Date":True,"Name":False})
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      margin=dict(t=10,b=40,l=10,r=10), height=220,
                      xaxis=dict(gridcolor=CHART_GRID),
                      legend=dict(orientation="h", y=-0.3, font=dict(size=11, color=CHART_FONT)),
                      font=dict(family="Inter, sans-serif", size=12, color=CHART_FONT))
    st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
    card_close()

    card_open("Campaign Details")
    camp_show = camp[["Name","Start Date","End Date","Status Label"]].copy()
    camp_show["Duration (days)"] = (camp["End Date"] - camp["Start Date"]).dt.days
    camp_show["Start Date"] = camp_show["Start Date"].dt.strftime("%Y-%m-%d")
    camp_show["End Date"]   = camp_show["End Date"].dt.strftime("%Y-%m-%d")
    camp_show.columns = ["Campaign Name","Start Date","End Date","Status","Duration (days)"]
    camp_show.index = pd.RangeIndex(1, len(camp_show)+1)
    st.dataframe(camp_show, use_container_width=True)
    card_close()

    card_open("Campaign Status Distribution")
    status_dist = camp["Status Label"].value_counts().reset_index()
    status_dist.columns = ["Status","Count"]
    fig2 = px.bar(status_dist, x="Status", y="Count", color="Status",
                  color_discrete_map=camp_colors, text="Count")
    fig2.update_traces(textposition="outside", textfont=dict(size=12),
                       marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
    fig2.update_layout(**white_layout(240))
    fig2.update_layout(showlegend=False, xaxis=dict(tickangle=0))
    st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)
    card_close()

    # ── Download ──────────────────────────────────────────────────────────────────
    _camp_dl = camp[["ID","Status Label","Start Date","End Date","Created At"]].copy() if len(camp) else pd.DataFrame()
    _camp_pdf = None
    if _PDF_AVAIL:
        _p = TribePDF(); _p.add_page()
        _p.add_header("Campaigns", "Pre-order campaign timeline and status")
        _p.add_kpi_row([
            ("Total Campaigns", f"{total_campaigns:,}"),
            ("Active",          f"{active_campaigns:,}"),
            ("Completed",       f"{completed_campaigns:,}"),
            ("Programme Span",  f"{span_days} days"),
        ])
        _sd = camp["Status Label"].value_counts().reset_index()
        _sd.columns = ["Status","Count"]
        if len(_sd):
            _p.add_chart(_bar_png(_sd["Status"], _sd["Count"],
                                  "Campaigns by Status", color=BRAND_GREEN),
                         "Campaign Status Distribution")
        _p.add_table(camp_show.reset_index(drop=True)[["Campaign Name","Start Date","End Date","Status","Duration (days)"]],
                     "Campaign Details")
        _camp_pdf = bytes(_p.output())
    dl_row({"Campaigns": _camp_dl}, "Campaigns.xlsx",
           _camp_pdf, "Campaigns.pdf", "Campaigns")


# ══════════════════════════════════════════════════════════════════════════════════
# PAGE — HISTORICAL ANALYSIS (2023 · 2024 · 2025 Sales Ledger)
# ══════════════════════════════════════════════════════════════════════════════════
elif page == "Historical Analysis":
    # ── Load data ────────────────────────────────────────────────────────────────
    _h_so, _h_inv, _h_pay = load_hist_data()

    if _h_so.empty:
        st.warning("Historical data files not found. Make sure the '3 years data' folder is in the project directory.")
        st.stop()

    # ── Year filter ───────────────────────────────────────────────────────────────
    _h_col1, _ = st.columns([1, 5])
    with _h_col1:
        _h_yr = st.selectbox("Year", ["All Years", "2023", "2024", "2025"], key="hist_yr")

    if _h_yr != "All Years":
        _hy = int(_h_yr)
        h_so  = _h_so[_h_so["Year"]  == _hy].copy()
        h_inv = _h_inv[_h_inv["Year"] == _hy].copy()
        h_pay = _h_pay[_h_pay["Year"] == _hy].copy()
    else:
        h_so, h_inv, h_pay = _h_so.copy(), _h_inv.copy(), _h_pay.copy()

    # ── Metrics ───────────────────────────────────────────────────────────────────
    h_total_rev    = h_so["Invoice Total"].sum()
    h_total_inv    = h_inv["Total"].sum()
    h_collected    = h_inv["Payment"].sum()
    h_outstanding  = h_inv["Balance"].sum()
    h_coll_rate    = (h_collected / h_total_inv * 100) if h_total_inv > 0 else 0
    h_total_orders = h_so["Sales Order ID"].nunique()
    h_customers    = h_so["Customer Name"].nunique()
    h_products     = h_so["Item Name"].nunique()
    h_top_prod_row = (h_so.groupby("Item Name")["Invoice Total"].sum()
                        .sort_values(ascending=False).reset_index())
    h_top_prod     = h_top_prod_row.iloc[0]["Item Name"] if len(h_top_prod_row) else "—"

    r1 = (
        kpi_card("Total Revenue (GHS)", f"GHS {h_total_rev:,.2f}",
                 f"{h_so['Year'].nunique()} year(s) of sales", BRAND_GREEN)
        + kpi_card("Total Collected (GHS)", f"GHS {h_collected:,.2f}",
                   f"of GHS {h_total_inv:,.2f} invoiced", "#16a34a")
        + kpi_card("Outstanding Balance (GHS)", f"GHS {h_outstanding:,.2f}",
                   "unpaid invoices", "#dc2626")
        + kpi_card("Collection Rate", f"{h_coll_rate:.1f}%",
                   "payments vs invoiced", "#f59e0b")
    )
    r2 = (
        kpi_card("Total Sales Orders", f"{h_total_orders:,}",
                 "unique orders", "#0891b2")
        + kpi_card("Active Customers", f"{h_customers:,}",
                   "unique buyers", "#7c3aed")
        + kpi_card("Products Sold", f"{h_products:,}",
                   "unique products", "#0f766e")
        + kpi_card("Top Product", h_top_prod,
                   "by revenue", "#be185d")
    )
    _g = kpi_grid(r1)
    if _g: st.markdown(_g, unsafe_allow_html=True)
    _g = kpi_grid(r2)
    if _g: st.markdown(_g, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Revenue by Year (when All Years selected) ─────────────────────────────────
    if _h_yr == "All Years":
        card_open("Annual Revenue Comparison",
                               "Total sales revenue by year — GHS")
        _yr_rev = (_h_so.groupby("Year")["Invoice Total"].sum().reset_index()
                        .rename(columns={"Year": "Year", "Invoice Total": "Revenue GHS"}))
        _yr_rev["Year"] = _yr_rev["Year"].astype(str)
        fig_yr = px.bar(_yr_rev, x="Year", y="Revenue GHS", text="Revenue GHS",
                        color="Year",
                        color_discrete_sequence=[BRAND_GREEN_DEEP,"#16a34a","#f59e0b"],
                        labels={"Revenue GHS": "Revenue (GHS)"})
        fig_yr.update_traces(texttemplate="GHS %{y:,.2f}", textposition="outside",
                             marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig_yr.update_layout(**white_layout(320))
        st.plotly_chart(fig_yr, use_container_width=True, config=CHART_CFG)
        card_close()

    # ── Monthly Revenue ───────────────────────────────────────────────────────────
    card_open("Monthly Revenue (GHS)",
                           "Revenue trend by month")
    _mo_rev = (h_so.groupby("Month")["Invoice Total"].sum().reset_index()
                   .rename(columns={"Invoice Total": "Revenue GHS"})
                   .sort_values("Month"))
    _mo_rev["Month Label"] = _mo_rev["Month"].apply(
        lambda m: pd.Period(m, freq="M").strftime("%b %Y") if m and m != "NaT" else m)
    fig_mo = px.bar(_mo_rev, x="Month Label", y="Revenue GHS",
                    color_discrete_sequence=[BRAND_GREEN],
                    labels={"Month Label": "", "Revenue GHS": "Revenue (GHS)"})
    fig_mo.update_traces(marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
    fig_mo.update_layout(**white_layout(300))
    st.plotly_chart(fig_mo, use_container_width=True, config=CHART_CFG)
    card_close()

    # ── Side-by-side: Top Products & Top Customers ───────────────────────────────
    _c1, _c2 = st.columns(2)
    with _c1:
        card_open("Top 10 Products", "by revenue GHS")
        _tp = (h_so.groupby("Item Name")["Invoice Total"].sum()
                   .sort_values(ascending=False).head(10).reset_index()
                   .rename(columns={"Invoice Total": "Revenue GHS"}))
        fig_tp = px.bar(_tp, y="Item Name", x="Revenue GHS", orientation="h",
                        color_discrete_sequence=[BRAND_GREEN],
                        labels={"Item Name": "", "Revenue GHS": "Revenue (GHS)"})
        fig_tp.update_traces(marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig_tp.update_layout(**white_layout(360))
        fig_tp.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_tp, use_container_width=True, config=CHART_CFG)
        card_close()

    with _c2:
        card_open("Top 10 Customers", "by revenue GHS")
        _tc = (h_so.groupby("Customer Name")["Invoice Total"].sum()
                   .sort_values(ascending=False).head(10).reset_index()
                   .rename(columns={"Invoice Total": "Revenue GHS"}))
        fig_tc = px.bar(_tc, y="Customer Name", x="Revenue GHS", orientation="h",
                        color_discrete_sequence=["#16a34a"],
                        labels={"Customer Name": "", "Revenue GHS": "Revenue (GHS)"})
        fig_tc.update_traces(marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig_tc.update_layout(**white_layout(360))
        fig_tc.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_tc, use_container_width=True, config=CHART_CFG)
        card_close()

    # ── Sales by Region & Delivery Method ────────────────────────────────────────
    _c3, _c4 = st.columns(2)
    with _c3:
        card_open("Revenue by Region", "")
        if "Region" in h_so.columns:
            _reg = (h_so.groupby("Region")["Invoice Total"].sum()
                        .sort_values(ascending=False).head(10).reset_index()
                        .rename(columns={"Invoice Total": "Revenue GHS"}))
            fig_reg = px.pie(_reg, names="Region", values="Revenue GHS",
                             color_discrete_sequence=px.colors.qualitative.Set2)
            fig_reg.update_traces(textposition="inside", textinfo="percent+label")
            fig_reg.update_layout(**white_layout(300))
            st.plotly_chart(fig_reg, use_container_width=True, config=CHART_CFG)
        else:
            st.info("Region data not available for this selection.")
        card_close()

    with _c4:
        card_open("Revenue by Product Category", "")
        if "Product Category" in h_so.columns:
            _cat = (h_so.groupby("Product Category")["Invoice Total"].sum()
                        .sort_values(ascending=False).reset_index()
                        .rename(columns={"Invoice Total": "Revenue GHS"}))
            fig_cat = px.pie(_cat, names="Product Category", values="Revenue GHS",
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_cat.update_traces(textposition="inside", textinfo="percent+label")
            fig_cat.update_layout(**white_layout(300))
            st.plotly_chart(fig_cat, use_container_width=True, config=CHART_CFG)
        card_close()

    # ── Payment Mode Breakdown ────────────────────────────────────────────────────
    if "Mode of Payment" in h_pay.columns:
        card_open("Payment Mode Breakdown", "How customers paid")
        _pm = (h_pay.groupby("Mode of Payment")["Amount Received"].sum()
                   .sort_values(ascending=False).reset_index()
                   .rename(columns={"Amount Received": "Amount GHS"}))
        fig_pm = px.bar(_pm, x="Mode of Payment", y="Amount GHS", text="Amount GHS",
                        color_discrete_sequence=["#0891b2"])
        fig_pm.update_traces(texttemplate="GHS %{y:,.2f}", textposition="outside",
                             marker_cornerradius=6, marker_line=dict(color="rgba(255,255,255,0.55)", width=1))
        fig_pm.update_layout(**white_layout(280))
        st.plotly_chart(fig_pm, use_container_width=True, config=CHART_CFG)
        card_close()

    # ── Monthly Breakdown Table ───────────────────────────────────────────────────
    st.markdown("#### Monthly Sales Breakdown")
    _mo_tbl = (h_so.groupby("Month").agg(
        Orders=("Sales Order ID", "nunique"),
        Revenue_GHS=("Invoice Total", "sum"),
    ).reset_index().sort_values("Month"))
    _mo_inv = (h_inv.groupby(
        h_inv["Invoice Date"].dt.to_period("M").astype(str)
    ).agg(Collected_GHS=("Payment", "sum"), Total_GHS=("Total", "sum"))
    .reset_index().rename(columns={"Invoice Date": "Month"}))
    _mo_tbl = _mo_tbl.merge(_mo_inv, on="Month", how="left")
    _mo_tbl["Collection Rate"] = (_mo_tbl["Collected_GHS"] / _mo_tbl["Total_GHS"] * 100).fillna(0)
    _mo_tbl["Month Label"] = _mo_tbl["Month"].apply(
        lambda m: pd.Period(m, freq="M").strftime("%b %Y") if m and m != "NaT" else m)
    _mo_tbl["Revenue GHS"]    = _mo_tbl["Revenue_GHS"].map(lambda x: f"GHS {x:,.2f}")
    _mo_tbl["Collected GHS"]  = _mo_tbl["Collected_GHS"].fillna(0).map(lambda x: f"GHS {x:,.2f}")
    _mo_tbl["Collection Rate"] = _mo_tbl["Collection Rate"].map(lambda x: f"{x:.1f}%")
    _mo_show = _mo_tbl[["Month Label","Orders","Revenue GHS","Collected GHS","Collection Rate"]].rename(
        columns={"Month Label": "Month"})
    st.dataframe(_mo_show, use_container_width=True, hide_index=True)

    # ── Download ──────────────────────────────────────────────────────────────────
    dl_button(
        {"Sales Orders": h_so, "Invoices": h_inv, "Payments": h_pay},
        f"Historical_Analysis_{_h_yr.replace(' ','_')}.xlsx",
        "Download Historical Data"
    )
