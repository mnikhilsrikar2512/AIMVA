"""Settings loaded from backend/.env (see .env.example)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _secret_key() -> str:
    """Use SECRET_KEY from .env, else generate one once and persist it in data/."""
    key = _env("SECRET_KEY")
    if key:
        if len(key) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters (or leave it empty to auto-generate).")
        return key
    path = BASE_DIR / "data" / ".secret_key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


def _database_url() -> str:
    """DATABASE_URL, with the postgres:// form most hosts hand out mapped to the psycopg 3 driver."""
    url = _env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'aimva.db'}")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    app_name = "AIMVA"
    # development (default) or production. Production refuses to start with unsafe settings (see problems()).
    environment = _env("ENVIRONMENT", "development").lower()
    secret_key = _secret_key()
    database_url = _database_url()
    db_pool_size = int(_env("DB_POOL_SIZE", "10"))
    db_max_overflow = int(_env("DB_MAX_OVERFLOW", "10"))
    # Error tracking (https://sentry.io or any Sentry-compatible service such as GlitchTip). Empty = off.
    sentry_dsn = _env("SENTRY_DSN")
    release = _env("RELEASE") or _env("GIT_SHA")
    # Logs: "text" for reading in a terminal, "json" for a log service. LOG_LEVEL is DEBUG / INFO / WARNING.
    log_format = _env("LOG_FORMAT", "text").lower()
    log_level = _env("LOG_LEVEL", "INFO").upper()
    public_url = _env("PUBLIC_URL", "http://localhost:8000")
    # User-added AI providers may point at local/private addresses (Ollama, ComfyUI on your LAN).
    # Safe on a personal machine; keep it false on a shared/public server to prevent SSRF.
    allow_private_providers = _env(
        "ALLOW_PRIVATE_PROVIDERS", "true" if "localhost" in _env("PUBLIC_URL", "http://localhost:8000") else "false"
    ).lower() == "true"
    frontend_url = _env("FRONTEND_URL", "http://localhost:5173")
    cookie_secure = _env("COOKIE_SECURE", "false").lower() == "true"
    session_days = int(_env("SESSION_DAYS", "7"))
    # Owners who can see platform-wide quality and usage metrics (comma-separated emails).
    admin_emails = {e.strip().lower() for e in _env("ADMIN_EMAILS").split(",") if e.strip()}

    # Email (Gmail SMTP with an App Password)
    smtp_host = _env("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(_env("SMTP_PORT", "587"))
    smtp_user = _env("SMTP_USER")
    smtp_password = _env("SMTP_PASSWORD")
    mail_from = _env("MAIL_FROM") or _env("SMTP_USER")

    # AI providers
    gemini_api_key = _env("GEMINI_API_KEY")
    gemini_model = _env("GEMINI_MODEL", "gemini-2.5-flash")
    fal_key = _env("FAL_KEY")
    # Optional Pollinations key: the keyless free tier allows ~1 image / 45 s per server IP, shared by every user.
    pollinations_token = _env("POLLINATIONS_TOKEN")
    # AIMVA free AI: keyless text generation (Pollinations, open source) used when no key is set up. Shared by the
    # whole server (about 1 reply / 30 s without POLLINATIONS_TOKEN), so agents also remember answers and fall back to rules.
    free_ai = _env("FREE_AI", "true").lower() == "true"
    # Work agents (app/agents): the background scheduler for follow-ups, Autopilot and weekly reports
    agents_scheduler = _env("AGENTS_SCHEDULER", "true").lower() == "true"
    tz_offset_minutes = int(_env("TZ_OFFSET_MINUTES", "330") or 0)  # business time zone for "9 am" / "Monday" (default IST)

    # OAuth apps (connect later)
    meta_app_id = _env("META_APP_ID")
    meta_app_secret = _env("META_APP_SECRET")
    google_client_id = _env("GOOGLE_CLIENT_ID")
    google_client_secret = _env("GOOGLE_CLIENT_SECRET")
    google_ads_developer_token = _env("GOOGLE_ADS_DEVELOPER_TOKEN")
    linkedin_client_id = _env("LINKEDIN_CLIENT_ID")
    linkedin_client_secret = _env("LINKEDIN_CLIENT_SECRET")
    microsoft_client_id = _env("MICROSOFT_CLIENT_ID")
    microsoft_client_secret = _env("MICROSOFT_CLIENT_SECRET")

    # WhatsApp Cloud API
    whatsapp_verify_token = _env("WHATSAPP_VERIFY_TOKEN", "aimva-verify")

    # Voice (Twilio for real phone calls)
    twilio_account_sid = _env("TWILIO_ACCOUNT_SID")
    twilio_auth_token = _env("TWILIO_AUTH_TOKEN")
    twilio_from_number = _env("TWILIO_FROM_NUMBER")

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def problems(self) -> list[str]:
        """Settings that are fine on a laptop but unsafe on a public server. Production won't start with any of these."""
        out = []
        if not _env("SECRET_KEY"):
            out.append("SECRET_KEY is empty: set a long random value (python -c 'import secrets; print(secrets.token_urlsafe(48))')")
        if self.database_url.startswith("sqlite"):
            out.append("DATABASE_URL points at SQLite: use Postgres (postgresql://user:pass@host/db)")
        if not self.public_url.startswith("https://"):
            out.append("PUBLIC_URL must start with https://")
        if not self.cookie_secure:
            out.append("COOKIE_SECURE must be true so the session cookie is only sent over HTTPS")
        if self.allow_private_providers:
            out.append("ALLOW_PRIVATE_PROVIDERS must be false on a public server (it lets users reach your private network)")
        if not self.meta_app_secret:
            out.append("META_APP_SECRET is empty: every WhatsApp webhook would be rejected")
        if self.whatsapp_verify_token in ("", "aimva-verify"):
            out.append("WHATSAPP_VERIFY_TOKEN is the public default: set your own random value")
        if not self.smtp_configured:
            out.append("SMTP_USER / SMTP_PASSWORD are empty: verification codes would only be printed in the log")
        return out


settings = Settings()
