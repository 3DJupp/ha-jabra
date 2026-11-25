from __future__ import annotations

from jabra2mqtt.models import Battery, Device, Features, Setting, Target, slugify

from .conftest import INSTANCE, sample_device, sample_settings


def test_slugify() -> None:
    assert slugify("08C8C2253931") == "08c8c2253931"
    assert slugify("Jabra Evolve2 85!") == "jabra_evolve2_85"
    assert slugify("???", "fallback") == "fallback"


def test_device_parse_and_properties() -> None:
    device = Device.parse(sample_device())
    assert device is not None
    assert device.slug == "08c8c2253931"
    assert device.scope == "headset"
    assert device.battery == Battery(level=82, charging=False, low=False)


def test_device_without_serial_gets_pid_slug() -> None:
    device = Device.parse(sample_device(serial="", name="Jabra Link 380", isDongle=True))
    assert device is not None
    assert device.slug == "jabra_link_380_24ba"
    assert device.scope == "dongle"


def test_device_parse_rejects_garbage() -> None:
    assert Device.parse(None) is None
    assert Device.parse({"name": "no id"}) is None


def test_battery_is_clamped_and_optional() -> None:
    assert Battery.parse({"level": 150}) == Battery(100)
    assert Battery.parse({"level": -3}) == Battery(0)
    assert Battery.parse({}) is None
    assert Battery.parse({"level": "x"}) is None


def test_setting_writable_rules() -> None:
    parsed = {s.key: s for s in map(Setting.parse, sample_settings()) if s}
    assert parsed["noise-control"].writable
    assert not parsed["power-saving"].writable  # support state unavailable
    assert not parsed["audio-codec"].writable  # not editable, no choices
    assert parsed["noise-control"].target == Target(7, INSTANCE)


def test_setting_without_support_info_is_writable_when_editable() -> None:
    setting = Setting.parse({"key": "k", "editable": True, "choices": ["a", "b"]})
    assert setting is not None
    assert setting.writable


def test_setting_parse_rejects_missing_key() -> None:
    assert Setting.parse({"label": "x"}) is None


def test_target_params_omit_empty_topology() -> None:
    assert Target(1, "a" * 32).to_params() == {"id": 1, "instance": "a" * 32}
    assert Target(1, "a" * 32, "usb").to_params()["topology"] == "usb"


def test_features_parse() -> None:
    assert Features.parse({"busyLight": True}).busylight
    assert not Features.parse(None).busylight
