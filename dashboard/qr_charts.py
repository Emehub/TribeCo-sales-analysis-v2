"""
Charts for the Quarterly Review (PNG bytes). Each chart answers one management question and is
used both on the dashboard page and in the PDF, so the two always match.
"""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

GREEN, DEEP, LIGHT = "#1f7a4d", "#024b30", "#3fa873"
GOLD, RED, AMBER, GREY, INK = "#c9975a", "#b91c1c", "#d97706", "#9ca3af", "#374151"
TITLE = "#14532d"


def _k(v, _=None):
    return f"{v/1e6:.2f}M" if abs(v) >= 1e6 else f"{v/1e3:,.0f}k"


def _att(a):
    return f"{a:.1f}%" if 99 <= a <= 101.5 else f"{a:.0f}%"


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _style(ax, title=None, yfmt=None, grid="y"):
    if title:
        ax.set_title(title, fontsize=10.5, fontweight="bold", color=TITLE, pad=8, loc="left")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#d1d5db")
    ax.spines["bottom"].set_color("#d1d5db")
    ax.tick_params(labelsize=8, colors=INK)
    if grid:
        getattr(ax, f"{grid}axis").grid(True, alpha=0.3, zorder=0)
    ax.set_axisbelow(True)
    if yfmt:
        (ax.xaxis if grid == "x" else ax.yaxis).set_major_formatter(plt.FuncFormatter(yfmt))


def _legend(ax, ncol=3):
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=ncol, frameon=False)


# ── Quarter pages ─────────────────────────────────────────────────────────────────
def quarter_months(r):
    """Did each month of the quarter hit target, and did cash keep up with sales?"""
    m = r["monthly"][r["monthly"]["Q"] == r["quarter"]]
    x = np.arange(len(m))
    fig, ax = plt.subplots(figsize=(10, 3.3))
    bars = ax.bar(x, m["Revenue"], 0.5, color=GREEN, zorder=3, label="Revenue")
    ax.scatter(x, m["Target"], marker="_", s=2200, linewidths=3, color=GOLD, zorder=4, label="Target")
    ax.plot(x, m["Collections"], color=DEEP, marker="o", lw=2.2, zorder=5, label="Cash collected")
    for xi, (rev, att, col) in enumerate(zip(m["Revenue"], m["Attainment %"], m["Collections"])):
        ax.annotate(f"GHS {_k(rev)}\n{_att(att)} of target", (xi, rev / 2), ha="center", va="center",
                    fontsize=8, color="white", fontweight="bold", zorder=6)
        ax.annotate(f"Cash {_k(col)}", (xi, col), textcoords="offset points", xytext=(0, -15), ha="center",
                    fontsize=7.5, color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=DEEP, ec="none"))
    ax.set_xticks(x)
    ax.set_xticklabels(m["Label"], fontsize=9)
    ax.set_ylim(0, max(m["Revenue"].max(), m["Target"].max(), m["Collections"].max()) * 1.18)
    _style(ax, f"Q{r['quarter']} month by month: revenue vs target, and cash collected (GHS)", _k)
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False,
              markerscale=0.35)
    return _png(fig)


def bridge(r):
    """What moved revenue from last quarter to this one?"""
    steps = r["drivers"].get("bridge")
    if not steps:
        return None
    labels = [s[0] if len(s[0]) <= 22 else s[0][:21] + "." for s in steps]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    run = 0
    for i, (lab, val, kind) in enumerate(steps):
        if kind == "total":
            ax.bar(i, val, 0.6, color=DEEP, zorder=3)
            ax.annotate(f"GHS {_k(val)}", (i, val), textcoords="offset points", xytext=(0, 4),
                        ha="center", fontsize=8.5, fontweight="bold", color=INK)
            run = val
        else:
            bottom = run if val >= 0 else run + val
            ax.bar(i, abs(val), 0.6, bottom=bottom, color=GREEN if val >= 0 else RED, zorder=3, alpha=0.9)
            ax.annotate(f"{'+' if val >= 0 else '-'}{_k(abs(val))}", (i, run + max(val, 0)),
                        textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8,
                        color=GREEN if val >= 0 else RED, fontweight="bold")
            if i + 1 < len(steps):
                ax.plot([i + 0.3, i + 0.7], [run + val] * 2, color=GREY, lw=0.8, ls=":", zorder=2)
            run += val
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels(labels, fontsize=7.5, rotation=18, ha="right")
    lo = min(s[1] for s in steps if s[2] == "total")
    ax.set_ylim(lo * 0.55, max(s[1] for s in steps if s[2] == "total") * 1.12)
    _style(ax, f"What moved revenue from Q{r['quarter']-1} to Q{r['quarter']} (GHS, by customer)", _k)
    return _png(fig)


def mix_compare(r, top=6):
    """Did the product mix shift?"""
    mc = r["drivers"].get("mix_compare")
    if mc is None or mc.empty or r["quarter"] < 2:
        return None
    mc = mc.head(top).iloc[::-1]
    q, p = r["quarter"], r["quarter"] - 1
    y = np.arange(len(mc))
    fig, ax = plt.subplots(figsize=(5, 3.4))
    ax.barh(y - 0.19, mc[p], 0.38, color=GREY, zorder=3, label=f"Q{p}")
    b = ax.barh(y + 0.19, mc[q], 0.38, color=GREEN, zorder=3, label=f"Q{q}")
    ax.bar_label(b, labels=[f"{v:.0f}%" for v in mc[q]], fontsize=7.5, padding=2, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([(n.title() if n.isupper() else n)[:18] for n in mc.index], fontsize=7.5)
    ax.set_xlim(0, mc.values.max() * 1.25)
    _style(ax, "Product mix (share of revenue)", lambda v, _: f"{v:.0f}%", grid="x")
    _legend(ax, 2)
    return _png(fig)


def aging(r):
    """How old is the money customers owe us?"""
    a = r["aging"]
    if a["Amount"].sum() == 0:
        return None
    colors = [GREEN, "#84cc16", AMBER, "#ea580c", RED]
    y = np.arange(len(a))[::-1]
    fig, ax = plt.subplots(figsize=(5, 3.4))
    b = ax.barh(y, a["Amount"], 0.6, color=colors[:len(a)], zorder=3)
    ax.bar_label(b, labels=[f"{_k(v)}  ({s:.0f}%)" for v, s in zip(a["Amount"], a["Share %"])],
                 fontsize=7.5, padding=3, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(list(a.index), fontsize=7.5)
    ax.set_xlim(0, a["Amount"].max() * 1.45)
    _style(ax, f"Receivables by age at {r['aging_asof']:%d %b} (GHS)", _k, grid="x")
    return _png(fig)


# ── Year-to-date pages ────────────────────────────────────────────────────────────
def cumulative(r):
    """Are we on track for the annual goal, and where will the year land?"""
    m, y = r["monthly"], r["ytd"]
    x = np.arange(len(m))
    done = m["Revenue"].notna().values
    last = int(np.where(done)[0].max())
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(x, m["Cum Target"], color=GOLD, lw=2, ls="--", marker="o", ms=3.5, zorder=3, label="Cumulative target")
    ax.plot(x[done], m["Cum Revenue"][done], color=GREEN, lw=2.8, marker="o", ms=5, zorder=4, label="Cumulative revenue")
    ax.fill_between(x[done], m["Cum Revenue"][done], m["Cum Target"][done],
                    where=m["Cum Revenue"][done] >= m["Cum Target"][done], color=GREEN, alpha=0.08, zorder=2)
    if last < len(m) - 1:
        px = np.arange(last, len(m))
        proj = m["Cum Revenue"].iloc[last] + y["run_rate"] * (px - last)
        ax.plot(px, proj, color=GREEN, lw=2, ls=":", zorder=3, label=f"Projection at Q{r['quarter']} run-rate")
        ax.annotate(f"Projected\nGHS {_k(proj[-1])}", (px[-1], proj[-1]), textcoords="offset points",
                    xytext=(6, -4), fontsize=8, color=GREEN, fontweight="bold", va="center")
    ax.axhline(y["annual_target"], color=RED, lw=1.2, ls="-.", zorder=2)
    ax.annotate(f"Annual goal GHS {_k(y['annual_target'])}", (0, y["annual_target"]), textcoords="offset points",
                xytext=(2, 4), fontsize=8, color=RED, fontweight="bold")
    ax.annotate(f"YTD GHS {_k(m['Cum Revenue'].iloc[last])}\n{y['attainment']:.0f}% of YTD target",
                (last, m["Cum Revenue"].iloc[last]), textcoords="offset points", xytext=(8, -14),
                ha="left", va="top", fontsize=8, color=DEEP, fontweight="bold")
    ax.axvspan(last + 0.5, len(m) - 0.5, color="#f3f4f6", zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels(m["Label"], fontsize=8.5)
    ax.set_ylim(0, max(y["annual_target"], y["projected"]) * 1.15)
    ax.set_xlim(-0.4, len(m) - 0.1)
    _style(ax, "Cumulative revenue vs target and the annual goal (GHS)", _k)
    _legend(ax, 3)
    return _png(fig)


def monthly_attainment(r):
    """Which months beat or missed target?"""
    m = r["monthly"]
    x = np.arange(len(m))
    done = m["Revenue"].notna()
    fig, ax = plt.subplots(figsize=(10, 2.5))
    ax.bar(x[~done], m["Target"][~done], 0.6, color="white", edgecolor=GOLD, ls="--", lw=1.2, zorder=3,
           label="Remaining target")
    cols = [GREEN if a >= 100 else RED for a in m["Attainment %"][done]]
    b = ax.bar(x[done], m["Revenue"][done], 0.6, color=cols, zorder=3, label="Revenue")
    ax.plot(x, m["Target"], color=GOLD, lw=1.6, marker="_", ms=14, mew=2.5, ls="none", zorder=4, label="Target")
    ax.bar_label(b, labels=[_att(a) for a in m["Attainment %"][done]], fontsize=7.5, padding=2, color=INK)
    for xi, t in zip(x[~done], m["Target"][~done]):
        ax.annotate(_k(t), (xi, t), textcoords="offset points", xytext=(0, 3), ha="center", fontsize=7, color=GOLD)
    ax.set_xticks(x)
    ax.set_xticklabels(m["Label"], fontsize=8.5)
    ax.set_ylim(0, max(m["Revenue"].max(), m["Target"].max()) * 1.18)
    _style(ax, "Monthly revenue vs target (label = attainment %)", _k)
    _legend(ax, 3)
    return _png(fig)


def trends(r, terms_days):
    """Six line charts: how each part of the business moved quarter by quarter."""
    s = r["score"]
    ql = [f"Q{q}" for q in s.columns]
    row = lambda m: [float(v) for v in s.loc[m]]
    x = list(range(len(ql)))
    fig, axes = plt.subplots(2, 3, figsize=(10.5, 6.0))

    def line(ax, metric, color, label, labels=None, below=False, dash="-"):
        ys = row(metric)
        ax.plot(x, ys, marker="o", markersize=5, color=color, lw=2.2, ls=dash, zorder=3, label=label)
        for xi, yv, t in zip(x, ys, labels or [None] * len(ys)):
            if t:
                ax.annotate(t, (xi, yv), textcoords="offset points", xytext=(0, -10 if below else 7),
                            ha="center", va="top" if below else "bottom", fontsize=6.8, color=INK)

    def fin(ax, title, fmt=None, legend=True):
        ax.set_xticks(x)
        ax.set_xticklabels(ql, fontsize=8)
        ax.set_xlim(-0.3, len(x) - 0.7)
        top = max(max(l.get_ydata()) for l in ax.get_lines())
        ax.set_ylim(0, top * 1.32)
        _style(ax, None, fmt)
        ax.set_title(title, fontsize=9.5, fontweight="bold", color=TITLE, pad=5)
        if legend:
            ax.legend(fontsize=6.8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)

    ax = axes[0, 0]
    line(ax, "Revenue", GREEN, "Actual", [f"{a:.0f}%" for a in row("Attainment %")])
    line(ax, "Target", GOLD, "Target", below=True, dash="--")
    fin(ax, "Revenue vs target (GHS)", _k)
    ax = axes[0, 1]
    line(ax, "Orders", GREEN, "Orders", [f"{o:.0f}\nAOV {a/1e3:.1f}k" for o, a in zip(row("Orders"), row("AOV"))])
    fin(ax, "Orders (with average order value)", legend=False)
    ax = axes[0, 2]
    line(ax, "Active customers", GREEN, "Active", [f"{v:.0f}" for v in row("Active customers")])
    line(ax, "New customers", GOLD, "New", [f"{v:.0f}" for v in row("New customers")])
    fin(ax, "Customers")
    ax = axes[1, 0]
    line(ax, "Revenue", GREY, "Invoiced", dash="--")
    line(ax, "Collections", GREEN, "Collected", [f"{c:.0f}%" for c in row("Collection ratio %")], below=True)
    fin(ax, "Collections vs revenue (GHS)", _k)
    ax = axes[1, 1]
    line(ax, "AR at quarter end", RED, "Receivables",
         [f"{_k(v)}\nDSO {d:.0f}d" for v, d in zip(row("AR at quarter end"), row("DSO at quarter end"))])
    fin(ax, f"Receivables at quarter end (term {terms_days}d)", _k, legend=False)
    ax = axes[1, 2]
    line(ax, "Multi-SKU %", GREEN, "Multi-SKU orders", [f"{v:.0f}%" for v in row("Multi-SKU %")])
    line(ax, "Top-5 share %", GOLD, "Top-5 customer share", [f"{v:.0f}%" for v in row("Top-5 share %")], below=True)
    fin(ax, "Mix and concentration (%)")
    plt.tight_layout(pad=0.6, h_pad=1.4)
    return _png(fig)
