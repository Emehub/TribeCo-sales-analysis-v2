"""
Targeted extraction of the 10 core dashboard tables from Metabase.
Uses native SQL with WHERE filters (GH + 2025-2026) for large tables
to avoid memory issues from pulling the entire global dataset.

Run: python scripts/extract_core_tables.py
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import pandas as pd
from io import StringIO
from config import METABASE_CONFIG

BASE     = METABASE_CONFIG["url"]
DB_NAME  = METABASE_CONFIG.get("dbname", "tribecodb")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# ── SQL queries for each core table ──────────────────────────────────────────
# Large tables use WHERE to limit scope. Small tables fetch all rows.
QUERIES = {
    "invoice": """
        SELECT * FROM invoice
        WHERE country_code = 'GH'
          AND created_at >= '2025-01-01'
    """,
    "repayment": """
        SELECT * FROM repayment
        WHERE country_code = 'GH'
          AND created_at >= '2025-01-01'
    """,
    "retail_centre": """
        SELECT * FROM retail_centre
        WHERE country_code = 'GH'
    """,
    "payment": """
        SELECT * FROM payment
        WHERE created_at >= '2025-01-01'
    """,
    "invoice_line": """
        SELECT il.*
        FROM invoice_line il
        INNER JOIN invoice i ON i.id = il.invoice_id
        WHERE i.country_code = 'GH'
          AND i.created_at >= '2025-01-01'
    """,
    "inventory_request": """
        SELECT * FROM inventory_request
        WHERE country_code = 'GH'
          AND created_at >= '2025-01-01'
    """,
    "inventory_request_fulfillment": """
        SELECT irf.*
        FROM inventory_request_fulfillment irf
        INNER JOIN inventory_request ir ON ir.id = irf.request_id
        WHERE ir.country_code = 'GH'
          AND ir.created_at >= '2025-01-01'
    """,
    "inventory_balances_view": """
        SELECT ibv.*
        FROM inventory_balances_view ibv
        INNER JOIN retail_centre rc ON rc.id = ibv.retail_centre_id
        WHERE rc.country_code = 'GH'
    """,
    "product":          "SELECT * FROM product",
    "preorder_campaign":"SELECT * FROM preorder_campaign",
}


def login():
    r = requests.post(
        f"{BASE}/api/session",
        json={"username": METABASE_CONFIG["username"],
              "password": METABASE_CONFIG["password"]},
        timeout=15,
    )
    r.raise_for_status()
    print("Logged in successfully.")
    return r.json()["id"]


def get_db_id(token):
    r = requests.get(f"{BASE}/api/database",
                     headers={"X-Metabase-Session": token}, timeout=15)
    r.raise_for_status()
    dbs = r.json().get("data", r.json())
    db_id = next(d["id"] for d in dbs if d["name"].lower() == DB_NAME.lower())
    print(f"Connected to '{DB_NAME}' (ID={db_id})\n")
    return db_id


def run_sql(token, db_id, sql, table_name):
    """Run a native SQL query and return a DataFrame. Uses CSV export endpoint
    which has no row limit and is memory-efficient for large result sets."""
    r = requests.post(
        f"{BASE}/api/dataset/csv",
        headers={"X-Metabase-Session": token,
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"query": str({
            "database": db_id,
            "type": "native",
            "native": {"query": sql.strip()},
        }).replace("'", '"')},
        timeout=300,
    )
    # If CSV export doesn't accept that format, fall back to /api/dataset JSON
    if r.status_code != 200 or not r.text.strip():
        return run_sql_json(token, db_id, sql, table_name)
    try:
        df = pd.read_csv(StringIO(r.text))
        return df
    except Exception:
        return run_sql_json(token, db_id, sql, table_name)


def run_sql_json(token, db_id, sql, table_name):
    """Fallback: run SQL via /api/dataset JSON, paginated."""
    hdrs      = {"X-Metabase-Session": token}
    all_rows  = []
    cols      = None
    PAGE_SIZE = 2000
    offset    = 0
    page      = 1

    while True:
        payload = {
            "database": db_id,
            "type":     "native",
            "native":   {"query": sql.strip()},
            "parameters": [],
        }
        # Native queries don't support offset/limit in MBQL but
        # we add LIMIT/OFFSET to the SQL itself
        paginated_sql = f"SELECT * FROM ({sql.strip()}) AS _q LIMIT {PAGE_SIZE} OFFSET {offset}"
        payload["native"]["query"] = paginated_sql

        r = requests.post(f"{BASE}/api/dataset",
                          headers=hdrs, json=payload, timeout=300)
        if r.status_code != 202:
            print(f"  ERROR {r.status_code} page {page}: {r.text[:200]}")
            break

        data      = r.json().get("data", {})
        page_rows = data.get("rows", [])
        if cols is None:
            cols = [c.get("display_name", c.get("name"))
                    for c in data.get("cols", [])]

        all_rows.extend(page_rows)
        print(f"  Page {page}: {len(page_rows):,} rows (total: {len(all_rows):,})")

        if len(page_rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        page   += 1

    return pd.DataFrame(all_rows, columns=cols or [])


def to_display_name(col):
    """Convert snake_case DB column name to Metabase display name (Title Case)."""
    parts  = col.split("_")
    result = []
    for p in parts:
        result.append("ID" if p.lower() == "id" else p.capitalize())
    return " ".join(result)

def rename_cols(df):
    """Rename all columns from snake_case to Metabase display name format."""
    return df.rename(columns={c: to_display_name(c) for c in df.columns})

def main():
    token = login()
    db_id = get_db_id(token)

    for table_name, sql in QUERIES.items():
        print(f"[{table_name}]")
        try:
            df = run_sql_json(token, db_id, sql, table_name)
            if df.empty:
                print(f"  No rows returned -- skipping\n")
                continue
            df  = rename_cols(df)
            out = os.path.join(DATA_DIR, f"{table_name}.csv")
            df.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"  Saved {len(df):,} rows -> {out}\n")
        except Exception as e:
            print(f"  FAILED: {e}\n")

    print("Done. All core tables extracted.")


if __name__ == "__main__":
    main()
