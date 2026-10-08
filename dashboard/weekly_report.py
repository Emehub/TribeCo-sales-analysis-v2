"""
Weekly management report (the emailed version of the Weekly Info page).

compute() reproduces the Weekly Info page's formulas for one Monday-Sunday week; build_pdf() and
email_html() turn the result into the attachment and the email body. No Streamlit dependency.
"""
import html

import numpy as np
import pandas as pd

import report_pdf
from qr_charts import plt, _png, _style, _k, GREEN, DEEP, GOLD, RED, GREY

BUCKETS = ["Not yet due", "0-30 days overdue", "31-60 days overdue", "61-90 days overdue",
           "90+ days overdue", "No due date"]


def last_completed_week(today=None):
    """The most recent full Monday-Sunday week before `today` (pandas weekly period string)."""
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    last_sunday = today - pd.Timedelta(days=today.weekday() + 1)
    return str(pd.Period(last_sunday, freq="W"))


def _bucket(d):
    if pd.isna(d):
        return "No due date"
    if d < 0:
        return "Not yet due"
    if d <= 30:
        return "0-30 days overdue"
    if d <= 60:
        return "31-60 days overdue"
    if d <= 90:
        return "61-90 days overdue"
    return "90+ days overdue"


def compute(week, inv_scoped, rep_scoped, rc, il, weekly_targets, window_days=28, terms_days=28):
    per = pd.Period(week, freq="W")
    wk_start = per.start_time.tz_localize("UTC")
    wk_end = per.end_time.tz_localize("UTC")
    inv_wk = inv_scoped[inv_scoped["Week"] == week]
    rep = rep_scoped.copy()
    rep["Week"] = rep["Created At"].dt.to_period("W").astype(str)
    rep_wk = rep[rep["Week"] == week]

    # 1. Revenue vs weekly target
    trow = weekly_targets[weekly_targets["Week"] == week]
    target = float(trow["Target"].iloc[0]) if len(trow) else None
    revenue = float(inv_wk["Discountedvalue"].sum())
    attain = revenue / target * 100 if target else None

    # 2. Collections (repayments recorded during the week)
    collected = float(rep_wk["Amount"].sum())
    coll_pct = collected / revenue * 100 if revenue else 0.0

    # 3. DSO as of week-end (repaid amounts rebuilt from repayment dates)
    asof = min(wk_end, max(inv_scoped["Created At"].max(), rep_scoped["Created At"].max()))
    sales_win = inv_scoped[(inv_scoped["Created At"] > asof - pd.Timedelta(days=window_days)) &
                           (inv_scoped["Created At"] <= wk_end)]["Discountedvalue"].sum()
    ia = inv_scoped[inv_scoped["Created At"] <= wk_end][["ID", "Discountedvalue", "Customer ID", "Due Date"]].copy()
    repaid = rep_scoped[rep_scoped["Created At"] <= wk_end].groupby("Invoice ID")["Amount"].sum()
    ia["Repaid"] = ia["ID"].map(repaid).fillna(0)
    ia["Outstanding"] = (ia["Discountedvalue"] - ia["Repaid"]).clip(lower=0)
    ar = float(ia["Outstanding"].sum())
    dso = ar / sales_win * window_days if sales_win else None

    # 4. Active / repeat Agrovets
    agro = set(rc[rc["Segment Type"] == "Agrovet"]["ID"]) if "Segment Type" in rc.columns else set()
    wk_agro = set(inv_wk[inv_wk["Customer ID"].isin(agro)]["Customer ID"])
    prior = set(inv_scoped[(inv_scoped["Created At"] < wk_start) & inv_scoped["Customer ID"].isin(agro)]["Customer ID"])
    repeat_pct = len(wk_agro & prior) / len(wk_agro) * 100 if wk_agro else 0.0

    # 5. Multi-SKU adoption and order basics
    sku = il[il["Invoice ID"].isin(inv_wk["ID"])].groupby("Invoice ID")["Product ID"].nunique()
    multi_pct = (sku > 1).mean() * 100 if len(sku) else None

    # 6. Receivables ageing at week-end and the chase list
    ia = ia[ia["Outstanding"] > 0.01].copy()
    ia["Days Overdue"] = (wk_end - pd.to_datetime(ia["Due Date"], errors="coerce")).dt.days
    ia["Bucket"] = ia["Days Overdue"].apply(_bucket)
    aging = ia.groupby("Bucket")["Outstanding"].agg(Total="sum", Invoices="count").reindex(BUCKETS).dropna()
    names = rc.set_index("ID")["Name"].astype(str).str.split().str.join(" ") if "Name" in rc.columns else pd.Series(dtype=str)
    overdue = ia[~ia["Bucket"].isin(["Not yet due", "No due date"])]
    chase = (overdue.groupby("Customer ID").agg(Outstanding=("Outstanding", "sum"), Invoices=("ID", "count"),
                                                 Oldest=("Days Overdue", "max"))
             .sort_values("Outstanding", ascending=False).head(8))
    chase.index = [names.get(i, f"Customer {i}") for i in chase.index]

    # 7. Recent weeks for the trend (up to 8 weeks ending this week)
    weeks = sorted(w for w in inv_scoped["Week"].dropna().unique() if w <= week)[-8:]
    trend = pd.DataFrame({"Week": weeks})
    trend["Revenue"] = trend["Week"].map(inv_scoped.groupby("Week")["Discountedvalue"].sum()).fillna(0)
    trend["Target"] = trend["Week"].map(weekly_targets.set_index("Week")["Target"])
    trend["Label"] = trend["Week"].map(lambda w: pd.Period(w, freq="W").start_time.strftime("%d %b"))

    prev = weeks[-2] if len(weeks) > 1 else None
    prev_rev = float(trend["Revenue"].iloc[-2]) if prev else None

    r = dict(week=week, start=per.start_time, end=per.end_time, revenue=revenue, target=target, attain=attain,
             orders=int(len(inv_wk)), customers=int(inv_wk["Customer ID"].nunique()),
             collected=collected, coll_pct=coll_pct, ar=ar, dso=dso, terms_days=terms_days,
             active_agro=len(wk_agro), repeat_pct=repeat_pct, multi_pct=multi_pct,
             aging=aging, overdue_total=float(overdue["Outstanding"].sum()), chase=chase, trend=trend,
             prev_rev=prev_rev, week_no=per.start_time.isocalendar()[1])
    r["highlights"] = highlights(r)
    return r


def highlights(r):
    out = []
    if r["target"]:
        out.append(f"Revenue GHS {r['revenue']:,.0f} = {r['attain']:.0f}% of the GHS {r['target']:,.0f} weekly target"
                   + (f" ({(r['revenue'] / r['prev_rev'] - 1) * 100:+.0f}% vs the previous week)." if r["prev_rev"] else "."))
    else:
        out.append(f"Revenue GHS {r['revenue']:,.0f} (no weekly target on file).")
    out.append(f"Cash collected GHS {r['collected']:,.0f}, {r['coll_pct']:.0f}% of the week's sales "
               f"(payments land in later weeks, so read this alongside DSO).")
    if r["dso"] is not None:
        out.append(f"DSO {r['dso']:.0f} days against a {r['terms_days']}-day term "
                   f"({r['dso'] - r['terms_days']:+.0f} days); receivables GHS {r['ar']:,.0f}.")
    mid = r["aging"].reindex(["31-60 days overdue", "61-90 days overdue"])["Total"].fillna(0).sum()
    if mid > 0:
        out.append(f"GHS {mid:,.0f} is 31-90 days overdue: still collectible, chase before it ages past 90 days.")
    if r["multi_pct"] is not None:
        out.append(f"{r['orders']} orders from {r['customers']} customers; {r['multi_pct']:.0f}% had 2+ products.")
    return out


def chart_trend(r):
    t = r["trend"]
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 3.1))
    if t["Target"].notna().any():
        ax.plot(x, t["Target"], color=GOLD, lw=2, ls="--", marker="o", ms=4, label="Weekly target", zorder=3)
    ax.plot(x, t["Revenue"], color=GREEN, lw=2.6, marker="o", ms=6, label="Revenue", zorder=4)
    ax.scatter([x[-1]], [t["Revenue"].iloc[-1]], s=160, color=DEEP, zorder=5)
    for xi, v in zip(x, t["Revenue"]):
        ax.annotate(_k(v), (xi, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7.5,
                    color=DEEP, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"w/c {l}" for l in t["Label"]], fontsize=8)
    ax.set_ylim(0, max(t["Revenue"].max(), t["Target"].max() if t["Target"].notna().any() else 0) * 1.25)
    _style(ax, "Revenue vs weekly target, last 8 weeks (GHS)", _k)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
    return _png(fig)


def _tiles(r):
    ok = r["attain"] is not None and r["attain"] >= 100
    return [
        ("Revenue", f"GHS {r['revenue']:,.0f}",
         f"{r['attain']:.0f}% of GHS {r['target']:,.0f} target" if r["target"] else "no target on file",
         "#1f7a4d" if ok else "#b91c1c"),
        ("Orders / customers", f"{r['orders']} / {r['customers']}",
         f"{r['multi_pct']:.0f}% multi-SKU orders" if r["multi_pct"] is not None else "", "#1f7a4d"),
        ("Cash collected", f"GHS {r['collected']:,.0f}", f"{r['coll_pct']:.0f}% of the week's sales", "#0f766e"),
        ("DSO", f"{r['dso']:.0f} days" if r["dso"] is not None else "n/a", f"vs {r['terms_days']}-day term",
         "#b91c1c" if (r["dso"] or 0) > r["terms_days"] else "#1f7a4d"),
        ("Receivables", f"GHS {r['ar']:,.0f}", f"GHS {r['overdue_total']:,.0f} overdue", "#d97706"),
        ("Active Agrovets", f"{r['active_agro']}", f"{r['repeat_pct']:.0f}% repeat buyers", "#1f7a4d"),
    ]


def build_pdf(r, as_of):
    label = f"Week {r['week_no']} ({r['start']:%d %b} - {r['end']:%d %b %Y})"
    pdf = report_pdf.ReportPDF(f"TribeCo Ghana  |  Weekly Report  |  {label}")
    pdf.new_page()
    pdf.title_block("Ghana Weekly Report", label, f"Prepared for management  |  data as of {as_of}")
    pdf.section_title("1. The week at a glance")
    pdf.tiles(_tiles(r))
    pdf.section_title("2. Key points")
    pdf.bullets(r["highlights"], pdf._ACCENT)
    pdf.section_title("3. Trend", need=80)
    pdf.chart(chart_trend(r))
    pdf.section_title("4. Receivables")
    if len(r["aging"]):
        pdf.table(["Age at week-end", "Outstanding (GHS)", "Invoices"],
                  [(b, f"{v.Total:,.0f}", int(v.Invoices)) for b, v in r["aging"].iterrows()], [70, 60, 40])
    if len(r["chase"]):
        pdf.sub_title("Largest overdue balances (chase list)")
        pdf.table(["Customer", "Overdue (GHS)", "Invoices", "Oldest (days)"],
                  [(n[:40], f"{v.Outstanding:,.0f}", int(v.Invoices), int(v.Oldest)) for n, v in r["chase"].iterrows()],
                  [80, 40, 25, 30])
    pdf.body("Weeks run Monday to Sunday. Revenue = invoiced value after discount (Ghana FBC orders). "
             "Full detail on the Weekly Info page of the dashboard. Generated live from Metabase.")
    return pdf.output_bytes()


def email_html(r, dashboard_url=""):
    label = f"Week {r['week_no']} ({r['start']:%d %b} - {r['end']:%d %b %Y})"
    subject = (f"TribeCo Ghana weekly report: {label} | revenue GHS {r['revenue']:,.0f}"
               + (f" ({r['attain']:.0f}% of target)" if r["attain"] is not None else ""))
    return subject, _html_email("Ghana Weekly Report", label, _tiles(r), r["highlights"],
                                "The full report is attached as a PDF.", dashboard_url)


def _html_email(title, subtitle, tiles, points, footer, dashboard_url):
    """Simple, email-client-safe HTML (tables + inline styles)."""
    esc = html.escape
    cells = "".join(
        f'<td style="padding:6px;width:33%;vertical-align:top"><div style="background:#f1f7f4;border-radius:8px;'
        f'padding:10px 12px"><div style="font-size:11px;color:#6b7280;font-weight:bold;text-transform:uppercase">'
        f'{esc(l)}</div><div style="font-size:19px;font-weight:bold;color:#111827;margin:2px 0">{esc(v)}</div>'
        f'<div style="font-size:12px;color:{c}">{esc(s)}</div></div></td>' + ("</tr><tr>" if i % 3 == 2 else "")
        for i, (l, v, s, c) in enumerate(tiles))
    items = "".join(f'<li style="margin:0 0 6px">{esc(p)}</li>' for p in points)
    link = (f'<p><a href="{esc(dashboard_url)}" style="color:#1f7a4d;font-weight:bold">Open the dashboard</a></p>'
            if dashboard_url else "")
    return f"""<div style="font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:auto;color:#111827">
<div style="background:#024b30;color:#fff;padding:18px 20px;border-radius:10px 10px 0 0">
<div style="font-size:20px;font-weight:bold">{esc(title)}</div>
<div style="font-size:14px;color:#e0b980;margin-top:4px">{esc(subtitle)}</div></div>
<div style="border:1px solid #e5e7eb;border-top:none;padding:14px 14px 6px;border-radius:0 0 10px 10px">
<table role="presentation" style="width:100%;border-collapse:collapse"><tr>{cells}</tr></table>
<div style="font-size:15px;font-weight:bold;color:#024b30;margin:14px 6px 6px">Key points</div>
<ul style="font-size:14px;line-height:1.45;margin:0 0 10px;padding-left:26px">{items}</ul>
<p style="font-size:13px;color:#374151;margin:10px 6px">{esc(footer)}</p>{link}
<p style="font-size:11px;color:#9ca3af;margin:12px 6px 4px">Sent automatically by the TribeCo Ghana dashboard.
Data live from Metabase.</p></div></div>"""
