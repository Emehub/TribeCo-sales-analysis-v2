"""
Quarterly performance review vs. annual goals -- the numbers behind the "Quarterly Review" page
and its PDF. Pure pandas, no Streamlit, so the page and the PDF always show the same figures.

Conventions (kept consistent with the Credit & Collections workbook):
  * Revenue = Discountedvalue on scoped invoices, by invoice date.
  * Collections are dated by the recorded Repayment Date (when cash actually arrived), not the
    system entry timestamp -- entry runs weeks behind and in batches. Repayment dates before 2020
    are treated as typos and fall back to the entry date.
  * DSO at quarter end = AR outstanding at that date / sales in the trailing `window` days x window.
"""
import numpy as np
import pandas as pd

QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}


def _naive(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None)


def quarter_bounds(year, q):
    m0, m1 = QUARTER_MONTHS[q]
    start = pd.Timestamp(year, m0, 1)
    end = pd.Timestamp(year, m1, 1) + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    return start, end


def _pct(a, b):
    return a / b * 100 if b else np.nan


def build(inv_scoped, rep_scoped, full_hist, rc, il, prod, targets, year, quarter,
          window_days=28, terms_days=28):
    """Return every figure the Quarterly Review shows. `full_hist` is all scoped invoices across
    years (for true first-order dates); `targets` has Month (YYYY-MM) and Target columns."""
    inv = inv_scoped.copy()
    inv["Date"] = _naive(inv["Created At"])
    inv = inv[inv["Date"].dt.year == year].copy()
    inv["V"] = pd.to_numeric(inv["Discountedvalue"], errors="coerce").fillna(0)
    inv["Q"] = inv["Date"].dt.quarter
    inv["Month"] = inv["Date"].dt.strftime("%Y-%m")

    rep = rep_scoped.copy()
    rd, ca = _naive(rep["Repayment Date"]), _naive(rep["Created At"])
    bad_dates = int((rd < pd.Timestamp("2020-01-01")).sum())
    rep["PayDate"] = rd.where(rd >= pd.Timestamp("2020-01-01")).fillna(ca)
    rep["EntryDate"] = ca
    rep["Amount"] = pd.to_numeric(rep["Amount"], errors="coerce").fillna(0)

    hist = full_hist.copy()
    hist["Date"] = _naive(hist["Created At"])
    first_order = hist.groupby("Customer ID")["Date"].min()
    names = (rc.set_index("ID")["Name"].astype(str).str.split().str.join(" ")
             if "Name" in rc.columns else pd.Series(dtype=str))

    tg = targets.copy()
    tg = tg[tg["Month"].str.startswith(str(year))].copy()
    tg["Q"] = pd.to_datetime(tg["Month"]).dt.quarter
    annual_target = tg["Target"].sum()

    quarters = [q for q in range(1, quarter + 1)]
    data_end = max(inv["Date"].max(), rep["PayDate"].max())

    # ── Quarterly scorecard ──────────────────────────────────────────────────────
    rows = {}
    for q in quarters:
        qs, qe = quarter_bounds(year, q)
        sub = inv[inv["Q"] == q]
        custs = set(sub["Customer ID"].dropna())
        new = sum(1 for c in custs if c in first_order and qs <= first_order[c] <= qe)
        by_cust = sub.groupby("Customer ID")["V"].sum().sort_values(ascending=False)
        coll = rep[(rep["PayDate"] >= qs) & (rep["PayDate"] <= qe)]["Amount"].sum()
        coll_entry = rep[(rep["EntryDate"] >= qs) & (rep["EntryDate"] <= qe)]["Amount"].sum()
        asof = min(qe, data_end)
        ia = inv[inv["Date"] <= asof][["ID", "V", "Date"]]
        repaid = rep[rep["PayDate"] <= asof].groupby("Invoice ID")["Amount"].sum()
        ia = ia.assign(Out=(ia["V"] - ia["ID"].map(repaid).fillna(0)).clip(lower=0))
        ar = ia["Out"].sum()
        ar_overdue = ia.loc[(asof - ia["Date"]).dt.days > terms_days, "Out"].sum()
        sales_win = inv[(inv["Date"] > asof - pd.Timedelta(days=window_days)) & (inv["Date"] <= asof)]["V"].sum()
        target = tg.loc[tg["Q"] == q, "Target"].sum()
        rows[q] = {
            "Revenue": sub["V"].sum(), "Target": target, "Attainment %": _pct(sub["V"].sum(), target),
            "Orders": len(sub), "AOV": sub["V"].mean() if len(sub) else np.nan,
            "Median order": sub["V"].median() if len(sub) else np.nan,
            "Active customers": len(custs), "New customers": new,
            "Top-5 share %": _pct(by_cust.head(5).sum(), by_cust.sum()),
            "Collections": coll, "Collections (entry date)": coll_entry,
            "Collection ratio %": _pct(coll, sub["V"].sum()),
            "AR at quarter end": ar, "AR past terms": ar_overdue,
            "AR past terms %": _pct(ar_overdue, ar),
            "DSO at quarter end": ar / sales_win * window_days if sales_win else np.nan,
        }
    # Multi-SKU adoption (orders with 2+ distinct products)
    lines = il[il["Invoice ID"].isin(inv["ID"])].merge(inv[["ID", "Q"]], left_on="Invoice ID", right_on="ID")
    sku = lines.groupby(["Q", "Invoice ID"])["Product ID"].nunique().reset_index()
    for q in quarters:
        v = sku.loc[sku["Q"] == q, "Product ID"]
        rows[q]["Multi-SKU %"] = (v > 1).mean() * 100 if len(v) else np.nan
    score = pd.DataFrame(rows)   # metrics x quarters

    # ── YTD vs annual goal ───────────────────────────────────────────────────────
    ytd_rev = inv[inv["Q"] <= quarter]["V"].sum()
    ytd_target = tg.loc[tg["Q"] <= quarter, "Target"].sum()
    remaining = max(annual_target - ytd_rev, 0)
    rest_target = tg.loc[tg["Q"] > quarter, "Target"].sum()
    months_left = int((tg["Q"] > quarter).sum())
    q_run_rate = rows[quarter]["Revenue"] / 3
    projected = ytd_rev + q_run_rate * months_left
    ytd = {
        "revenue": ytd_rev, "target": ytd_target, "attainment": _pct(ytd_rev, ytd_target),
        "annual_target": annual_target, "annual_pct": _pct(ytd_rev, annual_target),
        "remaining": remaining, "rest_target": rest_target, "months_left": months_left,
        "needed_pct_of_rest_target": _pct(remaining, rest_target),
        "run_rate": q_run_rate, "projected": projected,
        "projected_pct": _pct(projected, annual_target),
        "collections": rep[(rep["PayDate"].dt.year == year) & (rep["PayDate"] <= quarter_bounds(year, quarter)[1])]["Amount"].sum(),
    }

    # ── Monthly revenue vs target, orders, cash, and cumulative position ──────────
    rep_yr = rep[rep["PayDate"].dt.year == year]
    monthly = (tg[["Month", "Target", "Q"]]
               .merge(inv.groupby("Month")["V"].agg(Revenue="sum", Orders="size").reset_index(), on="Month", how="left")
               .merge(rep_yr.groupby(rep_yr["PayDate"].dt.strftime("%Y-%m"))["Amount"].sum()
                      .rename("Collections").rename_axis("Month").reset_index(), on="Month", how="left"))
    future = monthly["Q"] > quarter
    monthly.loc[future, ["Revenue", "Orders", "Collections"]] = np.nan
    monthly["Collections"] = monthly["Collections"].where(future, monthly["Collections"].fillna(0))
    monthly["Attainment %"] = monthly["Revenue"] / monthly["Target"] * 100
    monthly["Cum Revenue"] = monthly["Revenue"].cumsum()
    monthly["Cum Target"] = monthly["Target"].cumsum()
    monthly["Label"] = pd.to_datetime(monthly["Month"]).dt.strftime("%b")

    # ── Receivables by age at the selected quarter end ───────────────────────────
    qs_sel, qe_sel = quarter_bounds(year, quarter)
    asof = min(qe_sel, data_end)
    ia = inv[inv["Date"] <= asof][["ID", "V", "Date"]].copy()
    repaid = rep[rep["PayDate"] <= asof].groupby("Invoice ID")["Amount"].sum()
    ia["Out"] = (ia["V"] - ia["ID"].map(repaid).fillna(0)).clip(lower=0)
    ia = ia[ia["Out"] > 0.01]
    dpd = (asof - (ia["Date"] + pd.Timedelta(days=terms_days))).dt.days
    ia["Bucket"] = pd.cut(dpd, [-10**6, 0, 30, 60, 90, 10**6],
                          labels=["Within terms", "1-30 days past", "31-60 days past", "61-90 days past", "90+ days past"])
    aging = ia.groupby("Bucket", observed=False)["Out"].agg(Amount="sum", Invoices="size")
    aging["Share %"] = aging["Amount"] / aging["Amount"].sum() * 100 if aging["Amount"].sum() else 0

    # ── Drivers: customer, city and product movement vs previous quarter ──────────
    drivers = {}
    if quarter > 1:
        def _mover(col, label_map=None):
            g = inv[inv["Q"].isin([quarter - 1, quarter])].groupby(["Q", col])["V"].sum().unstack(0).fillna(0)
            g = g.reindex(columns=[quarter - 1, quarter], fill_value=0)
            g.columns = ["Prev", "Curr"]
            g["Change"] = g["Curr"] - g["Prev"]
            if label_map is not None:
                g.index = [label_map.get(i, f"Customer {i}") for i in g.index]
            return g.sort_values("Change")
        drivers["customers"] = _mover("Customer ID", names)
        if "Customer City" in inv.columns:
            drivers["cities"] = _mover("Customer City")
        prev_c = set(inv[inv["Q"] == quarter - 1]["Customer ID"]); cur_c = set(inv[inv["Q"] == quarter]["Customer ID"])
        lapsed = inv[(inv["Q"] == quarter - 1) & inv["Customer ID"].isin(prev_c - cur_c)].groupby("Customer ID")["V"].sum()
        drivers["lapsed"] = [(names.get(i, f"Customer {i}"), v) for i, v in lapsed.sort_values(ascending=False).items()]
        drivers["retained"], drivers["gained"] = len(prev_c & cur_c), len(cur_c - prev_c)

        # Revenue bridge, previous quarter -> this quarter, by customer behaviour.
        pv = inv[inv["Q"] == quarter - 1].groupby("Customer ID")["V"].sum()
        cv = inv[inv["Q"] == quarter].groupby("Customer ID")["V"].sum()
        both = pv.index.intersection(cv.index)
        diff = (cv.reindex(both) - pv.reindex(both)).sort_values()
        top_dec = diff[diff < 0].head(3)
        steps = [(f"Q{quarter-1} revenue", pv.sum(), "total")]
        steps += [(names.get(i, f"Customer {i}"), v, "delta") for i, v in top_dec.items()]
        steps += [("Other lower spend", diff[diff < 0].iloc[3:].sum() if (diff < 0).sum() > 3 else 0.0, "delta"),
                  ("Stopped ordering", -pv.reindex(pv.index.difference(cv.index)).sum(), "delta"),
                  ("Higher spend, existing", diff[diff > 0].sum(), "delta"),
                  ("New / returning", cv.reindex(cv.index.difference(pv.index)).sum(), "delta"),
                  (f"Q{quarter} revenue", cv.sum(), "total")]
        drivers["bridge"] = [s for s in steps if s[2] == "total" or abs(s[1]) >= 1]
    pl = lines.merge(prod[["ID", "Generic Name", "Brand Name", "Sku"]].rename(columns={"ID": "PID"}),
                     left_on="Product ID", right_on="PID", how="left")
    pl["Product"] = pl["Generic Name"].fillna(pl["Brand Name"]).fillna(pl["Sku"]).fillna("Unknown")
    pl["LR"] = pd.to_numeric(pl["Price"], errors="coerce") * pd.to_numeric(pl["Quantity"], errors="coerce")
    mix = pl[pl["Q"] == quarter].groupby("Product")["LR"].sum().sort_values(ascending=False)
    drivers["products"] = (mix / mix.sum() * 100) if mix.sum() else mix
    pmix = pl[pl["Q"].isin([quarter - 1, quarter])].groupby(["Product", "Q"])["LR"].sum().unstack(fill_value=0)
    pmix = pmix.reindex(columns=[quarter - 1, quarter], fill_value=0)
    drivers["mix_compare"] = (pmix / pmix.sum().replace(0, np.nan) * 100).fillna(0) \
        .sort_values(quarter, ascending=False)

    # ── Data gaps and figures to validate ────────────────────────────────────────
    att = monthly.dropna(subset=["Revenue"])
    exact = att[(att["Attainment %"] - 100).abs() <= 0.5]
    flags = {
        "exact_months": list(exact["Month"]),
        "bad_dates": bad_dates,
        "entry_vs_paid": (rows[quarter]["Collections (entry date)"], rows[quarter]["Collections"]),
        "placeholder_am": None,
        "data_end": data_end,
    }
    if "Account Manager" in rc.columns:
        am = inv["Customer ID"].map(rc.set_index("ID")["Account Manager"])
        flags["placeholder_am"] = (am.astype(str).str.contains("John Doe", case=False).mean() * 100)

    ytd["collection_ratio"] = _pct(ytd["collections"], ytd_rev)
    ytd["months_on_target"] = int((monthly["Attainment %"] >= 100).sum())
    ytd["months_done"] = int(monthly["Revenue"].notna().sum())
    return dict(year=year, quarter=quarter, score=score, ytd=ytd, monthly=monthly, aging=aging,
                aging_asof=asof, drivers=drivers, flags=flags, window_days=window_days, terms_days=terms_days)


def insights(r):
    """Quarter-only ahead/behind statements, YTD points, and next-quarter focus -- all from the data.
    Returns (q_ahead, q_behind, ytd_points, focus); ytd_points are (label, text, tone) tuples."""
    q, s, y, mo = r["quarter"], r["score"], r["ytd"], r["monthly"]
    cur = s[q]
    prev = s[q - 1] if q > 1 else None
    ql, pl = f"Q{q}", f"Q{q-1}"
    q_ahead, q_behind, focus = [], [], []
    qm = mo[mo["Q"] == q]
    on_target = int((qm["Attainment %"] >= 100).sum())

    if cur["Attainment %"] >= 100:
        q_ahead.append(f"Revenue GHS {cur['Revenue']:,.0f} = {cur['Attainment %']:.1f}% of the GHS "
                       f"{cur['Target']:,.0f} target (+GHS {cur['Revenue']-cur['Target']:,.0f}); "
                       f"{on_target} of {len(qm)} months on or above target.")
    else:
        q_behind.append(f"Revenue GHS {cur['Revenue']:,.0f} = {cur['Attainment %']:.1f}% of the GHS "
                        f"{cur['Target']:,.0f} target (short by GHS {cur['Target']-cur['Revenue']:,.0f}); "
                        f"{on_target} of {len(qm)} months on target.")
    if prev is not None:
        if cur["Multi-SKU %"] > prev["Multi-SKU %"]:
            q_ahead.append(f"Basket breadth improving: {cur['Multi-SKU %']:.0f}% of orders had 2+ products "
                           f"(from {prev['Multi-SKU %']:.0f}% in {pl}).")
        if cur["Top-5 share %"] < prev["Top-5 share %"]:
            q_ahead.append(f"Revenue less concentrated: top-5 customers {cur['Top-5 share %']:.0f}% of revenue "
                           f"(from {prev['Top-5 share %']:.0f}%).")
        if cur["Active customers"] > prev["Active customers"]:
            q_ahead.append(f"More customers buying: {int(cur['Active customers'])} active "
                           f"(from {int(prev['Active customers'])} in {pl}).")
        if cur["Collection ratio %"] > prev["Collection ratio %"]:
            q_ahead.append(f"Cash collected GHS {cur['Collections']:,.0f} = {cur['Collection ratio %']:.0f}% of "
                           f"revenue (up from {prev['Collection ratio %']:.0f}%).")

        rev_chg = _pct(cur["Revenue"] - prev["Revenue"], prev["Revenue"])
        if rev_chg < 0:
            tgt_chg = _pct(cur["Target"] - prev["Target"], prev["Target"])
            q_behind.append(f"Revenue {rev_chg:+.1f}% vs {pl} (GHS {prev['Revenue']:,.0f} to "
                            f"GHS {cur['Revenue']:,.0f}) on {int(cur['Orders'])} orders vs {int(prev['Orders'])}"
                            + (f"; the {ql} target was itself {abs(tgt_chg):.0f}% lower, so the dip was partly "
                               f"planned." if tgt_chg < 0 else "."))
        if cur["AR at quarter end"] > prev["AR at quarter end"]:
            q_behind.append(f"Receivables rose to GHS {cur['AR at quarter end']:,.0f} "
                            f"(+GHS {cur['AR at quarter end']-prev['AR at quarter end']:,.0f}); DSO "
                            f"{cur['DSO at quarter end']:.0f} days vs a {r['terms_days']}-day term, with "
                            f"{cur['AR past terms %']:.0f}% of the balance past terms.")
        if cur["Collection ratio %"] < prev["Collection ratio %"]:
            q_behind.append(f"Cash collected GHS {cur['Collections']:,.0f} = {cur['Collection ratio %']:.0f}% of "
                            f"revenue (down from {prev['Collection ratio %']:.0f}%).")
    if cur["Collection ratio %"] < 100:
        q_behind.append(f"Collections covered {cur['Collection ratio %']:.0f}% of what was invoiced, so "
                        f"GHS {cur['Revenue']-cur['Collections']:,.0f} of {ql} sales added to receivables.")
    if cur["New customers"] <= 5:
        q_behind.append(f"Acquisition is thin: {int(cur['New customers'])} new customers in {ql}.")
    d = r["drivers"]
    if d.get("lapsed"):
        big = [(n, v) for n, v in d["lapsed"] if v >= 10000]
        if big:
            q_behind.append(f"Stopped ordering after {pl}: " +
                            ", ".join(f"{n} (GHS {v:,.0f} in {pl})" for n, v in big) + ".")

    # Year to date
    ytd_points = [
        ("YTD vs target", f"GHS {y['revenue']:,.0f} = {y['attainment']:.1f}% of the GHS {y['target']:,.0f} "
                          f"YTD target; {y['months_on_target']} of {y['months_done']} months on or above target.",
         "good" if y["attainment"] >= 100 else "bad"),
        ("Progress to annual goal", f"{y['annual_pct']:.1f}% of the GHS {y['annual_target']:,.0f} goal reached "
                                    f"with {y['months_left']} months left; GHS {y['remaining']:,.0f} still needed, "
                                    f"which is {y['needed_pct_of_rest_target']:.0f}% of the remaining targets.",
         "good" if y["needed_pct_of_rest_target"] <= 100 else "bad"),
    ]
    if y["months_left"]:
        ytd_points.append(("Year-end outlook",
                           f"At the {ql} run-rate (GHS {y['run_rate']:,.0f}/month) the year lands near "
                           f"GHS {y['projected']:,.0f}, {y['projected_pct']:.0f}% of goal. Matching the "
                           f"remaining monthly targets would give GHS {y['revenue'] + y['rest_target']:,.0f} "
                           f"({_pct(y['revenue'] + y['rest_target'], y['annual_target']):.0f}%).",
                           "good" if y["projected_pct"] >= 100 else "bad"))
    ar_first, ar_last = s.iloc[:, 0]["AR at quarter end"], cur["AR at quarter end"]
    cash_txt = f"GHS {y['collections']:,.0f} collected YTD = {y['collection_ratio']:.0f}% of YTD revenue. "
    if q > 1:
        cash_txt += (f"Receivables went from GHS {ar_first:,.0f} (end Q1) to GHS {ar_last:,.0f} (end {ql})"
                     + (" -- sales are turning into cash more slowly as the year goes on."
                        if ar_last > ar_first else "."))
    else:
        cash_txt += f"Receivables stood at GHS {ar_last:,.0f} at the end of Q1."
    ytd_points.append(("Cash conversion", cash_txt, "bad" if q > 1 and ar_last > ar_first else "neutral"))
    if q > 1:
        ytd_points.append(("Customer base",
                           f"{int(s.loc['New customers'].sum())} new customers YTD "
                           f"({int(s.loc['New customers'].iloc[0])} of them in Q1); growth since has come from "
                           f"existing accounts and broader baskets (multi-SKU {s.loc['Multi-SKU %'].iloc[0]:.0f}% "
                           f"to {cur['Multi-SKU %']:.0f}%).", "neutral"))

    # Next-quarter focus
    nq = f"Q{q+1}" if q < 4 else "Q1"
    if prev is not None and cur["AR at quarter end"] > prev["AR at quarter end"]:
        focus.append(f"Collections first: work down the GHS {cur['AR past terms']:,.0f} past terms and set a "
                     f"{nq} DSO target (e.g. back to {max(r['terms_days'], int(prev['DSO at quarter end']))} days).")
    if "customers" in d:
        dec = d["customers"].head(5)
        dec = dec[dec["Change"] < 0]
        if len(dec):
            focus.append("Recover volume from the accounts that slowed most: " +
                         ", ".join(f"{n} ({c:+,.0f})" for n, c in dec["Change"].items()) + ".")
    if y["months_left"]:
        focus.append(f"Hold monthly revenue at or above target (GHS {y['rest_target']/y['months_left']:,.0f} "
                     f"average) to finish the year above goal, not just at it.")
    if cur["New customers"] <= 5:
        focus.append("Set a new-customer acquisition goal -- the customer base has barely grown since Q1.")
    focus.append("Agree targets beyond revenue (collections/DSO, new customers) so the next quarter can be "
                 "measured on more than sales.")
    return q_ahead, q_behind, ytd_points, focus


def data_gaps(r):
    """(title, explanation) pairs: data gaps and figures management should validate."""
    q, s, f = r["quarter"], r["score"], r["flags"]
    gaps = [("Only revenue has targets",
             "Revenue is the only metric with a goal on file (monthly targets summing to the annual goal). "
             "Collections, DSO, customers, orders and multi-SKU are reported as trends, not attainment. "
             "Suggest agreeing Q4 targets for collections/DSO and new customers.")]
    if len(f["exact_months"]) >= 3:
        lab = ", ".join(pd.to_datetime(m).strftime("%b") for m in f["exact_months"])
        gaps.append(("Validate: monthly attainment suspiciously exact",
                     f"Revenue landed within 0.5% of target in {len(f['exact_months'])} months ({lab}). "
                     f"Please confirm these targets were fixed before each month started; if they were "
                     f"re-based to actuals, 'on target' in those months is not an independent read."))
    entry, paid = f["entry_vs_paid"]
    if paid and abs(entry - paid) / paid > 0.15:
        gaps.append(("Validate: repayments are recorded late",
                     f"Q{q} repayments by actual payment date total GHS {paid:,.0f}, but GHS {entry:,.0f} was "
                     f"entered into the system during the quarter -- payments are logged in late batches. This "
                     f"report uses the payment date; the Weekly Info and YTD Review pages use the entry date, "
                     f"so their collections and DSO history read differently."))
    if f["bad_dates"]:
        gaps.append(("Data error: invalid repayment dates",
                     f"{f['bad_dates']} repayment record(s) carry an impossible date (e.g. year 0002) and were "
                     f"dated by their entry date instead. Please correct at source."))
    if f["placeholder_am"] and f["placeholder_am"] > 5:
        gaps.append(("Data gap: account manager not assigned",
                     f"{f['placeholder_am']:.0f}% of this year's invoices belong to customers whose account manager "
                     f"is the placeholder 'Mr John Doe', so performance cannot be split by sales person."))
    gaps.append(("Data gap: payment terms and margin",
                 f"Metabase records 30-day terms on every invoice and has no Cash vs Credit flag; DSO is "
                 f"benchmarked against the {r['terms_days']}-day standard term. Gross margin is excluded -- it is "
                 f"calculated at month-end (Zipline costs) and product cost data is incomplete."))
    gaps.append(("Data freshness", f"Figures use data up to {f['data_end']:%d %b %Y %H:%M}."))
    return gaps



def _shape(vals, labels):
    """Plain-language description of how a series moved across quarters."""
    v = list(vals)
    if len(v) < 2:
        return "only one quarter so far"
    diffs = np.diff(v)
    if all(d > 0 for d in diffs):
        word = "rose every quarter"
    elif all(d < 0 for d in diffs):
        word = "fell every quarter"
    else:
        i_max, i_min = int(np.argmax(v)), int(np.argmin(v))
        if 0 < i_max < len(v) - 1:
            word = f"peaked in {labels[i_max]}, then eased"
        elif 0 < i_min < len(v) - 1:
            word = f"dipped in {labels[i_min]}, then recovered"
        else:
            word = "moved unevenly"
    if v[0] and not np.isnan(v[0]):
        word += f"; {labels[0]} to {labels[-1]} {(v[-1] / v[0] - 1) * 100:+.0f}%"
    return word


def trend_lines(r):
    """One sentence per theme describing the quarter-by-quarter trajectory."""
    s = r["score"]
    qs = list(s.columns)
    L = [f"Q{q}" for q in qs]
    row = lambda m: [float(s.loc[m, q]) for q in qs]
    arrow = lambda vals, fmt: " -> ".join(fmt(x) for x in vals)
    money = lambda x: f"{x/1e6:.2f}M" if abs(x) >= 1e6 else f"{x/1e3:,.0f}k"
    pct = lambda x: f"{x:.0f}%"
    rev, att, aov = row("Revenue"), row("Attainment %"), row("AOV")
    new, act = row("New customers"), row("Active customers")
    ratio, ar = row("Collection ratio %"), row("AR at quarter end")

    rev_txt = (f"Revenue {arrow(rev, money)}, attainment {arrow(att, pct)}. Revenue {_shape(rev, L)}. ")
    rev_txt += ("Every quarter met target, but the margin over target narrowed after Q1."
                if min(att) >= 100 and len(att) > 1 and att[0] > max(att[1:]) + 5 else
                "Every quarter met target." if min(att) >= 100 else
                f"Below target in {', '.join(l for l, a in zip(L, att) if a < 100)}.")

    basket_stable = (max(aov) - min(aov)) / np.mean(aov) < 0.15
    ord_txt = (f"Orders {arrow(row('Orders'), lambda x: f'{x:.0f}')} ({_shape(row('Orders'), L)}). Average order "
               f"GHS {arrow(aov, lambda x: f'{x:,.0f}')}, typical (median) order GHS "
               f"{arrow(row('Median order'), lambda x: f'{x:,.0f}')}. ")
    ord_txt += ("Basket size is broadly stable, so revenue moves with order volume." if basket_stable else
                "Basket size has shifted materially, so revenue changes reflect order size as well as volume.")

    cust_txt = (f"Active customers {arrow(act, lambda x: f'{x:.0f}')}; new customers "
                f"{arrow(new, lambda x: f'{x:.0f}')} ({_shape(new, L)}).")
    if new[-1] < 0.25 * act[-1]:
        cust_txt += " Most activity now comes from existing accounts rather than new ones."

    coll_txt = (f"Cash collected GHS {arrow(row('Collections'), money)}, equal to {arrow(ratio, pct)} of each "
                f"quarter's revenue; the ratio {_shape(ratio, L)}.")
    if max(ratio) < 100:
        coll_txt += " It has stayed below 100% every quarter, so receivables keep building."

    ar_txt = (f"Receivables at quarter end GHS {arrow(ar, money)}; DSO "
              f"{arrow(row('DSO at quarter end'), lambda x: f'{x:.0f}d')} against a {r['terms_days']}-day term; "
              f"share past terms {arrow(row('AR past terms %'), pct)}. Receivables {_shape(ar, L)}.")
    if all(d > 0 for d in np.diff(ar)) and len(ar) > 1:
        ar_txt += " This is the clearest worsening trend of the year."

    mix_txt = (f"Multi-SKU orders {arrow(row('Multi-SKU %'), pct)} ({_shape(row('Multi-SKU %'), L)}). "
               f"Top-5 customer share {arrow(row('Top-5 share %'), pct)} ({_shape(row('Top-5 share %'), L)}).")

    return [("Revenue vs target", rev_txt), ("Orders and basket size", ord_txt), ("Customers", cust_txt),
            ("Collections", coll_txt), ("Receivables and DSO", ar_txt), ("Mix and concentration", mix_txt)]
