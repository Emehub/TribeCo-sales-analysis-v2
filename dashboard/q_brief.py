"""
Brief quarter report: targets vs actuals (quarter and YTD), a month-by-month trend within the quarter,
and the year-to-date vaccine doses trend. Figures + charts only; the page composes the document.
"""
import numpy as np
import pandas as pd

import qr_charts as qc
from qr_charts import plt, _png, _style, _k, GREEN, DEEP, GOLD, RED, GREY, INK

DISEASE_MAP = {
    "LASOTA": "Newcastle", "NewCavac": "Newcastle", "HB1": "Newcastle", "I-2 Vaccine": "Newcastle",
    "Lasota + IB": "Newcastle", "ND+IB+EDS": "Newcastle", "GUMBORO INTER": "Gumboro",
    "FOWL POX": "Fowl pox", "Infectious Coryza": "Other poultry",
}
DISEASE_COLORS = {"Newcastle": DEEP, "Gumboro": GOLD, "Fowl pox": "#0e7490", "Other poultry": GREY}


def _naive(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None)


def vaccine_trend(inv_scoped, il, prod, year, last_month):
    """Monthly vaccine doses by disease for the year to date (doses = vials x doses per vial)."""
    inv = inv_scoped.copy()
    inv["Date"] = _naive(inv["Created At"])
    inv = inv[(inv["Date"].dt.year == year) & (inv["Date"].dt.strftime("%Y-%m") <= last_month)]
    x = il[il["Invoice ID"].isin(inv["ID"])].merge(
        prod[["ID", "Generic Name", "Brand Name", "Unit Quantity"]], left_on="Product ID", right_on="ID", how="left")
    x["Disease"] = x["Generic Name"].fillna(x["Brand Name"]).map(DISEASE_MAP)
    x = x[x["Disease"].notna()].copy()
    x["Vials"] = pd.to_numeric(x["Quantity"], errors="coerce").fillna(0)
    x["Doses"] = x["Vials"] * pd.to_numeric(x["Unit Quantity"], errors="coerce").fillna(1000)
    x["Month"] = x["Invoice ID"].map(inv.set_index("ID")["Date"]).dt.strftime("%Y-%m")
    t = x.pivot_table(index="Month", columns="Disease", values="Doses", aggfunc="sum", fill_value=0)
    t = t.reindex(columns=[d for d in DISEASE_COLORS if d in t.columns])
    t["Total"] = t.sum(axis=1)
    t["Label"] = pd.to_datetime(t.index).strftime("%b")
    t["Q"] = pd.to_datetime(t.index).quarter
    return t, x["Vials"].sum()


# ── charts ────────────────────────────────────────────────────────────────────────
def chart_quarter_months(qm, quarter):
    """Month-by-month trend within the quarter: revenue vs target, with attainment."""
    x = np.arange(len(qm))
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.plot(x, qm["Target"], color=GOLD, lw=2.2, ls="--", marker="o", ms=6, label="Monthly target", zorder=3)
    ax.plot(x, qm["Revenue"], color=GREEN, lw=3, marker="o", ms=9, label="Actual revenue", zorder=4)
    ax.fill_between(x, qm["Revenue"], qm["Target"], where=qm["Revenue"] >= qm["Target"],
                    color=GREEN, alpha=0.10, interpolate=True, zorder=2)
    ax.fill_between(x, qm["Revenue"], qm["Target"], where=qm["Revenue"] < qm["Target"],
                    color=RED, alpha=0.10, interpolate=True, zorder=2)
    for xi, (rv, tg, at) in enumerate(zip(qm["Revenue"], qm["Target"], qm["Attainment %"])):
        ax.annotate(f"GHS {_k(rv)}\n{at:.1f}% of target", (xi, max(rv, tg)), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=8.5, color=DEEP, fontweight="bold")
        ax.annotate(f"target {_k(tg)}", (xi, min(rv, tg)), textcoords="offset points", xytext=(0, -16),
                    ha="center", fontsize=7.5, color=GOLD)
    ax.set_xticks(x)
    ax.set_xticklabels(list(qm["Label"]), fontsize=10)
    ax.set_xlim(-0.4, len(qm) - 0.6)
    lo = min(qm["Revenue"].min(), qm["Target"].min())
    hi = max(qm["Revenue"].max(), qm["Target"].max())
    pad = (hi - lo) * 0.45 or hi * 0.1          # zoom to the data so the month-to-month trend is visible
    ax.set_ylim(max(0, lo - pad), hi + pad)
    _style(ax, f"Q{quarter} month-by-month trend: revenue vs target (GHS)", _k)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    return _png(fig)


def chart_vaccines(t):
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 3.0))
    for d, c in DISEASE_COLORS.items():
        if d in t.columns and t[d].sum() > 0:
            ax.plot(x, t[d] / 1e6, color=c, lw=2.4, marker="o", ms=5, label=d, zorder=3)
    ax.plot(x, t["Total"] / 1e6, color=GREEN, lw=1.6, ls=":", marker="s", ms=4, label="All vaccines", zorder=2)
    for xi, v in enumerate(t["Total"] / 1e6):
        ax.annotate(f"{v:.2f}M", (xi, v), textcoords="offset points", xytext=(0, 7), ha="center",
                    fontsize=7.5, color=GREEN, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(t["Label"], fontsize=8.5)
    ax.set_ylim(0, (t["Total"] / 1e6).max() * 1.2)
    _style(ax, "Vaccine doses delivered per month, year to date (millions of doses)", lambda v, _: f"{v:.0f}M")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=5, frameon=False)
    return _png(fig)
