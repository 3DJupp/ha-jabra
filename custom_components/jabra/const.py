"""Constants for the Jabra integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "jabra"

# 16-bit member UUID assigned to GN Netcom (Jabra). Advertised by Jabra headsets.
GN_SERVICE_UUID: Final = "0000feff-0000-1000-8000-00805f9b34fb"

CONF_SERIAL: Final = "serial"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 15
MIN_SCAN_INTERVAL_MINUTES: Final = 5
MAX_SCAN_INTERVAL_MINUTES: Final = 24 * 60

# After a failed update, an advertisement from a Jabra headset may trigger an early refresh,
# but not more often than this.
ADVERTISEMENT_REFRESH_COOLDOWN: Final = timedelta(minutes=2)


def scan_interval(minutes: int | None) -> timedelta:
    """Return a clamped polling interval."""
    value = DEFAULT_SCAN_INTERVAL_MINUTES if minutes is None else int(minutes)
    value = max(MIN_SCAN_INTERVAL_MINUTES, min(MAX_SCAN_INTERVAL_MINUTES, value))
    return timedelta(minutes=value)
