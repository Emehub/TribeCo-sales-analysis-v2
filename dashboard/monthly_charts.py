"""
Charts for the monthly management report (PNG bytes for report_pdf.ReportPDF.chart).
Same matplotlib style as the quarterly review (qr_charts).
"""
import numpy as np
import pandas as pd

from qr_charts import plt, _png, _style, _k, GREEN, DEEP, LIGHT, GOLD, RED, AMBER, GREY, INK

GOLD_SOFT = "#e7d3b5"


def _short(text, n=30):
    text = str(text)
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def actual_vs_target(r):
    """Monthly revenue vs target for the year: target bar behind, actual bar in front, attainment on top."""
    mo = r["mo"]
    x = np.arange(len(mo))
    done = mo["Revenue"].notna().values
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.bar(x, mo["Target"], 0.72, color=GOLD_SOFT, edgecolor=GOLD, linewidth=1, zorder=2, label="Target")
    hit = (mo["Revenue"] >= mo["Target"]).values
    ax.bar(x[done], mo["Revenue"][done], 0.42, color=[GREEN if h else RED for h in hit[done]], zorder=3,
           label="Actual")
    top = max(mo["Revenue"].max(), mo["Target"].max())
    for xi in np.where(done)[0]:
        a = mo["Attainment %"].iloc[xi]
        y = max(mo["Revenue"].iloc[xi], mo["Target"].iloc[xi])
        ax.text(xi, y + top * 0.025, f"{a:.0f}%", ha="center", va="bottom", fontsize=8.5, fontweight="bold",
                color=GREEN if a >= 100 else RED)
    cur = np.where(done)[0].max()
    ax.annotate(f"GHS {mo['Revenue'].iloc[cur]:,.0f}", (cur, mo["Revenue"].iloc[cur] / 2), ha="center", va="center",
                fontsize=7.5, color="white", fontweight="bold", rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels(mo["Label"], fontsize=9)
    ax.set_ylim(0, top * 1.18)
    _style(ax, f"Actual vs target by month, {r['year']} (label = % of target; green = target met)", _k)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=GOLD_SOFT, edgecolor=GOLD, label="Target"),
                       Patch(facecolor=GREEN, label="Actual (target met)"),
                       Patch(facecolor=RED, label="Actual (below target)")],
              fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, frameon=False)
    return _png(fig)


def cumulative(r):
    """Year to date: cumulative revenue vs cumulative target, the annual goal and the projected finish."""
    mo, y = r["mo"], r["ytd"]
    x = np.arange(len(mo))
    done = mo["Revenue"].notna().values
    cum_t = mo["Target"].cumsum().values
    cum_a = mo["Revenue"].fillna(0).cumsum().values
    last = int(np.where(done)[0].max())
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.fill_between(x[:last + 1], cum_a[:last + 1], color=GREEN, alpha=0.12, zorder=2)
    ax.plot(x, cum_t, color=GOLD, lw=2, ls="--", marker="o", ms=3.5, label="Cumulative target", zorder=3)
    ax.plot(x[:last + 1], cum_a[:last + 1], color=GREEN, lw=3, marker="o", ms=5, label="Cumulative actual", zorder=4)
    if y["months_left"]:
        pace = (y["projected"] - y["revenue"]) / y["months_left"]
        px = np.arange(last, len(mo))
        ax.plot(px, cum_a[last] + pace * (px - last), color=GREEN, lw=2, ls=":", label="Projection at recent pace",
                zorder=3)
    ax.axhline(y["annual"], color=DEEP, lw=1, alpha=0.6)
    ax.text(0, y["annual"] * 1.015, f"Annual goal GHS {y['annual']:,.0f}", fontsize=8, color=DEEP, va="bottom")
    ax.annotate(f"GHS {cum_a[last]:,.0f}\n{y['attain']:.0f}% of YTD target", (last, cum_a[last]),
                textcoords="offset points", xytext=(12, -34), ha="left", fontsize=8.5, fontweight="bold",
                color=GREEN if y["attain"] >= 100 else RED,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#d1d5db", lw=0.8))
    ax.set_xticks(x)
    ax.set_xticklabels(mo["Label"], fontsize=9)
    ax.set_ylim(0, max(y["annual"], y["projected"], cum_t[-1]) * 1.12)
    _style(ax, f"Year to date: {y['annual_pct']:.0f}% of the annual goal reached, "
               f"projected {y['projected_pct']:.0f}% by December", _k)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, frameon=False)
    return _png(fig)


def top_customers(t5, label, prev_label="last month"):
    """Top customers: revenue this month vs last month, with share of the month and orders."""
    t = t5.iloc[::-1]
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 0.62 * len(t) + 1.2))
    ax.barh(y + 0.2, t["Prev"], 0.38, color=GREY, alpha=0.55, zorder=2, label="Last month")
    up = (t["Revenue"] >= t["Prev"]).values
    ax.barh(y - 0.2, t["Revenue"], 0.38, color=[GREEN if u else AMBER for u in up], zorder=3, label=label)
    mx = max(t["Revenue"].max(), t["Prev"].max())
    for yi, row in zip(y, t.itertuples()):
        if row.Prev:
            g = row.Revenue / row.Prev - 1
            chg = ("> +300%" if g > 3 else f"{g * 100:+.0f}%") + " vs last month"
        else:
            chg = "new customer this year" if row.YTD <= row.Revenue else f"no order in {prev_label}"
        ax.text(max(row.Revenue, row.Prev) + mx * 0.01, yi, f"GHS {row.Revenue:,.0f}  ({row.Share * 100:.0f}%)  ·  "
                f"{row.Orders} order{'s' if row.Orders != 1 else ''}  ·  {chg}", va="center", fontsize=8, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([_short(v, 28) for v in t["Name"]], fontsize=9)
    ax.set_xlim(0, mx * 1.6)
    _style(ax, f"Top {len(t)} customers: revenue {label} vs last month (amber = buying less; "
               f"% = share of {label} revenue)", _k, grid="x")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    return _png(fig)


def top_products(p, label, n=10):
    """Revenue by product this month vs last month, with customers and change in customers."""
    t = p.head(n).iloc[::-1]
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(t) + 1.2))
    ax.barh(y + 0.2, t["prev_revenue"], 0.38, color=GREY, alpha=0.55, zorder=2, label="Last month")
    ax.barh(y - 0.2, t["revenue"], 0.38, color=GREEN, zorder=3, label=label)
    mx = max(t["revenue"].max(), t["prev_revenue"].max())
    for yi, row in zip(y, t.itertuples()):
        dc = row.customers - row.prev_customers
        mv = f"{dc:+d}" if dc else "same"
        ax.text(max(row.revenue, row.prev_revenue) + mx * 0.01, yi, f"GHS {row.revenue:,.0f}  ·  "
                f"{row.customers} customers ({mv})", va="center", fontsize=7.8, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([_short(v) for v in t["Product"]], fontsize=8.5)
    ax.set_xlim(0, mx * 1.5)
    _style(ax, f"Top products: revenue {label} vs last month, with customers buying", _k, grid="x")
    ax.legend(fontsize=8, loc="lower right", frameon=False)
    return _png(fig)


def product_customers(p, label, n=10):
    """Products by number of customers buying, this month vs last month (who is moving)."""
    t = p.sort_values(["customers", "revenue"], ascending=False).head(n).iloc[::-1]
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(t) + 1.2))
    ax.barh(y + 0.2, t["prev_customers"], 0.38, color=GREY, alpha=0.55, zorder=2, label="Last month")
    up = (t["customers"] >= t["prev_customers"]).values
    ax.barh(y - 0.2, t["customers"], 0.38, color=[GREEN if u else AMBER for u in up], zorder=3, label=label)
    mx = max(t["customers"].max(), t["prev_customers"].max(), 1)
    for yi, row in zip(y, t.itertuples()):
        dc = row.customers - row.prev_customers
        ax.text(row.customers + mx * 0.015, yi - 0.2, f"{row.customers}  ({dc:+d})" if dc else f"{row.customers}",
                va="center", fontsize=8, fontweight="bold", color=GREEN if dc >= 0 else AMBER)
    ax.set_yticks(y)
    ax.set_yticklabels([_short(v) for v in t["Product"]], fontsize=8.5)
    ax.set_xlim(0, mx * 1.25)
    _style(ax, f"Customers buying each product: {label} vs last month (amber = fewer customers)", None, grid="x")
    ax.legend(fontsize=8, loc="lower right", frameon=False)
    return _png(fig)


def cities(c, label, n=10):
    t = c[c["City"] != "Not recorded"].head(n).iloc[::-1]
    if t.empty:
        return None
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 0.36 * len(t) + 1.0))
    ax.barh(y, t["revenue"], 0.6, color=GREEN, zorder=3)
    mx = t["revenue"].max()
    for yi, row in zip(y, t.itertuples()):
        g = row.growth
        chg = "new" if pd.isna(g) else "> +300%" if g > 3 else f"{g * 100:+.0f}%"
        ax.text(row.revenue + mx * 0.01, yi, f"GHS {row.revenue:,.0f}  ({row.share * 100:.0f}%)  ·  "
                f"{row.customers} customer{'s' if row.customers != 1 else ''}  ·  {chg} vs last month",
                va="center", fontsize=8, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(t["City"], fontsize=8.5)
    ax.set_xlim(0, mx * 1.75)
    _style(ax, f"Revenue by customer city, {label}", _k, grid="x")
    return _png(fig)


def stock_weeks(sp, low=6, watch=10):
    """Weeks of stock left per product at the current sales pace (red = reorder now, amber = watch)."""
    t = sp[(sp["remaining"] > 0) & sp["weeks_left"].notna()].sort_values("weeks_left", ascending=False)
    if t.empty:
        return None
    y = np.arange(len(t))
    cap = 30
    w = t["weeks_left"].clip(upper=cap)
    colors = [RED if v < low else AMBER if v < watch else GREEN for v in t["weeks_left"]]
    fig, ax = plt.subplots(figsize=(10, 0.36 * len(t) + 1.1))
    ax.barh(y, w, 0.6, color=colors, zorder=3)
    for yi, (wl, rem) in zip(y, zip(t["weeks_left"], t["remaining"])):
        txt = f"{wl:.0f} wks" + (" +" if wl > cap else "") + f"  ·  {rem:,} units"
        ax.text(min(wl, cap) + 0.3, yi, txt, va="center", fontsize=8, color=INK)
    ax.axvline(low, color=RED, lw=1, ls="--", alpha=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels([_short(v, 34) for v in t["Product"]], fontsize=8.2)
    ax.set_xlim(0, cap * 1.35)
    ax.set_xlabel("Weeks of stock left at the current sales pace", fontsize=8, color=INK)
    _style(ax, f"Weeks of stock left (red = under {low} weeks: reorder; amber = under {watch})", None, grid="x")
    return _png(fig)
