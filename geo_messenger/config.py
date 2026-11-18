"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime settings required by the bot."""

    bot_token: str
    database_path: str


def get_settings() -> Settings:
    """Load and validate settings from the environment."""
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is required; set it in geo_messenger/.env")
    database_path = os.getenv(
        "DATABASE_PATH", str(PROJECT_DIR / "geo_messenger.sqlite3")
    )
    return Settings(bot_token=bot_token, database_path=database_path)
