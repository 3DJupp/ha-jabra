"""Configuration from the add-on options file and environment variables."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_OPTIONS_PATH = Path("/data/options.json")


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def default_socket_path(env: Mapping[str, str]) -> str:
    """Mirror jabridge: JABRIDGE_SOCKET or $XDG_RUNTIME_DIR/jabridge.sock."""
    explicit = env.get("JABRIDGE_SOCKET")
    if explicit:
        return explicit
    runtime = env.get("XDG_RUNTIME_DIR")
    if runtime:
        return str(Path(runtime) / "jabridge.sock")
    return "/run/jabridge/jabridge.sock"


@dataclass(frozen=True)
class Config:
    socket_path: str
    mqtt_host: str = ""  # empty: ask the Supervisor (add-on mode)
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False
    base_topic: str = "jabra2mqtt"
    discovery_prefix: str = "homeassistant"
    poll_interval: float = 60.0
    settings_interval: float = 300.0
    allow_writes: bool = True
    busylight_allow_auto: bool = False
    device_serial: str | None = None
    log_level: str = "INFO"

    def validate(self) -> None:
        if not self.base_topic or "#" in self.base_topic or "+" in self.base_topic:
            raise ValueError("base_topic must be a non-empty topic without wildcards")
        if self.poll_interval < 5:
            raise ValueError("poll_interval must be at least 5 seconds")
        if self.settings_interval < self.poll_interval:
            raise ValueError("settings_interval must not be smaller than poll_interval")
        if not 0 < self.mqtt_port < 65536:
            raise ValueError("mqtt_port out of range")


_OPTION_KEYS: dict[str, Callable[[Any], Any]] = {
    "socket_path": str,
    "mqtt_host": str,
    "mqtt_port": int,
    "mqtt_username": str,
    "mqtt_password": str,
    "mqtt_tls": _truthy,
    "base_topic": str,
    "discovery_prefix": str,
    "poll_interval": float,
    "settings_interval": float,
    "allow_writes": _truthy,
    "busylight_allow_auto": _truthy,
    "device_serial": str,
    "log_level": str,
}


def load_config(
    env: Mapping[str, str] | None = None,
    options_path: Path | None = None,
) -> Config:
    """Build a Config. Environment variables (JABRA2MQTT_<KEY>) beat the options file."""
    environment = dict(os.environ if env is None else env)
    values: dict[str, object] = {}

    path = options_path if options_path is not None else DEFAULT_OPTIONS_PATH
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path} must contain a JSON object")
        for key in _OPTION_KEYS:
            if key in raw and raw[key] not in (None, ""):
                values[key] = raw[key]

    for key in _OPTION_KEYS:
        env_value = environment.get(f"JABRA2MQTT_{key.upper()}")
        if env_value not in (None, ""):
            values[key] = env_value

    converted: dict[str, object] = {}
    for key, value in values.items():
        converted[key] = _OPTION_KEYS[key](value)

    if "socket_path" not in converted:
        converted["socket_path"] = default_socket_path(environment)

    config = Config(**converted)  # type: ignore[arg-type]
    config.validate()
    return config
