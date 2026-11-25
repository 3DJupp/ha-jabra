"""Bluetooth access to a Jabra headset: connect, read, disconnect.

The headset uses a resolvable private address that changes over time, so a configured headset is
identified by its serial number, not by its address. Connections are short: the integration never
keeps a link open, so Jabra Sound+ or a Link dongle can still use the headset in between.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import GN_SERVICE_UUID
from .gatt import HeadsetInfo, read_headset_info

_LOGGER = logging.getLogger(__name__)

# Errors that mean "could not talk to this headset right now".
CONNECT_ERRORS: tuple[type[Exception], ...] = (BleakError, TimeoutError, OSError)


class _ClientReader:
    """Adapts a connected Bleak client to the GattReader protocol."""

    def __init__(self, client: BleakClient) -> None:
        self._client = client

    def has_characteristic(self, uuid: str) -> bool:
        return self._client.services.get_characteristic(uuid) is not None

    async def read(self, uuid: str) -> bytes:
        return bytes(await self._client.read_gatt_char(uuid))


async def async_read_headset(ble_device: BLEDevice, name: str) -> HeadsetInfo:
    """Connect to the headset, read the standard values and disconnect."""
    client = await establish_connection(
        BleakClientWithServiceCache, ble_device, name, max_attempts=2
    )
    try:
        return await read_headset_info(_ClientReader(client))
    finally:
        await client.disconnect()


def is_jabra(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if an advertisement belongs to a Jabra (GN) device."""
    return GN_SERVICE_UUID in service_info.service_uuids


def order_candidates(
    infos: Iterable[BluetoothServiceInfoBleak],
    preferred_address: str | None,
    skip: set[str],
) -> list[BluetoothServiceInfoBleak]:
    """Return Jabra advertisements to try, the last known address first."""
    candidates = [i for i in infos if is_jabra(i) and i.address not in skip]
    candidates.sort(key=lambda i: (i.address != preferred_address, -(i.rssi or -127)))
    return candidates
