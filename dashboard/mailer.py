"""
Send report emails.

Provider is chosen by the config dict:
  * Resend (preferred):  {"provider": "resend", "api_key": ..., "from": "TribeCo Ghana Reports <reports@cowtribe.com>",
                          "reply_to": "optional@cowtribe.com"}
  * Gmail / Workspace SMTP (fallback): {"user": ..., "password": <app password>, "from_name": ...}
"""
import base64
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import requests

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_TEXT = "This report is best viewed in an email client that shows HTML. The PDF is attached."


def send(cfg, to, subject, html, attachments=(), text=None, idempotency_key=None):
    """attachments: iterable of (filename, bytes, mime). Returns the list of recipients sent to."""
    to = [t.strip() for t in to if t and t.strip()]
    if not to:
        raise ValueError("No recipients")
    if cfg.get("provider") == "resend":
        return _send_resend(cfg, to, subject, html, attachments, text, idempotency_key)
    return _send_smtp(cfg, to, subject, html, attachments, text)


def _send_resend(cfg, to, subject, html, attachments, text, idempotency_key):
    body = {
        "from": cfg["from"],
        "to": to,
        "subject": subject,
        "html": html,
        "text": text or DEFAULT_TEXT,
        "attachments": [{"filename": name, "content": base64.b64encode(data).decode("ascii")}
                        for name, data, _mime in attachments],
    }
    if cfg.get("reply_to"):
        body["reply_to"] = cfg["reply_to"]
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:256]   # Resend ignores repeats of the same key for 24h
    r = requests.post(RESEND_URL, json=body, headers=headers, timeout=60)
    if r.status_code >= 400:
        try:
            err = r.json()
            detail = f"{err.get('name', '')}: {err.get('message', r.text)}"
        except ValueError:
            detail = r.text[:300]
        raise RuntimeError(f"Resend {r.status_code} - {detail}")
    return to


def _send_smtp(cfg, to, subject, html, attachments, text):
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.get("from_name", "TribeCo Ghana Reports"), cfg["user"]))
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if cfg.get("reply_to"):
        msg["Reply-To"] = cfg["reply_to"]
    msg.set_content(text or DEFAULT_TEXT)
    msg.add_alternative(html, subtype="html")
    for name, data, mime in attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    host, port = cfg.get("host", "smtp.gmail.com"), int(cfg.get("port", 465))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=60) as s:
        s.login(cfg["user"], cfg["password"])
        s.send_message(msg)
    return to


def config_from(secrets):
    """Pick the email config from a secrets-shaped mapping: [resend] first, then [smtp]; None if neither."""
    rs = secrets.get("resend")
    if rs and rs.get("api_key"):
        return {"provider": "resend", "api_key": rs["api_key"],
                "from": rs.get("from", "TribeCo Ghana Reports <onboarding@resend.dev>"),
                "reply_to": rs.get("reply_to", "")}
    sm = secrets.get("smtp")
    if sm and sm.get("user"):
        return dict(sm)
    return None
