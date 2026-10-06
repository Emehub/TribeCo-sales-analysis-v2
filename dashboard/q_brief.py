"""
Brief quarter report: targets vs actuals (quarter and YTD), a weekly trend within the quarter,
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


def weekly_trend(inv_scoped, weekly_targets, year, quarter, data_end):
    """Weekly revenue vs weekly target for weeks starting inside the quarter."""
    from quarterly_review import quarter_bounds
    qs, qe = quarter_bounds(year, quarter)
    inv = inv_scoped.copy()
    inv["Date"] = _naive(inv["Created At"])
    inv["V"] = pd.to_numeric(inv["Discountedvalue"], errors="coerce").fillna(0)
    inv["Week Start"] = (inv["Date"] - pd.to_timedelta(inv["Date"].dt.weekday, unit="D")).dt.normalize()
    wt = weekly_targets.copy()
    wt["Week Start"] = pd.to_datetime(wt["Week Start"])
    wt = wt[(wt["Week Start"] >= qs) & (wt["Week Start"] <= qe)].copy()
    wt["Revenue"] = wt["Week Start"].map(inv.groupby("Week Start")["V"].sum()).fillna(0)
    wt["Week End"] = wt["Week Start"] + pd.Timedelta(days=6)
    wt["Partial"] = (wt["Week End"] > qe.normalize()) | (wt["Week End"] > data_end)
    wt["Label"] = wt["Week Start"].dt.strftime("%d %b")
    wt["Attainment %"] = wt["Revenue"] / wt["Target"] * 100
    return wt.reset_index(drop=True)


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
def chart_weekly(wt, quarter):
    x = np.arange(len(wt))
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.plot(x, wt["Target"], color=GOLD, lw=2, ls="--", marker="o", ms=4, label="Weekly target", zorder=3)
    ax.plot(x, wt["Revenue"], color=GREEN, lw=2.6, marker="o", ms=6, label="Actual revenue", zorder=4)
    ax.fill_between(x, wt["Revenue"], wt["Target"], where=wt["Revenue"] >= wt["Target"],
                    color=GREEN, alpha=0.10, interpolate=True, zorder=2)
    ax.fill_between(x, wt["Revenue"], wt["Target"], where=wt["Revenue"] < wt["Target"],
                    color=RED, alpha=0.10, interpolate=True, zorder=2)
    for xi, (rv, tg, part) in enumerate(zip(wt["Revenue"], wt["Target"], wt["Partial"])):
        ax.annotate(_k(rv) + ("*" if part else ""), (xi, max(rv, tg)), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=7.5, color=DEEP, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"w/c\n{l}" for l in wt["Label"]], fontsize=7.5)
    ax.set_ylim(0, max(wt["Revenue"].max(), wt["Target"].max()) * 1.2)
    _style(ax, f"Q{quarter} weekly trend: revenue vs weekly target (GHS)", _k)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False)
    return _png(fig)


def chart_vaccines(t):
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 3.4))
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
