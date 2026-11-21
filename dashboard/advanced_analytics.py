"""
Advanced Analytics -- the calculations behind the "Advanced Analytics" page.

Everything here is plain pandas/numpy (no statsmodels or scikit-learn on the deployment), and
every function takes and returns DataFrames so it can be checked outside Streamlit.

Inputs are the FBC-scoped invoices across all loaded years (data_layer.fbc_invoices), the
invoice lines and the product table. Dates are converted to naive Africa/Accra time (= UTC).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


# ════════════════════════════════════════════════════════════════════════════════
# Preparation
# ════════════════════════════════════════════════════════════════════════════════
def prep_invoices(inv_fbc, rc_names):
    """One row per invoice: Date, Customer ID, Customer, City, Value, Outstanding, Invoice ID."""
    df = inv_fbc.copy()
    d = pd.to_datetime(df["Created At"], errors="coerce")
    if getattr(d.dt, "tz", None) is not None:
        d = d.dt.tz_convert(None)
    names = rc_names.set_index("ID")["Name"] if "Name" in rc_names.columns else pd.Series(dtype=str)
    out = pd.DataFrame({
        "Invoice ID":  df["ID"],
        "Date":        d,
        "Customer ID": df["Customer ID"],
        "Value":       pd.to_numeric(df["Discountedvalue"], errors="coerce").fillna(0),
        "Outstanding": pd.to_numeric(df.get("Outstanding", 0), errors="coerce").fillna(0),
        "City":        df.get("Customer City", pd.Series("", index=df.index)).fillna("").astype(str).str.strip(),
    })
    fallback = df.get("Customerbusinessname", pd.Series("", index=df.index)).fillna("")
    out["Customer"] = out["Customer ID"].map(names).fillna(fallback)
    out.loc[out["Customer"].astype(str).str.strip() == "", "Customer"] = "Customer " + out["Customer ID"].astype(str)
    out = out.dropna(subset=["Date", "Customer ID"])
    return out[out["Value"] > 0].sort_values("Date").reset_index(drop=True)


def trading_start(df, min_share=0.25):
    """First month of sustained trading: the first month whose order count reaches `min_share`
    of the median monthly count and stays there. Pilot months before it would distort trends."""
    m = df.groupby(df["Date"].dt.to_period("M")).size()
    if m.empty:
        return None
    floor = m.median() * min_share
    ok = m >= floor
    # first month at or above the floor after the last month below it (months with no orders
    # at all are missing from `m`, so this also skips gaps)
    below = ok[~ok]
    later = ok[ok].index if not len(below) else ok[ok & (ok.index > below.index.max())].index
    start = later.min() if len(later) else m.index.min()
    return start.start_time


# ════════════════════════════════════════════════════════════════════════════════
# 1. Forecast -- Holt's damped-trend exponential smoothing on weekly revenue
# ════════════════════════════════════════════════════════════════════════════════
@dataclass
class Forecast:
    history: pd.DataFrame      # Week, Revenue, Fitted, Residual, z, Anomaly
    future: pd.DataFrame       # Week, Forecast, Lo80, Hi80, Lo95, Hi95
    params: dict               # alpha, beta, phi
    wape_model: float          # back-test error over the hold-out weeks
    wape_naive: float          # same, for a "same as last 4-week average" baseline
    holdout_weeks: int
    partial_week: pd.Timestamp | None   # the in-progress week left out of the fit
    partial_value: float


def weekly_revenue(df, start):
    """Weekly revenue (weeks ending Sunday) from `start`, zero-filled. Returns (series, partial_week, partial_value)."""
    d = df[df["Date"] >= start]
    s = d.set_index("Date")["Value"].resample("W-SUN").sum()
    if s.empty:
        return s, None, 0.0
    last_date = d["Date"].max()
    partial = None
    partial_val = 0.0
    # Leave the current, unfinished week out of the model -- it would read as a collapse.
    if last_date.normalize() < s.index[-1].normalize():
        partial, partial_val = s.index[-1], float(s.iloc[-1])
        s = s.iloc[:-1]
    return s, partial, partial_val


def _holt_damped(y, alpha, beta, phi):
    level, trend = y[0], (y[1] - y[0]) if len(y) > 1 else 0.0
    fitted = np.empty(len(y))
    fitted[0] = y[0]
    for t in range(1, len(y)):
        fitted[t] = level + phi * trend
        new_level = alpha * y[t] + (1 - alpha) * (level + phi * trend)
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return fitted, level, trend


def _fit_holt(y):
    """Grid-search alpha, beta, phi on one-step-ahead squared error (ignoring the first 2 points)."""
    best = None
    for a in np.arange(0.05, 0.96, 0.05):
        for b in (0.01, 0.05, 0.1, 0.2, 0.3):
            for phi in (0.8, 0.88, 0.94, 0.98):
                f, lv, tr = _holt_damped(y, a, b, phi)
                sse = float(np.sum((y[2:] - f[2:]) ** 2))
                if best is None or sse < best[0]:
                    best = (sse, a, b, phi, f, lv, tr)
    return best


def _project(level, trend, phi, h):
    return np.array([level + trend * sum(phi ** i for i in range(1, k + 1)) for k in range(1, h + 1)])


def forecast_weekly(df, start, horizon=8, holdout=8):
    y_s, partial, partial_val = weekly_revenue(df, start)
    y = y_s.values.astype(float)
    if len(y) < 12:
        return None

    # Back-test: fit on everything except the last `holdout` weeks, forecast them, compare.
    hold = min(holdout, max(4, len(y) // 5))
    train, test = y[:-hold], y[-hold:]
    _, a, b, phi, _, lv, tr = _fit_holt(train)
    bt = np.clip(_project(lv, tr, phi, hold), 0, None)
    naive = np.repeat(train[-4:].mean(), hold)
    denom = max(test.sum(), 1e-9)
    wape_model = float(np.abs(test - bt).sum() / denom)
    wape_naive = float(np.abs(test - naive).sum() / denom)

    # Final model on the full history.
    _, a, b, phi, fitted, lv, tr = _fit_holt(y)
    resid = y - fitted
    sigma = float(np.std(resid[2:], ddof=1)) if len(y) > 4 else 0.0
    mad = float(np.median(np.abs(resid[2:] - np.median(resid[2:])))) * 1.4826 if len(y) > 4 else 0.0
    z = resid / mad if mad > 0 else np.zeros_like(resid)
    z[:2] = 0
    hist = pd.DataFrame({"Week": y_s.index, "Revenue": y, "Fitted": fitted, "Residual": resid, "z": z})
    hist["Anomaly"] = np.where(hist["z"] >= 2.5, "Spike", np.where(hist["z"] <= -2.5, "Dip", ""))

    fc = _project(lv, tr, phi, horizon)
    k = np.arange(1, horizon + 1)
    # Approximate prediction-interval width for damped Holt: grows with the horizon.
    se = sigma * np.sqrt(1 + (k - 1) * a ** 2 * (1 + b) ** 2)
    weeks = pd.date_range(y_s.index[-1] + pd.Timedelta(weeks=1), periods=horizon, freq="W-SUN")
    fut = pd.DataFrame({
        "Week": weeks, "Forecast": np.clip(fc, 0, None),
        "Lo80": np.clip(fc - 1.2816 * se, 0, None), "Hi80": fc + 1.2816 * se,
        "Lo95": np.clip(fc - 1.96 * se, 0, None), "Hi95": fc + 1.96 * se,
    })
    return Forecast(hist, fut, {"alpha": round(float(a), 2), "beta": b, "phi": phi},
                    wape_model, wape_naive, hold, partial, partial_val)


def year_end_projection(df, fc: Forecast, as_of):
    """Actual revenue this calendar year to date + forecast for the rest of the year.
    The in-progress week contributes its forecast pro rata for the days still to come."""
    year_end = pd.Timestamp(year=as_of.year, month=12, day=31)
    ytd = df[df["Date"].dt.year == as_of.year]["Value"].sum()
    rest = 0.0
    if fc.partial_week is not None:
        days_left = max((fc.partial_week.normalize() - as_of.normalize()).days, 0)
        rest += float(fc.future["Forecast"].iloc[0]) * days_left / 7
    fut = fc.future[fc.future["Week"] <= year_end + pd.Timedelta(days=6)]
    # weeks that straddle 31 Dec only count their days inside the year
    for _, r in fut.iterrows():
        wk_start = r["Week"] - pd.Timedelta(days=6)
        days_in = max(min((year_end - wk_start).days + 1, 7), 0)
        rest += r["Forecast"] * days_in / 7
    # if the horizon stops short of 31 Dec, extend with the last forecast value
    if len(fc.future) and fc.future["Week"].iloc[-1] < year_end:
        extra_days = (year_end - fc.future["Week"].iloc[-1]).days
        rest += fc.future["Forecast"].iloc[-1] * extra_days / 7
    return float(ytd), float(rest)


# ════════════════════════════════════════════════════════════════════════════════
# 2. RFM segmentation
# ════════════════════════════════════════════════════════════════════════════════
SEGMENT_ORDER = ["Champions", "Loyal", "Promising", "Needs attention", "At risk", "Can't lose", "Hibernating"]
SEGMENT_ACTION = {
    "Champions":       "Protect: priority stock, early access to campaigns, ask for referrals.",
    "Loyal":           "Grow basket: bundle offers and the cross-sell pairs below.",
    "Promising":       "Recent but light buyers: follow-up call within 2 weeks to secure a repeat order.",
    "Needs attention": "Ordering is slowing: check stock-outs, delivery and credit limits.",
    "At risk":         "Used to buy often, gone quiet: field visit this week.",
    "Can't lose":      "High-value accounts gone quiet: manager-level call, review terms.",
    "Hibernating":     "Low and lapsed: low-cost SMS reactivation only.",
}


def _score(s, ascending=True):
    """1-5 score by percentile rank (ties share a rank, so small customer bases still spread)."""
    r = s.rank(pct=True, method="average", ascending=ascending)
    return np.ceil(r * 5).clip(1, 5).astype(int)


def rfm(df, as_of):
    g = df.groupby(["Customer ID", "Customer"]).agg(
        Last=("Date", "max"), First=("Date", "min"),
        Orders=("Invoice ID", "nunique"), Revenue=("Value", "sum"),
        Outstanding=("Outstanding", "sum"),
    ).reset_index()
    g["Recency (days)"] = (as_of.normalize() - g["Last"].dt.normalize()).dt.days
    g["R"] = _score(g["Recency (days)"], ascending=False)
    g["F"] = _score(g["Orders"])
    g["M"] = _score(g["Revenue"])

    def seg(r):
        if r.R >= 4 and r.F >= 4:               return "Champions"
        if r.R <= 2 and r.M >= 4 and r.F >= 3:  return "Can't lose"
        if r.R <= 2 and r.F >= 3:               return "At risk"
        if r.R >= 3 and r.F >= 3:               return "Loyal"
        if r.R >= 4:                            return "Promising"
        if r.R == 3:                            return "Needs attention"
        return "Hibernating"
    g["Segment"] = g.apply(seg, axis=1)
    return g


def segment_summary(r):
    tot = r["Revenue"].sum() or 1
    s = r.groupby("Segment").agg(Customers=("Customer ID", "count"), Revenue=("Revenue", "sum"),
                                 Orders=("Orders", "sum"), **{"Avg recency (days)": ("Recency (days)", "mean")})
    s = s.reindex([x for x in SEGMENT_ORDER if x in s.index]).reset_index()
    s["Revenue share"] = s["Revenue"] / tot * 100
    s["Action"] = s["Segment"].map(SEGMENT_ACTION)
    return s


# ════════════════════════════════════════════════════════════════════════════════
# 3. Churn risk -- each customer against their own reorder rhythm
# ════════════════════════════════════════════════════════════════════════════════
def churn_risk(df, as_of, lookback_days=180):
    """For each customer: their median days between orders (their own rhythm; the company-wide
    median for customers with fewer than 3 orders), how far past it they are, and the monthly
    revenue that is at stake if they have stopped."""
    rows = []
    gaps_all = []
    by = {k: v.sort_values("Date") for k, v in df.groupby(["Customer ID", "Customer"])}
    for _, v in by.items():
        days = v["Date"].dt.normalize().drop_duplicates()
        if len(days) >= 2:
            gaps_all.extend(days.diff().dt.days.dropna().tolist())
    global_gap = float(np.median(gaps_all)) if gaps_all else 30.0

    for (cid, name), v in by.items():
        days = v["Date"].dt.normalize().drop_duplicates()
        gaps = days.diff().dt.days.dropna()
        own = len(days) >= 3
        gap = float(gaps.median()) if own else global_gap
        gap = max(gap, 7.0)
        since = (as_of.normalize() - days.max()).days
        ratio = since / gap
        # Monthly run-rate over the customer's last active stretch (up to `lookback_days`
        # before their last order), so a newer customer is not diluted by months before they joined.
        win_start = max(days.max() - pd.Timedelta(days=lookback_days), days.min())
        recent = v[v["Date"].dt.normalize() >= win_start]
        span_m = max((days.max() - win_start).days / 30.44, 1)
        monthly = recent["Value"].sum() / span_m
        rows.append(dict(**{"Customer ID": cid, "Customer": name, "Orders": int(v["Invoice ID"].nunique()),
                            "Typical gap (days)": round(gap), "Days since last order": since,
                            "Overdue ratio": ratio, "Avg monthly revenue": monthly,
                            "Lifetime revenue": v["Value"].sum(), "Rhythm": "own" if own else "company"}))
    out = pd.DataFrame(rows)
    if out.empty:
        return out, global_gap
    out["Status"] = pd.cut(out["Overdue ratio"], [-np.inf, 1.0, 1.5, 3.0, np.inf],
                           labels=["On track", "Due now", "Late", "Lapsed"]).astype(str)
    # Gone for over a year (mostly 2025 pilot accounts): a reactivation list, not a churn alert.
    out.loc[out["Days since last order"] > 365, "Status"] = "Dormant 12m+"
    # Who to call first: run-rate at stake, weighted by how far past their rhythm they are.
    at_risk = out["Status"].isin(["Due now", "Late", "Lapsed"])
    out["Priority"] = np.where(at_risk, out["Avg monthly revenue"] * out["Overdue ratio"].clip(upper=5), 0)
    return out.sort_values(["Priority", "Overdue ratio"], ascending=False), global_gap


# ════════════════════════════════════════════════════════════════════════════════
# 4. Cohort retention
# ════════════════════════════════════════════════════════════════════════════════
def cohorts(df, start):
    d = df[df["Date"] >= start].copy()
    d["Month"] = d["Date"].dt.to_period("M")
    first = d.groupby("Customer ID")["Month"].min().rename("Cohort")
    d = d.join(first, on="Customer ID")
    d["Offset"] = (d["Month"] - d["Cohort"]).apply(lambda x: x.n)
    active = d.groupby(["Cohort", "Offset"])["Customer ID"].nunique().unstack(fill_value=0)
    size = active[0]
    retention = active.div(size, axis=0) * 100
    # cells in the future (cohort + offset beyond the last month) are unknown, not zero
    last = d["Month"].max()
    for c in retention.index:
        for o in retention.columns:
            if c + o > last:
                retention.loc[c, o] = np.nan
    retention.index = [p.strftime("%b %Y") for p in retention.index]
    size.index = retention.index
    return retention, size


# ════════════════════════════════════════════════════════════════════════════════
# 5. Concentration -- Pareto, Lorenz curve, Gini, ABC classes
# ════════════════════════════════════════════════════════════════════════════════
def concentration(values: pd.Series):
    v = values[values > 0].sort_values(ascending=False)
    n = len(v)
    if n == 0:
        return None
    share = v / v.sum()
    cum = share.cumsum()
    abc = np.where(cum.shift(fill_value=0) < 0.80, "A", np.where(cum.shift(fill_value=0) < 0.95, "B", "C"))
    tbl = pd.DataFrame({"Name": v.index, "Revenue": v.values, "Share": share.values * 100,
                        "Cumulative": cum.values * 100, "Class": abc})
    asc = np.sort(v.values)
    lorenz_y = np.concatenate([[0], np.cumsum(asc) / asc.sum()])
    lorenz_x = np.linspace(0, 1, n + 1)
    _trap = getattr(np, "trapezoid", None) or np.trapz
    gini = 1 - 2 * _trap(lorenz_y, lorenz_x)
    top20 = cum.iloc[max(int(np.ceil(n * 0.2)) - 1, 0)] * 100
    return dict(table=tbl, lorenz_x=lorenz_x, lorenz_y=lorenz_y, gini=float(gini),
                top20_share=float(top20), n=n, n_for_80=int((cum < 0.80).sum() + 1))


# ════════════════════════════════════════════════════════════════════════════════
# 6. Growth drivers -- customer revenue bridge and product price/volume split
# ════════════════════════════════════════════════════════════════════════════════
def periods(as_of, days):
    cur_end = as_of.normalize() + pd.Timedelta(days=1)
    cur_start = cur_end - pd.Timedelta(days=days)
    prev_start = cur_start - pd.Timedelta(days=days)
    return prev_start, cur_start, cur_end


def customer_bridge(df, as_of, days=90):
    prev_start, cur_start, cur_end = periods(as_of, days)
    p0 = df[(df["Date"] >= prev_start) & (df["Date"] < cur_start)].groupby("Customer")["Value"].sum()
    p1 = df[(df["Date"] >= cur_start) & (df["Date"] < cur_end)].groupby("Customer")["Value"].sum()
    before = set(df[df["Date"] < prev_start]["Customer"])
    allc = p0.index.union(p1.index)
    a0, a1 = p0.reindex(allc, fill_value=0), p1.reindex(allc, fill_value=0)
    cat = pd.Series("", index=allc)
    cat[(a0 == 0) & (a1 > 0)] = ["Reactivated" if c in before else "New customers" for c in allc[(a0 == 0) & (a1 > 0)]]
    cat[(a0 > 0) & (a1 == 0)] = "Lost customers"
    cat[(a0 > 0) & (a1 > 0) & (a1 >= a0)] = "Existing: grew"
    cat[(a0 > 0) & (a1 > 0) & (a1 < a0)] = "Existing: shrank"
    detail = pd.DataFrame({"Customer": allc, "Previous": a0.values, "Current": a1.values,
                           "Change": (a1 - a0).values, "Driver": cat.values})
    steps = detail.groupby("Driver")["Change"].sum()
    order = ["New customers", "Reactivated", "Existing: grew", "Existing: shrank", "Lost customers"]
    steps = steps.reindex(order).fillna(0)
    return dict(prev=float(a0.sum()), cur=float(a1.sum()), steps=steps,
                detail=detail.sort_values("Change"), window=(prev_start, cur_start, cur_end))


def product_price_volume(inv_df, il, prod, as_of, days=90):
    """Line-level revenue (quantity x unit price) change per product, split into a volume effect
    (change in units at the old price) and a price effect (change in price on the new units).
    New and discontinued products are separate steps."""
    prev_start, cur_start, cur_end = periods(as_of, days)
    dates = inv_df.set_index("Invoice ID")["Date"]
    l = il[il["Invoice ID"].isin(dates.index)].copy()
    l["Date"] = l["Invoice ID"].map(dates)
    l["Quantity"] = pd.to_numeric(l["Quantity"], errors="coerce").fillna(0)
    l["Price"] = pd.to_numeric(l["Price"], errors="coerce").fillna(0)
    l["Rev"] = l["Quantity"] * l["Price"]
    names = prod.set_index("ID")
    nm = names["Generic Name"].fillna(names.get("Brand Name")) if "Generic Name" in names.columns else names.get("Brand Name")
    l["Product"] = l["Product ID"].map(nm).fillna("Product " + l["Product ID"].astype(str)).astype(str).str.strip()

    def agg(a, b):
        x = l[(l["Date"] >= a) & (l["Date"] < b)].groupby("Product").agg(Q=("Quantity", "sum"), R=("Rev", "sum"))
        x["P"] = x["R"] / x["Q"].replace(0, np.nan)
        return x
    x0, x1 = agg(prev_start, cur_start), agg(cur_start, cur_end)
    allp = x0.index.union(x1.index)
    x0, x1 = x0.reindex(allp), x1.reindex(allp)
    t = pd.DataFrame({"Product": allp, "Units before": x0["Q"].fillna(0).values, "Units now": x1["Q"].fillna(0).values,
                      "Revenue before": x0["R"].fillna(0).values, "Revenue now": x1["R"].fillna(0).values,
                      "Price before": x0["P"].values, "Price now": x1["P"].values})
    both = (t["Revenue before"] > 0) & (t["Revenue now"] > 0)
    t["Volume effect"] = np.where(both, (t["Units now"] - t["Units before"]) * t["Price before"], 0)
    t["Price effect"] = np.where(both, (t["Price now"] - t["Price before"]) * t["Units now"], 0)
    t["New"] = np.where((t["Revenue before"] == 0) & (t["Revenue now"] > 0), t["Revenue now"], 0)
    t["Discontinued"] = np.where((t["Revenue before"] > 0) & (t["Revenue now"] == 0), -t["Revenue before"], 0)
    t["Change"] = t["Revenue now"] - t["Revenue before"]
    steps = pd.Series({"Volume": t["Volume effect"].sum(), "Price": t["Price effect"].sum(),
                       "New products": t["New"].sum(), "Dropped products": t["Discontinued"].sum()})
    return dict(table=t.sort_values("Change"), steps=steps,
                prev=float(t["Revenue before"].sum()), cur=float(t["Revenue now"].sum()))


# ════════════════════════════════════════════════════════════════════════════════
# 7. Cross-sell -- product pairs bought together (market-basket lift)
# ════════════════════════════════════════════════════════════════════════════════
def basket_pairs(inv_df, il, prod, min_together=4):
    ids = set(inv_df["Invoice ID"])
    l = il[il["Invoice ID"].isin(ids)][["Invoice ID", "Product ID"]].dropna().drop_duplicates()
    names = prod.set_index("ID")
    nm = names["Generic Name"].fillna(names.get("Brand Name")) if "Generic Name" in names.columns else names.get("Brand Name")
    l["Product"] = l["Product ID"].map(nm).fillna("Product " + l["Product ID"].astype(str)).astype(str).str.strip()
    l = l[["Invoice ID", "Product"]].drop_duplicates()
    n = l["Invoice ID"].nunique()
    if n == 0:
        return pd.DataFrame()
    item_cnt = l.groupby("Product")["Invoice ID"].nunique()
    m = l.merge(l, on="Invoice ID")
    m = m[m["Product_x"] < m["Product_y"]]
    pc = m.groupby(["Product_x", "Product_y"])["Invoice ID"].nunique().reset_index(name="Together")
    pc = pc[pc["Together"] >= min_together]
    if pc.empty:
        return pc
    ca, cb = pc["Product_x"].map(item_cnt), pc["Product_y"].map(item_cnt)
    pc["Support %"] = pc["Together"] / n * 100
    pc["Lift"] = (pc["Together"] / n) / ((ca / n) * (cb / n))
    # confidence in the stronger direction, with that direction named
    conf_ab, conf_ba = pc["Together"] / ca, pc["Together"] / cb
    pc["If they buy"] = np.where(conf_ab >= conf_ba, pc["Product_x"], pc["Product_y"])
    pc["They also buy"] = np.where(conf_ab >= conf_ba, pc["Product_y"], pc["Product_x"])
    pc["Confidence %"] = np.maximum(conf_ab, conf_ba) * 100
    return pc[pc["Lift"] > 1].sort_values(["Lift", "Together"], ascending=False)[
        ["If they buy", "They also buy", "Together", "Support %", "Confidence %", "Lift"]]
