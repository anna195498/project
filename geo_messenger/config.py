"""Application configuration loaded from environment variables."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime settings required by the bot."""

    bot_token: str
    database_path: str
    database_url: str | None
    vercel_runtime: bool
    use_webhook: bool
    webhook_url: str | None
    webhook_path: str
    webhook_secret: str | None
    webhook_cert_file: str | None
    webhook_key_file: str | None
    webhook_host: str
    webhook_port: int


def get_settings() -> Settings:
    """Load and validate settings from the environment."""
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is required; set it in geo_messenger/.env")
    webhook_value = os.getenv("USE_WEBHOOK", "false").strip().lower()
    if webhook_value not in {"true", "false"}:
        raise ValueError("USE_WEBHOOK must be either true or false")
    use_webhook = webhook_value == "true"
    database_path = os.getenv(
        "DATABASE_PATH", str(PROJECT_DIR / "geo_messenger.sqlite3")
    )
    database_url = os.getenv("DATABASE_URL", "").strip() or None
    vercel_runtime = os.getenv("VERCEL", "").strip().lower() in {"1", "true"}
    webhook_url = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
    webhook_path = os.getenv("WEBHOOK_PATH", "/telegram").strip()
    webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    webhook_cert_file = os.getenv("WEBHOOK_CERT_FILE", "").strip()
    webhook_key_file = os.getenv("WEBHOOK_KEY_FILE", "").strip()
    webhook_host = os.getenv("WEBHOOK_HOST", "0.0.0.0").strip()
    try:
        webhook_port = int(os.getenv("WEBHOOK_PORT", "443"))
    except ValueError as error:
        raise ValueError("WEBHOOK_PORT must be an integer") from error

    if vercel_runtime:
        if not use_webhook:
            raise ValueError("USE_WEBHOOK=true is required on Vercel")
        if not database_url:
            raise ValueError("DATABASE_URL is required for Vercel deployments")

    if use_webhook:
        parsed_url = urlsplit(webhook_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("WEBHOOK_URL must be an HTTPS URL, for example https://bot.example")
        if parsed_url.username or parsed_url.password:
            raise ValueError("WEBHOOK_URL must not contain credentials")
        try:
            webhook_url_port = parsed_url.port
        except ValueError as error:
            raise ValueError("WEBHOOK_URL contains an invalid port") from error
        if webhook_url_port not in {None, 443}:
            raise ValueError("WEBHOOK_URL must use HTTPS on port 443")
        if parsed_url.path not in {"", "/"} or parsed_url.query or parsed_url.fragment:
            raise ValueError("WEBHOOK_URL must be an HTTPS origin without a path or query")
        if (
            not webhook_path.startswith("/")
            or "?" in webhook_path
            or "#" in webhook_path
        ):
            raise ValueError("WEBHOOK_PATH must be an absolute URL path")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", webhook_secret):
            raise ValueError(
                "WEBHOOK_SECRET must contain 1-256 letters, digits, underscores, or hyphens"
            )
        if not vercel_runtime and (not webhook_cert_file or not webhook_key_file):
            raise ValueError(
                "WEBHOOK_CERT_FILE and WEBHOOK_KEY_FILE are required when USE_WEBHOOK=true"
            )
        if not vercel_runtime and (not webhook_host or not 1 <= webhook_port <= 65535):
            raise ValueError("WEBHOOK_HOST and a valid WEBHOOK_PORT are required")
        if vercel_runtime and webhook_path != "/api/webhook":
            raise ValueError("On Vercel, WEBHOOK_PATH must be /api/webhook")
    return Settings(
        bot_token=bot_token,
        database_path=database_path,
        database_url=database_url,
        vercel_runtime=vercel_runtime,
        use_webhook=use_webhook,
        webhook_url=webhook_url or None,
        webhook_path=webhook_path,
        webhook_secret=webhook_secret or None,
        webhook_cert_file=webhook_cert_file or None,
        webhook_key_file=webhook_key_file or None,
        webhook_host=webhook_host,
        webhook_port=webhook_port,
    )
