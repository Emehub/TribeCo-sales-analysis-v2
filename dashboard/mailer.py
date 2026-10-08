"""Send report emails through Gmail / Google Workspace SMTP (app password)."""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


def send(smtp, to, subject, html, attachments=(), text=None):
    """smtp: dict(user, password, from_name, host='smtp.gmail.com', port=465).
    attachments: iterable of (filename, bytes, mime 'type/subtype')."""
    to = [t.strip() for t in to if t and t.strip()]
    if not to:
        raise ValueError("No recipients")
    msg = EmailMessage()
    msg["From"] = formataddr((smtp.get("from_name", "TribeCo Ghana Reports"), smtp["user"]))
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(text or "This report is best viewed in an email client that shows HTML. The PDF is attached.")
    msg.add_alternative(html, subtype="html")
    for name, data, mime in attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    host, port = smtp.get("host", "smtp.gmail.com"), int(smtp.get("port", 465))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=60) as s:
        s.login(smtp["user"], smtp["password"])
        s.send_message(msg)
    return to
