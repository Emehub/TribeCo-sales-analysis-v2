"""
Extract data from Metabase API.
Connects to the 'tribecodb' database in Metabase and exports all tables + saved questions.
Run after filling in config.py with your Metabase credentials.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pandas as pd
from io import StringIO
from config import METABASE_CONFIG

BASE    = METABASE_CONFIG["url"]
DB_NAME = METABASE_CONFIG.get("dbname", "tribecodb")

def login():
    resp = requests.post(
        f"{BASE}/api/session",
        json={"username": METABASE_CONFIG["username"], "password": METABASE_CONFIG["password"]},
        timeout=10
    )
    resp.raise_for_status()
    token = resp.json()["id"]
    print("Logged into Metabase successfully.")
    return token

def get_headers(token):
    return {"X-Metabase-Session": token}

def find_database(token):
    """Find the database ID for tribecodb."""
    resp = requests.get(f"{BASE}/api/database", headers=get_headers(token), timeout=10)
    resp.raise_for_status()
    databases = resp.json().get("data", resp.json())
    print("\nDatabases found in Metabase:")
    target_id = None
    for db in databases:
        marker = " ◀ target" if db["name"].lower() == DB_NAME.lower() else ""
        print(f"  ID {db['id']:>3} — {db['name']}{marker}")
        if db["name"].lower() == DB_NAME.lower():
            target_id = db["id"]
    if not target_id:
        raise ValueError(f"Database '{DB_NAME}' not found in Metabase.")
    print(f"\nUsing database: '{DB_NAME}' (ID={target_id})")
    return target_id

def list_tables(token, db_id):
    """List all tables in the target database."""
    resp = requests.get(f"{BASE}/api/database/{db_id}/metadata", headers=get_headers(token), timeout=15)
    resp.raise_for_status()
    tables = resp.json().get("tables", [])
    print(f"\nTables in '{DB_NAME}':")
    for t in tables:
        print(f"  ID {t['id']:>4} — {t['name']}")
    return tables

def export_table(token, db_id, table):
    """Export a full table via /api/dataset JSON response (avoids CSV endpoint quirks)."""
    payload = {
        "database": db_id,
        "type": "query",
        "query": {"source-table": table["id"]}
    }
    resp = requests.post(
        f"{BASE}/api/dataset",
        headers=get_headers(token),
        json=payload,
        timeout=120
    )
    if resp.status_code != 202:
        print(f"  ERROR {resp.status_code} on '{table['name']}': {resp.text[:300]}")
        return None

    result = resp.json()
    data   = result.get("data", {})
    cols   = [c.get("display_name", c.get("name")) for c in data.get("cols", [])]
    rows   = data.get("rows", [])

    if not cols:
        print(f"  Skipped '{table['name']}': empty or no columns returned")
        return None

    df = pd.DataFrame(rows, columns=cols)
    safe_name = table["name"].replace(" ", "_")
    out_path  = f"d:/company-dashboard/data/{safe_name}.csv"
    df.to_csv(out_path, index=False)
    print(f"  Exported '{table['name']}' — {len(df):,} rows → {out_path}")
    return df

def export_saved_questions(token, db_id):
    """Also export any saved Metabase questions tied to this database."""
    resp = requests.get(f"{BASE}/api/card", headers=get_headers(token), timeout=10)
    resp.raise_for_status()
    all_questions = resp.json()
    db_questions = [q for q in all_questions if q.get("database_id") == db_id]

    if not db_questions:
        print("\nNo saved questions found for this database.")
        return

    print(f"\nSaved questions for '{DB_NAME}' ({len(db_questions)} found):")
    for q in db_questions:
        try:
            r = requests.post(
                f"{BASE}/api/card/{q['id']}/query/csv",
                headers=get_headers(token),
                timeout=60
            )
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text))
            safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in q["name"])
            out_path = f"d:/company-dashboard/data/question_{safe_name}.csv"
            df.to_csv(out_path, index=False)
            print(f"  Exported '{q['name']}' — {len(df):,} rows → {out_path}")
        except Exception as e:
            print(f"  Skipped '{q['name']}': {e}")

if __name__ == "__main__":
    token  = login()
    db_id  = find_database(token)
    tables = list_tables(token, db_id)

    print(f"\nExporting all {len(tables)} tables...")
    for table in tables:
        try:
            export_table(token, db_id, table)
        except Exception as e:
            print(f"  Skipped '{table['name']}': {e}")

    export_saved_questions(token, db_id)

    print("\nDone. All data saved to d:/company-dashboard/data/")
