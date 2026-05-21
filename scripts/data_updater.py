"""
Background data updater — polls Metabase every 5 minutes and refreshes all CSVs.
Run this alongside the Streamlit dashboard so the charts always show current data.

Usage:
    python scripts/data_updater.py
"""
import sys
import os
import time
import logging
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from scripts.extract_metabase import login, find_database, list_tables, export_table, export_saved_questions

INTERVAL = 300  # seconds between refreshes (5 minutes)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR  = os.path.join(BASE_DIR, "logs")
TS_FILE  = os.path.join(DATA_DIR, "last_updated.txt")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "updater.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def snapshot_row_counts():
    """Return {filename: row_count} for every CSV currently in DATA_DIR."""
    counts = {}
    for fname in os.listdir(DATA_DIR):
        if fname.endswith(".csv"):
            try:
                df = pd.read_csv(os.path.join(DATA_DIR, fname))
                counts[fname] = len(df)
            except Exception:
                counts[fname] = 0
    return counts


def write_timestamp():
    ts = datetime.now().strftime("%H:%M  %d %b %Y")
    with open(TS_FILE, "w", encoding="utf-8") as f:
        f.write(ts)
    return ts


def run_once():
    """One full extraction cycle: fetch from Metabase, save CSVs, report new rows."""
    try:
        before = snapshot_row_counts()

        token  = login()
        db_id  = find_database(token)
        tables = list_tables(token, db_id)

        for table in tables:
            try:
                export_table(token, db_id, table)
            except Exception as e:
                log.warning(f"  Skipped table '{table['name']}': {e}")

        export_saved_questions(token, db_id)

        after      = snapshot_row_counts()
        new_total  = 0

        for fname in sorted(after):
            old = before.get(fname, 0)
            new = after[fname]
            diff = new - old
            if diff > 0:
                log.info(f"  NEW DATA  {fname}: +{diff:,} rows  ({old:,} → {new:,})")
                new_total += diff

        if new_total == 0:
            log.info("  No new entries detected across all tables.")
        else:
            log.info(f"  Total new entries this cycle: {new_total:,}")

        ts = write_timestamp()
        log.info(f"  Timestamp written: {ts}")

    except Exception as e:
        log.error(f"Refresh cycle failed: {e}")


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("CowTribe Data Updater — refresh every 5 minutes")
    log.info(f"  Data dir : {DATA_DIR}")
    log.info(f"  Log file : {os.path.join(LOG_DIR, 'updater.log')}")
    log.info("=" * 60)

    while True:
        log.info("--- Starting refresh cycle ---")
        run_once()
        log.info(f"--- Done. Sleeping {INTERVAL // 60} min before next cycle ---\n")
        time.sleep(INTERVAL)
