"""Config flow tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv
import probatio
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jabra.const import CONF_SCAN_INTERVAL, CONF_SERIAL, DOMAIN

from .conftest import ADDRESS, INFO, NAME, SERIAL, service_info


async def test_bluetooth_discovery_creates_entry(
    hass: HomeAssistant, discovered: list[Any], read_headset: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    assert result["description_placeholders"] == {"name": NAME}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_SERIAL: SERIAL}
    assert result["result"].unique_id == SERIAL


async def test_bluetooth_discovery_of_configured_headset_aborts(
    hass: HomeAssistant, read_headset: AsyncMock
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_SERIAL: SERIAL}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bluetooth_discovery_cannot_connect(
    hass: HomeAssistant, headsets: dict[str, Any], read_headset: AsyncMock
) -> None:
    headsets[ADDRESS] = TimeoutError()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_bluetooth_discovery_without_serial(
    hass: HomeAssistant, headsets: dict[str, Any], read_headset: AsyncMock
) -> None:
    headsets[ADDRESS] = replace(INFO, serial=None)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_of_non_gn_device(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info(uuids=[])
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_user_flow(
    hass: HomeAssistant, discovered: list[Any], read_headset: AsyncMock
) -> None:
    discovered.append(service_info("11:22:33:44:55:66", name="Other speaker", uuids=[]))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    fields = probatio.to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    assert fields[0]["name"] == CONF_ADDRESS
    assert [value for value, _label in fields[0]["options"]] == [ADDRESS]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_SERIAL: SERIAL}


async def test_user_flow_cannot_connect_then_retry(
    hass: HomeAssistant,
    discovered: list[Any],
    headsets: dict[str, Any],
    read_headset: AsyncMock,
) -> None:
    headsets[ADDRESS] = TimeoutError()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    headsets[ADDRESS] = INFO
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_no_devices(hass: HomeAssistant, discovered: list[Any]) -> None:
    discovered.clear()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_options_flow(
    hass: HomeAssistant, discovered: list[Any], read_headset: AsyncMock
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_SERIAL: SERIAL}, title=NAME)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_SCAN_INTERVAL: 30}
    assert entry.runtime_data.update_interval.total_seconds() == 30 * 60
