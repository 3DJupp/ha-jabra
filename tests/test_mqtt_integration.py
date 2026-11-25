"""End to end: fake jabridge <-> Bridge <-> MqttAdapter <-> real (in-process) MQTT broker."""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

import aiomqtt
import pytest

from jabra2mqtt.bridge import Bridge
from jabra2mqtt.config import Config
from jabra2mqtt.mqtt import MqttAdapter

from .conftest import FakeJabridge

pytest.importorskip("amqtt")
from amqtt.broker import Broker  # noqa: E402

SLUG = "08c8c2253931"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def eventually(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.05)


@pytest.fixture
async def broker(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[int, Broker]]:
    # amqtt waits 10 s for its broadcast task on shutdown; that only slows the tests down.
    monkeypatch.setattr("amqtt.broker._BROADCAST_SHUTDOWN_TIMEOUT", 0.2)
    port = free_port()
    instance = Broker(
        {
            "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
            "plugins": {
                "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
            },
        }
    )
    await instance.start()
    yield port, instance
    with contextlib.suppress(Exception):
        await instance.shutdown()


@pytest.fixture
def mqtt_cfg(cfg: Config, broker: tuple[int, Broker]) -> Config:
    return replace(cfg, mqtt_host="127.0.0.1", mqtt_port=broker[0], poll_interval=5.0)


class Watcher:
    """A second MQTT client that records everything on our topics."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self.seen: dict[str, str] = {}
        self.retained: dict[str, bool] = {}
        self._task: asyncio.Task[None] | None = None
        self.client: aiomqtt.Client | None = None

    async def __aenter__(self) -> Watcher:
        ready = asyncio.Event()

        async def run() -> None:
            async with aiomqtt.Client(self._cfg.mqtt_host, self._cfg.mqtt_port) as client:
                self.client = client
                await client.subscribe("#")
                ready.set()
                async for message in client.messages:
                    payload = message.payload
                    text = payload.decode() if isinstance(payload, bytes) else str(payload)
                    self.seen[str(message.topic)] = text
                    self.retained[str(message.topic)] = message.retain

        self._task = asyncio.create_task(run())
        await asyncio.wait_for(ready.wait(), 5)
        return self

    async def __aexit__(self, *_: Any) -> None:
        assert self._task is not None
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        assert self.client is not None
        await self.client.publish(topic, payload, retain=retain)


class Stack:
    def __init__(self, cfg: Config) -> None:
        holder: dict[str, Bridge] = {}
        self.adapter = MqttAdapter(
            cfg,
            on_connect=lambda: holder["b"].request_republish(),
            on_command=lambda t, p: holder["b"].submit_command(t, p),
        )
        self.bridge = Bridge(cfg, self.adapter)
        holder["b"] = self.bridge
        self.tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        self.tasks = [
            asyncio.create_task(self.adapter.run()),
            asyncio.create_task(self.bridge.run()),
        ]

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


@pytest.fixture
async def stack(
    mqtt_cfg: Config, server: FakeJabridge, broker: tuple[int, Broker]
) -> AsyncIterator[Stack]:
    stack = Stack(mqtt_cfg)
    yield stack
    # amqtt keeps connections open until it shuts down, which would stall the client's
    # disconnect handshake. Real brokers close right away.
    with contextlib.suppress(Exception):
        await broker[1].shutdown()
    await stack.stop()


async def test_discovery_state_and_status_reach_the_broker(
    mqtt_cfg: Config, stack: Stack, server: FakeJabridge
) -> None:
    async with Watcher(mqtt_cfg) as watcher:
        stack.start()
        await eventually(lambda: watcher.seen.get(f"jabra2mqtt/{SLUG}/availability") == "online")
        assert watcher.seen["jabra2mqtt/bridge/status"] == "online"
        state = json.loads(watcher.seen[f"jabra2mqtt/{SLUG}/state"])
        assert state["battery"] == 82
        config = json.loads(watcher.seen[f"homeassistant/sensor/jabra2mqtt_{SLUG}/battery/config"])
        assert config["unique_id"] == f"jabra2mqtt_{SLUG}_battery"


async def test_commands_over_mqtt_reach_jabridge(
    mqtt_cfg: Config, stack: Stack, server: FakeJabridge
) -> None:
    async with Watcher(mqtt_cfg) as watcher:
        stack.start()
        await eventually(lambda: watcher.seen.get(f"jabra2mqtt/{SLUG}/availability") == "online")
        await watcher.publish(f"jabra2mqtt/{SLUG}/set/busylight", "on")
        await eventually(lambda: {"mode": "on"} in server.calls("device.busylight"))
        await watcher.publish(f"jabra2mqtt/{SLUG}/set/setting/noise-control", "Off")
        await eventually(lambda: len(server.calls("settings.set")) == 1)
        await eventually(
            lambda: (
                json.loads(watcher.seen[f"jabra2mqtt/{SLUG}/state"])["settings"]["noise-control"]
                == "Off"
            )
        )


async def test_retained_command_is_ignored(
    mqtt_cfg: Config, stack: Stack, server: FakeJabridge
) -> None:
    async with Watcher(mqtt_cfg) as watcher:
        await watcher.publish(f"jabra2mqtt/{SLUG}/set/setting/noise-control", "Off", retain=True)
        await asyncio.sleep(0.2)
        stack.start()
        await eventually(lambda: watcher.seen.get(f"jabra2mqtt/{SLUG}/availability") == "online")
        await asyncio.sleep(0.5)
        assert server.calls("settings.set") == []


async def test_home_assistant_birth_message_triggers_republish(
    mqtt_cfg: Config, stack: Stack
) -> None:
    async with Watcher(mqtt_cfg) as watcher:
        stack.start()
        await eventually(lambda: watcher.seen.get(f"jabra2mqtt/{SLUG}/availability") == "online")
        topic = f"homeassistant/sensor/jabra2mqtt_{SLUG}/battery/config"
        watcher.seen.pop(topic)
        await watcher.publish("homeassistant/status", "online")
        await eventually(lambda: topic in watcher.seen)


async def test_state_and_discovery_are_retained(mqtt_cfg: Config, stack: Stack) -> None:
    async with Watcher(mqtt_cfg) as watcher:
        stack.start()
        await eventually(lambda: watcher.seen.get(f"jabra2mqtt/{SLUG}/availability") == "online")
    # a fresh subscriber must receive the retained messages straight away
    async with Watcher(mqtt_cfg) as late:
        await eventually(lambda: f"jabra2mqtt/{SLUG}/state" in late.seen)
        assert late.retained[f"jabra2mqtt/{SLUG}/state"] is True
        assert late.retained["jabra2mqtt/bridge/status"] is True


async def test_process_runs_and_stops_cleanly_on_sigterm(
    mqtt_cfg: Config, server: FakeJabridge
) -> None:
    import os
    import signal
    import sys

    env = {
        **os.environ,
        "JABRIDGE_SOCKET": mqtt_cfg.socket_path,
        "JABRA2MQTT_MQTT_HOST": mqtt_cfg.mqtt_host,
        "JABRA2MQTT_MQTT_PORT": str(mqtt_cfg.mqtt_port),
    }
    async with Watcher(mqtt_cfg) as watcher:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "jabra2mqtt", env=env, stderr=asyncio.subprocess.PIPE
        )
        try:
            await eventually(
                lambda: watcher.seen.get(f"jabra2mqtt/{SLUG}/availability") == "online", 10
            )
            process.send_signal(signal.SIGTERM)
            code = await asyncio.wait_for(process.wait(), 8)
            assert code == 0
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


async def test_invalid_configuration_exits_with_code_2() -> None:
    import os
    import sys

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "jabra2mqtt",
        env={**os.environ, "JABRA2MQTT_BASE_TOPIC": "bad/#"},
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(process.communicate(), 10)
    assert process.returncode == 2
    assert b"configuration error" in stderr
