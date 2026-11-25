"""Typed views of jabridge IPC replies. Parsing is tolerant: unknown fields are ignored."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def slugify(text: str, fallback: str = "device") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or fallback


@dataclass(frozen=True)
class Battery:
    level: int
    charging: bool = False
    low: bool = False

    @classmethod
    def parse(cls, raw: Any) -> Battery | None:
        data = _as_dict(raw)
        if "level" not in data:
            return None
        try:
            level = int(data["level"])
        except (TypeError, ValueError):
            return None
        return cls(
            level=max(0, min(100, level)),
            charging=bool(data.get("charging", False)),
            low=bool(data.get("low", False)),
        )


@dataclass(frozen=True)
class Target:
    id: int
    instance: str
    topology: str = ""

    def to_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"id": self.id, "instance": self.instance}
        if self.topology:
            params["topology"] = self.topology
        return params

    @classmethod
    def parse(cls, raw: Any) -> Target | None:
        data = _as_dict(raw)
        if "id" not in data or "instance" not in data:
            return None
        return cls(int(data["id"]), str(data["instance"]), str(data.get("topology", "")))


@dataclass(frozen=True)
class Device:
    id: int
    instance: str
    name: str
    serial: str
    pid: int
    is_dongle: bool
    connection: str
    firmware: str
    selected: bool
    battery: Battery | None
    topology: str = ""

    @property
    def slug(self) -> str:
        """Stable identifier used in topics and unique IDs."""
        if self.serial:
            return slugify(self.serial)
        return f"{slugify(self.name)}_{self.pid:04x}"

    @property
    def scope(self) -> str:
        """The `device` parameter for settings.list / settings.set."""
        return "dongle" if self.is_dongle else "headset"

    @classmethod
    def parse(cls, raw: Any) -> Device | None:
        data = _as_dict(raw)
        if "id" not in data:
            return None
        return cls(
            id=int(data["id"]),
            instance=str(data.get("instance", "")),
            name=str(data.get("name", "Jabra device")),
            serial=str(data.get("serial", "")),
            pid=int(data.get("pid", 0)),
            is_dongle=bool(data.get("isDongle", False)),
            connection=str(data.get("connection", "")),
            firmware=str(data.get("firmware", "")),
            selected=bool(data.get("selected", False)),
            battery=Battery.parse(data.get("battery")),
            topology=str(data.get("topology", "")),
        )


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    value: str
    editable: bool
    choices: tuple[str, ...]
    group: str = ""
    help: str = ""
    kind: str = ""
    support_state: str = ""
    target: Target | None = None
    may_restart: bool = False
    requires_restart: bool | None = None

    @property
    def writable(self) -> bool:
        """Only offer controls jabridge itself marks as editable and available."""
        if not self.editable or not self.choices:
            return False
        return self.support_state in ("", "available")

    @classmethod
    def parse(cls, raw: Any) -> Setting | None:
        data = _as_dict(raw)
        key = data.get("key")
        if not isinstance(key, str) or not key:
            return None
        support = _as_dict(data.get("support"))
        requires_restart = data.get("requiresRestart")
        return cls(
            key=key,
            label=str(data.get("label", key)),
            value=str(data.get("value", "")),
            editable=bool(data.get("editable", False)),
            choices=tuple(str(c) for c in data.get("choices") or ()),
            group=str(data.get("group", "")),
            help=str(data.get("help", "")),
            kind=str(data.get("kind", "")),
            support_state=str(support.get("state", "")),
            target=Target.parse(data.get("target")),
            may_restart=bool(data.get("mayRestart", False)),
            requires_restart=requires_restart if isinstance(requires_restart, bool) else None,
        )


@dataclass(frozen=True)
class Features:
    busylight: bool = False

    @classmethod
    def parse(cls, raw: Any) -> Features:
        return cls(busylight=bool(_as_dict(raw).get("busyLight", False)))


@dataclass
class DeviceDetails:
    """Per-device data that needs the device to be selected first."""

    features: Features = field(default_factory=Features)
    settings: list[Setting] = field(default_factory=list)
    busylight_mode: str | None = None
    fetched_at: float = float("-inf")

    def invalidate(self) -> None:
        """Force a fresh read on the next refresh (monotonic clocks can start near zero)."""
        self.fetched_at = float("-inf")
