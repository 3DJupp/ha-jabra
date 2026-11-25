"""Polling coordinator for one Jabra headset."""

from __future__ import annotations

import logging
import time

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, CONF_SERIAL, DOMAIN, scan_interval
from .device import CONNECT_ERRORS, async_read_headset, order_candidates
from .gatt import HeadsetInfo

_LOGGER = logging.getLogger(__name__)

type JabraConfigEntry = ConfigEntry[JabraCoordinator]


class JabraCoordinator(DataUpdateCoordinator[HeadsetInfo]):
    """Finds the configured headset by serial number and reads it periodically."""

    config_entry: JabraConfigEntry

    def __init__(self, hass: HomeAssistant, entry: JabraConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=scan_interval(entry.options.get(CONF_SCAN_INTERVAL)),
        )
        self.serial: str = entry.data[CONF_SERIAL]
        self.address: str | None = None
        # Addresses that answered with another serial number (other Jabra devices).
        self._foreign: dict[str, str] = {}
        self.last_attempt: float = 0.0

    async def _async_update_data(self) -> HeadsetInfo:
        self.last_attempt = time.monotonic()
        infos = bluetooth.async_discovered_service_info(self.hass, connectable=True)
        visible = {info.address for info in infos}
        # Forget foreign addresses that are no longer advertised (private addresses rotate).
        self._foreign = {a: s for a, s in self._foreign.items() if a in visible}

        for info in order_candidates(infos, self.address, set(self._foreign)):
            try:
                result = await async_read_headset(info.device, info.name or self.serial)
            except CONNECT_ERRORS as err:
                _LOGGER.debug("Could not read %s: %s", info.address, err)
                continue
            if result.serial == self.serial:
                self.address = info.address
                self._update_device_registry(result)
                return result
            if result.serial:
                self._foreign[info.address] = result.serial
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="headset_unreachable",
        )

    def _update_device_registry(self, info: HeadsetInfo) -> None:
        """Keep firmware and hardware versions of the device entry current."""
        registry = dr.async_get(self.hass)
        # async_entries_for_config_entry works on all supported HA versions; the identifier
        # lookups changed in 2026.x.
        device = next(
            (
                d
                for d in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id)
                if (DOMAIN, self.serial) in d.identifiers
            ),
            None,
        )
        if device is None:
            return
        if device.sw_version != info.firmware or device.hw_version != info.hardware:
            registry.async_update_device(
                device.id, sw_version=info.firmware, hw_version=info.hardware
            )
