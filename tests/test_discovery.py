from __future__ import annotations

import json

from jabra2mqtt.config import Config
from jabra2mqtt.discovery import build_entities, build_state, busylight_modes
from jabra2mqtt.models import Device, DeviceDetails, Features, Setting

from .conftest import sample_device, sample_settings


def make_details(busylight: bool = True) -> DeviceDetails:
    return DeviceDetails(
        features=Features(busylight=busylight),
        settings=[s for s in map(Setting.parse, sample_settings()) if s],
        busylight_mode="off" if busylight else None,
    )


def entities_by_id(cfg: Config, details: DeviceDetails | None):  # type: ignore[no-untyped-def]
    device = Device.parse(sample_device())
    assert device is not None
    return {e.object_id: e for e in build_entities(cfg, device, details)}


def test_full_entity_set(cfg: Config) -> None:
    entities = entities_by_id(cfg, make_details())
    assert set(entities) == {
        "firmware",
        "connection",
        "battery",
        "charging",
        "battery_low",
        "busylight",
        "setting_noise_control",
        "setting_hearthrough_level",
        "setting_power_saving",
        "setting_audio_codec",
    }
    assert entities["battery"].component == "sensor"
    assert entities["charging"].component == "binary_sensor"
    assert entities["busylight"].component == "select"


def test_battery_entities_need_battery_data(cfg: Config) -> None:
    device = Device.parse(sample_device(battery=None))
    assert device is not None
    ids = {e.object_id for e in build_entities(cfg, device, None)}
    assert ids == {"firmware", "connection"}


def test_writable_setting_becomes_select(cfg: Config) -> None:
    select = entities_by_id(cfg, make_details())["setting_noise_control"]
    assert select.component == "select"
    assert select.config["options"] == ["Off", "HearThrough", "ANC"]
    assert select.config["command_topic"] == "jabra2mqtt/08c8c2253931/set/setting/noise-control"
    assert select.config["entity_category"] == "config"


def test_unavailable_and_readonly_settings_are_disabled_sensors(cfg: Config) -> None:
    entities = entities_by_id(cfg, make_details())
    for object_id in ("setting_power_saving", "setting_audio_codec"):
        assert entities[object_id].component == "sensor"
        assert entities[object_id].config["enabled_by_default"] is False
        assert "command_topic" not in entities[object_id].config


def test_writes_disabled_turns_selects_into_sensors(cfg: Config) -> None:
    read_only = Config(**{**cfg.__dict__, "allow_writes": False})
    entities = entities_by_id(read_only, make_details())
    assert entities["setting_noise_control"].component == "sensor"
    assert entities["busylight"].component == "sensor"
    assert "command_topic" not in entities["busylight"].config


def test_busylight_options_follow_config(cfg: Config) -> None:
    assert busylight_modes(cfg) == ["on", "off"]
    with_auto = Config(**{**cfg.__dict__, "busylight_allow_auto": True})
    assert busylight_modes(with_auto) == ["on", "off", "auto"]


def test_no_busylight_entity_without_feature(cfg: Config) -> None:
    assert "busylight" not in entities_by_id(cfg, make_details(busylight=False))


def test_common_payload_fields(cfg: Config) -> None:
    battery = entities_by_id(cfg, make_details())["battery"]
    config = battery.config
    assert config["unique_id"] == "jabra2mqtt_08c8c2253931_battery"
    assert config["default_entity_id"] == "sensor.jabra_08c8c2253931_battery"
    assert "object_id" not in config
    assert config["availability_mode"] == "all"
    assert [a["topic"] for a in config["availability"]] == [
        "jabra2mqtt/bridge/status",
        "jabra2mqtt/08c8c2253931/availability",
    ]
    assert config["device"]["identifiers"] == ["jabra2mqtt_08c8c2253931"]
    assert config["device"]["manufacturer"] == "Jabra"
    assert config["device"]["sw_version"] == "1.5.7"
    json.dumps(config)  # must be serialisable


def test_discovery_topic_layout(cfg: Config) -> None:
    battery = entities_by_id(cfg, make_details())["battery"]
    assert (
        battery.topic("homeassistant", "08c8c2253931")
        == "homeassistant/sensor/jabra2mqtt_08c8c2253931/battery/config"
    )


def test_state_document(cfg: Config) -> None:
    device = Device.parse(sample_device())
    assert device is not None
    state = build_state(device, make_details())
    assert state["battery"] == 82
    assert state["charging"] is False
    assert state["busylight"] == "off"
    assert state["settings"]["noise-control"] == "ANC"
    assert state["firmware"] == "1.5.7"


def test_setting_key_with_quotes_is_escaped_in_template(cfg: Config) -> None:
    device = Device.parse(sample_device())
    assert device is not None
    odd = Setting.parse({"key": 'we"ird', "editable": False})
    assert odd is not None
    details = DeviceDetails(settings=[odd])
    entity = next(
        e for e in build_entities(cfg, device, details) if e.object_id.startswith("setting_")
    )
    assert '\\"' in entity.config["value_template"]
