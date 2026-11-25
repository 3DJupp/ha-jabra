"""Read MQTT credentials from the Home Assistant Supervisor when running as an add-on."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from .config import Config

SUPERVISOR_MQTT_URL = "http://supervisor/services/mqtt"


def fetch_mqtt_service(
    token: str,
    *,
    url: str = SUPERVISOR_MQTT_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with opener(request, timeout=10) as response:
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("host"):
        raise ValueError("Supervisor returned no MQTT service data")
    return data


async def resolve_mqtt(
    cfg: Config,
    env: Mapping[str, str],
    fetch: Callable[[str], dict[str, Any]] = fetch_mqtt_service,
) -> Config:
    """Return cfg with broker settings filled in from the Supervisor when mqtt_host is empty."""
    if cfg.mqtt_host:
        return cfg
    token = env.get("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("mqtt_host is required when not running as a Home Assistant add-on")
    try:
        data = await asyncio.to_thread(fetch, token)
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise ValueError(f"could not read the MQTT service from the Supervisor: {err}") from err
    return replace(
        cfg,
        mqtt_host=str(data["host"]),
        mqtt_port=int(data.get("port", 1883)),
        mqtt_username=data.get("username") or None,
        mqtt_password=data.get("password") or None,
        mqtt_tls=bool(data.get("ssl", False)),
    )
