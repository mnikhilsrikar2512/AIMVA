"""Gmail SMTP sender. Without SMTP credentials it logs the email to the console (dev mode)."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("aimva.mail")


def _html(title: str, code: str, note: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#0b1020;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:40px 16px">
<table width="480" cellpadding="0" cellspacing="0" style="background:#121a33;border-radius:16px;padding:32px;color:#e6e9f5">
<tr><td style="font-size:20px;font-weight:bold;color:#fff">AIMVA</td></tr>
<tr><td style="padding-top:20px;font-size:16px">{title}</td></tr>
<tr><td style="padding:24px 0;font-size:36px;letter-spacing:10px;font-weight:bold;color:#7dd3fc">{code}</td></tr>
<tr><td style="font-size:13px;color:#9aa3c0">{note}</td></tr>
</table></td></tr></table></body></html>"""


def send_code_email(to: str, name: str, code: str, purpose: str) -> None:
    if purpose == "verify":
        subject = f"{code} is your AIMVA verification code"
        title = f"Hi {name}, use this code to verify your email:"
    else:
        subject = f"{code} is your AIMVA password reset code"
        title = f"Hi {name}, use this code to reset your password:"
    note = "The code expires in 10 minutes. If you didn't request it, you can ignore this email."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"AIMVA <{settings.mail_from}>" if settings.mail_from else "AIMVA"
    msg["To"] = to
    msg.set_content(f"{title}\n\n{code}\n\n{note}")
    msg.add_alternative(_html(title, code, note), subtype="html")

    if not settings.smtp_configured:
        log.warning("SMTP not configured - email to %s | %s", to, subject)
        print(f"\n[DEV MAIL] to={to} purpose={purpose} code={code}\n", flush=True)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def send_email(to: str, subject: str, text: str, html: str = "") -> bool:
    """Any other email (weekly reports, agent summaries). Returns False when SMTP isn't set up (logged instead).
    Mail for a client workspace goes to its people (owner, admins, client), never to its placeholder address."""
    if to.endswith("@workspaces.aimva.invalid"):
        from sqlalchemy import select

        from .db import SessionLocal
        from .models import User
        from .workspaces import member_emails
        with SessionLocal() as db:
            ws = db.scalar(select(User).where(User.email == to))
            people = member_emails(db, ws) if ws else []
        return any([send_email(p, subject, text, html) for p in people])
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"AIMVA <{settings.mail_from}>" if settings.mail_from else "AIMVA"
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    if not settings.smtp_configured:
        log.warning("SMTP not configured - email to %s | %s", to, subject)
        return False
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException):
        log.exception("Couldn't send email to %s", to)
        return False
    return True
