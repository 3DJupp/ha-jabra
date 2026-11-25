"""Shared fixtures. Bluetooth is faked: no adapter, no D-Bus, no real headset."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant
import pytest

from custom_components.jabra.const import GN_SERVICE_UUID
from custom_components.jabra.gatt import HeadsetInfo

SERIAL = "08C8C2253931"
OTHER_SERIAL = "70BF92A0B1C2"
ADDRESS = "77:E6:29:5E:80:55"
ADDRESS_ROTATED = "5A:11:22:33:44:55"
OTHER_ADDRESS = "6B:00:00:00:00:01"
NAME = "Jabra Evolve2 85"

INFO = HeadsetInfo(
    serial=SERIAL,
    name=NAME,
    manufacturer="GN Audio A/S",
    firmware="1.5.7",
    hardware="01-67",
    battery=80,
)


def service_info(
    address: str = ADDRESS,
    name: str = NAME,
    uuids: list[str] | None = None,
    rssi: int = -60,
) -> BluetoothServiceInfoBleak:
    """A connectable advertisement like the one the Evolve2 85 sends."""
    uuids = [GN_SERVICE_UUID] if uuids is None else uuids
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=rssi,
        manufacturer_data={},
        service_data={},
        service_uuids=uuids,
        source="local",
        device=BLEDevice(address, name, None),
        advertisement=AdvertisementData(
            local_name=name,
            manufacturer_data={},
            service_data={},
            service_uuids=uuids,
            tx_power=None,
            rssi=rssi,
            platform_data=(),
        ),
        connectable=True,
        time=0.0,
        tx_power=None,
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture(autouse=True)
def fake_bluetooth(hass: HomeAssistant) -> Generator[MagicMock]:
    """Pretend the bluetooth integrations are loaded and stub callback registration."""
    hass.config.components.update({"bluetooth", "bluetooth_adapters"})
    with patch(
        "custom_components.jabra.bluetooth.async_register_callback",
        return_value=lambda: None,
    ) as register:
        yield register


@pytest.fixture
def discovered() -> Generator[list[BluetoothServiceInfoBleak]]:
    """Advertisements visible to Home Assistant; tests append to this list."""
    infos: list[BluetoothServiceInfoBleak] = [service_info()]
    with (
        patch(
            "custom_components.jabra.coordinator.bluetooth.async_discovered_service_info",
            side_effect=lambda *_a, **_k: list(infos),
        ),
        patch(
            "custom_components.jabra.config_flow.async_discovered_service_info",
            side_effect=lambda *_a, **_k: list(infos),
        ),
    ):
        yield infos


@pytest.fixture
def headsets() -> dict[str, Any]:
    """Map address -> HeadsetInfo or exception, used by the read_headset mock."""
    return {ADDRESS: INFO}


@pytest.fixture
def read_headset(headsets: dict[str, Any]) -> Generator[AsyncMock]:
    """Patch every connect-and-read with answers from ``headsets``."""

    async def _read(ble_device: BLEDevice, _name: str) -> HeadsetInfo:
        result = headsets.get(ble_device.address, TimeoutError("not reachable"))
        if isinstance(result, Exception):
            raise result
        return result

    mock = AsyncMock(side_effect=_read)
    with (
        patch("custom_components.jabra.coordinator.async_read_headset", mock),
        patch("custom_components.jabra.config_flow.async_read_headset", mock),
    ):
        yield mock
