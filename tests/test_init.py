"""Setup, sensors, polling and address rotation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jabra.const import CONF_SERIAL, DOMAIN
from custom_components.jabra.diagnostics import async_get_config_entry_diagnostics

from .conftest import (
    ADDRESS,
    ADDRESS_ROTATED,
    INFO,
    NAME,
    OTHER_ADDRESS,
    OTHER_SERIAL,
    SERIAL,
    service_info,
)

BATTERY = "sensor.jabra_evolve2_85_battery"
FIRMWARE = "sensor.jabra_evolve2_85_firmware"


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_SERIAL: SERIAL}, title=NAME)
    entry.add_to_hass(hass)
    return entry


def _device(hass: HomeAssistant, entry: MockConfigEntry) -> dr.DeviceEntry | None:
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return next((d for d in devices if (DOMAIN, SERIAL) in d.identifiers), None)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_sensors(
    hass: HomeAssistant, entry: MockConfigEntry, discovered: list[Any], read_headset: AsyncMock
) -> None:
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(BATTERY).state == "80"
    assert hass.states.get(BATTERY).attributes["unit_of_measurement"] == "%"
    assert hass.states.get(FIRMWARE).state == "1.5.7"

    ent_reg = er.async_get(hass)
    hardware = ent_reg.async_get("sensor.jabra_evolve2_85_hardware_revision")
    assert hardware is not None and hardware.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    device = _device(hass, entry)
    assert device is not None
    assert device.serial_number == SERIAL
    assert device.manufacturer == "Jabra"


async def test_headset_off_does_not_block_setup(
    hass: HomeAssistant, entry: MockConfigEntry, discovered: list[Any], read_headset: AsyncMock
) -> None:
    discovered.clear()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(BATTERY).state == STATE_UNAVAILABLE
    read_headset.assert_not_called()


async def test_rotated_address_is_found_by_serial(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    discovered: list[Any],
    headsets: dict[str, Any],
    read_headset: AsyncMock,
) -> None:
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    assert coordinator.address == ADDRESS

    # The headset now advertises under a new private address; another Jabra is nearby.
    discovered[:] = [service_info(OTHER_ADDRESS, rssi=-40), service_info(ADDRESS_ROTATED)]
    headsets.clear()
    headsets[OTHER_ADDRESS] = replace(INFO, serial=OTHER_SERIAL, name="Jabra Evolve2 65")
    headsets[ADDRESS_ROTATED] = replace(INFO, battery=55)
    read_headset.reset_mock()
    await coordinator.async_refresh()
    assert coordinator.address == ADDRESS_ROTATED
    assert hass.states.get(BATTERY).state == "55"
    assert read_headset.await_count == 2  # the stronger foreign device first, then ours

    # The foreign headset is remembered and not connected again while it advertises.
    read_headset.reset_mock()
    await coordinator.async_refresh()
    assert read_headset.await_count == 1
    assert read_headset.await_args.args[0].address == ADDRESS_ROTATED


async def test_unreachable_marks_unavailable(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    discovered: list[Any],
    headsets: dict[str, Any],
    read_headset: AsyncMock,
) -> None:
    await _setup(hass, entry)
    headsets[ADDRESS] = TimeoutError()
    await entry.runtime_data.async_refresh()
    assert not entry.runtime_data.last_update_success
    assert hass.states.get(BATTERY).state == STATE_UNAVAILABLE


async def test_firmware_change_updates_device(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    discovered: list[Any],
    headsets: dict[str, Any],
    read_headset: AsyncMock,
) -> None:
    await _setup(hass, entry)
    headsets[ADDRESS] = replace(INFO, firmware="1.6.0")
    await entry.runtime_data.async_refresh()
    device = _device(hass, entry)
    assert device is not None and device.sw_version == "1.6.0"


async def test_unload(
    hass: HomeAssistant, entry: MockConfigEntry, discovered: list[Any], read_headset: AsyncMock
) -> None:
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redact_serial(
    hass: HomeAssistant, entry: MockConfigEntry, discovered: list[Any], read_headset: AsyncMock
) -> None:
    await _setup(hass, entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    assert SERIAL not in text
    assert ADDRESS not in text
    assert diag["data"]["battery"] == 80


async def test_advertisement_triggers_early_refresh_after_failure(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    discovered: list[Any],
    headsets: dict[str, Any],
    read_headset: AsyncMock,
    fake_bluetooth: MagicMock,
) -> None:
    headsets[ADDRESS] = TimeoutError()
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    assert not coordinator.last_update_success
    on_advertisement = fake_bluetooth.call_args.args[1]

    # Within the cooldown nothing happens.
    read_headset.reset_mock()
    on_advertisement(service_info(), None)
    await hass.async_block_till_done()
    read_headset.assert_not_called()

    # After the cooldown the headset is read again and becomes available.
    headsets[ADDRESS] = INFO
    coordinator.last_attempt -= 10_000
    on_advertisement(service_info(), None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.last_update_success
    assert hass.states.get(BATTERY).state == "80"

    # While updates succeed, advertisements do not cause extra connections.
    read_headset.reset_mock()
    coordinator.last_attempt -= 10_000
    on_advertisement(service_info(), None)
    await hass.async_block_till_done(wait_background_tasks=True)
    read_headset.assert_not_called()
