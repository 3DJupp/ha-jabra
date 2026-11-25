"""The Jabra integration: battery and device information over Bluetooth LE."""

from __future__ import annotations

import time

from homeassistant.components import bluetooth
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .const import ADVERTISEMENT_REFRESH_COOLDOWN, GN_SERVICE_UUID
from .coordinator import JabraConfigEntry, JabraCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: JabraConfigEntry) -> bool:
    """Set up a Jabra headset from a config entry."""
    coordinator = JabraCoordinator(hass, entry)
    entry.runtime_data = coordinator
    # A headset that is off or out of range is normal; do not block setup on it.
    await coordinator.async_refresh()

    @callback
    def _on_advertisement(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Refresh early when a Jabra headset shows up after a failed update."""
        if coordinator.last_update_success:
            return
        if time.monotonic() - coordinator.last_attempt < ADVERTISEMENT_REFRESH_COOLDOWN.seconds:
            return
        coordinator.last_attempt = time.monotonic()
        entry.async_create_background_task(
            hass, coordinator.async_request_refresh(), "jabra_advertisement_refresh"
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _on_advertisement,
            bluetooth.BluetoothCallbackMatcher(service_uuid=GN_SERVICE_UUID, connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: JabraConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: JabraConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
