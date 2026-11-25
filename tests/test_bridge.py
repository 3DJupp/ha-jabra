from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

import pytest

from jabra2mqtt.bridge import Bridge, MqttUnavailable
from jabra2mqtt.config import Config

from .conftest import FakeJabridge, RecordingPublisher, sample_device

SLUG = "08c8c2253931"
STATE = f"jabra2mqtt/{SLUG}/state"
AVAIL = f"jabra2mqtt/{SLUG}/availability"
DISCOVERY_BATTERY = f"homeassistant/sensor/jabra2mqtt_{SLUG}/battery/config"


async def eventually(predicate: Callable[[], bool], timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


def state(publisher: RecordingPublisher) -> dict[str, Any]:
    payload = publisher.last(STATE)
    assert payload is not None
    return json.loads(payload)  # type: ignore[no-any-return]


@pytest.fixture
async def running(
    server: FakeJabridge, publisher: RecordingPublisher, cfg: Config
) -> AsyncIterator[Bridge]:
    bridge = Bridge(cfg, publisher)
    bridge.reconnect_delay = 0.05
    task = asyncio.create_task(bridge.run())
    await eventually(lambda: publisher.last(AVAIL) == "online")
    yield bridge
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_initial_publish(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    assert DISCOVERY_BATTERY in publisher.topics()
    assert all(retain for t, _, retain in publisher.messages if t.endswith("/config"))
    snapshot = state(publisher)
    assert snapshot["battery"] == 82
    assert snapshot["busylight"] == "off"
    assert snapshot["settings"]["noise-control"] == "ANC"
    config = json.loads(
        publisher.last(f"homeassistant/select/jabra2mqtt_{SLUG}/setting_noise_control/config")
        or "{}"
    )
    assert config["options"] == ["Off", "HearThrough", "ANC"]
    assert server.calls("subscribe") == [{}]
    # an already selected device must not be re-selected
    assert server.calls("device.select") == []


async def test_event_triggers_state_update(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    server.devices[0]["battery"]["level"] = 41
    await server.notify("device.battery.update", {"id": 7})
    await eventually(lambda: state(publisher)["battery"] == 41)


async def test_periodic_poll_without_events(
    server: FakeJabridge, publisher: RecordingPublisher, cfg: Config
) -> None:
    fast = replace(cfg, poll_interval=0.1, settings_interval=0.1)
    bridge = Bridge(fast, publisher)
    task = asyncio.create_task(bridge.run())
    try:
        await eventually(lambda: publisher.last(AVAIL) == "online")
        server.devices[0]["battery"]["level"] = 12
        await eventually(lambda: state(publisher)["battery"] == 12)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_unchanged_state_is_not_republished(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    publisher.clear()
    await server.notify("device.button", {})
    await eventually(lambda: len(server.calls("devices.list")) >= 2)
    await asyncio.sleep(0.2)
    assert STATE not in publisher.topics()
    assert DISCOVERY_BATTERY not in publisher.topics()


async def test_busylight_command(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    running.submit_command(f"jabra2mqtt/{SLUG}/set/busylight", "on")
    await eventually(lambda: state(publisher).get("busylight") == "on")
    assert {"mode": "on"} in server.calls("device.busylight")


@pytest.mark.parametrize("mode", ["blink", "auto", ""])
async def test_busylight_rejects_invalid_modes(
    running: Bridge, server: FakeJabridge, mode: str
) -> None:
    running.submit_command(f"jabra2mqtt/{SLUG}/set/busylight", mode)
    await asyncio.sleep(0.3)
    assert all("mode" not in c or c["mode"] == "" for c in server.calls("device.busylight"))
    assert server.busylight_mode == "off"


async def test_setting_command_sends_target_and_previous(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    running.submit_command(f"jabra2mqtt/{SLUG}/set/setting/noise-control", "HearThrough")
    await eventually(lambda: state(publisher)["settings"]["noise-control"] == "HearThrough")
    (call,) = server.calls("settings.set")
    assert call["device"] == "headset"
    assert call["key"] == "noise-control"
    assert call["value"] == "HearThrough"
    assert call["previous"] == "ANC"
    assert call["target"]["id"] == 7
    assert len(call["target"]["instance"]) == 32


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("noise-control", "Turbo"),  # not a listed choice
        ("power-saving", "Off"),  # support state unavailable
        ("audio-codec", "AAC"),  # read-only
        ("does-not-exist", "x"),
        ("noise-control", "ANC"),  # unchanged value
    ],
)
async def test_setting_command_rejections(
    running: Bridge, server: FakeJabridge, key: str, value: str
) -> None:
    running.submit_command(f"jabra2mqtt/{SLUG}/set/setting/{key}", value)
    await asyncio.sleep(0.3)
    assert server.calls("settings.set") == []


async def test_writes_disabled(
    server: FakeJabridge, publisher: RecordingPublisher, cfg: Config
) -> None:
    bridge = Bridge(replace(cfg, allow_writes=False), publisher)
    task = asyncio.create_task(bridge.run())
    try:
        await eventually(lambda: publisher.last(AVAIL) == "online")
        bridge.submit_command(f"jabra2mqtt/{SLUG}/set/busylight", "on")
        bridge.submit_command(f"jabra2mqtt/{SLUG}/set/setting/noise-control", "Off")
        await asyncio.sleep(0.3)
        assert server.calls("settings.set") == []
        assert {"mode": "on"} not in server.calls("device.busylight")
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_failed_write_is_not_retried_and_state_is_reread(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    server.errors["settings.set"] = (-32603, "device refused")
    reads_before = len(server.calls("settings.list"))
    running.submit_command(f"jabra2mqtt/{SLUG}/set/setting/noise-control", "Off")
    await eventually(lambda: len(server.calls("settings.list")) > reads_before)
    await asyncio.sleep(0.2)
    assert len(server.calls("settings.set")) == 1
    assert state(publisher)["settings"]["noise-control"] == "ANC"


async def test_write_timeout_is_not_retried(
    running: Bridge, server: FakeJabridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("jabra2mqtt.bridge.SETTINGS_SET_TIMEOUT", 0.2)
    server.silent.add("settings.set")
    running.submit_command(f"jabra2mqtt/{SLUG}/set/setting/noise-control", "Off")
    await eventually(lambda: len(server.calls("settings.set")) == 1)
    await asyncio.sleep(0.5)
    assert len(server.calls("settings.set")) == 1


@pytest.mark.parametrize(
    "topic",
    [
        "other/08c8c2253931/set/busylight",
        "jabra2mqtt/unknown/set/busylight",
        f"jabra2mqtt/{SLUG}/get/busylight",
        f"jabra2mqtt/{SLUG}/set/reset",
        f"jabra2mqtt/{SLUG}/set/firmware",
    ],
)
async def test_unknown_commands_do_nothing(
    running: Bridge, server: FakeJabridge, topic: str
) -> None:
    running.submit_command(topic, "x")
    await asyncio.sleep(0.2)
    methods = {name for name, _ in server.requests}
    assert methods.isdisjoint({"settings.set", "device.reset", "device.reset.bound"})
    assert {"mode": "x"} not in server.calls("device.busylight")


async def test_no_firmware_or_reset_methods_are_ever_called(
    running: Bridge, server: FakeJabridge
) -> None:
    running.submit_command(f"jabra2mqtt/{SLUG}/set/setting/noise-control", "Off")
    running.submit_command(f"jabra2mqtt/{SLUG}/set/busylight", "on")
    await asyncio.sleep(0.3)
    for name, _ in server.requests:
        assert not name.startswith(("device.reset", "firmware", "bt.", "diagnostics"))


async def test_device_disappearing_marks_it_offline(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    server.devices.clear()
    await server.notify("device.detached", {"id": 7})
    await eventually(lambda: publisher.last(AVAIL) == "offline")
    server.devices.append(sample_device())
    await server.notify("device.attached", {"id": 7})
    await eventually(lambda: publisher.last(AVAIL) == "online")


async def test_reconnect_after_jabridge_restart(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    await server.drop_clients()
    await eventually(lambda: publisher.last(AVAIL) == "offline")
    await eventually(lambda: publisher.last(AVAIL) == "online")
    assert len(server.calls("subscribe")) == 2


async def test_bridge_waits_while_socket_is_missing(
    publisher: RecordingPublisher, cfg: Config
) -> None:
    bridge = Bridge(cfg, publisher)
    bridge.reconnect_delay = 0.05
    task = asyncio.create_task(bridge.run())
    try:
        await asyncio.sleep(0.2)
        assert publisher.messages == []
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_republish_request_resends_retained_discovery(
    running: Bridge, publisher: RecordingPublisher
) -> None:
    publisher.clear()
    running.request_republish()
    await eventually(lambda: DISCOVERY_BATTERY in publisher.topics())
    assert STATE in publisher.topics()


async def test_removed_setting_clears_its_discovery_topic(
    running: Bridge, publisher: RecordingPublisher, server: FakeJabridge
) -> None:
    topic = f"homeassistant/select/jabra2mqtt_{SLUG}/setting_hearthrough_level/config"
    assert publisher.last(topic) not in (None, "")
    server.settings = [s for s in server.settings if s["key"] != "hearthrough-level"]
    await server.notify("device.attached", {"id": 7})
    await eventually(lambda: publisher.last(topic) == "")


async def test_settings_failure_keeps_basic_entities(
    server: FakeJabridge, publisher: RecordingPublisher, cfg: Config
) -> None:
    server.errors["settings.list"] = (-32603, "not supported")
    bridge = Bridge(cfg, publisher)
    task = asyncio.create_task(bridge.run())
    try:
        await eventually(lambda: publisher.last(AVAIL) == "online")
        assert state(publisher)["battery"] == 82
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_device_serial_filter(
    server: FakeJabridge, publisher: RecordingPublisher, cfg: Config
) -> None:
    server.devices.append(
        sample_device(
            id=9,
            serial="DONGLE-1",
            name="Jabra Link 380",
            isDongle=True,
            selected=False,
            battery=None,
        )
    )
    bridge = Bridge(replace(cfg, device_serial="dongle-1"), publisher)
    task = asyncio.create_task(bridge.run())
    try:
        await eventually(lambda: publisher.last("jabra2mqtt/dongle_1/availability") == "online")
        assert AVAIL not in publisher.topics()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_second_device_is_selected_before_reading_details(
    server: FakeJabridge, publisher: RecordingPublisher, cfg: Config
) -> None:
    server.devices.append(
        sample_device(
            id=9,
            serial="DONGLE-1",
            name="Jabra Link 380",
            isDongle=True,
            selected=False,
            battery=None,
        )
    )
    bridge = Bridge(cfg, publisher)
    task = asyncio.create_task(bridge.run())
    try:
        await eventually(lambda: publisher.last("jabra2mqtt/dongle_1/availability") == "online")
        assert {"id": 9} in server.calls("device.select")
        scopes = [c["device"] for c in server.calls("settings.list")]
        assert scopes == ["headset", "dongle"]
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class FlakyPublisher(RecordingPublisher):
    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        if self.fail:
            raise MqttUnavailable("broker down")
        await super().publish(topic, payload, retain=retain)


async def test_publishes_after_broker_comes_back(server: FakeJabridge, cfg: Config) -> None:
    flaky = FlakyPublisher()
    bridge = Bridge(cfg, flaky)
    task = asyncio.create_task(bridge.run())
    try:
        await asyncio.sleep(0.3)
        assert flaky.messages == []
        flaky.fail = False
        bridge.request_republish()
        await eventually(lambda: flaky.last(AVAIL) == "online")
        assert DISCOVERY_BATTERY in flaky.topics()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
