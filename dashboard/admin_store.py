"""
Admin settings store: users and roles, report settings, and the email log.

Two backends with the same interface:
  * GoogleSheetStore - a Google Sheet shared with a service account (production; survives restarts
    on Streamlit Cloud and is readable by the scheduled email job).
  * LocalStore - a JSON file (local development and testing).
open_store(cfg) picks the sheet when [admin_store] sheet_id and [gcp_service_account] are configured.
"""
import json
import os
from datetime import datetime, timezone

ROLES = ["Admin", "Manager", "Viewer"]
USER_COLS = ["email", "name", "role", "weekly", "monthly", "active", "added_by", "added_at"]
LOG_COLS = ["timestamp", "report", "period", "recipients", "status", "detail", "triggered_by"]
DEFAULT_SETTINGS = {
    "weekly_enabled": "yes", "monthly_enabled": "yes",
    "send_day": "Friday", "send_time": "09:00", "timezone": "Africa/Accra",
    "dashboard_url": "",
}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm(email):
    return (email or "").strip().lower()


def _yes(v):
    return str(v).strip().lower() in ("yes", "true", "1", "y")


class _Base:
    # ── users ────────────────────────────────────────────────────────────────
    def get_user(self, email):
        e = _norm(email)
        return next((u for u in self.list_users() if _norm(u["email"]) == e), None)

    def role_for(self, email, bootstrap_admins=()):
        """Role of a signed-in user, or None if they are not on the list. Bootstrap admins (from secrets)
        are always Admin so the first admin can sign in before anyone has been added."""
        e = _norm(email)
        if e in {_norm(a) for a in bootstrap_admins}:
            return "Admin"
        u = self.get_user(e)
        return u["role"] if u and _yes(u.get("active", "yes")) else None

    def recipients(self, report):
        """Active users with the flag for this report ('weekly' or 'monthly') switched on."""
        return [u["email"] for u in self.list_users() if _yes(u.get("active")) and _yes(u.get(report))]

    def upsert_user(self, email, name, role, weekly, monthly, active, by):
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        users = self.list_users()
        e = _norm(email)
        row = {"email": e, "name": name.strip(), "role": role, "weekly": "yes" if weekly else "no",
               "monthly": "yes" if monthly else "no", "active": "yes" if active else "no",
               "added_by": by, "added_at": _now()}
        for i, u in enumerate(users):
            if _norm(u["email"]) == e:
                row["added_at"] = u.get("added_at") or row["added_at"]
                users[i] = row
                break
        else:
            users.append(row)
        self._save_users(users)

    def remove_user(self, email):
        self._save_users([u for u in self.list_users() if _norm(u["email"]) != _norm(email)])

    # ── settings / log ───────────────────────────────────────────────────────
    def get_settings(self):
        s = dict(DEFAULT_SETTINGS)
        s.update({k: v for k, v in self._load_settings().items() if v not in (None, "")})
        return s

    def log(self, report, period, recipients, status, detail="", triggered_by="schedule"):
        self._append_log({"timestamp": _now(), "report": report, "period": period,
                          "recipients": ", ".join(recipients), "status": status,
                          "detail": str(detail)[:500], "triggered_by": triggered_by})

    def already_sent(self, report, period):
        return any(l["report"] == report and l["period"] == period and l["status"] == "sent"
                   and l.get("triggered_by") == "schedule" for l in self.list_log(500))


class LocalStore(_Base):
    def __init__(self, path):
        self.path = path

    def _read(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        return {"users": [], "settings": {}, "log": []}

    def _write(self, d):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)

    def list_users(self):
        return self._read()["users"]

    def _save_users(self, users):
        d = self._read(); d["users"] = users; self._write(d)

    def _load_settings(self):
        return self._read()["settings"]

    def set_settings(self, s):
        d = self._read(); d["settings"] = {**d["settings"], **s}; self._write(d)

    def _append_log(self, row):
        d = self._read(); d["log"].append(row); d["log"] = d["log"][-1000:]; self._write(d)

    def list_log(self, n=100):
        return list(reversed(self._read()["log"]))[:n]


class GoogleSheetStore(_Base):
    """Tabs: Users, Settings (key/value), EmailLog. Created on first use."""

    def __init__(self, sheet_id, service_account_info):
        import gspread
        gc = gspread.service_account_from_dict(dict(service_account_info))
        self.sh = gc.open_by_key(sheet_id)

    def _tab(self, name, header):
        import gspread
        try:
            ws = self.sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=name, rows=200, cols=len(header))
            ws.append_row(header)
        return ws

    def list_users(self):
        return [{c: str(r.get(c, "")) for c in USER_COLS} for r in self._tab("Users", USER_COLS).get_all_records()]

    def _save_users(self, users):
        ws = self._tab("Users", USER_COLS)
        ws.clear()
        ws.update([USER_COLS] + [[u.get(c, "") for c in USER_COLS] for u in users])

    def _load_settings(self):
        return {r["key"]: str(r["value"]) for r in self._tab("Settings", ["key", "value"]).get_all_records()}

    def set_settings(self, s):
        cur = {**self._load_settings(), **{k: str(v) for k, v in s.items()}}
        ws = self._tab("Settings", ["key", "value"])
        ws.clear()
        ws.update([["key", "value"]] + [[k, v] for k, v in cur.items()])

    def _append_log(self, row):
        self._tab("EmailLog", LOG_COLS).append_row([row[c] for c in LOG_COLS])

    def list_log(self, n=100):
        rows = self._tab("EmailLog", LOG_COLS).get_all_records()
        return [{c: str(r.get(c, "")) for c in LOG_COLS} for r in reversed(rows)][:n]


def open_store(cfg, local_path):
    """cfg: mapping with optional [admin_store].sheet_id and [gcp_service_account] (secrets-shaped)."""
    sheet = (cfg.get("admin_store") or {}).get("sheet_id")
    sa = cfg.get("gcp_service_account")
    if sheet and sa:
        return GoogleSheetStore(sheet, sa)
    return LocalStore(local_path)
