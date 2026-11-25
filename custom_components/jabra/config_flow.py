"""Config flow for Jabra headsets.

A headset advertises with a rotating private address, so the flow connects once and uses the
serial number (Device Information 0x2A25) as the unique id.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
import voluptuous as vol

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)
from .coordinator import JabraConfigEntry
from .device import CONNECT_ERRORS, async_read_headset, is_jabra
from .gatt import HeadsetInfo

_LOGGER = logging.getLogger(__name__)


def _title(service_info: BluetoothServiceInfoBleak, info: HeadsetInfo | None = None) -> str:
    name = (info.name if info else None) or service_info.name or "Jabra headset"
    return name.strip()


class JabraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Jabra headset."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._info: HeadsetInfo | None = None
        self._candidates: dict[str, BluetoothServiceInfoBleak] = {}

    async def _async_identify(self, service_info: BluetoothServiceInfoBleak) -> HeadsetInfo:
        """Connect once and read the serial number. Raises CONNECT_ERRORS."""
        return await async_read_headset(service_info.device, _title(service_info))

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a headset found by Bluetooth discovery."""
        if not is_jabra(discovery_info):
            return self.async_abort(reason="not_supported")
        # Private addresses rotate: a configured headset reappears under a new address.
        for entry in self._async_current_entries(include_ignore=False):
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is not None and coordinator.address == discovery_info.address:
                return self.async_abort(reason="already_configured")
        if self._async_in_progress(include_uninitialized=True):
            return self.async_abort(reason="already_in_progress")
        try:
            info = await self._async_identify(discovery_info)
        except CONNECT_ERRORS as err:
            _LOGGER.debug("Discovery could not read %s: %s", discovery_info.address, err)
            return self.async_abort(reason="cannot_connect")
        if not info.serial:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(info.serial)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self._info = info
        self.context["title_placeholders"] = {"name": _title(discovery_info, info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered headset."""
        assert self._discovery is not None and self._info is not None
        if user_input is not None:
            return self._async_create(self._discovery, self._info)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": _title(self._discovery, self._info)},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a Jabra headset that is currently advertising."""
        errors: dict[str, str] = {}
        if user_input is not None:
            service_info = self._candidates[user_input[CONF_ADDRESS]]
            try:
                info = await self._async_identify(service_info)
            except CONNECT_ERRORS as err:
                _LOGGER.debug("Could not read %s: %s", service_info.address, err)
                errors["base"] = "cannot_connect"
            else:
                if not info.serial:
                    return self.async_abort(reason="not_supported")
                await self.async_set_unique_id(info.serial, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self._async_create(service_info, info)

        for service_info in async_discovered_service_info(self.hass, connectable=True):
            if is_jabra(service_info):
                self._candidates.setdefault(service_info.address, service_info)
        if not self._candidates:
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        address: f"{_title(info)} ({address})"
                        for address, info in self._candidates.items()
                    }
                )
            }
        )
        # HA >= 2026.10 maps voluptuous to probatio at import time; mypy sees real voluptuous.
        return self.async_show_form(
            step_id="user",
            data_schema=schema,  # type: ignore[arg-type]
            errors=errors,
        )

    @callback
    def _async_create(
        self, service_info: BluetoothServiceInfoBleak, info: HeadsetInfo
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=_title(service_info, info),
            data={CONF_SERIAL: info.serial},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: JabraConfigEntry) -> JabraOptionsFlow:
        """Return the options flow."""
        return JabraOptionsFlow()


class JabraOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)  # type: ignore[arg-type]
