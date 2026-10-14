"""
Admin page: users and roles, report settings, preview / send reports, and the email log.
Rendered by app.py only for signed-in Admins.
"""
import pandas as pd
import streamlit as st

import admin_store
import monthly_report
import report_jobs
import weekly_report


def _week_options(d, now):
    return sorted(w for w in d["inv_scoped"]["Week"].dropna().unique()
                  if w <= weekly_report.last_completed_week(now))[-12:][::-1]


def _week_label(w):
    return f"{pd.Period(w, freq='W').start_time:%d %b} - {pd.Period(w, freq='W').end_time:%d %b %Y}"


def _month_options(now):
    return [str(p) for p in pd.period_range(f"{now.year}-01", monthly_report.previous_month(now), freq="M")][::-1]


def _month_label(m):
    return pd.Period(m, freq="M").strftime("%B %Y")


def render(store, me, bootstrap_admins, d, smtp):
    st.markdown("Manage who can sign in, who receives the management emails, and when they are sent.")
    t_users, t_settings, t_send, t_sched, t_log = st.tabs(["👥 Users & roles", "⚙️ Report settings",
                                                           "📧 Preview & send", "📅 Scheduled sends", "🧾 Email log"])

    # ── Users & roles ─────────────────────────────────────────────────────────
    with t_users:
        users = store.list_users()
        st.caption("Admins can open this page and manage users. Managers and Viewers can see the dashboard. "
                   "Tick Weekly / Monthly to receive those emails (all Managers get both by default).")
        if bootstrap_admins:
            st.info("Permanent admins (set in the app secrets, cannot be removed here): " + ", ".join(bootstrap_admins))
        if users:
            df = pd.DataFrame(users)[["email", "name", "role", "weekly", "monthly", "active", "added_by", "added_at"]]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("No users yet. Add the first Managers below.")

        st.markdown("**Add or update a user**")
        existing = {u["email"]: u for u in users}
        pick = st.selectbox("Edit an existing user, or choose 'New user'", ["New user"] + sorted(existing),
                            key="adm_pick")
        u = existing.get(pick, {})
        with st.form("adm_user_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            email = c1.text_input("Google email address", value=u.get("email", ""), disabled=bool(u))
            name = c2.text_input("Name", value=u.get("name", ""))
            c3, c4, c5, c6 = st.columns(4)
            role = c3.selectbox("Role", admin_store.ROLES,
                                index=admin_store.ROLES.index(u.get("role", "Manager")) if u else 1)
            default_mail = (u.get("weekly", "yes") == "yes") if u else True
            weekly = c4.checkbox("Weekly email", value=default_mail)
            monthly = c5.checkbox("Monthly email", value=(u.get("monthly", "yes") == "yes") if u else True)
            active = c6.checkbox("Active", value=(u.get("active", "yes") == "yes") if u else True)
            if st.form_submit_button("Save user", type="primary"):
                e = (u.get("email") or email).strip().lower()
                if "@" not in e:
                    st.error("Enter a valid email address.")
                else:
                    store.upsert_user(e, name or e, role, weekly, monthly, active, me)
                    st.success(f"Saved {e} as {role}.")
                    st.rerun()
        if u and u["email"].lower() != me.lower():
            if st.button(f"Remove {u['email']}", key="adm_remove"):
                store.remove_user(u["email"])
                st.success(f"Removed {u['email']}.")
                st.rerun()

    # ── Report settings ───────────────────────────────────────────────────────
    with t_settings:
        s = store.get_settings()
        with st.form("adm_settings"):
            c1, c2 = st.columns(2)
            wk_on = c1.checkbox("Send the weekly report", value=s["weekly_enabled"] == "yes")
            mo_on = c2.checkbox("Send the monthly report", value=s["monthly_enabled"] == "yes")
            c3, c4 = st.columns(2)
            day = c3.selectbox("Send day", report_jobs.DAYS, index=report_jobs.DAYS.index(s["send_day"]))
            hh, mm = (int(x) for x in s["send_time"].split(":"))
            tm = c4.time_input("Send time (Ghana time)", value=pd.Timestamp(2000, 1, 1, hh, mm).time(), step=3600)
            url = st.text_input("Dashboard link to include in the emails", value=s.get("dashboard_url", ""))
            st.caption("Weekly: sent on the send day, covering the last full Monday-Sunday week. "
                       "Monthly: sent on the first send day of each month, covering the previous month. "
                       "The scheduler checks every hour between 06:00 and 18:59, so choose a time in that window.")
            if st.form_submit_button("Save settings", type="primary"):
                if not 6 <= tm.hour <= 18:
                    st.error("Choose a send time between 06:00 and 18:59.")
                else:
                    store.set_settings({"weekly_enabled": "yes" if wk_on else "no",
                                        "monthly_enabled": "yes" if mo_on else "no", "send_day": day,
                                        "send_time": tm.strftime("%H:%M"), "dashboard_url": url.strip()})
                    st.success("Settings saved.")

    # ── Preview & send ────────────────────────────────────────────────────────
    with t_send:
        kind = st.radio("Report", ["weekly", "monthly"], horizontal=True, format_func=str.title, key="adm_kind")
        now = pd.Timestamp.now()
        if kind == "weekly":
            period = st.selectbox("Week", _week_options(d, now), key="adm_week", format_func=_week_label)
        else:
            period = st.selectbox("Month", _month_options(now), key="adm_month", format_func=_month_label)
        recips = store.recipients(kind)
        st.caption(f"Recipients for the {kind} report ({len(recips)}): " + (", ".join(recips) or "none yet"))

        if st.button("Build preview", key="adm_build"):
            with st.spinner("Building the report..."):
                st.session_state["adm_parts"] = report_jobs.build(kind, d, period, store.get_settings())
        parts = st.session_state.get("adm_parts")
        if parts and parts["period"] == period:
            st.markdown(f"**Subject:** {parts['subject']}")
            st.download_button("⬇ Download the PDF", parts["pdf"], file_name=parts["pdf_name"], mime="application/pdf")
            with st.expander("Email preview"):
                st.html(parts["html"])

        st.divider()
        if not smtp:
            st.warning("Email sending is not configured yet (add a [resend] section to the app secrets).")
        else:
            c1, c2 = st.columns(2)
            if c1.button(f"Send a test to me ({me})", key="adm_test"):
                with st.spinner("Sending..."):
                    try:
                        report_jobs.send(kind, d, store, smtp, period, recipients=[me], triggered_by=f"test by {me}")
                        st.success(f"Test sent to {me}.")
                    except Exception as e:
                        st.error(f"Send failed: {e}")
            confirm = c2.checkbox(f"I want to send this to all {len(recips)} recipients", key="adm_confirm")
            if c2.button("Send to all recipients now", disabled=not (confirm and recips), key="adm_send_all"):
                with st.spinner("Sending..."):
                    try:
                        report_jobs.send(kind, d, store, smtp, period, triggered_by=f"manual by {me}")
                        st.success(f"Sent to {len(recips)} recipients.")
                    except Exception as e:
                        st.error(f"Send failed: {e}")

    # ── Scheduled (one-off) sends ─────────────────────────────────────────────
    with t_sched:
        st.caption("Send a report once, on a date and time you choose, in addition to the regular schedule. "
                   "It goes to everyone with that report switched on (Users & roles).")
        now = pd.Timestamp.now(tz="Africa/Accra").tz_localize(None)
        c1, c2 = st.columns(2)
        s_kind = c1.radio("Report", ["weekly", "monthly"], horizontal=True, format_func=str.title, key="sch_kind")
        if s_kind == "weekly":
            s_period = c2.selectbox("Which week", _week_options(d, now), key="sch_week", format_func=_week_label)
        else:
            s_period = c2.selectbox("Which month", _month_options(now), key="sch_month", format_func=_month_label)
        c3, c4 = st.columns(2)
        s_date = c3.date_input("Send on (date)", value=now.date(), min_value=now.date(), key="sch_date")
        s_time = c4.time_input("At (Ghana time)", value=pd.Timestamp(2000, 1, 1, 9, 0).time(), step=3600,
                               key="sch_time")
        when = pd.Timestamp.combine(s_date, s_time)
        st.caption("Sends go out at the next hourly check after the chosen time (usually within the hour).")
        if st.button("📅 Schedule this send", type="primary", key="sch_add"):
            if when < now.floor("h"):
                st.error("Choose a time in the future.")
            else:
                new_id = store.add_oneoff(s_kind, s_period, when.strftime("%Y-%m-%d %H:%M"), me)
                st.success(f"Scheduled #{new_id}: the {s_kind} report for "
                           f"{_week_label(s_period) if s_kind == 'weekly' else _month_label(s_period)} "
                           f"on {when:%a %d %b %Y at %H:%M}.")

        rows = store.list_oneoffs()
        pending = [r for r in rows if r["status"] == "pending"]
        st.markdown("**Upcoming**")
        if pending:
            st.dataframe(pd.DataFrame(pending)[["id", "report", "period", "send_at", "created_by"]],
                         use_container_width=True, hide_index=True)
            cancel = st.selectbox("Cancel a scheduled send", ["—"] + [f"#{r['id']} {r['report']} {r['period']} "
                                                                    f"at {r['send_at']}" for r in pending],
                                  key="sch_cancel_pick")
            if cancel != "—" and st.button("Cancel it", key="sch_cancel"):
                store.set_oneoff_status(cancel.split()[0][1:], "cancelled", f"cancelled by {me}")
                st.success(f"Cancelled {cancel.split()[0]}.")
                st.rerun()
        else:
            st.info("Nothing scheduled.")
        done = [r for r in rows if r["status"] != "pending"]
        if done:
            with st.expander(f"Past scheduled sends ({len(done)})"):
                st.dataframe(pd.DataFrame(done[::-1])[["id", "report", "period", "send_at", "status", "detail"]],
                             use_container_width=True, hide_index=True)

    # ── Email log ─────────────────────────────────────────────────────────────
    with t_log:
        log = store.list_log(200)
        if log:
            st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True)
        else:
            st.info("No emails sent yet.")
