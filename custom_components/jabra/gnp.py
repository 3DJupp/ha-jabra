"""GNP frame codec (prepared, not used by any entity yet).

GNP is the Jabra device protocol that Jabra Sound+ also speaks over the GN Bluetooth service
(0xFEFF). The frame layout follows jabridge (Apache-2.0); command numbers and value encodings follow
GN Audio's ``@gnaudio/jabra-properties-definition`` (Apache-2.0). See docs/PROTOCOL_NOTES.md.

Nothing here talks to a device. Writing is deliberately not wired up until the BLE framing has been
verified on real hardware with read-only queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Final

HOST_DESTINATION: Final = 0x08
FLAG_QUERY: Final = 0x40
FLAG_COMMAND: Final = 0x80
FLAG_REPLY: Final = 0xC0
OP_ACK: Final = 0xFF
OP_NAK: Final = 0xFE
MAX_FRAME: Final = 0x3F
HEADER_LEN: Final = 6


class GnpError(Exception):
    """A frame could not be built or understood."""


class GnpNak(GnpError):
    """The device rejected a request."""

    def __init__(self, code: int) -> None:
        super().__init__(f"GNP NAK 0x{code:02x}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Command:
    """A GNP command class and operation."""

    cls: int
    op: int


# From the Apache-2.0 property definitions (command, subcommand).
BATTERY_V2: Final = Command(0x12, 0x02)
BUSY_STATE: Final = Command(0x12, 0x08)
DEVICE_NAME: Final = Command(0x13, 0x5B)
BLUETOOTH_NAME: Final = Command(0x13, 0x56)
ANC_MODE: Final = Command(0x13, 0x87)


class AncMode(IntEnum):
    """Values of the ancMode property."""

    OFF = 0
    ANC = 1
    HEAR_THROUGH = 2
    HEAR_THROUGH_MIX = 3


def build_frame(
    command: Command,
    seq: int,
    *,
    flag: int = FLAG_QUERY,
    payload: bytes = b"",
    destination: int = HOST_DESTINATION,
) -> bytes:
    """Build a request frame: dst, src, seq, flags|length, class, op, payload."""
    length = HEADER_LEN + len(payload)
    if length > MAX_FRAME:
        raise GnpError(f"payload too large: {len(payload)} bytes")
    if flag not in (FLAG_QUERY, FLAG_COMMAND):
        raise GnpError(f"invalid flag 0x{flag:02x}")
    for name, value in (("seq", seq), ("destination", destination)):
        if not 0 <= value <= 0xFF:
            raise GnpError(f"{name} out of range: {value}")
    return bytes((destination, 0x00, seq, flag | length, command.cls, command.op)) + payload


def parse_reply(
    frame: bytes, command: Command, seq: int, *, source: int = HOST_DESTINATION
) -> bytes:
    """Validate a reply to ``command`` and return its payload. Raises GnpNak on rejection."""
    if len(frame) < 5:
        raise GnpError(f"reply too short: {len(frame)} bytes")
    if frame[0] != 0x00 or frame[1] != source:
        raise GnpError("reply is for another endpoint")
    if frame[2] != seq:
        raise GnpError(f"sequence mismatch: got {frame[2]}, want {seq}")
    if frame[3] & FLAG_REPLY != FLAG_REPLY:
        raise GnpError(f"not a reply: 0x{frame[3]:02x}")
    if frame[4] == OP_NAK:
        raise GnpNak(frame[5] if len(frame) > 5 else 0)
    length = frame[3] & MAX_FRAME
    if length < HEADER_LEN or length > len(frame):
        raise GnpError(f"invalid length: {length}")
    if frame[4] != command.cls or frame[5] != command.op:
        raise GnpError("reply belongs to another command")
    return bytes(frame[HEADER_LEN:length])


def decode_battery_v2(payload: bytes) -> int:
    """Primary battery level in percent from a batteryLevelV2 reply."""
    if len(payload) < 2:
        raise GnpError("battery payload too short")
    level = payload[1]
    if level > 100:
        raise GnpError(f"battery level out of range: {level}")
    return level


def decode_length_prefixed(payload: bytes) -> str:
    """UTF-8 string with a one byte length prefix (deviceName)."""
    if not payload:
        raise GnpError("empty string payload")
    size = payload[0]
    if size > len(payload) - 1:
        raise GnpError("string length exceeds payload")
    return payload[1 : 1 + size].decode("utf-8")


def encode_length_prefixed(value: str) -> bytes:
    """Encode a deviceName value."""
    raw = value.encode("utf-8")
    if not raw:
        raise GnpError("name must not be empty")
    if len(raw) > MAX_FRAME - HEADER_LEN - 1:
        raise GnpError("name too long")
    return bytes((len(raw),)) + raw


def decode_null_terminated(payload: bytes) -> str:
    """UTF-8 string terminated by NUL (bluetoothName)."""
    return payload.split(b"\x00", 1)[0].decode("utf-8")


def decode_anc_mode(payload: bytes) -> AncMode:
    """Decode the ancMode property."""
    if not payload:
        raise GnpError("empty ANC payload")
    try:
        return AncMode(payload[0])
    except ValueError as err:
        raise GnpError(f"unknown ANC mode {payload[0]}") from err


def decode_bool(payload: bytes) -> bool:
    """Decode a one byte boolean property (busyStatePresence)."""
    if not payload:
        raise GnpError("empty boolean payload")
    return payload[0] != 0
