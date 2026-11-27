import os
import smtplib
from email.message import EmailMessage
from email.utils import formatdate


def smtp_configured():
    return bool(os.environ.get("SMTP_HOST"))


def send(destinataire, sujet, contenu):
    """Envoie un e-mail. Retourne True si envoyé réellement (SMTP), False si simulé.

    Config via variables d'environnement : SMTP_HOST, SMTP_PORT (587),
    SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS (starttls si absent = "0").
    """
    if not smtp_configured():
        return False
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", "noreply@lcp.fr")
    msg["To"] = destinataire
    msg["Subject"] = sujet
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(contenu)
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    use_tls = os.environ.get("SMTP_TLS", "1") != "0"
    with smtplib.SMTP(host, port, timeout=15) as srv:
        if use_tls:
            srv.starttls()
        if user:
            srv.login(user, password)
        srv.send_message(msg)
    return True
