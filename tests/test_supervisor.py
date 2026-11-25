from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from jabra2mqtt.config import Config
from jabra2mqtt.supervisor import fetch_mqtt_service, resolve_mqtt


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def test_fetch_sends_bearer_token_and_parses_data() -> None:
    seen: dict[str, Any] = {}

    def opener(request: Any, timeout: float) -> FakeResponse:
        seen["auth"] = request.get_header("Authorization")
        seen["url"] = request.full_url
        body = {"result": "ok", "data": {"host": "core-mosquitto", "port": 1883}}
        return FakeResponse(json.dumps(body).encode())

    data = fetch_mqtt_service("tok", opener=opener)
    assert data["host"] == "core-mosquitto"
    assert seen["auth"] == "Bearer tok"
    assert seen["url"].endswith("/services/mqtt")


def test_fetch_rejects_empty_payload() -> None:
    def opener(request: Any, timeout: float) -> FakeResponse:
        return FakeResponse(b'{"result": "error", "data": {}}')

    with pytest.raises(ValueError):
        fetch_mqtt_service("tok", opener=opener)


async def test_resolve_keeps_explicit_host() -> None:
    cfg = Config(socket_path="/s", mqtt_host="broker")
    assert await resolve_mqtt(cfg, {}) is cfg


async def test_resolve_requires_host_outside_addon() -> None:
    with pytest.raises(ValueError, match="mqtt_host is required"):
        await resolve_mqtt(Config(socket_path="/s"), {})


async def test_resolve_fills_in_supervisor_values() -> None:
    def fetch(token: str) -> dict[str, Any]:
        assert token == "tok"
        return {"host": "h", "port": 8883, "username": "u", "password": "p", "ssl": True}

    cfg = await resolve_mqtt(Config(socket_path="/s"), {"SUPERVISOR_TOKEN": "tok"}, fetch)
    assert (cfg.mqtt_host, cfg.mqtt_port) == ("h", 8883)
    assert (cfg.mqtt_username, cfg.mqtt_password, cfg.mqtt_tls) == ("u", "p", True)


async def test_resolve_wraps_network_errors() -> None:
    def fetch(token: str) -> dict[str, Any]:
        raise urllib.error.URLError("unreachable")

    with pytest.raises(ValueError, match="could not read the MQTT service"):
        await resolve_mqtt(Config(socket_path="/s"), {"SUPERVISOR_TOKEN": "t"}, fetch)
