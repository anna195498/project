"""Abstractions for obtaining user location samples."""

from abc import ABC, abstractmethod


class LocationProvider(ABC):
    """Interface for sources that provide a user's most recent position."""

    @abstractmethod
    async def get_location(self, user_id: int) -> tuple[float, float] | None:
        """Return the most recent latitude and longitude, if available."""
        raise NotImplementedError


class TelegramLiveLocationProvider(LocationProvider):
    """Store location samples pushed by Telegram location updates."""

    def __init__(self) -> None:
        """Initialize an in-memory cache for received Telegram positions."""
        self._locations: dict[int, tuple[float, float]] = {}

    async def update_location(
        self, user_id: int, latitude: float, longitude: float
    ) -> None:
        """Cache a location received from a Telegram update."""
        self._locations[user_id] = (latitude, longitude)

    async def get_location(self, user_id: int) -> tuple[float, float] | None:
        """Return the most recently received Telegram position."""
        return self._locations.get(user_id)

    # TODO: Add Google Maps as an alternative location provider.
    # TODO: Add 2GIS as an alternative location provider.
