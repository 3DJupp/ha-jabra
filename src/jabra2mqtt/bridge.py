"""Core logic: mirror jabridge devices to MQTT and apply commands back.

Safety rules (see CLAUDE.md):
  * Never install firmware, never reset a device.
  * Writes only for settings jabridge marks editable and available, with the
    complete target and previous value from the latest settings.list.
  * No automatic retries of writes. After an error or timeout, read again.
  * Retained MQTT commands are ignored by the adapter, so stale writes never replay.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Config
from .discovery import (
    Entity,
    build_entities,
    build_state,
    busylight_modes,
    device_topic,
)
from .models import Device, DeviceDetails, Features, Setting
from .rpc import ConnectionLost, JabridgeClient, RpcError, RpcTimeout

log = logging.getLogger(__name__)

SETTINGS_SET_TIMEOUT = 95.0  # jabridge documents up to 90 s for configuration writes
REPUBLISH = "__republish__"
EVENT_DEBOUNCE = 0.5


class MqttUnavailable(Exception):
    """Publishing was not possible because the broker connection is down."""


class Publisher(Protocol):
    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> None: ...


@dataclass
class KnownDevice:
    device: Device
    details: DeviceDetails | None = None
    available: bool = False
    published_configs: dict[str, str] = field(default_factory=dict)  # topic -> payload json
    published_state: str | None = None


class Bridge:
    def __init__(
        self,
        cfg: Config,
        publisher: Publisher,
        client_factory: Callable[[str], JabridgeClient] = JabridgeClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cfg = cfg
        self._pub = publisher
        self._client_factory = client_factory
        self._clock = clock
        self.commands: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._known: dict[str, KnownDevice] = {}
        self._selected_id: int | None = None
        self._force_publish = True
        self._session_ready = False
        self.reconnect_delay = 1.0

    # ------------------------------------------------------------------ public

    def request_republish(self) -> None:
        """Called when MQTT (re)connects or Home Assistant announces it is online."""
        self.commands.put_nowait((REPUBLISH, ""))

    def submit_command(self, topic: str, payload: str) -> None:
        self.commands.put_nowait((topic, payload))

    async def run(self) -> None:
        backoff = self.reconnect_delay
        while True:
            client = self._client_factory(self._cfg.socket_path)
            self._session_ready = False
            shutting_down = False
            try:
                await client.connect()
                await self._session(client)
            except asyncio.CancelledError:
                shutting_down = True
                raise
            except (OSError, ConnectionLost, RpcTimeout, RpcError) as err:
                log.warning("jabridge session ended: %s", err)
            finally:
                await client.close()
                self._selected_id = None
                # On shutdown the bridge status topic (last will) already marks every
                # entity unavailable, and the broker connection is going away anyway.
                if not shutting_down:
                    await self._mark_all_offline()
            if self._session_ready:
                backoff = self.reconnect_delay
            log.info("reconnecting to jabridge in %.1f s", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    # ----------------------------------------------------------------- session

    async def _session(self, client: JabridgeClient) -> None:
        await client.call("service.ping")
        await client.call("subscribe")
        await self.refresh(client, full=True)
        self._session_ready = True
        log.info("connected to jabridge, %d device(s)", len(self._known))

        while True:
            getters: dict[asyncio.Task[Any], str] = {
                asyncio.ensure_future(client.notifications.get()): "event",
                asyncio.ensure_future(self.commands.get()): "command",
                asyncio.ensure_future(client.closed.wait()): "closed",
            }
            try:
                await asyncio.wait(
                    getters, timeout=self._cfg.poll_interval, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                for task in getters:
                    if not task.done():
                        task.cancel()

            commands: list[tuple[str, str]] = []
            full = False
            event_seen = False
            closed = False
            for task, kind in getters.items():
                if not task.done() or task.cancelled():
                    continue
                if kind == "command":
                    commands.append(task.result())
                elif kind == "event":
                    event_seen = True
                    full = full or task.result().method in _TOPOLOGY_EVENTS
                else:
                    closed = True

            if event_seen:
                await asyncio.sleep(EVENT_DEBOUNCE)
                while not client.notifications.empty():
                    note = client.notifications.get_nowait()
                    full = full or note.method in _TOPOLOGY_EVENTS

            for topic, payload in commands:
                if topic == REPUBLISH:
                    self._force_publish = True
                else:
                    await self.handle_command(client, topic, payload)

            if closed and not commands and not event_seen:
                raise ConnectionLost("jabridge closed the connection")
            await self.refresh(client, full=full)
            if closed:
                raise ConnectionLost("jabridge closed the connection")

    # ----------------------------------------------------------------- refresh

    async def refresh(self, client: JabridgeClient, *, full: bool = False) -> None:
        raw = await client.call("devices.list")
        devices = [d for d in (Device.parse(item) for item in raw or []) if d is not None]
        if self._cfg.device_serial:
            wanted = self._cfg.device_serial.lower()
            devices = [d for d in devices if d.serial.lower() == wanted]
        self._remember_selection(devices)

        now = self._clock()
        current: set[str] = set()
        for device in devices:
            current.add(device.slug)
            known = self._known.get(device.slug)
            if known is None:
                known = KnownDevice(device)
                self._known[device.slug] = known
            replaced = known.device.instance != device.instance
            known.device = device
            stale = (
                known.details is None
                or replaced
                or (now - known.details.fetched_at) >= self._cfg.settings_interval
            )
            if full or stale:
                known.details = await self._fetch_details(client, device, known.details)
            await self._publish_device(known)

        for slug, known in self._known.items():
            if slug not in current and known.available:
                known.available = False
                await self._publish(
                    device_topic(self._cfg, known.device, "availability"), "offline", retain=True
                )
        self._force_publish = False

    def _remember_selection(self, devices: list[Device]) -> None:
        for device in devices:
            if device.selected:
                self._selected_id = device.id
                return

    async def _select(self, client: JabridgeClient, device: Device) -> None:
        if self._selected_id == device.id:
            return
        await client.call("device.select", {"id": device.id})
        self._selected_id = device.id

    async def _fetch_details(
        self, client: JabridgeClient, device: Device, previous: DeviceDetails | None
    ) -> DeviceDetails:
        details = DeviceDetails(fetched_at=self._clock())
        try:
            await self._select(client, device)
            details.features = Features.parse(await _optional(client, "device.features"))
            raw_settings = await client.call("settings.list", {"device": device.scope})
            details.settings = [
                s for s in (Setting.parse(item) for item in raw_settings or []) if s is not None
            ]
            if details.features.busylight:
                reply = await _optional(client, "device.busylight")
                mode = reply.get("mode") if isinstance(reply, dict) else None
                details.busylight_mode = mode if isinstance(mode, str) and mode else None
        except (RpcError, RpcTimeout) as err:
            log.warning("could not read details for %s: %s", device.name, err)
            if previous is not None:
                previous.fetched_at = self._clock()
                return previous
        return details

    # ----------------------------------------------------------------- publish

    async def _publish(self, topic: str, payload: str, *, retain: bool = True) -> bool:
        try:
            await self._pub.publish(topic, payload, retain=retain)
        except MqttUnavailable as err:
            log.warning("MQTT unavailable, will republish later: %s", err)
            self._force_publish = True
            return False
        return True

    async def _publish_device(self, known: KnownDevice) -> None:
        cfg = self._cfg
        device = known.device
        force = self._force_publish

        entities = build_entities(cfg, device, known.details)
        wanted: dict[str, Entity] = {
            e.topic(cfg.discovery_prefix, device.slug): e for e in entities
        }
        for topic, entity in wanted.items():
            payload = json.dumps(entity.config, sort_keys=True)
            changed = force or known.published_configs.get(topic) != payload
            if changed and await self._publish(topic, payload):
                known.published_configs[topic] = payload
        for topic in [t for t in known.published_configs if t not in wanted]:
            if await self._publish(topic, ""):
                del known.published_configs[topic]

        state = json.dumps(build_state(device, known.details), sort_keys=True)
        state_changed = force or known.published_state != state
        if state_changed and await self._publish(device_topic(cfg, device, "state"), state):
            known.published_state = state
        needs_online = force or not known.available
        if needs_online and await self._publish(
            device_topic(cfg, device, "availability"), "online"
        ):
            known.available = True

    async def _mark_all_offline(self) -> None:
        for known in self._known.values():
            known.available = False
            with contextlib.suppress(MqttUnavailable):
                await self._pub.publish(
                    device_topic(self._cfg, known.device, "availability"), "offline", retain=True
                )

    # ---------------------------------------------------------------- commands

    async def handle_command(self, client: JabridgeClient, topic: str, payload: str) -> None:
        prefix = f"{self._cfg.base_topic}/"
        if not topic.startswith(prefix):
            return
        parts = topic[len(prefix) :].split("/", 3)
        if len(parts) < 3 or parts[1] != "set":
            return
        slug, rest = parts[0], "/".join(parts[2:])
        known = self._known.get(slug)
        if known is None or not known.available:
            log.warning("ignoring command for unavailable device %s", slug)
            return
        if not self._cfg.allow_writes:
            log.warning("writes are disabled, ignoring command %s", topic)
            return
        value = payload.strip()
        try:
            if rest == "busylight":
                await self._set_busylight(client, known, value)
            elif rest.startswith("setting/"):
                await self._set_setting(client, known, rest[len("setting/") :], value)
            else:
                log.warning("unknown command topic %s", topic)
        except (RpcError, RpcTimeout) as err:
            # Never retry a write. Force a fresh read before anything else happens.
            log.error("command %s=%s failed: %s", rest, value, err)
            if known.details is not None:
                known.details.invalidate()

    async def _set_busylight(self, client: JabridgeClient, known: KnownDevice, mode: str) -> None:
        details = known.details
        if details is None or not details.features.busylight:
            log.warning("%s has no busylight", known.device.name)
            return
        if mode not in busylight_modes(self._cfg):
            log.warning("busylight mode %r not allowed", mode)
            return
        await self._select(client, known.device)
        await client.call("device.busylight", {"mode": mode})
        reply = await client.call("device.busylight")
        read_back = reply.get("mode") if isinstance(reply, dict) else None
        details.busylight_mode = read_back if isinstance(read_back, str) else mode
        log.info("busylight of %s set to %s", known.device.name, details.busylight_mode)

    async def _set_setting(
        self, client: JabridgeClient, known: KnownDevice, key: str, value: str
    ) -> None:
        details = known.details
        setting = None
        if details is not None:
            setting = next((s for s in details.settings if s.key == key), None)
        if setting is None:
            log.warning("unknown setting %r on %s", key, known.device.name)
            return
        if not setting.writable:
            log.warning("setting %r is not writable", key)
            return
        if value not in setting.choices:
            log.warning("value %r is not a valid choice for %r", value, key)
            return
        if value == setting.value:
            return
        params: dict[str, Any] = {
            "device": known.device.scope,
            "key": key,
            "value": value,
        }
        if setting.target is not None:
            params["target"] = setting.target.to_params()
            params["previous"] = setting.value
        await self._select(client, known.device)
        reply = await client.call("settings.set", params, timeout=SETTINGS_SET_TIMEOUT)
        updated = Setting.parse(reply)
        assert details is not None
        if updated is not None:
            details.settings = [updated if s.key == key else s for s in details.settings]
        else:
            details.invalidate()
        log.info("setting %s of %s changed to %s", key, known.device.name, value)


_TOPOLOGY_EVENTS = frozenset({"device.attached", "device.detached", "device.pairing.update"})


async def _optional(client: JabridgeClient, method: str) -> Any:
    """Call a method that some models do not implement; return None on RPC errors."""
    try:
        return await client.call(method)
    except RpcError as err:
        log.debug("%s unavailable: %s", method, err)
        return None
