"""Test helpers: a fake jabridge JSON-RPC server on a Unix socket and a recording publisher.

The device payloads are synthetic. They follow the field names in jabridge's IPC
types (daemon/ipc/handler.go) but are not captured from real hardware.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from jabra2mqtt.config import Config

INSTANCE = "0123456789abcdef0123456789abcdef"


def sample_device(**overrides: Any) -> dict[str, Any]:
    device: dict[str, Any] = {
        "id": 7,
        "instance": INSTANCE,
        "name": "Jabra Evolve2 85",
        "pid": 0x24BA,
        "serial": "08C8C2253931",
        "isDongle": False,
        "connection": "usb",
        "firmware": "1.5.7",
        "selected": True,
        "battery": {"level": 82, "charging": False, "low": False, "component": 0},
    }
    device.update(overrides)
    return device


def sample_settings() -> list[dict[str, Any]]:
    target = {"id": 7, "instance": INSTANCE}
    return [
        {
            "device": "headset",
            "key": "noise-control",
            "label": "Noise control",
            "value": "ANC",
            "editable": True,
            "choices": ["Off", "HearThrough", "ANC"],
            "target": target,
            "support": {"state": "available", "sources": ["model-catalog"]},
        },
        {
            "device": "headset",
            "key": "hearthrough-level",
            "label": "HearThrough level",
            "value": "Medium",
            "editable": True,
            "choices": ["Low", "Medium", "High"],
            "target": target,
            "support": {"state": "available"},
        },
        {
            "device": "headset",
            "key": "power-saving",
            "label": "Power saving",
            "value": "On",
            "editable": True,
            "choices": ["On", "Off"],
            "target": target,
            "support": {"state": "unavailable", "reason": "unknown firmware profile"},
        },
        {
            "device": "headset",
            "key": "audio-codec",
            "label": "Audio codec",
            "value": "SBC",
            "editable": False,
            "target": target,
        },
    ]


class FakeJabridge:
    """Serves canned replies and records every request it receives."""

    def __init__(self, path: Path) -> None:
        self.path = str(path)
        self.devices: list[dict[str, Any]] = [sample_device()]
        self.settings: list[dict[str, Any]] = sample_settings()
        self.busylight_mode = "off"
        self.features = {"busyLight": True}
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.errors: dict[str, tuple[int, str]] = {}
        self.silent: set[str] = set()
        self.hooks: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._server: asyncio.AbstractServer | None = None
        self._writers: list[asyncio.StreamWriter] = []

    async def start(self) -> None:
        self._server = await asyncio.start_unix_server(self._handle, path=self.path)

    async def stop(self) -> None:
        await self.drop_clients()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()

    async def drop_clients(self) -> None:
        for writer in list(self._writers):
            writer.close()
        self._writers.clear()

    async def notify(self, method: str, params: Any = None) -> None:
        line = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
        for writer in list(self._writers):
            writer.write(line.encode())
            await writer.drain()

    def calls(self, method: str) -> list[dict[str, Any]]:
        return [params for name, params in self.requests if name == method]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.append(writer)
        try:
            while line := await reader.readline():
                request = json.loads(line)
                method = request["method"]
                params = request.get("params") or {}
                self.requests.append((method, params))
                if method in self.silent:
                    continue
                if method in self.errors:
                    code, message = self.errors[method]
                    reply: dict[str, Any] = {
                        "jsonrpc": "2.0",
                        "id": request["id"],
                        "error": {"code": code, "message": message},
                    }
                else:
                    reply = {
                        "jsonrpc": "2.0",
                        "id": request["id"],
                        "result": self._result(method, params),
                    }
                writer.write((json.dumps(reply) + "\n").encode())
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    def _result(self, method: str, params: dict[str, Any]) -> Any:
        if method in self.hooks:
            return self.hooks[method](params)
        if method == "service.ping":
            return {"ok": True}
        if method == "subscribe":
            return {"subscribed": True}
        if method == "devices.list":
            return copy.deepcopy(self.devices)
        if method == "device.select":
            for device in self.devices:
                device["selected"] = device["id"] == params.get("id")
            return {"ok": True}
        if method == "device.features":
            return self.features
        if method == "settings.list":
            return copy.deepcopy(self.settings)
        if method == "device.busylight":
            if params.get("mode"):
                self.busylight_mode = params["mode"]
            return {"mode": self.busylight_mode}
        if method == "settings.set":
            for setting in self.settings:
                if setting["key"] == params["key"]:
                    setting["value"] = params["value"]
                    return copy.deepcopy(setting)
            return None
        raise AssertionError(f"unexpected method {method}")


class RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, bool]] = []

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        self.messages.append((topic, payload, retain))

    def last(self, topic: str) -> str | None:
        for t, payload, _ in reversed(self.messages):
            if t == topic:
                return payload
        return None

    def topics(self) -> list[str]:
        return [t for t, _, _ in self.messages]

    def clear(self) -> None:
        self.messages.clear()


@pytest.fixture
async def server(tmp_path: Path) -> AsyncIterator[FakeJabridge]:
    fake = FakeJabridge(tmp_path / "jabridge.sock")
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
def publisher() -> RecordingPublisher:
    return RecordingPublisher()


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        socket_path=str(tmp_path / "jabridge.sock"),
        poll_interval=5.0,
        settings_interval=300.0,
    )
