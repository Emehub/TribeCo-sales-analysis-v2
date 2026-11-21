"""
Extract data directly from PostgreSQL database.
Run this after filling in config.py with your DB credentials.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import create_engine, text
from config import DB_CONFIG

def connect():
    cfg = DB_CONFIG
    url = f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    engine = create_engine(url)
    print("Connected to PostgreSQL successfully.")
    return engine

def list_tables(engine):
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """
    df = pd.read_sql(query, engine)
    print("\nAvailable tables:")
    for t in df["table_name"]:
        print(f"  - {t}")
    return df["table_name"].tolist()

def export_table(engine, table_name):
    df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
    out_path = f"d:/company-dashboard-v2/data/{table_name}.csv"
    df.to_csv(out_path, index=False)
    print(f"Exported {len(df)} rows → {out_path}")
    return df

def export_custom_query(engine, query, filename):
    df = pd.read_sql(query, engine)
    out_path = f"d:/company-dashboard-v2/data/{filename}.csv"
    df.to_csv(out_path, index=False)
    print(f"Exported {len(df)} rows → {out_path}")
    return df

if __name__ == "__main__":
    engine = connect()
    tables = list_tables(engine)

    # Export all tables automatically
    for table in tables:
        export_table(engine, table)

    print("\nAll tables exported to d:/company-dashboard-v2/data/")
