"""Build Home Assistant MQTT discovery payloads and state documents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import __version__
from .config import Config
from .models import Device, DeviceDetails, slugify

SUPPORT_URL = "https://github.com/3DJupp/ha-jabra"


@dataclass(frozen=True)
class Entity:
    component: str
    object_id: str
    config: dict[str, Any]

    def topic(self, prefix: str, slug: str) -> str:
        return f"{prefix}/{self.component}/jabra2mqtt_{slug}/{self.object_id}/config"


def bridge_status_topic(cfg: Config) -> str:
    return f"{cfg.base_topic}/bridge/status"


def device_topic(cfg: Config, device: Device, suffix: str) -> str:
    return f"{cfg.base_topic}/{device.slug}/{suffix}"


def busylight_modes(cfg: Config) -> list[str]:
    return ["on", "off", "auto"] if cfg.busylight_allow_auto else ["on", "off"]


def build_state(device: Device, details: DeviceDetails | None) -> dict[str, Any]:
    state: dict[str, Any] = {
        "firmware": device.firmware,
        "connection": device.connection,
    }
    if device.battery is not None:
        state["battery"] = device.battery.level
        state["charging"] = device.battery.charging
        state["low"] = device.battery.low
    if details is not None:
        if details.busylight_mode is not None:
            state["busylight"] = details.busylight_mode
        state["settings"] = {s.key: s.value for s in details.settings}
    return state


def build_entities(cfg: Config, device: Device, details: DeviceDetails | None) -> list[Entity]:
    state_topic = device_topic(cfg, device, "state")
    base: dict[str, Any] = {
        "state_topic": state_topic,
        "availability": [
            {"topic": bridge_status_topic(cfg)},
            {"topic": device_topic(cfg, device, "availability")},
        ],
        "availability_mode": "all",
        "device": {
            "identifiers": [f"jabra2mqtt_{device.slug}"],
            "name": device.name,
            "manufacturer": "Jabra",
            "model": device.name,
            "sw_version": device.firmware or None,
        },
        "origin": {
            "name": "ha-jabra (jabra2mqtt)",
            "sw_version": __version__,
            "support_url": SUPPORT_URL,
        },
    }
    base["device"] = {k: v for k, v in base["device"].items() if v is not None}

    def make(component: str, object_id: str, **extra: Any) -> Entity:
        payload = dict(base)
        payload["unique_id"] = f"jabra2mqtt_{device.slug}_{object_id}"
        # HA replaced the deprecated `object_id` with `default_entity_id` ("domain.slug").
        payload["default_entity_id"] = f"{component}.jabra_{device.slug}_{object_id}"
        payload.update(extra)
        return Entity(component, object_id, payload)

    entities: list[Entity] = [
        make(
            "sensor",
            "firmware",
            name="Firmware",
            value_template="{{ value_json.firmware }}",
            entity_category="diagnostic",
            icon="mdi:chip",
        ),
        make(
            "sensor",
            "connection",
            name="Connection",
            value_template="{{ value_json.connection }}",
            entity_category="diagnostic",
            icon="mdi:connection",
        ),
    ]

    if device.battery is not None:
        entities += [
            make(
                "sensor",
                "battery",
                name="Battery",
                device_class="battery",
                unit_of_measurement="%",
                state_class="measurement",
                value_template="{{ value_json.battery }}",
            ),
            make(
                "binary_sensor",
                "charging",
                name="Charging",
                device_class="battery_charging",
                value_template="{{ 'ON' if value_json.charging else 'OFF' }}",
            ),
            make(
                "binary_sensor",
                "battery_low",
                name="Battery low",
                device_class="battery",
                value_template="{{ 'ON' if value_json.low else 'OFF' }}",
                entity_category="diagnostic",
            ),
        ]

    if details is not None:
        if details.features.busylight and details.busylight_mode is not None:
            if cfg.allow_writes:
                entities.append(
                    make(
                        "select",
                        "busylight",
                        name="Busylight",
                        options=busylight_modes(cfg),
                        command_topic=device_topic(cfg, device, "set/busylight"),
                        value_template="{{ value_json.busylight }}",
                        icon="mdi:led-on",
                    )
                )
            else:
                entities.append(
                    make(
                        "sensor",
                        "busylight",
                        name="Busylight",
                        value_template="{{ value_json.busylight }}",
                        icon="mdi:led-on",
                    )
                )
        for setting in details.settings:
            object_id = f"setting_{slugify(setting.key)}"
            template = f"{{{{ value_json.settings[{json.dumps(setting.key)}] }}}}"
            if setting.writable and cfg.allow_writes:
                entities.append(
                    make(
                        "select",
                        object_id,
                        name=setting.label,
                        options=list(setting.choices),
                        command_topic=device_topic(cfg, device, f"set/setting/{setting.key}"),
                        value_template=template,
                        entity_category="config",
                    )
                )
            else:
                entities.append(
                    make(
                        "sensor",
                        object_id,
                        name=setting.label,
                        value_template=template,
                        entity_category="diagnostic",
                        enabled_by_default=False,
                    )
                )
    return entities
