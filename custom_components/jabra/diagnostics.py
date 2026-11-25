"""Diagnostics for the Jabra integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_SERIAL
from .coordinator import JabraConfigEntry

TO_REDACT = {CONF_SERIAL, "serial", "address"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: JabraConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with serial number and address removed."""
    coordinator = entry.runtime_data
    data = asdict(coordinator.data) if coordinator.data else None
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "address": coordinator.address,
            "last_update_success": coordinator.last_update_success,
            "data": data,
        },
        TO_REDACT,
    )
