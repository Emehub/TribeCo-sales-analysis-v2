"""
Shared data layer: Metabase fetch, CSV fallback and the scoping/cleaning pipeline.

Used by the Streamlit dashboard (dashboard/app.py) and by the scheduled email job
(scripts/send_scheduled_reports.py), so both always see exactly the same data and filters.
`cfg` is the [metabase] secrets section: url, username, password, dbname.
"""
import os

import pandas as pd
import requests

TABLES = ["payment", "invoice", "repayment", "retail_centre", "product", "invoice_line",
          "inventory_request", "inventory_balances_view", "preorder_campaign",
          "inventory_request_fulfillment"]


# ── SQL queries — same filters as extract_core_tables.py ────────────────────────
QUERIES = {
    "payment": "SELECT * FROM payment WHERE created_at >= '2025-01-01'",
    "invoice": "SELECT * FROM invoice WHERE country_code = 'GH' AND created_at >= '2025-01-01'",
    "repayment": "SELECT * FROM repayment WHERE country_code = 'GH' AND created_at >= '2025-01-01'",
    "retail_centre": "SELECT * FROM retail_centre WHERE country_code = 'GH'",
    "product": "SELECT * FROM product",
    "invoice_line": """SELECT il.* FROM invoice_line il
        INNER JOIN invoice i ON i.id = il.invoice_id
        WHERE i.country_code = 'GH' AND i.created_at >= '2025-01-01'""",
    "inventory_request": "SELECT * FROM inventory_request WHERE country_code = 'GH' AND created_at >= '2025-01-01'",
    "inventory_balances_view": """SELECT ibv.* FROM inventory_balances_view ibv
        INNER JOIN retail_centre rc ON rc.id = ibv.retail_centre_id
        WHERE rc.country_code = 'GH'""",
    "preorder_campaign": "SELECT * FROM preorder_campaign",
    "inventory_request_fulfillment": """SELECT irf.* FROM inventory_request_fulfillment irf
        INNER JOIN inventory_request ir ON ir.id = irf.request_id
        WHERE ir.country_code = 'GH' AND ir.created_at >= '2025-01-01'""",
}


class _Metabase:
    def __init__(self, cfg):
        self.base = cfg["url"].rstrip("/")
        self.cfg = cfg

    def login(self):
        r = requests.post(f"{self.base}/api/session",
                          json={"username": self.cfg["username"], "password": self.cfg["password"]}, timeout=15)
        r.raise_for_status()
        return r.json()["id"]

    def db_id(self, token):
        r = requests.get(f"{self.base}/api/database", headers={"X-Metabase-Session": token}, timeout=15)
        r.raise_for_status()
        dbs = r.json().get("data", r.json())
        name = self.cfg.get("dbname", "tribecodb").lower()
        return next(d["id"] for d in dbs if d["name"].lower() == name)


def _mb_rename(df):
    """Convert snake_case DB column names to Title Case display names."""
    def _dn(col):
        parts = str(col).split("_")
        return " ".join("ID" if p.lower() == "id" else p.capitalize() for p in parts)
    return df.rename(columns={c: _dn(c) for c in df.columns})

def _mb_sql(token, db_id, sql, base):
    """Run a native SQL query via Metabase, return a renamed DataFrame."""
    hdrs = {"X-Metabase-Session": token}
    # Paginated JSON — reliable across all Metabase versions
    PAGE = 2000; all_rows = []; cols = None; offset = 0
    while True:
        paged = f"SELECT * FROM ({sql.strip()}) AS _q LIMIT {PAGE} OFFSET {offset}"
        r = requests.post(f"{base}/api/dataset", headers=hdrs,
                          json={"database": db_id, "type": "native",
                                "native": {"query": paged}}, timeout=120)
        if r.status_code not in (200, 202):
            raise RuntimeError(f"Metabase {r.status_code}: {r.text[:200]}")
        data = r.json().get("data", {})
        rows = data.get("rows", [])
        if cols is None:
            cols = [c.get("display_name", c.get("name")) for c in data.get("cols", [])]
        all_rows.extend(rows)
        if len(rows) < PAGE:
            break
        offset += PAGE
    return _mb_rename(pd.DataFrame(all_rows, columns=cols or []))



def fetch_raw(cfg, data_dir, save_csv=True):
    """Fetch every table live from Metabase; fall back to the last saved CSVs if that fails.
    Returns (raw_dict, from_metabase, fetch_error)."""
    raw, from_mb, err = {}, False, ""
    try:
        mb = _Metabase(cfg)
        tok = mb.login()
        dbid = mb.db_id(tok)
        for name, sql in QUERIES.items():
            raw[name] = _mb_sql(tok, dbid, sql, mb.base)
        from_mb = True
    except Exception as e:  # Metabase unreachable -- use the last saved copy
        err = f"{type(e).__name__}: {e}"
        raw = {t: pd.read_csv(os.path.join(data_dir, f"{t}.csv")) for t in TABLES}
    if from_mb and save_csv:
        # Persist fresh CSVs as a local backup; a read-only filesystem (Streamlit Cloud) is fine.
        try:
            os.makedirs(data_dir, exist_ok=True)
            for name, df in raw.items():
                df.to_csv(os.path.join(data_dir, f"{name}.csv"), index=False, encoding="utf-8-sig")
            with open(os.path.join(data_dir, "last_updated.txt"), "w", encoding="utf-8") as f:
                f.write(pd.Timestamp.now().strftime("%d %b %Y %H:%M"))
        except Exception:
            pass
    return raw, from_mb, err


# Central stock: each batch received into the Ghana warehouse, with its catalogue product and prices.
STOCK_SQL = """SELECT b.*, s.product_id AS catalog_product_id, s.cost_price, s.selling_price
    FROM batchorder b LEFT JOIN seller_product_catalog s ON s.id = b.seller_product_catalogid
    WHERE b.country_code = 'GH'"""
STOCK_CSV = "stock_batches.csv"


def load_stock(cfg, data_dir, save_csv=True):
    """Ghana stock batches live from Metabase, else the last saved copy. Returns (df, from_metabase, error)."""
    try:
        mb = _Metabase(cfg)
        tok = mb.login()
        df = _mb_sql(tok, mb.db_id(tok), STOCK_SQL, mb.base)
    except Exception as e:
        path = os.path.join(data_dir, STOCK_CSV)
        return (pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()), False, f"{type(e).__name__}: {e}"
    if save_csv:
        try:
            df.to_csv(os.path.join(data_dir, STOCK_CSV), index=False, encoding="utf-8-sig")
        except Exception:
            pass
    return df, True, ""


def load(cfg, data_dir, save_csv=True):
    """Fetch + process in one call: returns the same tuple the dashboard unpacks."""
    raw, from_mb, err = fetch_raw(cfg, data_dir, save_csv=save_csv)
    return process_raw(raw, target_year=None, from_metabase=from_mb, fetch_error=err)


def process_raw(_raw, target_year=None, from_metabase=True, fetch_error=""):
    """
    Convert a dict of raw DataFrames into the full set of processed variables.
    target_year=None → live mode (filter inv_scoped to year >= 2026)
    target_year=<int> → historical mode (filter inv_scoped to that exact year)
    """
    pay  = _raw.get("payment",                       pd.DataFrame()).copy()
    inv  = _raw.get("invoice",                       pd.DataFrame()).copy()
    rep  = _raw.get("repayment",                     pd.DataFrame()).copy()
    rc   = _raw.get("retail_centre",                 pd.DataFrame()).copy()
    prod = _raw.get("product",                       pd.DataFrame()).copy()
    il   = _raw.get("invoice_line",                  pd.DataFrame()).copy()
    ir   = _raw.get("inventory_request",             pd.DataFrame()).copy()
    ibv  = _raw.get("inventory_balances_view",       pd.DataFrame()).copy()
    camp = _raw.get("preorder_campaign",             pd.DataFrame()).copy()
    irf  = _raw.get("inventory_request_fulfillment", pd.DataFrame()).copy()

    # ── Parse date columns ──────────────────────────────────────────────────────
    for _col in ["Created At"]:
        if _col in pay.columns:  pay[_col]  = pd.to_datetime(pay[_col],  errors="coerce")
    for _col in ["Created At", "Due Date"]:
        if _col in inv.columns:  inv[_col]  = pd.to_datetime(inv[_col],  errors="coerce")
    for _col in ["Created At"]:
        if _col in rep.columns:  rep[_col]  = pd.to_datetime(rep[_col],  errors="coerce")
    for _col in ["Created At"]:
        if _col in ir.columns:   ir[_col]   = pd.to_datetime(ir[_col],   errors="coerce")

    # ── Filter to Ghana (GH) ────────────────────────────────────────────────────
    if "Country Code" in inv.columns: inv = inv[inv["Country Code"] == "GH"].copy()
    if "Country Code" in rep.columns: rep = rep[rep["Country Code"] == "GH"].copy()
    if "Country Code" in rc.columns:  rc  = rc[rc["Country Code"]   == "GH"].copy()
    gh_inv_ids = set(inv["ID"].dropna().astype(int)) if "ID" in inv.columns else set()
    if "Invoice ID" in il.columns:
        il = il[il["Invoice ID"].isin(gh_inv_ids)].copy()
    gh_rc_ids = set(rc["ID"].dropna()) if "ID" in rc.columns else set()
    if "Retail Centre ID" in ibv.columns:
        ibv = ibv[ibv["Retail Centre ID"].isin(gh_rc_ids)].copy()

    # ── Derived columns ─────────────────────────────────────────────────────────
    if "Status" in pay.columns:
        pay["Payment Status"] = pay["Status"].map({0: "Failed", 1: "Success"})
    if "Created At" in inv.columns:
        inv["Month"] = inv["Created At"].dt.to_period("M").astype(str)
        inv["Week"]  = inv["Created At"].dt.to_period("W").astype(str)
    if "Status" in ir.columns:
        ir["Request Status"] = ir["Status"].map({0:"Draft",1:"Pending",2:"Processing",3:"Completed",4:"Cancelled",5:"Failed"})
    if "Delivery Type" in ir.columns:
        ir["Delivery Label"] = ir["Delivery Type"].map({0.0:"Direct",1.0:"Via Hub"})

    if "Quantity" in il.columns and "Price" in il.columns:
        il["Line Revenue"] = pd.to_numeric(il["Quantity"], errors="coerce") * pd.to_numeric(il["Price"], errors="coerce")
    if not prod.empty and "Product ID" in il.columns and "ID" in prod.columns:
        _pcols = [c for c in ["ID","Generic Name","Brand Name"] if c in prod.columns]
        prod_rev = il.merge(prod[_pcols], left_on="Product ID", right_on="ID", how="left")
        _gn = prod_rev["Generic Name"] if "Generic Name" in prod_rev.columns else pd.Series(dtype=str)
        _bn = prod_rev["Brand Name"]   if "Brand Name"   in prod_rev.columns else pd.Series(dtype=str)
        prod_rev["Product Name"] = _gn.fillna(_bn).str.strip()
    else:
        prod_rev = il.copy()
        prod_rev["Product Name"] = ""

    if not camp.empty:
        for _col in ["Start Date","End Date","Created At"]:
            if _col in camp.columns:
                try:
                    camp[_col] = pd.to_datetime(camp[_col], format="ISO8601", utc=True).dt.tz_convert(None)
                except Exception:
                    camp[_col] = pd.to_datetime(camp[_col], errors="coerce")
        if "Status" in camp.columns:
            camp["Status Label"] = camp["Status"].map({1:"Active",2:"Completed",3:"Cancelled"}).fillna("Unknown")

    if not irf.empty:
        for _col in ["Expected At","Created At"]:
            if _col in irf.columns:
                try:
                    irf[_col] = pd.to_datetime(irf[_col], format="ISO8601", utc=True).dt.tz_convert(None)
                except Exception:
                    irf[_col] = pd.to_datetime(irf[_col], errors="coerce")
        if "Status" in irf.columns:
            irf["Fulfillment Status"] = irf["Status"].map({0:"Pending",1:"Processing",2:"Failed",3:"Fulfilled",4:"Cancelled"}).fillna("Unknown")

    _rc_cols = [c for c in ["ID","Name","Status","Country Code"] if c in rc.columns]
    rc_names = rc[_rc_cols].copy() if _rc_cols else rc.copy()

    # ── Inventory request filters ───────────────────────────────────────────────
    _ir_cols = ["Channel","Fulfillment Type","Request Type","Status"]
    if not ir.empty and all(c in ir.columns for c in _ir_cols):
        ir_fbc = ir[
            (ir["Channel"] != "BufferPesa") &
            (ir["Fulfillment Type"] != 3) &
            (ir["Request Type"] == 0) &
            (ir["Status"].isin([3, 5, 7]))
        ].copy()
        ir_all_fbc = ir[
            (ir["Channel"] != "BufferPesa") &
            (ir["Fulfillment Type"] != 3) &
            (ir["Request Type"] == 0) &
            (ir["Status"] != 4)
        ].copy()
    else:
        ir_fbc = ir.copy()
        ir_all_fbc = ir.copy()

    if not ir_all_fbc.empty and "Status" in ir_all_fbc.columns:
        ir_all_fbc["Fulfillment Label"] = ir_all_fbc["Status"].map({
            0: "Not Started", 1: "Scheduled", 2: "In Progress",
            3: "Completed",   5: "Completed", 7: "Completed",
        }).fillna("Unknown")

    # ── Invoice scope (FBC orders, not cancelled) ───────────────────────────────
    _inv_fbc_filter = pd.Series([True] * len(inv), index=inv.index)
    if "Order Type" in inv.columns: _inv_fbc_filter &= (inv["Order Type"] == 1)
    if "Channel"    in inv.columns: _inv_fbc_filter &= (inv["Channel"] != "BufferPesa")
    inv_fbc_ids = set(inv[_inv_fbc_filter]["ID"].dropna()) if "ID" in inv.columns else set()

    _scoped_filter = _inv_fbc_filter.copy()
    if "Status" in inv.columns: _scoped_filter &= (inv["Status"] != 5)
    inv_scoped = inv[_scoped_filter].copy()

    if "Discountedvalue" in inv_scoped.columns:
        inv_scoped["Discountedvalue"] = pd.to_numeric(inv_scoped["Discountedvalue"], errors="coerce").fillna(0)
        if "Total Order Value" in inv_scoped.columns:
            _tov = pd.to_numeric(inv_scoped["Total Order Value"], errors="coerce").fillna(0)
            inv_scoped["Discountedvalue"] = inv_scoped["Discountedvalue"].where(inv_scoped["Discountedvalue"] > 0, _tov)
    if "Totalrepaid" in inv_scoped.columns:
        inv_scoped["Totalrepaid"] = pd.to_numeric(inv_scoped["Totalrepaid"], errors="coerce").fillna(0)
    if "Discountedvalue" in inv_scoped.columns and "Totalrepaid" in inv_scoped.columns:
        inv_scoped["Outstanding"] = (inv_scoped["Discountedvalue"] - inv_scoped["Totalrepaid"]).clip(lower=0)

    # ── Year scope ──────────────────────────────────────────────────────────────
    if "Created At" in inv_scoped.columns:
        if target_year is not None:
            inv_scoped = inv_scoped[inv_scoped["Created At"].dt.year == target_year].copy()
        else:
            inv_scoped = inv_scoped[inv_scoped["Created At"].dt.year >= 2026].copy()

    if "Created At" in inv_scoped.columns:
        inv_scoped["Month"] = inv_scoped["Created At"].dt.to_period("M").astype(str)
        inv_scoped["Week"]  = inv_scoped["Created At"].dt.to_period("W").astype(str)

    _rep_filter = pd.Series([True] * len(rep), index=rep.index)
    if "Invoice ID" in rep.columns: _rep_filter &= rep["Invoice ID"].isin(inv_fbc_ids)
    if "Status"     in rep.columns: _rep_filter &= (rep["Status"] == "Confirmed")
    rep_scoped = rep[_rep_filter].copy()

    _fetch_ts = pd.Timestamp.now().strftime("%d %b %Y %H:%M")
    return (pay, inv, rep, rc, prod, il, ir, prod_rev, rc_names, ibv, camp, irf,
            inv_scoped, rep_scoped, ir_all_fbc, _fetch_ts, from_metabase, fetch_error)


