import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


class Config:

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "development-secret-change-before-deployment"
    )

    # Default: SQLite file in ./instance/inventory.db
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'instance' / 'inventory.db').as_posix()}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = (
        {"connect_args": {"timeout": 20}}
        if SQLALCHEMY_DATABASE_URI.startswith("sqlite")
        else {"pool_pre_ping": True}
    )

    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv(
        "COOKIE_SECURE", "False"
    ).lower() == "true"

    WTF_CSRF_TIME_LIMIT = None

    # Stock-check alerts
    ALERT_SCHEDULER = os.getenv("ALERT_SCHEDULER", "True").lower() == "true"
    ALERT_INTERVAL_MINUTES = int(os.getenv("ALERT_INTERVAL_MINUTES", "60"))
    ALERT_MAX_TASKS_PER_RUN = int(os.getenv("ALERT_MAX_TASKS_PER_RUN", "25"))

    # Optional e-mail notifications (leave MAIL_SERVER empty to disable)
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_FROM = os.getenv("MAIL_FROM", "")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000")


class TestConfig(Config):

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    ALERT_SCHEDULER = False
    MAIL_SERVER = ""
    SECRET_KEY = "test-secret"
