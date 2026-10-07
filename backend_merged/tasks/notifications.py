import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from celery_app import celery_app
from config import settings


@celery_app.task
def send_email_notification(to_email: str, subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
        else:
            print(f"[EMAIL MOCK] To: {to_email} | Subject: {subject}")
            print(f"[EMAIL MOCK] Body: {body}")

        return {"status": "sent", "to": to_email}
    except Exception as e:
        print(f"Email error: {e}")
        return {"status": "failed", "error": str(e)}


def send_email(to_email: str, subject: str, body: str) -> str:
    """Use Celery if it's turned on, otherwise send right away.

    Without SMTP settings, the email is printed in the terminal as [EMAIL MOCK].
    """
    if settings.USE_CELERY:
        try:
            send_email_notification.delay(to_email, subject, body)
            return "queued"
        except Exception as exc:
            print(f"Celery/Redis not available, sending directly: {exc}")

    result = send_email_notification(to_email, subject, body)
    return result.get("status", "sent")