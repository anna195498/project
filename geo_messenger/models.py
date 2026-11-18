"""Typed data models shared by the application."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Contact:
    """A Telegram user connected to an owner as a notification contact."""

    id: int
    owner_id: int
    contact_telegram_id: int
    contact_name: str


@dataclass(frozen=True)
class Rule:
    """An active location-based notification rule."""

    id: int
    owner_id: int
    contact_id: int
    latitude: float
    longitude: float
    radius_m: int
    message_text: str
    is_inside: bool
    contact_telegram_id: int
