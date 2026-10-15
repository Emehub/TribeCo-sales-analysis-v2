"""
Admin page: users and roles, report settings, preview / send reports, scheduled sends and the email log.
Rendered by app.py only for signed-in Admins.
"""
import html as _html

import pandas as pd
import streamlit as st

import admin_store
import monthly_report
import report_jobs
import weekly_report

GREEN = "#024b30"
GOLD = "#c9975a"


def _week_options(d, now):
    return sorted(w for w in d["inv_scoped"]["Week"].dropna().unique()
                  if w <= weekly_report.last_completed_week(now))[-12:][::-1]


def _week_label(w):
    return f"{pd.Period(w, freq='W').start_time:%d %b} - {pd.Period(w, freq='W').end_time:%d %b %Y}"


def _month_options(now):
    return [str(p) for p in pd.period_range(f"{now.year}-01", monthly_report.previous_month(now), freq="M")][::-1]


def _month_label(m):
    return pd.Period(m, freq="M").strftime("%B %Y")


def _period_label(kind, period):
    return _week_label(period) if kind == "weekly" else _month_label(period)


def _t(hhmm):
    hh, mm = (int(x) for x in str(hhmm).split(":")[:2])
    return pd.Timestamp(2000, 1, 1, hh, mm).time()


def _next_send(kind, settings, now):
    """First hour from now when the regular schedule sends this report, or None if it is switched off."""
    t = pd.Timestamp(now).floor("h")
    for _ in range(24 * 40):
        if report_jobs.due(kind, settings, t)[0]:
            return t
        t += pd.Timedelta(hours=1)
    return None


def _heading(title, sub=""):
    sub = f'<div style="color:#6b7280;font-size:13px;margin-top:2px">{_html.escape(sub)}</div>' if sub else ""
    st.markdown(f'<div style="margin:4px 0 10px"><div style="font-size:16px;font-weight:700;color:{GREEN}">'
                f'{_html.escape(title)}</div>{sub}</div>', unsafe_allow_html=True)


def _stat(label, value, sub, color=GREEN):
    return (f'<div class="kpi-card" style="border-top-color:{color}"><div class="kpi-label">{_html.escape(label)}'
            f'</div><div class="kpi-value" style="font-size:20px">{_html.escape(str(value))}</div>'
            f'<div class="kpi-sub">{_html.escape(sub)}</div></div>')


def _table(rows, cols):
    """rows: list of dicts; cols: {source column: heading}. Yes/no values shown as Yes / No."""
    df = pd.DataFrame(rows)
    df = df[[c for c in cols if c in df.columns]].rename(columns=cols)
    df = df.replace({"yes": "Yes", "no": "No"})
    st.dataframe(df, width="stretch", hide_index=True)


def render(store, me, bootstrap_admins, d, smtp):
    settings = store.get_settings()
    users = store.list_users()
    oneoffs = store.list_oneoffs()
    pending = [r for r in oneoffs if r["status"] == "pending"]
    now = pd.Timestamp.now(tz="Africa/Accra").tz_localize(None)

    # ── Summary ───────────────────────────────────────────────────────────────
    nxt = {k: _next_send(k, settings, now) for k in ("weekly", "monthly")}
    active = [u for u in users if u.get("active", "yes") == "yes"]
    cards = [
        _stat("Users", len(active), f"{sum(u['role'] == 'Admin' for u in active)} admin(s), "
                                    f"{sum(u['role'] == 'Manager' for u in active)} manager(s)"),
        _stat("Next weekly email", f"{nxt['weekly']:%a %d %b}" if nxt["weekly"] else "Off",
              f"at {nxt['weekly']:%H:%M} to {len(store.recipients('weekly'))} recipient(s)" if nxt["weekly"]
              else "Switched off in Report settings", GOLD),
        _stat("Next monthly email", f"{nxt['monthly']:%a %d %b}" if nxt["monthly"] else "Off",
              f"at {nxt['monthly']:%H:%M} to {len(store.recipients('monthly'))} recipient(s)" if nxt["monthly"]
              else "Switched off in Report settings", GOLD),
        _stat("One-off sends", len(pending), "scheduled and waiting"),
    ]
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    st.write("")

    t_users, t_settings, t_send, t_sched, t_log = st.tabs(
        ["Users and roles", "Report schedule", "Preview and send", "One-off sends", "Email log"])

    # ── Users and roles ───────────────────────────────────────────────────────
    with t_users:
        with st.container(border=True):
            _heading("Team members", "Admins manage this page. Managers and Viewers see the dashboard. "
                                     "Tick Weekly or Monthly to receive those emails.")
            if bootstrap_admins:
                st.caption("Permanent admins (set in the app secrets): " + ", ".join(bootstrap_admins))
            if users:
                _table(users, {"name": "Name", "email": "Email", "role": "Role", "weekly": "Weekly email",
                               "monthly": "Monthly email", "active": "Active", "added_by": "Added by",
                               "added_at": "Added on"})
            else:
                st.info("No users yet. Add the first managers below.")

        with st.container(border=True):
            _heading("Add or edit a user")
            existing = {u["email"]: u for u in users}
            pick = st.selectbox("User", ["New user"] + sorted(existing), key="adm_pick",
                                format_func=lambda e: e if e == "New user" else
                                f"{existing[e].get('name') or e}  ({e})")
            u = existing.get(pick, {})
            with st.form("adm_user_form", clear_on_submit=False, border=False):
                c1, c2, c3 = st.columns([2, 2, 1])
                email = c1.text_input("Google email address", value=u.get("email", ""), disabled=bool(u))
                name = c2.text_input("Name", value=u.get("name", ""))
                role = c3.selectbox("Role", admin_store.ROLES,
                                    index=admin_store.ROLES.index(u.get("role", "Manager")) if u else 1)
                c4, c5, c6 = st.columns(3)
                weekly = c4.checkbox("Receives the weekly email", value=(u.get("weekly", "yes") == "yes") if u else True)
                monthly = c5.checkbox("Receives the monthly email",
                                      value=(u.get("monthly", "yes") == "yes") if u else True)
                active_ = c6.checkbox("Active", value=(u.get("active", "yes") == "yes") if u else True)
                if st.form_submit_button("Save user", type="primary"):
                    e = (u.get("email") or email).strip().lower()
                    if "@" not in e:
                        st.error("Enter a valid email address.")
                    else:
                        store.upsert_user(e, name or e, role, weekly, monthly, active_, me)
                        st.success(f"Saved {e} as {role}.")
                        st.rerun()
            if u and u["email"].lower() != me.lower():
                if st.button(f"Remove {u['email']}", key="adm_remove"):
                    store.remove_user(u["email"])
                    st.success(f"Removed {u['email']}.")
                    st.rerun()

    # ── Report schedule ───────────────────────────────────────────────────────
    with t_settings:
        s = settings
        with st.form("adm_settings", border=False):
            c_w, c_m = st.columns(2)
            with c_w.container(border=True):
                _heading("Weekly report", "Covers the last full Monday to Sunday week.")
                wk_on = st.toggle("Send the weekly report", value=s["weekly_enabled"] == "yes")
                day = st.selectbox("Day", report_jobs.DAYS, index=report_jobs.DAYS.index(s["send_day"]))
                tm = st.time_input("Time (Ghana)", value=_t(s["send_time"]), step=3600)
            with c_m.container(border=True):
                _heading("Monthly report", "Covers the previous calendar month.")
                mo_on = st.toggle("Send the monthly report", value=s["monthly_enabled"] == "yes")
                rules = {"first_weekday": "First weekday of the month", "day_of_month": "Fixed date"}
                rule = st.radio("Send on", list(rules), format_func=rules.get, horizontal=True,
                                index=list(rules).index(s["monthly_rule"]))
                c1, c2 = st.columns(2)
                m_day = c1.selectbox("Weekday", report_jobs.DAYS, index=report_jobs.DAYS.index(s["monthly_day"]),
                                     help="Used with 'First weekday of the month'.")
                m_date = c2.number_input("Date", min_value=1, max_value=28, value=int(s["monthly_date"]),
                                         help="Used with 'Fixed date' (1 to 28).")
                m_tm = st.time_input("Time (Ghana)", value=_t(s["monthly_time"]), step=3600, key="adm_m_time")

            with st.container(border=True):
                _heading("Email content")
                url = st.text_input("Dashboard link included in the emails", value=s.get("dashboard_url", ""))
            st.caption("Choose send times between 06:00 and 18:59.")
            if st.form_submit_button("Save schedule", type="primary"):
                if not (6 <= tm.hour <= 18 and 6 <= m_tm.hour <= 18):
                    st.error("Choose send times between 06:00 and 18:59.")
                else:
                    store.set_settings({"weekly_enabled": "yes" if wk_on else "no",
                                        "monthly_enabled": "yes" if mo_on else "no", "send_day": day,
                                        "send_time": tm.strftime("%H:%M"), "monthly_rule": rule,
                                        "monthly_day": m_day, "monthly_date": str(int(m_date)),
                                        "monthly_time": m_tm.strftime("%H:%M"), "dashboard_url": url.strip()})
                    when = f"the first {m_day}" if rule == "first_weekday" else f"day {int(m_date)}"
                    st.success(f"Saved. Weekly: {day}s at {tm:%H:%M}. Monthly: {when} of each month at {m_tm:%H:%M}.")

    # ── Preview and send ──────────────────────────────────────────────────────
    with t_send:
        with st.container(border=True):
            _heading("Choose a report")
            c1, c2 = st.columns([1, 2])
            kind = c1.radio("Report", ["weekly", "monthly"], horizontal=True, format_func=str.title, key="adm_kind")
            if kind == "weekly":
                period = c2.selectbox("Week", _week_options(d, now), key="adm_week", format_func=_week_label)
            else:
                period = c2.selectbox("Month", _month_options(now), key="adm_month", format_func=_month_label)
            recips = store.recipients(kind)
            st.caption(f"Recipients ({len(recips)}): " + (", ".join(recips) or "none yet"))
            if st.button("Build preview", key="adm_build"):
                with st.spinner("Building the report..."):
                    st.session_state["adm_parts"] = report_jobs.build(kind, d, period, store.get_settings())
            parts = st.session_state.get("adm_parts")
            if parts and parts["period"] == period:
                st.markdown(f"**Subject:** {parts['subject']}")
                st.download_button("Download the PDF", parts["pdf"], file_name=parts["pdf_name"],
                                   mime="application/pdf")
                with st.expander("Email preview"):
                    st.html(parts["html"])

        with st.container(border=True):
            _heading("Send now")
            if not smtp:
                st.warning("Email sending is not configured yet (add a [resend] section to the app secrets).")
            else:
                c1, c2 = st.columns(2)
                c1.caption("Send only to yourself to check it first.")
                if c1.button(f"Send a test to {me}", key="adm_test"):
                    with st.spinner("Sending..."):
                        try:
                            report_jobs.send(kind, d, store, smtp, period, recipients=[me],
                                             triggered_by=f"test by {me}")
                            st.success(f"Test sent to {me}.")
                        except Exception as e:
                            st.error(f"Send failed: {e}")
                confirm = c2.checkbox(f"I want to send this to all {len(recips)} recipients", key="adm_confirm")
                if c2.button("Send to all recipients", type="primary", disabled=not (confirm and recips),
                             key="adm_send_all"):
                    with st.spinner("Sending..."):
                        try:
                            report_jobs.send(kind, d, store, smtp, period, triggered_by=f"manual by {me}")
                            st.success(f"Sent to {len(recips)} recipients.")
                        except Exception as e:
                            st.error(f"Send failed: {e}")

    # ── One-off sends ─────────────────────────────────────────────────────────
    with t_sched:
        with st.container(border=True):
            _heading("Schedule a one-off send", "Sent once on the date and time you choose, in addition to the "
                                                "regular schedule, to everyone with that report switched on.")
            c1, c2 = st.columns([1, 2])
            s_kind = c1.radio("Report", ["weekly", "monthly"], horizontal=True, format_func=str.title, key="sch_kind")
            if s_kind == "weekly":
                s_period = c2.selectbox("Which week", _week_options(d, now), key="sch_week", format_func=_week_label)
            else:
                s_period = c2.selectbox("Which month", _month_options(now), key="sch_month",
                                        format_func=_month_label)
            c3, c4 = st.columns(2)
            s_date = c3.date_input("Date", value=now.date(), min_value=now.date(), key="sch_date")
            s_time = c4.time_input("Time (Ghana)", value=pd.Timestamp(2000, 1, 1, 9, 0).time(), step=3600,
                                   key="sch_time")
            when = pd.Timestamp.combine(s_date, s_time)
            if st.button("Schedule send", type="primary", key="sch_add"):
                if when < now.floor("h"):
                    st.error("Choose a time in the future.")
                else:
                    new_id = store.add_oneoff(s_kind, s_period, when.strftime("%Y-%m-%d %H:%M"), me)
                    st.success(f"Scheduled #{new_id}: the {s_kind} report for {_period_label(s_kind, s_period)} "
                               f"on {when:%a %d %b %Y at %H:%M}.")
                    pending = [r for r in store.list_oneoffs() if r["status"] == "pending"]
            st.caption("Goes out within the hour after the chosen time.")

        with st.container(border=True):
            _heading("Upcoming")
            if pending:
                _table([{**r, "period": _period_label(r["report"], r["period"]), "report": r["report"].title()}
                        for r in pending],
                       {"id": "#", "report": "Report", "period": "Period", "send_at": "Send at",
                        "created_by": "Scheduled by"})
                cancel = st.selectbox("Cancel a scheduled send", ["None"] + [
                    f"#{r['id']} {r['report'].title()} {_period_label(r['report'], r['period'])} at {r['send_at']}"
                    for r in pending], key="sch_cancel_pick")
                if cancel != "None" and st.button("Cancel this send", key="sch_cancel"):
                    store.set_oneoff_status(cancel.split()[0][1:], "cancelled", f"cancelled by {me}")
                    st.success(f"Cancelled {cancel.split()[0]}.")
                    st.rerun()
            else:
                st.caption("Nothing scheduled.")
            done = [r for r in oneoffs if r["status"] != "pending"]
            if done:
                with st.expander(f"Past one-off sends ({len(done)})"):
                    _table(done[::-1], {"id": "#", "report": "Report", "period": "Period", "send_at": "Send at",
                                        "status": "Status", "detail": "Detail"})

    # ── Email log ─────────────────────────────────────────────────────────────
    with t_log:
        with st.container(border=True):
            _heading("Email log", "Every report email sent, newest first.")
            log = store.list_log(200)
            if log:
                _table(log, {"timestamp": "Sent at", "report": "Report", "period": "Period",
                             "recipients": "Recipients", "status": "Status", "triggered_by": "Triggered by",
                             "detail": "Detail"})
            else:
                st.caption("No emails sent yet.")
