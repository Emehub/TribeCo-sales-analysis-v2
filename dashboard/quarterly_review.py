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

    # ── Monthly revenue vs target ────────────────────────────────────────────────
    monthly = (tg[["Month", "Target", "Q"]]
               .merge(inv.groupby("Month")["V"].sum().rename("Revenue").reset_index(), on="Month", how="left"))
    monthly.loc[monthly["Q"] > quarter, "Revenue"] = np.nan
    monthly["Attainment %"] = monthly["Revenue"] / monthly["Target"] * 100

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
    pl = lines.merge(prod[["ID", "Generic Name", "Brand Name", "Sku"]].rename(columns={"ID": "PID"}),
                     left_on="Product ID", right_on="PID", how="left")
    pl["Product"] = pl["Generic Name"].fillna(pl["Brand Name"]).fillna(pl["Sku"]).fillna("Unknown")
    pl["LR"] = pd.to_numeric(pl["Price"], errors="coerce") * pd.to_numeric(pl["Quantity"], errors="coerce")
    mix = pl[pl["Q"] == quarter].groupby("Product")["LR"].sum().sort_values(ascending=False)
    drivers["products"] = (mix / mix.sum() * 100) if mix.sum() else mix

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

    return dict(year=year, quarter=quarter, score=score, ytd=ytd, monthly=monthly,
                drivers=drivers, flags=flags, window_days=window_days, terms_days=terms_days)


def insights(r):
    """Ahead / behind / Q4 focus statements, generated from the figures."""
    q, s, y = r["quarter"], r["score"], r["ytd"]
    cur = s[q]
    prev = s[q - 1] if q > 1 else None
    ql, pl = f"Q{q}", f"Q{q-1}"
    ahead, behind, focus = [], [], []

    if cur["Attainment %"] >= 100:
        ahead.append(f"{ql} revenue GHS {cur['Revenue']:,.0f} = {cur['Attainment %']:.1f}% of the "
                     f"GHS {cur['Target']:,.0f} quarterly target.")
    else:
        behind.append(f"{ql} revenue GHS {cur['Revenue']:,.0f} = {cur['Attainment %']:.1f}% of the "
                      f"GHS {cur['Target']:,.0f} quarterly target (short by GHS {cur['Target']-cur['Revenue']:,.0f}).")
    (ahead if y["attainment"] >= 100 else behind).append(
        f"YTD revenue GHS {y['revenue']:,.0f} = {y['attainment']:.1f}% of YTD target and "
        f"{y['annual_pct']:.1f}% of the GHS {y['annual_target']:,.0f} annual goal.")
    if y["months_left"]:
        ahead.append(f"Only GHS {y['remaining']:,.0f} more is needed to hit the annual goal -- "
                     f"{y['needed_pct_of_rest_target']:.0f}% of the remaining target. At the {ql} run-rate "
                     f"(GHS {y['run_rate']:,.0f}/month) the year lands near GHS {y['projected']:,.0f} "
                     f"({y['projected_pct']:.0f}% of goal).")
    if prev is not None:
        if cur["Multi-SKU %"] > prev["Multi-SKU %"]:
            ahead.append(f"Multi-SKU adoption up to {cur['Multi-SKU %']:.0f}% of orders "
                         f"(from {prev['Multi-SKU %']:.0f}% in {pl}).")
        if cur["Top-5 share %"] < prev["Top-5 share %"]:
            ahead.append(f"Less reliance on big accounts: top-5 customers {cur['Top-5 share %']:.0f}% of "
                         f"revenue (from {prev['Top-5 share %']:.0f}%).")
        rev_chg = _pct(cur["Revenue"] - prev["Revenue"], prev["Revenue"])
        if rev_chg < 0:
            tgt_chg = _pct(cur["Target"] - prev["Target"], prev["Target"])
            behind.append(f"Revenue {rev_chg:+.1f}% vs {pl} (GHS {prev['Revenue']:,.0f} to "
                          f"GHS {cur['Revenue']:,.0f}); orders {int(prev['Orders'])} to {int(cur['Orders'])}"
                          + (f". The {ql} target was itself {tgt_chg:+.0f}% vs {pl}, so the dip was "
                             f"partly planned." if tgt_chg < 0 else "."))
        if cur["AR at quarter end"] > prev["AR at quarter end"]:
            behind.append(f"Receivables up to GHS {cur['AR at quarter end']:,.0f} at quarter end "
                          f"(from GHS {prev['AR at quarter end']:,.0f}); DSO {cur['DSO at quarter end']:.0f} days "
                          f"vs {prev['DSO at quarter end']:.0f} and a {r['terms_days']}-day term. "
                          f"{cur['AR past terms %']:.0f}% of AR is past terms.")
        if cur["Collection ratio %"] < prev["Collection ratio %"]:
            behind.append(f"Cash collected GHS {cur['Collections']:,.0f} = {cur['Collection ratio %']:.0f}% of "
                          f"{ql} revenue (from {prev['Collection ratio %']:.0f}% in {pl}).")
        if cur["New customers"] <= 5:
            behind.append(f"Acquisition is thin: {int(cur['New customers'])} new customers in {ql} "
                          f"({int(cur['Active customers'])} active).")

    d = r["drivers"]
    if "customers" in d:
        dec = d["customers"].head(5)
        dec = dec[dec["Change"] < 0]
        if len(dec):
            focus.append(f"Win back volume from the accounts that slowed most: " +
                         ", ".join(f"{n} ({c:+,.0f})" for n, c in dec["Change"].items()) + ".")
    if prev is not None and cur["AR at quarter end"] > prev["AR at quarter end"]:
        focus.append(f"Make collections the Q{q+1 if q < 4 else 1} priority: chase the GHS "
                     f"{cur['AR past terms']:,.0f} past terms and set a DSO target (e.g. back under "
                     f"{max(r['terms_days'], int(prev['DSO at quarter end']))} days).")
    if y["months_left"]:
        focus.append(f"Keep monthly revenue at or above target (GHS {y['rest_target']/y['months_left']:,.0f} "
                     f"average) to finish above the annual goal rather than just reach it.")
    if cur["New customers"] <= 5:
        focus.append("Set a new-customer acquisition goal -- growth this year has come from existing accounts.")
    return ahead, behind, focus


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
