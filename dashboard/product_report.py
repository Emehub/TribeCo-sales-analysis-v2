"""
Product performance: sales, gross margin, reach by city, stock position and slow movers.

Used by the Product Stock page and the monthly management report. Inputs come from
data_layer.load_products(): costed invoice lines ("lines") and stock batches ("batches").
Sales are scoped like the rest of the reports (Ghana FBC invoices, not cancelled) by joining the lines
to inv_scoped. No Streamlit dependency.
"""
import numpy as np
import pandas as pd

import stock_report as stk

SLOW_DAYS = 60            # in stock, but no sale for this many days = slow mover
LOOKBACK_DAYS = 180       # "stopped selling": sold in this window before SLOW_DAYS, nothing since
LOW_MARGIN = 0.20         # products under this gross margin are flagged


def _naive(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None)


def lines(inv_scoped, raw):
    """One row per invoice line in scope, with date, month, customer, city, revenue, cost and margin."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    inv = inv_scoped[["ID", "Created At", "Customer ID", "Customer City"]].rename(columns={"ID": "_inv"})
    x = raw.merge(inv, left_on="Invoice ID", right_on="_inv")
    x["Date"] = _naive(x["Created At"])
    x["Month"] = x["Date"].dt.strftime("%Y-%m")
    city = x["Customer City"].fillna("").astype(str).str.strip().str.title()
    x["City"] = city.where(city != "", "Not recorded")
    for c in ["Quantity", "Price", "Cost Price"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x["Quantity"] = x["Quantity"].fillna(0)
    x["Revenue"] = x["Quantity"] * x["Price"].fillna(0)
    x["Cost"] = x["Quantity"] * x["Cost Price"]
    x["Product"] = x["Product"].fillna("").astype(str).str.strip()
    x.loc[x["Product"] == "", "Product"] = "Product " + x["Product ID"].astype(str)
    x["Category"] = x["Category"].fillna("Uncategorised")
    return x


def _prev(month):
    return (pd.Period(month, freq="M") - 1).strftime("%Y-%m")


def _margin(df):
    costed = df["Cost"].notna()
    rev = df.loc[costed, "Revenue"].sum()
    return (rev - df.loc[costed, "Cost"].sum()) / rev if rev else np.nan


def by(L, month, key):
    """Per product / category / city for the month: units, revenue, margin, customers, growth vs last month."""
    cur, prv = L[L["Month"] == month], L[L["Month"] == _prev(month)]
    if cur.empty:
        return pd.DataFrame()
    g = cur.groupby(key).agg(units=("Quantity", "sum"), revenue=("Revenue", "sum"), cost=("Cost", "sum"),
                             customers=("Customer ID", "nunique"), cities=("City", "nunique"),
                             products=("Product", "nunique"), category=("Category", "first"))
    g["margin"] = g["revenue"] - g["cost"]
    g["margin_pct"] = (g["margin"] / g["revenue"]).where(g["revenue"] > 0)
    g["share"] = g["revenue"] / g["revenue"].sum()
    g["prev_revenue"] = prv.groupby(key)["Revenue"].sum()
    g["prev_revenue"] = g["prev_revenue"].fillna(0)
    g["growth"] = (g["revenue"] / g["prev_revenue"] - 1).where(g["prev_revenue"] > 0)
    return g.sort_values("revenue", ascending=False).reset_index()


def top_city(L, month):
    cur = L[L["Month"] == month]
    if cur.empty:
        return pd.Series(dtype=str)
    t = cur.groupby(["Product", "City"])["Revenue"].sum().reset_index().sort_values("Revenue", ascending=False)
    return t.drop_duplicates("Product").set_index("Product")["City"]


def weekly(L, today=None, weeks=12):
    """Units sold a week (Mon-Sun) per Product ID over the last `weeks` complete weeks (for stock pace)."""
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    monday = today - pd.Timedelta(days=today.weekday())
    start = monday - pd.Timedelta(weeks=weeks)
    idx = pd.date_range(start, monday - pd.Timedelta(weeks=1), freq="7D")
    if L.empty:
        return pd.DataFrame(index=idx)
    x = L[(L["Date"] >= start) & (L["Date"] < monday)].copy()
    x["Week"] = x["Date"].dt.normalize() - pd.to_timedelta(x["Date"].dt.weekday, unit="D")
    return x.pivot_table(index="Week", columns="Product ID", values="Quantity", aggfunc="sum").reindex(idx).fillna(0)


def slow_movers(stock_products, L, today=None):
    """Products with stock left and no sale in SLOW_DAYS days, and products that stopped selling."""
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    last = L.groupby("Product ID")["Date"].max() if len(L) else pd.Series(dtype="datetime64[ns]")
    slow = pd.DataFrame()
    if len(stock_products):
        s = stock_products[stock_products["remaining"] > 0].copy()
        s["last_sale"] = s["product_id"].map(last)
        s["days_since"] = (today - s["last_sale"]).dt.days
        slow = s[s["last_sale"].isna() | (s["days_since"] > SLOW_DAYS)][
            ["Product", "remaining", "value_price", "last_sale", "days_since"]]
    stopped = pd.DataFrame()
    if len(L):
        recent = L[L["Date"] >= today - pd.Timedelta(days=SLOW_DAYS)]["Product ID"].unique()
        before = L[(L["Date"] < today - pd.Timedelta(days=SLOW_DAYS)) &
                   (L["Date"] >= today - pd.Timedelta(days=LOOKBACK_DAYS))]
        stopped = (before[~before["Product ID"].isin(recent)].groupby(["Product ID", "Product"])
                   .agg(revenue=("Revenue", "sum"), customers=("Customer ID", "nunique"), last_sale=("Date", "max"))
                   .reset_index().sort_values("revenue", ascending=False))
        stopped["days_since"] = (today - stopped["last_sale"]).dt.days
    return slow, stopped


def stock(frames, L, today=None):
    """Current stock position per product (stock_report), with the sales pace taken from the scoped lines."""
    b = stk.batches(frames.get("batches"), today)
    if b.empty:
        return b, pd.DataFrame(), {}
    p = stk.products(b, weekly(L, today))
    return b, p, stk.summary(p)


def compute(month, inv_scoped, frames, today=None):
    """Everything the monthly report and the page need for one month."""
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    L = lines(inv_scoped, frames.get("lines"))
    cur = L[L["Month"] == month] if len(L) else L
    prv = L[L["Month"] == _prev(month)] if len(L) else L
    prods = by(L, month, "Product") if len(L) else pd.DataFrame()
    if len(prods):
        prods["top_city"] = prods["Product"].map(top_city(L, month))
    cats = by(L, month, "Category") if len(L) else pd.DataFrame()
    cities = by(L, month, "City") if len(L) else pd.DataFrame()
    batches, stock_p, stock_s = stock(frames, L, today)
    slow, stopped = slow_movers(stock_p, L, today)
    rev, prev_rev = float(cur["Revenue"].sum()) if len(cur) else 0.0, float(prv["Revenue"].sum()) if len(prv) else 0.0
    tot = dict(revenue=rev, prev_revenue=prev_rev, growth=rev / prev_rev - 1 if prev_rev else np.nan,
               margin_pct=_margin(cur) if len(cur) else np.nan, prev_margin_pct=_margin(prv) if len(prv) else np.nan,
               margin=float((cur["Revenue"] - cur["Cost"]).sum()) if len(cur) else 0.0,
               units=float(cur["Quantity"].sum()) if len(cur) else 0.0, products=len(prods),
               cities=int((cities["City"] != "Not recorded").sum()) if len(cities) else 0,
               top3_share=float(prods["share"].head(3).sum()) if len(prods) else np.nan)
    r = dict(month=month, label=pd.Period(month, freq="M").strftime("%B %Y"), lines=L, products=prods,
             categories=cats, cities=cities, batches=batches, stock=stock_p, stock_summary=stock_s,
             slow=slow, stopped=stopped, totals=tot, today=today)
    r["points"], r["recs"] = points(r)
    return r


def points(r):
    """Plain-language findings and recommendations for the CEO."""
    t, p, s, m = r["totals"], r["products"], r["stock_summary"], pd.Timestamp(r["month"]).strftime("%B")
    pts, recs = [], []
    if t["products"]:
        mg = (f"gross margin {t['margin_pct'] * 100:.1f}% (GHS {t['margin']:,.0f})"
              if pd.notna(t["margin_pct"]) else "margin not available")
        chg = (f", {'up' if t['margin_pct'] >= t['prev_margin_pct'] else 'down'} from "
               f"{t['prev_margin_pct'] * 100:.1f}% last month" if pd.notna(t["prev_margin_pct"]) else "")
        pts.append(f"{t['products']} products sold in {m} for GHS {t['revenue']:,.0f} at list price (before invoice "
                   f"discounts); {mg}{chg}.")
        top = p.head(3)
        pts.append("Top products: " + ", ".join(f"{n} (GHS {v:,.0f}, {sh * 100:.0f}%)" for n, v, sh in
                                                zip(top["Product"], top["revenue"], top["share"]))
                   + f". The top 3 make up {t['top3_share'] * 100:.0f}% of product revenue.")
        g = p[p["growth"].notna() & (p["prev_revenue"] >= 5000)].sort_values("growth")
        if len(g) >= 2:
            pts.append(f"Biggest rise: {g.iloc[-1]['Product']} ({g.iloc[-1]['growth'] * 100:+.0f}%). "
                       f"Biggest fall: {g.iloc[0]['Product']} ({g.iloc[0]['growth'] * 100:+.0f}%).")
        low = p[p["margin_pct"] < LOW_MARGIN]
        if len(low):
            recs.append("Review pricing on low-margin products: " + ", ".join(
                f"{n} ({v * 100:.0f}%)" for n, v in zip(low["Product"].head(3), low["margin_pct"].head(3))) + ".")
    c = r["cities"]
    if len(c):
        known = c[c["City"] != "Not recorded"]
        if len(known):
            pts.append(f"Sales reached {t['cities']} cities; the biggest were " + ", ".join(
                f"{n} ({sh * 100:.0f}%)" for n, sh in zip(known["City"].head(3), known["share"].head(3))) + ".")
    if s:
        pts.append(f"Stock today: {s['remaining']:,} units worth GHS {s['value_price']:,.0f} at selling price "
                   f"across {s['in_stock']} products.")
        st_ = r["stock"]
        low_st = st_[(st_["weeks_left"] < 6) & (st_["remaining"] > 0)].sort_values("weeks_left")
        if len(low_st):
            recs.append("Reorder soon (under 6 weeks of stock at the current pace): " + ", ".join(
                f"{n} ({w:.0f} wks)" for n, w in zip(low_st["Product"].head(4), low_st["weeks_left"].head(4))) + ".")
        if s["expiring_units"] or s["expired_units"]:
            recs.append(f"Clear stock near or past expiry: {s['expiring_units']:,} units expiring within "
                        f"{stk.EXPIRY_WARN_DAYS} days and {s['expired_units']:,} already expired "
                        f"(GHS {s['expiring_value'] + s['expired_value']:,.0f}).")
    if len(r["slow"]):
        recs.append("Push or stop reordering slow movers (in stock, no sale in "
                    f"{SLOW_DAYS} days): " + ", ".join(r["slow"]["Product"].head(4)) + ".")
    if len(r["stopped"]):
        st2 = r["stopped"].head(3)
        recs.append("Find out why these stopped selling (no sale in "
                    f"{SLOW_DAYS} days): " + ", ".join(f"{n} (last sold {d:%d %b})" for n, d in
                                                      zip(st2["Product"], st2["last_sale"])) + ".")
    return pts, recs


# ── monthly report section ────────────────────────────────────────────────────
def _short(text, n):
    text = str(text)
    return text if len(text) <= n else text[:n - 3].rstrip() + "..."


def _pct(v):
    return f"{v * 100:.1f}%" if pd.notna(v) else "-"


def _growth(v):
    if pd.isna(v):
        return "new"
    if v > 3:
        return "> +300%"
    return "0%" if abs(v) < 0.005 else f"{v * 100:+.0f}%"


def pdf_section(pdf, r, n):
    """Append the product performance section to a ReportPDF; n = first section number."""
    t, p = r["totals"], r["products"]
    pdf.section_title(f"{n}. Product performance: {r['label']}", need=70)
    if not len(p):
        pdf.body("No product sales recorded in the month.")
        return n + 1
    pdf.table(["Product", "Units", "Revenue", "Share", "Margin", "vs last mth", "Customers"],
              [(_short(row.Product, 38), f"{row.units:,.0f}", f"GHS {row.revenue:,.0f}", f"{row.share * 100:.0f}%",
                _pct(row.margin_pct), _growth(row.growth), f"{row.customers}") for row in p.head(12).itertuples()],
              [62, 16, 28, 15, 18, 22, 22])
    pdf.body(f"Total GHS {t['revenue']:,.0f} from {t['products']} products ({_growth(t['growth'])} vs last month); "
             f"gross margin {_pct(t['margin_pct'])} (last month {_pct(t['prev_margin_pct'])}). Product revenue is at list "
             f"price before invoice discounts, so it is slightly above invoiced revenue. Margin = (price - the order's "
             f"cost price) / price.")
    if len(r["categories"]) > 1:
        c = r["categories"]
        pdf.sub_title("By category")
        pdf.table(["Category", "Revenue", "Share", "Margin", "vs last mth"],
                  [(row.Category[:40], f"GHS {row.revenue:,.0f}", f"{row.share * 100:.0f}%", _pct(row.margin_pct),
                    _growth(row.growth)) for row in c.itertuples()], [70, 35, 22, 25, 31])
    n += 1

    cities = r["cities"]
    if len(cities):
        pdf.section_title(f"{n}. Where products sold: top cities", need=60)
        pdf.table(["City", "Revenue", "Share", "Customers", "Products", "vs last mth"],
                  [(row.City[:34], f"GHS {row.revenue:,.0f}", f"{row.share * 100:.0f}%", f"{row.customers}",
                    f"{row.products}", _growth(row.growth)) for row in cities.head(10).itertuples()],
                  [55, 33, 20, 25, 23, 27])
        n += 1

    s, sp = r["stock_summary"], r["stock"]
    if s:
        pdf.section_title(f"{n}. Stock position today ({r['today']:%d %b %Y})", need=70)
        pdf.table(["Product", "Remaining", "Sold/wk", "Weeks left", "Next expiry", "Status"],
                  [(_short(row.Product, 42), f"{row.remaining:,}", f"{row.pace:,.0f}",
                    f"{row.weeks_left:.0f}" if pd.notna(row.weeks_left) else "-",
                    f"{row.next_expiry:%d %b %Y}" if pd.notna(row.next_expiry) else "-", row.status)
                   for row in sp[sp["remaining"] > 0].sort_values("weeks_left").itertuples()],
                  [74, 20, 17, 20, 27, 25])
        pdf.body(f"{s['received']:,} units received, {s['sold']:,} sold ({s['sold'] / s['received'] * 100:.0f}%), "
                 f"{s['remaining']:,} left worth GHS {s['value_price']:,.0f} at selling price "
                 f"(GHS {s['value_cost']:,.0f} at cost). Out of stock: {s['out']}. Expiring within "
                 f"{stk.EXPIRY_WARN_DAYS} days: {s['expiring_units']:,} units; expired: {s['expired_units']:,} units.")
        n += 1

    pdf.section_title(f"{n}. Product findings and actions", need=40)
    pdf.bullets(r["points"], pdf._ACCENT)
    if r["recs"]:
        pdf.bullets(r["recs"], pdf._GOLD)
    return n + 1


def email_points(r):
    """Two or three short product lines for the email body."""
    out = r["points"][:2]
    if r["recs"]:
        out.append(f"Product action: {r['recs'][0]}")
    return out
