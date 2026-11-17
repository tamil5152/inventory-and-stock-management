import logging
import smtplib
import threading
from email.message import EmailMessage

from flask import current_app

from app.extensions import db
from app.models.alerts import Notification
from app.models.user import User

log = logging.getLogger(__name__)


class NotificationService:
    """In-app notifications, with optional e-mail when SMTP is configured."""

    @staticmethod
    def notify(user, title, message="", category="INFO", link=None, email=False):

        if user is None or not user.is_active_user:
            return None

        notification = Notification(
            user_id=user.id,
            category=category,
            title=title[:150],
            message=message,
            link=link,
        )
        db.session.add(notification)

        if email:
            NotificationService.send_email(user.email, title, message, link)

        return notification

    @staticmethod
    def notify_roles(roles, title, message="", category="INFO", link=None, exclude_user_id=None, email=False):

        users = User.query.filter(
            User.role.in_(roles),
            User.is_active_user.is_(True),
        ).all()

        return [
            NotificationService.notify(u, title, message, category, link, email)
            for u in users
            if u.id != exclude_user_id
        ]

    # -------------------------------------------------------------
    # E-mail (optional)
    # -------------------------------------------------------------

    @staticmethod
    def email_enabled():
        config = current_app.config
        return bool(config.get("MAIL_SERVER") and config.get("MAIL_FROM"))

    # Messages "sent" while TESTING are collected here so tests can inspect them.
    outbox = []

    @staticmethod
    def _build(to_address, subject, body, link=None):

        config = current_app.config
        base_url = config.get("APP_BASE_URL", "").rstrip("/")

        message = EmailMessage()
        message["Subject"] = f"[StockFlow] {subject}"
        message["From"] = config["MAIL_FROM"]
        message["To"] = to_address
        message.set_content(
            f"{body}\n\n"
            + (f"Open in StockFlow: {base_url}{link}\n" if link and base_url else "")
            + "\nThis is an automatic message from StockFlow."
        )
        return message

    @staticmethod
    def _settings():

        config = current_app.config
        return {
            "server": config["MAIL_SERVER"],
            "port": int(config.get("MAIL_PORT", 587)),
            "username": config.get("MAIL_USERNAME"),
            "password": config.get("MAIL_PASSWORD"),
            "use_tls": config.get("MAIL_USE_TLS", True),
        }

    @staticmethod
    def admin_address():
        return (current_app.config.get("ADMIN_EMAIL") or "").strip()

    @staticmethod
    def email_admin(subject, body, link=None):
        """Send a copy of an event to the admin mailbox (ADMIN_EMAIL)."""

        return NotificationService.send_email(NotificationService.admin_address(), subject, body, link)

    @staticmethod
    def send_email_now(to_address, subject, body):
        """Send synchronously and raise on failure (used for the test e-mail button)."""

        if not NotificationService.email_enabled():
            raise RuntimeError("E-mail is not set up. Add MAIL_SERVER and MAIL_FROM to the .env file and restart.")

        message = NotificationService._build(to_address, subject, body)

        if current_app.config.get("TESTING"):
            NotificationService.outbox.append(message)
            return True

        NotificationService._deliver(NotificationService._settings(), message, raise_errors=True)
        return True

    @staticmethod
    def send_email(to_address, subject, body, link=None):

        if not to_address or not NotificationService.email_enabled():
            return False

        message = NotificationService._build(to_address, subject, body, link)
        settings = NotificationService._settings()

        if current_app.config.get("TESTING"):
            NotificationService.outbox.append(message)
            return True

        # Send in the background so a slow mail server never blocks a request.
        threading.Thread(
            target=NotificationService._deliver, args=(settings, message), daemon=True
        ).start()

        return True

    @staticmethod
    def _deliver(settings, message, raise_errors=False):

        try:
            with smtplib.SMTP(settings["server"], settings["port"], timeout=15) as smtp:
                if settings["use_tls"]:
                    smtp.starttls()
                if settings["username"]:
                    smtp.login(settings["username"], settings["password"])
                smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as error:
            log.warning("E-mail login failed for %s: %s", settings["username"], error)
            if raise_errors:
                raise RuntimeError(
                    "Gmail rejected the login. Use a 16-character App Password in MAIL_PASSWORD, "
                    "not your normal Gmail password."
                ) from error
        except Exception as error:  # network dependent
            log.warning("E-mail to %s failed: %s", message["To"], error)
            if raise_errors:
                raise RuntimeError(f"Could not send e-mail: {error}") from error
