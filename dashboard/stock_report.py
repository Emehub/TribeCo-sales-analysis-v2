"""
Product stock: what was received into the Ghana central warehouse, what has been sold and what remains,
per batch and per product, with sales pace, weeks of stock left and expiry risk.

Source: Metabase batchorder (one row per batch received) joined to seller_product_catalog for the
product and prices (data_layer.load_stock). Sales pace comes from invoice lines on non-cancelled invoices.
"""
import pandas as pd

EXPIRY_WARN_DAYS = 90      # remaining stock expiring within this many days is flagged
LOW_STOCK_WEEKS = 4        # fewer weeks of stock than this (at the recent sales pace) is "Low stock"
PACE_WEEKS = 8             # sales pace = average units a week over the last PACE_WEEKS complete weeks
STATUS_ORDER = ["Out of stock", "Expired stock", "Expiring soon", "Low stock", "Not selling", "In stock"]


def _naive(s):
    s = pd.to_datetime(s, errors="coerce", utc=True)
    return s.dt.tz_convert(None)


def batches(raw, today=None):
    """One row per batch: received, sold, remaining, prices, expiry and days to expiry."""
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    if raw is None or raw.empty:
        return pd.DataFrame()
    b = raw.copy()
    num = ["Receivedquantity", "Stockssold", "Cost Price", "Selling Price"]
    for c in num:
        b[c] = pd.to_numeric(b.get(c), errors="coerce").fillna(0)
    b = b[b.get("Status", "Received").astype(str) != "Pending"].copy()
    out = pd.DataFrame({
        "Product": b["Productname"].astype(str).str.strip(),
        "Product ID": b.get("Catalog Product ID"),
        "Batch": b["Batchnumber"].astype(str),
        "Storage": b.get("Storagecondition", ""),
        "Received": b["Receivedquantity"].astype(int),
        "Sold": b["Stockssold"].astype(int),
        "Cost Price": b["Cost Price"],
        "Selling Price": b["Selling Price"],
        "Manufactured": _naive(b["Manufacturedate"]),
        "Expiry": _naive(b["Expirydate"]),
    })
    out["Remaining"] = (out["Received"] - out["Sold"]).clip(lower=0)
    out["Days to Expiry"] = (out["Expiry"] - today).dt.days
    return out.sort_values(["Product", "Expiry"]).reset_index(drop=True)


def weekly_sales(inv, il, product_ids, today=None, weeks=12):
    """Units sold a week (Mon-Sun) for these products over the last `weeks` complete weeks.
    Returns a DataFrame indexed by week start with one column per Product ID."""
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    this_monday = today - pd.Timedelta(days=today.weekday())
    start = this_monday - pd.Timedelta(weeks=weeks)
    ok = inv[pd.to_numeric(inv.get("Status"), errors="coerce") != 5][["ID", "Created At"]].copy()
    ok["Date"] = _naive(ok["Created At"])
    lines = il[il["Product ID"].isin(set(product_ids))].merge(ok, left_on="Invoice ID", right_on="ID")
    lines = lines[(lines["Date"] >= start) & (lines["Date"] < this_monday)]
    lines["Week"] = lines["Date"].dt.normalize() - pd.to_timedelta(lines["Date"].dt.weekday, unit="D")
    lines["Quantity"] = pd.to_numeric(lines["Quantity"], errors="coerce").fillna(0)
    table = lines.pivot_table(index="Week", columns="Product ID", values="Quantity", aggfunc="sum")
    weeks_idx = pd.date_range(start, this_monday - pd.Timedelta(weeks=1), freq="7D")
    return table.reindex(weeks_idx).fillna(0)


def products(b, weekly, today=None):
    """One row per product: totals, stock value, sales pace, weeks left, nearest expiry and a status."""
    if b.empty:
        return pd.DataFrame()
    live = b[b["Remaining"] > 0]
    g = b.groupby("Product").agg(
        product_id=("Product ID", "first"), batches=("Batch", "count"), received=("Received", "sum"),
        sold=("Sold", "sum"), remaining=("Remaining", "sum"), cost=("Cost Price", "max"),
        price=("Selling Price", "max"))
    g["expired"] = live[live["Days to Expiry"] < 0].groupby("Product")["Remaining"].sum()
    g["expiring"] = live[live["Days to Expiry"].between(0, EXPIRY_WARN_DAYS)].groupby("Product")["Remaining"].sum()
    g["next_expiry"] = live[live["Days to Expiry"] >= 0].groupby("Product")["Expiry"].min()
    g[["expired", "expiring"]] = g[["expired", "expiring"]].fillna(0).astype(int)

    recent = weekly.tail(PACE_WEEKS) if len(weekly) else weekly
    pace = recent.mean() if len(recent) else pd.Series(dtype=float)
    g["pace"] = g["product_id"].map(pace).fillna(0)
    g["weeks_left"] = (g["remaining"] / g["pace"]).where(g["pace"] > 0)

    def status(r):
        if r["remaining"] == 0:
            return "Out of stock"
        if r["expired"] > 0:
            return "Expired stock"
        if r["expiring"] > 0:
            return "Expiring soon"
        if r["pace"] == 0:
            return "Not selling"
        if r["weeks_left"] < LOW_STOCK_WEEKS:
            return "Low stock"
        return "In stock"

    g["status"] = g.apply(status, axis=1)
    g["sold_pct"] = (g["sold"] / g["received"]).where(g["received"] > 0, 0)
    g["value_price"] = g["remaining"] * g["price"]
    g["value_cost"] = g["remaining"] * g["cost"]
    g["status_rank"] = g["status"].map(STATUS_ORDER.index)
    return g.reset_index().sort_values(["status_rank", "remaining"], ascending=[True, False]).reset_index(drop=True)


def summary(p):
    if p.empty:
        return {}
    return {
        "products": len(p), "in_stock": int((p["remaining"] > 0).sum()),
        "received": int(p["received"].sum()), "sold": int(p["sold"].sum()), "remaining": int(p["remaining"].sum()),
        "value_price": float(p["value_price"].sum()), "value_cost": float(p["value_cost"].sum()),
        "out": int((p["status"] == "Out of stock").sum()), "low": int((p["status"] == "Low stock").sum()),
        "expired_units": int(p["expired"].sum()), "expiring_units": int(p["expiring"].sum()),
        "expired_value": float((p["expired"] * p["price"]).sum()),
        "expiring_value": float((p["expiring"] * p["price"]).sum()),
    }
