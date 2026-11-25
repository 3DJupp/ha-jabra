"""MQTT adapter around aiomqtt: reconnects, birth/will, and command intake."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

import aiomqtt

from .bridge import MqttUnavailable
from .config import Config
from .discovery import bridge_status_topic

log = logging.getLogger(__name__)

PUBLISH_WAIT = 10.0


class MqttAdapter:
    def __init__(
        self,
        cfg: Config,
        on_connect: Callable[[], None],
        on_command: Callable[[str, str], None],
    ) -> None:
        self._cfg = cfg
        self._on_connect = on_connect
        self._on_command = on_command
        self._client: aiomqtt.Client | None = None
        self._connected = asyncio.Event()

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        if not self._connected.is_set():
            try:
                await asyncio.wait_for(self._connected.wait(), PUBLISH_WAIT)
            except TimeoutError as err:
                raise MqttUnavailable("not connected to the broker") from err
        client = self._client
        if client is None:
            raise MqttUnavailable("not connected to the broker")
        try:
            await client.publish(topic, payload, retain=retain, qos=1)
        except aiomqtt.MqttError as err:
            raise MqttUnavailable(str(err)) from err

    async def run(self) -> None:
        cfg = self._cfg
        status_topic = bridge_status_topic(cfg)
        ha_status_topic = f"{cfg.discovery_prefix}/status"
        backoff = 1.0
        while True:
            will = aiomqtt.Will(topic=status_topic, payload="offline", qos=1, retain=True)
            try:
                async with aiomqtt.Client(
                    hostname=cfg.mqtt_host,
                    port=cfg.mqtt_port,
                    username=cfg.mqtt_username,
                    password=cfg.mqtt_password,
                    tls_params=aiomqtt.TLSParameters() if cfg.mqtt_tls else None,
                    identifier="jabra2mqtt",
                    will=will,
                    timeout=5,
                ) as client:
                    self._client = client
                    await client.publish(status_topic, "online", qos=1, retain=True)
                    await client.subscribe(f"{cfg.base_topic}/+/set/#", qos=1)
                    await client.subscribe(ha_status_topic, qos=1)
                    self._connected.set()
                    self._on_connect()
                    backoff = 1.0
                    log.info("connected to MQTT broker %s:%s", cfg.mqtt_host, cfg.mqtt_port)
                    try:
                        async for message in client.messages:
                            self._handle_message(
                                str(message.topic), message.payload, message.retain, ha_status_topic
                            )
                    except asyncio.CancelledError:
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(
                                client.publish(status_topic, "offline", qos=1, retain=True), 3
                            )
                        raise
            except aiomqtt.MqttError as err:
                log.warning("MQTT connection lost: %s", err)
            finally:
                self._client = None
                self._connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    def _handle_message(
        self, topic: str, raw: object, retained: bool, ha_status_topic: str
    ) -> None:
        payload = raw.decode("utf-8", "replace") if isinstance(raw, bytes | bytearray) else str(raw)
        if topic == ha_status_topic:
            if payload == "online":
                self._on_connect()
            return
        if retained:
            # A retained command would replay an old write after every reconnect.
            log.warning("ignoring retained command on %s", topic)
            return
        self._on_command(topic, payload)
