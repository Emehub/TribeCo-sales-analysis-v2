"""
Scheduled management emails (run by GitHub Actions every hour; sends only when a report is due).

  python scripts/send_scheduled_reports.py                 # send whatever is due now (idempotent)
  python scripts/send_scheduled_reports.py --report weekly --force --to me@cowtribe.com
  python scripts/send_scheduled_reports.py --report monthly --period 2026-09 --dry-run --out exports/
  python scripts/send_scheduled_reports.py --report auto --trigger external   # called by an outside scheduler

Configuration comes from environment variables (GitHub Actions secrets) or, when running locally,
from .streamlit/secrets.toml:
  METABASE_URL, METABASE_USERNAME, METABASE_PASSWORD, METABASE_DBNAME
  RESEND_API_KEY, RESEND_FROM, RESEND_REPLY_TO      (or SMTP_USER, SMTP_PASSWORD for Gmail)
  ADMIN_SHEET_ID, GCP_SERVICE_ACCOUNT_JSON
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
DATA = os.path.join(ROOT, "data")
LOCAL_STORE = os.path.join(ROOT, "data", "admin_store.local.json")


def load_config():
    cfg = {}
    sec = os.path.join(ROOT, ".streamlit", "secrets.toml")
    if os.path.exists(sec):
        import tomllib
        with open(sec, "rb") as f:
            cfg = tomllib.load(f)
    def env(name, default=""):
        """Secret value with stray spaces / line breaks from copy-paste removed; empty counts as unset."""
        return (os.environ.get(name) or "").strip() or default
    if env("METABASE_URL"):
        cfg["metabase"] = {"url": env("METABASE_URL"), "username": env("METABASE_USERNAME"),
                           "password": env("METABASE_PASSWORD"), "dbname": env("METABASE_DBNAME", "tribecodb")}
    if env("RESEND_API_KEY"):
        cfg["resend"] = {"api_key": env("RESEND_API_KEY"),
                         "from": env("RESEND_FROM") or "TribeCo Ghana Reports <onboarding@resend.dev>",
                         "reply_to": env("RESEND_REPLY_TO", "")}
    if env("SMTP_USER"):
        cfg["smtp"] = {"user": env("SMTP_USER"), "password": env("SMTP_PASSWORD"),
                       "from_name": env("SMTP_FROM_NAME", "TribeCo Ghana Reports")}
    if env("ADMIN_SHEET_ID"):
        cfg["admin_store"] = {"sheet_id": env("ADMIN_SHEET_ID")}
    if env("GCP_SERVICE_ACCOUNT_JSON"):
        cfg["gcp_service_account"] = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"].strip())
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", choices=["auto", "weekly", "monthly"], default="auto")
    ap.add_argument("--period", help="weekly: e.g. 2026-09-28/2026-10-04; monthly: e.g. 2026-09")
    ap.add_argument("--force", action="store_true", help="send even if not due or already sent")
    ap.add_argument("--to", help="comma-separated recipients (overrides the store; for testing)")
    ap.add_argument("--dry-run", action="store_true", help="build only; write files instead of sending")
    ap.add_argument("--trigger", choices=["internal", "external"], default="internal",
                    help="external = called by the company scheduler (hourly heartbeat); timing still follows "
                         "the Admin page settings")
    ap.add_argument("--out", default=os.path.join(ROOT, "exports"))
    a = ap.parse_args()

    import admin_store
    import mailer
    import report_jobs as rj
    cfg = load_config()
    email_cfg = mailer.config_from(cfg)
    missing = [k for k in ("metabase", "admin_store", "gcp_service_account") if k not in cfg]
    if not a.dry_run and email_cfg is None:
        missing.append("resend (or smtp)")
    if missing and not a.dry_run:
        # Not set up yet (see docs/ADMIN_AND_EMAIL_SETUP.md): skip quietly instead of failing every hour.
        print("Scheduled reports are not configured yet (missing: " + ", ".join(missing) + "); nothing sent.")
        return 0
    store = admin_store.open_store(cfg, LOCAL_STORE)
    settings = store.get_settings()
    now = rj.now_local(settings)

    kinds = ["weekly", "monthly"] if a.report == "auto" else [a.report]
    todo = []
    for k in kinds:
        is_due, period = rj.due(k, settings, now)
        period = a.period or period
        if a.force or (is_due and not store.already_sent(k, period)):
            todo.append((k, period))
        else:
            print(f"{k}: not due ({'already sent' if is_due else 'outside schedule'}) for {period}")
    # One-off sends scheduled on the Admin page whose time has come (skipped for targeted test runs)
    oneoffs = [] if (a.force or a.to or a.period or a.report != "auto") else store.due_oneoffs(now)
    for o in oneoffs:
        print(f"one-off #{o['id']}: {o['report']} {o['period']} scheduled for {o['send_at']}")
    if not todo and not oneoffs:
        return 0

    import data_layer as dl
    (pay, inv, rep, rc, prod, il, ir, prod_rev, rc_names, ibv, camp, irf,
     inv_scoped, rep_scoped, ir_all_fbc, ts, live, err) = dl.load(cfg["metabase"], DATA, save_csv=False)
    if not live:
        print(f"WARNING: Metabase unavailable ({err}); using saved CSVs")
    d = dict(inv=inv, inv_scoped=inv_scoped, rep_scoped=rep_scoped, rc=rc, il=il, prod=prod, data_dir=DATA)
    to = [t.strip() for t in a.to.split(",")] if a.to else None

    failed = False
    for k, period in todo:
        try:
            parts = rj.send(k, d, store, email_cfg, period, recipients=to,
                            triggered_by=("manual" if (a.force or a.to) else
                                          "schedule (external)" if a.trigger == "external" else "schedule"),
                            dry_run=a.dry_run)
            if a.dry_run:
                os.makedirs(a.out, exist_ok=True)
                with open(os.path.join(a.out, parts["pdf_name"]), "wb") as f:
                    f.write(parts["pdf"])
                with open(os.path.join(a.out, parts["pdf_name"].replace(".pdf", ".html")), "w", encoding="utf-8") as f:
                    f.write(parts["html"])
                print(f"{k} {period}: built (dry run) -> {parts['pdf_name']} | would send to {parts['recipients']}")
            else:
                print(f"{k} {period}: sent to {len(parts['recipients'])} recipient(s)")
        except Exception as e:
            failed = True
            print(f"{k} {period}: FAILED - {type(e).__name__}: {e}")
    for o in oneoffs:
        try:
            if a.dry_run:
                print(f"one-off #{o['id']}: would send (dry run)")
                continue
            only = [x.strip() for x in str(o.get("send_to", "")).split(",") if x.strip()] or None
            parts = rj.send(o["report"], d, store, email_cfg, o["period"], recipients=only,
                            triggered_by=f"one-off #{o['id']}",
                            idempotency_key=f"tribeco-oneoff-{o['id']}")
            store.set_oneoff_status(o["id"], "sent", f"to {len(parts['recipients'])} recipient(s)")
            print(f"one-off #{o['id']}: sent to {len(parts['recipients'])} recipient(s)")
        except Exception as e:
            failed = True
            store.set_oneoff_status(o["id"], "failed", f"{type(e).__name__}: {e}")
            print(f"one-off #{o['id']}: FAILED - {type(e).__name__}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
