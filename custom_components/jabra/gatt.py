"""Read standard GATT information from a Jabra headset.

Only Bluetooth SIG standard services are used here (Device Information 0x180A, Battery 0x180F,
Generic Access 0x1800). Nothing in this module writes to the headset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

UUID_DEVICE_NAME: Final = "00002a00-0000-1000-8000-00805f9b34fb"
UUID_BATTERY_LEVEL: Final = "00002a19-0000-1000-8000-00805f9b34fb"
UUID_SERIAL_NUMBER: Final = "00002a25-0000-1000-8000-00805f9b34fb"
UUID_FIRMWARE_REVISION: Final = "00002a26-0000-1000-8000-00805f9b34fb"
UUID_HARDWARE_REVISION: Final = "00002a27-0000-1000-8000-00805f9b34fb"
UUID_MANUFACTURER_NAME: Final = "00002a29-0000-1000-8000-00805f9b34fb"


class GattReader(Protocol):
    """The part of a Bleak client this module needs."""

    def has_characteristic(self, uuid: str) -> bool:
        """Return True if the connected device exposes the characteristic."""

    async def read(self, uuid: str) -> bytes:
        """Read a characteristic value."""


@dataclass(frozen=True, slots=True)
class HeadsetInfo:
    """Values read from the headset in one connection."""

    serial: str | None
    name: str | None = None
    manufacturer: str | None = None
    firmware: str | None = None
    hardware: str | None = None
    battery: int | None = None


def decode_string(raw: bytes | bytearray) -> str | None:
    """Decode a GATT UTF-8 string, dropping trailing NUL bytes and whitespace."""
    text = bytes(raw).split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
    return text or None


def decode_battery(raw: bytes | bytearray) -> int | None:
    """Decode the Battery Level characteristic (uint8 percent, 0..100)."""
    if len(raw) < 1:
        return None
    value = raw[0]
    return value if value <= 100 else None


async def _read_optional(reader: GattReader, uuid: str) -> bytes | None:
    if not reader.has_characteristic(uuid):
        return None
    return await reader.read(uuid)


async def read_headset_info(reader: GattReader) -> HeadsetInfo:
    """Read all standard values the headset offers. Missing characteristics give None."""
    values: dict[str, bytes | None] = {}
    for uuid in (
        UUID_SERIAL_NUMBER,
        UUID_DEVICE_NAME,
        UUID_MANUFACTURER_NAME,
        UUID_FIRMWARE_REVISION,
        UUID_HARDWARE_REVISION,
        UUID_BATTERY_LEVEL,
    ):
        values[uuid] = await _read_optional(reader, uuid)

    def text(uuid: str) -> str | None:
        raw = values[uuid]
        return None if raw is None else decode_string(raw)

    battery_raw = values[UUID_BATTERY_LEVEL]
    return HeadsetInfo(
        serial=text(UUID_SERIAL_NUMBER),
        name=text(UUID_DEVICE_NAME),
        manufacturer=text(UUID_MANUFACTURER_NAME),
        firmware=text(UUID_FIRMWARE_REVISION),
        hardware=text(UUID_HARDWARE_REVISION),
        battery=None if battery_raw is None else decode_battery(battery_raw),
    )
