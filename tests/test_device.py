"""Connect/read/disconnect and candidate ordering."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
import pytest

from custom_components.jabra import device, gatt

from .conftest import ADDRESS, ADDRESS_ROTATED, OTHER_ADDRESS, service_info


def test_is_jabra() -> None:
    assert device.is_jabra(service_info())
    assert not device.is_jabra(service_info(uuids=["0000180f-0000-1000-8000-00805f9b34fb"]))


def test_order_candidates_prefers_known_address_then_rssi() -> None:
    infos = [
        service_info(OTHER_ADDRESS, rssi=-40),
        service_info(ADDRESS_ROTATED, rssi=-80),
        service_info(ADDRESS, rssi=-90),
        service_info("11:11:11:11:11:11", uuids=[], rssi=-10),
    ]
    ordered = device.order_candidates(infos, ADDRESS, set())
    assert [i.address for i in ordered] == [ADDRESS, OTHER_ADDRESS, ADDRESS_ROTATED]
    ordered = device.order_candidates(infos, None, {OTHER_ADDRESS})
    assert [i.address for i in ordered] == [ADDRESS_ROTATED, ADDRESS]


def _client(values: dict[str, bytes]) -> MagicMock:
    client = MagicMock()
    client.services.get_characteristic.side_effect = lambda uuid: (
        object() if uuid in values else None
    )
    client.read_gatt_char = AsyncMock(side_effect=lambda uuid: bytearray(values[uuid]))
    client.disconnect = AsyncMock()
    client.write_gatt_char = AsyncMock()
    return client


async def test_read_headset_disconnects_and_never_writes() -> None:
    client = _client({gatt.UUID_SERIAL_NUMBER: b"S1", gatt.UUID_BATTERY_LEVEL: b"\x10"})
    with patch.object(device, "establish_connection", AsyncMock(return_value=client)):
        info = await device.async_read_headset(service_info().device, "Jabra")
    assert info.serial == "S1" and info.battery == 16
    client.disconnect.assert_awaited_once()
    client.write_gatt_char.assert_not_called()


async def test_read_headset_disconnects_on_error() -> None:
    client = _client({gatt.UUID_SERIAL_NUMBER: b"S1"})
    client.read_gatt_char.side_effect = BleakError("gone")
    with (
        patch.object(device, "establish_connection", AsyncMock(return_value=client)),
        pytest.raises(BleakError),
    ):
        await device.async_read_headset(service_info().device, "Jabra")
    client.disconnect.assert_awaited_once()
