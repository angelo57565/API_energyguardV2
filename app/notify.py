"""Envio de avisos por Telegram e/ou e-mail (so usa biblioteca padrao)."""
import json
import logging
import smtplib
import urllib.request
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("energyguard")


def telegram_configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.alert_email_to)


def send_telegram(text: str) -> bool:
    s = get_settings()
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    data = json.dumps({"chat_id": s.telegram_chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status == 200


def send_email(text: str) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"] = "EnergyGuard: alerta"
    msg["From"] = s.smtp_user or s.alert_email_to
    msg["To"] = s.alert_email_to
    msg.set_content(text)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
    return True


def notify(text: str) -> bool:
    """Tenta todos os canais configurados. True se pelo menos um enviou."""
    ok = False
    if telegram_configured():
        try:
            ok = send_telegram(text) or ok
        except Exception:
            log.exception("Falha ao enviar Telegram")
    if email_configured():
        try:
            ok = send_email(text) or ok
        except Exception:
            log.exception("Falha ao enviar e-mail")
    return ok
