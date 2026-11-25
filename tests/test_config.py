from __future__ import annotations

import json
from pathlib import Path

import pytest

from jabra2mqtt.config import Config, default_socket_path, load_config


def test_socket_default_prefers_jabridge_socket() -> None:
    assert (
        default_socket_path({"JABRIDGE_SOCKET": "/x.sock", "XDG_RUNTIME_DIR": "/run/u"})
        == "/x.sock"
    )


def test_socket_default_uses_runtime_dir() -> None:
    assert (
        default_socket_path({"XDG_RUNTIME_DIR": "/run/user/1000"}) == "/run/user/1000/jabridge.sock"
    )


def test_options_file_and_env_override(tmp_path: Path) -> None:
    options = tmp_path / "options.json"
    options.write_text(
        json.dumps(
            {"mqtt_host": "broker", "mqtt_port": 1884, "allow_writes": False, "device_serial": ""}
        )
    )
    cfg = load_config({"JABRA2MQTT_MQTT_HOST": "override", "JABRIDGE_SOCKET": "/s.sock"}, options)
    assert cfg.mqtt_host == "override"
    assert cfg.mqtt_port == 1884
    assert cfg.allow_writes is False
    assert cfg.device_serial is None
    assert cfg.socket_path == "/s.sock"


def test_env_booleans_and_numbers(tmp_path: Path) -> None:
    cfg = load_config(
        {
            "JABRA2MQTT_MQTT_TLS": "true",
            "JABRA2MQTT_POLL_INTERVAL": "30",
            "JABRA2MQTT_SETTINGS_INTERVAL": "120",
            "JABRA2MQTT_BUSYLIGHT_ALLOW_AUTO": "1",
        },
        tmp_path / "missing.json",
    )
    assert cfg.mqtt_tls is True
    assert cfg.poll_interval == 30.0
    assert cfg.busylight_allow_auto is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_topic": ""},
        {"base_topic": "a/#"},
        {"poll_interval": 1},
        {"poll_interval": 60, "settings_interval": 10},
        {"mqtt_port": 0},
    ],
)
def test_validation_rejects_bad_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Config(socket_path="/s", **kwargs).validate()  # type: ignore[arg-type]


def test_options_file_must_be_object(tmp_path: Path) -> None:
    options = tmp_path / "options.json"
    options.write_text("[]")
    with pytest.raises(ValueError):
        load_config({}, options)
