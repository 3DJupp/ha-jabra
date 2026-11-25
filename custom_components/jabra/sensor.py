"""Sensors for Jabra headsets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import JabraConfigEntry, JabraCoordinator
from .entity import JabraEntity
from .gatt import HeadsetInfo


@dataclass(frozen=True, kw_only=True)
class JabraSensorDescription(SensorEntityDescription):
    """Describes a Jabra sensor."""

    value_fn: Callable[[HeadsetInfo], str | int | None]


SENSORS: tuple[JabraSensorDescription, ...] = (
    JabraSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda info: info.battery,
    ),
    JabraSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda info: info.firmware,
    ),
    JabraSensorDescription(
        key="hardware",
        translation_key="hardware",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda info: info.hardware,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JabraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Jabra sensors."""
    coordinator = entry.runtime_data
    async_add_entities(JabraSensor(coordinator, description) for description in SENSORS)


class JabraSensor(JabraEntity, SensorEntity):
    """A value read from the headset."""

    entity_description: JabraSensorDescription

    def __init__(self, coordinator: JabraCoordinator, description: JabraSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | None:
        data = self.coordinator.data
        return None if data is None else self.entity_description.value_fn(data)
