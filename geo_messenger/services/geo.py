"""Geospatial calculations and rule transition handling."""

import logging
import math

from aiogram import Bot

from db.repository import (
    get_active_rules,
    get_user_name,
    update_rule_inside_if_changed,
)
from services.notifier import send_notification

logger = logging.getLogger(__name__)
EARTH_RADIUS_M = 6_371_000


def calculate_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between coordinates in meters."""
    if not all(math.isfinite(value) for value in (lat1, lon1, lat2, lon2)):
        raise ValueError("Coordinates must be finite numbers")
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("Latitude must be between -90 and 90 degrees")
    if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("Longitude must be between -180 and 180 degrees")

    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    arc = 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
    return EARTH_RADIUS_M * arc


def is_inside_radius(
    lat: float,
    lon: float,
    target_lat: float,
    target_lon: float,
    radius_m: float,
) -> bool:
    """Return whether a coordinate lies within a radius of the target."""
    if radius_m <= 0:
        raise ValueError("Radius must be greater than zero")
    return calculate_distance_m(lat, lon, target_lat, target_lon) <= radius_m


async def check_rules_for_location(
    user_id: int, lat: float, lon: float, bot: Bot
) -> None:
    """Send notifications on outside-to-inside transitions for active rules."""
    rules = await get_active_rules(user_id)
    owner_name = await get_user_name(user_id)
    if owner_name is None:
        logger.warning("Location received for an unregistered account")
        return

    for rule in rules:
        if rule.owner_id != user_id:
            logger.error("Skipped a rule with mismatched owner")
            continue
        try:
            inside = is_inside_radius(
                lat, lon, rule.latitude, rule.longitude, rule.radius_m
            )
        except ValueError:
            logger.exception("Invalid geospatial data in an active rule")
            raise
        if inside == rule.is_inside:
            continue
        updated = await update_rule_inside_if_changed(
            rule.id,
            owner_id=user_id,
            expected_inside=rule.is_inside,
            new_inside=inside,
        )
        if updated and inside:
            await send_notification(
                bot,
                rule.contact_telegram_id,
                owner_name,
                rule.message_text,
                owner_telegram_id=user_id,
            )
