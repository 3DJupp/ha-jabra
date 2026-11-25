"""Base entity for Jabra headsets."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JabraCoordinator


class JabraEntity(CoordinatorEntity[JabraCoordinator]):
    """Shares the device info of one headset."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JabraCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.serial
        self._attr_unique_id = f"{serial}_{key}"
        info = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="Jabra",
            model=coordinator.config_entry.title,
            name=coordinator.config_entry.title,
            serial_number=serial,
            sw_version=info.firmware if info else None,
            hw_version=info.hardware if info else None,
        )
