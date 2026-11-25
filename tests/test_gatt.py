"""Standard GATT decoding."""

from __future__ import annotations

import pytest

from custom_components.jabra import gatt


class FakeReader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.reads: list[str] = []

    def has_characteristic(self, uuid: str) -> bool:
        return uuid in self.values

    async def read(self, uuid: str) -> bytes:
        self.reads.append(uuid)
        return self.values[uuid]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"1.5.7", "1.5.7"),
        (b"1.5.7\x00\x00", "1.5.7"),
        (b"  x \n", "x"),
        (b"", None),
        (b"\x00", None),
    ],
)
def test_decode_string(raw: bytes, expected: str | None) -> None:
    assert gatt.decode_string(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [(b"\x50", 80), (b"\x00", 0), (b"\x64", 100), (b"\x65", None), (b"", None)]
)
def test_decode_battery(raw: bytes, expected: int | None) -> None:
    assert gatt.decode_battery(raw) == expected


async def test_read_all_values() -> None:
    reader = FakeReader(
        {
            gatt.UUID_SERIAL_NUMBER: b"08C8C2253931",
            gatt.UUID_DEVICE_NAME: b"Jabra Evolve2 85",
            gatt.UUID_MANUFACTURER_NAME: b"GN Audio A/S",
            gatt.UUID_FIRMWARE_REVISION: b"1.5.7",
            gatt.UUID_HARDWARE_REVISION: b"01-67",
            gatt.UUID_BATTERY_LEVEL: b"\x2a",
        }
    )
    info = await gatt.read_headset_info(reader)
    assert info == gatt.HeadsetInfo(
        serial="08C8C2253931",
        name="Jabra Evolve2 85",
        manufacturer="GN Audio A/S",
        firmware="1.5.7",
        hardware="01-67",
        battery=42,
    )


async def test_missing_characteristics_are_none() -> None:
    reader = FakeReader({gatt.UUID_SERIAL_NUMBER: b"X1"})
    info = await gatt.read_headset_info(reader)
    assert info == gatt.HeadsetInfo(serial="X1")
    assert reader.reads == [gatt.UUID_SERIAL_NUMBER]
