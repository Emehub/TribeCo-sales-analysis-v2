"""
Report jobs shared by the scheduled email job and the Admin page's "Send now": decide what is due,
build the report (PDF + email body), send it and record the result in the admin store's email log.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import mailer
import monthly_report
import weekly_report

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def scoped_history(inv):
    """All Ghana FBC, non-cancelled invoices across years (for true first-order dates)."""
    f = pd.Series(True, index=inv.index)
    if "Order Type" in inv.columns:
        f &= inv["Order Type"] == 1
    if "Channel" in inv.columns:
        f &= inv["Channel"] != "BufferPesa"
    if "Status" in inv.columns:
        f &= inv["Status"] != 5
    return inv[f]


def now_local(settings):
    return datetime.now(ZoneInfo(settings.get("timezone", "Africa/Accra"))).replace(tzinfo=None)


def due(kind, settings, now):
    """(is_due, period). Weekly: on the send day at/after the send time. Monthly: the first such day of
    the month. Periods: last completed Monday-Sunday week / previous calendar month."""
    if settings.get(f"{kind}_enabled", "yes").lower() not in ("yes", "true", "1"):
        return False, None
    day = DAYS.index(settings.get("send_day", "Friday"))
    hh, mm = (int(x) for x in settings.get("send_time", "09:00").split(":"))
    on_time = now.weekday() == day and (now.hour, now.minute) >= (hh, mm)
    if kind == "weekly":
        return on_time, weekly_report.last_completed_week(now)
    return on_time and now.day <= 7, monthly_report.previous_month(now)


def build(kind, d, period, settings, as_of=None):
    """d: dict with inv, inv_scoped, rep_scoped, rc, il, prod, data_dir. Returns the email parts."""
    as_of = as_of or pd.Timestamp.now().strftime("%d %b %Y")
    url = settings.get("dashboard_url", "")
    if kind == "weekly":
        targets = pd.read_csv(os.path.join(d["data_dir"], "weekly_revenue_target.csv"))
        r = weekly_report.compute(period, d["inv_scoped"], d["rep_scoped"], d["rc"], d["il"], targets)
        subject, html = weekly_report.email_html(r, url)
        pdf = weekly_report.build_pdf(r, as_of)
        name = f"TribeCo_Ghana_Weekly_Report_{pd.Period(period, freq='W').start_time:%Y-%m-%d}.pdf"
    else:
        targets = pd.read_csv(os.path.join(d["data_dir"], "revenue_target.csv"))
        r = monthly_report.compute(period, d["inv_scoped"], d["rep_scoped"], d["rc"], d["il"], d["prod"],
                                   targets, scoped_history(d["inv"]))
        subject, html = monthly_report.email_html(r, url)
        pdf = monthly_report.build_pdf(r, as_of)
        name = f"TribeCo_Ghana_Monthly_Report_{period}.pdf"
    return dict(subject=subject, html=html, pdf=pdf, pdf_name=name, period=period)


def send(kind, d, store, smtp, period, recipients=None, triggered_by="schedule", dry_run=False):
    """Build and send one report; logs the outcome. Returns the built parts plus 'recipients'."""
    settings = store.get_settings()
    to = recipients if recipients is not None else store.recipients(kind)
    try:
        parts = build(kind, d, period, settings)
        parts["recipients"] = to
        if dry_run:
            return parts
        if not to:
            raise ValueError(f"No active users have the {kind} report switched on")
        mailer.send(smtp, to, parts["subject"], parts["html"],
                    [(parts["pdf_name"], parts["pdf"], "application/pdf")])
        store.log(kind, period, to, "sent", parts["subject"], triggered_by)
        return parts
    except Exception as e:
        store.log(kind, period, to or [], "failed", f"{type(e).__name__}: {e}", triggered_by)
        raise
