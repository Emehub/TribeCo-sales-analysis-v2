"""
Monthly management report (emailed on the first Friday of each month, covering the previous month).

Brief format: the month's targets vs actuals, year to date vs target and the annual goal, the
month-by-month trend, vaccine doses year to date, key drivers and recommendations.
No Streamlit dependency.
"""
import numpy as np
import pandas as pd

import q_brief
import report_pdf
import weekly_report
from qr_charts import plt, _png, _style, _k, GREEN, DEEP, GOLD, RED


def previous_month(today=None):
    today = pd.Timestamp(today or pd.Timestamp.now())
    return (today.to_period("M") - 1).strftime("%Y-%m")


def _naive(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None)


def _ar_at(inv, rep, when):
    ia = inv[inv["Date"] <= when]
    repaid = rep[rep["PayDate"] <= when].groupby("Invoice ID")["Amount"].sum()
    out = (ia["V"] - ia["ID"].map(repaid).fillna(0)).clip(lower=0)
    return float(out.sum()), ia.assign(Out=out)


def compute(month, inv_scoped, rep_scoped, rc, il, prod, monthly_targets, full_hist,
            window_days=28, terms_days=28):
    year = int(month[:4])
    m_start = pd.Period(month, freq="M").start_time
    m_end = pd.Period(month, freq="M").end_time
    prev_m = (pd.Period(month, freq="M") - 1).strftime("%Y-%m")

    inv = inv_scoped.copy()
    inv["Date"] = _naive(inv["Created At"])
    inv["V"] = pd.to_numeric(inv["Discountedvalue"], errors="coerce").fillna(0)
    inv["M"] = inv["Date"].dt.strftime("%Y-%m")
    rep = rep_scoped.copy()
    rd, ca = _naive(rep["Repayment Date"]), _naive(rep["Created At"])
    rep["PayDate"] = rd.where(rd >= pd.Timestamp("2020-01-01")).fillna(ca)
    rep["Amount"] = pd.to_numeric(rep["Amount"], errors="coerce").fillna(0)
    data_end = max(inv["Date"].max(), rep["PayDate"].max())

    tg = monthly_targets[monthly_targets["Month"].str.startswith(str(year))].copy()
    mo = tg.merge(inv[inv["Date"].dt.year == year].groupby("M")["V"].agg(Revenue="sum", Orders="size")
                  .rename_axis("Month").reset_index(), on="Month", how="left")
    mo.loc[mo["Month"] > month, ["Revenue", "Orders"]] = np.nan
    mo["Attainment %"] = mo["Revenue"] / mo["Target"] * 100
    mo["Label"] = pd.to_datetime(mo["Month"]).dt.strftime("%b")
    cur = mo[mo["Month"] == month].iloc[0]
    prv = mo[mo["Month"] == prev_m].iloc[0] if (mo["Month"] == prev_m).any() else None

    done = mo[mo["Month"] <= month]
    ytd_rev, ytd_tg = done["Revenue"].sum(), done["Target"].sum()
    annual = tg["Target"].sum()
    left = tg[tg["Month"] > month]
    run_rate = done["Revenue"].tail(3).mean()
    ytd = dict(revenue=ytd_rev, target=ytd_tg, attain=ytd_rev / ytd_tg * 100 if ytd_tg else np.nan,
               annual=annual, annual_pct=ytd_rev / annual * 100 if annual else np.nan,
               remaining=max(annual - ytd_rev, 0), rest_target=left["Target"].sum(), months_left=len(left),
               projected=ytd_rev + run_rate * len(left), on_target=int((done["Attainment %"] >= 100).sum()),
               months_done=len(done))
    ytd["projected_pct"] = ytd["projected"] / annual * 100 if annual else np.nan
    ytd["needed_pct"] = ytd["remaining"] / ytd["rest_target"] * 100 if ytd["rest_target"] else np.nan

    # Receivables and DSO at month-end, by actual payment date
    asof = min(m_end, data_end)
    ar, ia = _ar_at(inv, rep, asof)
    sales_win = inv[(inv["Date"] > asof - pd.Timedelta(days=window_days)) & (inv["Date"] <= asof)]["V"].sum()
    dso = ar / sales_win * window_days if sales_win else np.nan
    past = float(ia.loc[(asof - ia["Date"]).dt.days > terms_days, "Out"].sum())
    prev_end = pd.Period(prev_m, freq="M").end_time
    ar_prev, _ = _ar_at(inv, rep, prev_end)
    coll = float(rep[(rep["PayDate"] >= m_start) & (rep["PayDate"] <= m_end)]["Amount"].sum())

    # Customers: movers vs previous month, new customers
    names = rc.set_index("ID")["Name"].astype(str).str.split().str.join(" ") if "Name" in rc.columns else pd.Series(dtype=str)
    by = inv[inv["M"].isin([prev_m, month])].groupby(["M", "Customer ID"])["V"].sum().unstack(0).fillna(0)
    by = by.reindex(columns=[prev_m, month], fill_value=0)
    by.columns = ["Prev", "Curr"]
    by["Change"] = by["Curr"] - by["Prev"]
    by.index = [names.get(i, f"Customer {i}") for i in by.index]
    by = by.sort_values("Change")
    first = full_hist.assign(D=_naive(full_hist["Created At"])).groupby("Customer ID")["D"].min()
    custs = set(inv[inv["M"] == month]["Customer ID"])
    new_c = sum(1 for c in custs if c in first and m_start <= first[c] <= m_end)

    vax, vials = q_brief.vaccine_trend(inv_scoped, il, prod, year, month)

    r = dict(month=month, label=pd.Period(month, freq="M").strftime("%B %Y"), year=year, mo=mo, cur=cur, prv=prv,
             ytd=ytd, ar=ar, ar_prev=ar_prev, dso=dso, past=past, coll=coll, terms_days=terms_days,
             movers=by, active=len(custs), new_c=new_c, vax=vax, vials=vials, data_end=data_end)
    r["drivers"], r["recs"] = drivers_recs(r)
    return r


def drivers_recs(r):
    cur, prv, y = r["cur"], r["prv"], r["ytd"]
    d, rec = [], []
    m = pd.Timestamp(r["month"]).strftime("%B")
    if prv is not None and prv["Revenue"]:
        ch = cur["Revenue"] / prv["Revenue"] - 1
        tch = cur["Target"] / prv["Target"] - 1
        d.append(f"Revenue {'rose' if ch >= 0 else 'fell'} {abs(ch) * 100:.0f}% on {prv['Label']} "
                 f"(target {'up' if tch >= 0 else 'down'} {abs(tch) * 100:.0f}%), landing at "
                 f"{cur['Attainment %']:.1f}% of the {m} target.")
    dec = r["movers"][r["movers"]["Change"] < 0].head(3)
    inc = r["movers"][r["movers"]["Change"] > 0].tail(3).iloc[::-1]
    if len(dec):
        d.append("Biggest decreases vs last month: " + ", ".join(f"{n} ({v:+,.0f})" for n, v in dec["Change"].items())
                 + (". Biggest increases: " + ", ".join(f"{n} ({v:+,.0f})" for n, v in inc["Change"].items()) if len(inc) else "")
                 + ".")
    d.append(f"Cash collected GHS {r['coll']:,.0f} ({r['coll'] / cur['Revenue'] * 100:.0f}% of {m} sales). "
             f"Receivables GHS {r['ar']:,.0f} at month-end ({(r['ar'] / r['ar_prev'] - 1) * 100 if r['ar_prev'] else 0:+.0f}% "
             f"vs last month); DSO {r['dso']:.0f} days vs a {r['terms_days']}-day term.")
    v = r["vax"]
    if len(v) >= 2:
        d.append(f"Vaccine doses {v['Total'].iloc[-1] / 1e6:.2f}M in {m}, "
                 f"{(v['Total'].iloc[-1] / v['Total'].iloc[-2] - 1) * 100:+.0f}% vs {v['Label'].iloc[-2]}.")
    d.append(f"{r['active']} customers ordered in {m}, {r['new_c']} of them new.")

    if r["dso"] > r["terms_days"]:
        rec.append(f"Collections: chase the GHS {r['past']:,.0f} past terms, oldest first, to bring DSO "
                   f"({r['dso']:.0f} days) back towards the {r['terms_days']}-day term.")
    if len(dec) and dec["Change"].iloc[0] < -20000:
        rec.append(f"Follow up with {', '.join(dec.index[:2])} on the drop in orders this month.")
    if len(v) >= 2 and v["Total"].iloc[-1] < v["Total"].iloc[-2]:
        rec.append("Check why vaccine doses fell (demand, stock availability or seasonality).")
    if y["months_left"]:
        rec.append(f"Annual goal: GHS {y['remaining']:,.0f} still needed ({y['needed_pct']:.0f}% of the remaining "
                   f"targets); aim for at least GHS {y['rest_target'] / y['months_left']:,.0f} per month.")
    if r["new_c"] <= 1:
        rec.append("Customer acquisition is flat; agree a new-customer target.")
    return d, rec


def chart_months(r):
    mo = r["mo"]
    x = np.arange(len(mo))
    done = mo["Revenue"].notna().values
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.plot(x, mo["Target"], color=GOLD, lw=2, ls="--", marker="o", ms=4, label="Monthly target", zorder=3)
    ax.plot(x[done], mo["Revenue"][done], color=GREEN, lw=2.8, marker="o", ms=6, label="Revenue", zorder=4)
    last = int(np.where(done)[0].max())
    ax.scatter([last], [mo["Revenue"].iloc[last]], s=170, color=DEEP, zorder=5)
    for xi in np.where(done)[0]:
        a = mo["Attainment %"].iloc[xi]
        ax.annotate(f"{a:.0f}%", (xi, mo["Revenue"].iloc[xi]), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=7.5, color=GREEN if a >= 100 else RED, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(mo["Label"], fontsize=8.5)
    ax.set_ylim(0, max(mo["Revenue"].max(), mo["Target"].max()) * 1.2)
    _style(ax, f"Revenue vs target by month, {r['year']} (label = attainment)", _k)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    return _png(fig)


def _row(lbl, t, a):
    return (lbl, f"GHS {t:,.0f}", f"GHS {a:,.0f}", f"{a - t:+,.0f}", f"{a / t * 100:.1f}%" if t else "n/a")


def _tiles(r):
    c, y = r["cur"], r["ytd"]
    return [
        (f"{pd.Timestamp(r['month']):%B} revenue", f"GHS {c['Revenue']:,.0f}",
         f"{c['Attainment %']:.1f}% of GHS {c['Target']:,.0f} target", "#1f7a4d" if c["Attainment %"] >= 100 else "#b91c1c"),
        ("YTD revenue", f"GHS {y['revenue']:,.0f}", f"{y['attain']:.1f}% of YTD target",
         "#1f7a4d" if y["attain"] >= 100 else "#b91c1c"),
        ("Annual goal reached", f"{y['annual_pct']:.1f}%", f"projected {y['projected_pct']:.0f}% at recent pace", "#c9975a"),
        ("Cash collected", f"GHS {r['coll']:,.0f}", "payments received in the month", "#0f766e"),
        ("Receivables", f"GHS {r['ar']:,.0f}", f"DSO {r['dso']:.0f} days vs {r['terms_days']}-day term",
         "#b91c1c" if r["dso"] > r["terms_days"] else "#1f7a4d"),
        ("Vaccine doses", f"{r['vax']['Total'].iloc[-1] / 1e6:.2f}M" if len(r["vax"]) else "n/a",
         f"{r['vax']['Total'].sum() / 1e6:.1f}M year to date" if len(r["vax"]) else "", "#1f7a4d"),
    ]


def build_pdf(r, as_of):
    pdf = report_pdf.ReportPDF(f"TribeCo Ghana  |  Monthly Report  |  {r['label']}")
    pdf.new_page()
    pdf.title_block("Ghana Monthly Report", f"{r['label']}: Targets vs Actuals",
                    f"Prepared for management  |  data as of {as_of}")
    pdf.tiles(_tiles(r))
    mo = r["mo"]
    recent = mo[mo["Month"] <= r["month"]].tail(3)
    pdf.section_title(f"1. {r['label']} targets vs actuals (with the two months before)")
    pdf.table(["Month", "Target", "Actual", "Variance (GHS)", "Attainment"],
              [_row(f"{l} {r['year']}", t, a) for l, t, a in zip(recent["Label"], recent["Target"], recent["Revenue"])],
              [40, 37, 37, 37, 32])
    y = r["ytd"]
    pdf.section_title("2. Year to date vs target and the annual goal")
    pdf.table(["Period", "Target", "Actual", "Variance (GHS)", "Attainment"], [
        _row(f"YTD (Jan - {r['cur']['Label']})", y["target"], y["revenue"]),
        (f"Annual goal {r['year']}", f"GHS {y['annual']:,.0f}", f"GHS {y['revenue']:,.0f}",
         f"{y['revenue'] - y['annual']:+,.0f}", f"{y['annual_pct']:.1f}% reached")], [40, 37, 37, 37, 32])
    pdf.body(f"{y['on_target']} of {y['months_done']} months on or above target. "
             + (f"GHS {y['remaining']:,.0f} still needed for the annual goal; at the recent pace the year closes near "
                f"GHS {y['projected']:,.0f} ({y['projected_pct']:.0f}% of goal)." if y["months_left"] else ""))
    pdf.section_title("3. Trend: month by month", need=80)
    pdf.chart(chart_months(r))
    if len(r["vax"]):
        pdf.section_title("4. Vaccines delivered: year-to-date trend", need=80)
        pdf.chart(q_brief.chart_vaccines(r["vax"]))
    pdf.section_title("5. Key drivers")
    pdf.bullets(r["drivers"], pdf._ACCENT)
    if r["recs"]:
        pdf.section_title("6. Recommendations")
        pdf.bullets(r["recs"], pdf._GOLD)
    pdf.body("Revenue = invoiced value after discount (Ghana FBC orders). Collections and receivables by actual "
             "payment date. Generated live from Metabase.")
    return pdf.output_bytes()


def email_html(r, dashboard_url=""):
    c = r["cur"]
    subject = (f"TribeCo Ghana monthly report: {r['label']} | revenue GHS {c['Revenue']:,.0f} "
               f"({c['Attainment %']:.0f}% of target)")
    points = r["drivers"][:3] + [f"Recommendation: {x}" for x in r["recs"][:2]]
    return subject, weekly_report._html_email("Ghana Monthly Report", f"{r['label']}: Targets vs Actuals",
                                              _tiles(r), points, "The full report is attached as a PDF.",
                                              dashboard_url)
