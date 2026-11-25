"""GNP codec (prepared for BLE, not used by entities yet)."""

from __future__ import annotations

import pytest

from custom_components.jabra import gnp


def test_battery_query_frame_matches_manual_test() -> None:
    # The frame given to the owner for the nRF Connect test.
    assert gnp.build_frame(gnp.BATTERY_V2, 1).hex() == "080001461202"


def test_command_frame_with_payload() -> None:
    frame = gnp.build_frame(gnp.ANC_MODE, 7, flag=gnp.FLAG_COMMAND, payload=b"\x01")
    assert frame == bytes([0x08, 0x00, 0x07, 0x87, 0x13, 0x87, 0x01])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"payload": b"x" * 58},
        {"flag": 0xC0},
        {"seq": 256},
        {"destination": -1},
    ],
)
def test_build_frame_rejects_bad_input(kwargs: dict[str, object]) -> None:
    args = {"seq": 1, **kwargs}
    seq = args.pop("seq")
    with pytest.raises(gnp.GnpError):
        gnp.build_frame(gnp.BATTERY_V2, seq, **args)  # type: ignore[arg-type]


def test_parse_reply_returns_payload() -> None:
    reply = bytes([0x00, 0x08, 0x01, 0xC0 | 9, 0x12, 0x02, 0x00, 0x50, 0x00, 0xAA])
    payload = gnp.parse_reply(reply, gnp.BATTERY_V2, 1)
    assert payload == b"\x00\x50\x00"
    assert gnp.decode_battery_v2(payload) == 80


def test_parse_reply_nak() -> None:
    with pytest.raises(gnp.GnpNak) as err:
        gnp.parse_reply(bytes([0x00, 0x08, 0x01, 0xC6, 0xFE, 0x03]), gnp.BATTERY_V2, 1)
    assert err.value.code == 3


@pytest.mark.parametrize(
    "reply",
    [
        bytes([0x00, 0x08]),  # too short
        bytes([0x00, 0x01, 0x01, 0xC6, 0x12, 0x02]),  # other endpoint
        bytes([0x00, 0x08, 0x02, 0xC6, 0x12, 0x02]),  # other sequence
        bytes([0x00, 0x08, 0x01, 0x46, 0x12, 0x02]),  # a request, not a reply
        bytes([0x00, 0x08, 0x01, 0xC6, 0x13, 0x5B]),  # other command
        bytes([0x00, 0x08, 0x01, 0xC9, 0x12, 0x02]),  # length beyond frame
    ],
)
def test_parse_reply_rejects(reply: bytes) -> None:
    with pytest.raises(gnp.GnpError):
        gnp.parse_reply(reply, gnp.BATTERY_V2, 1)


def test_strings() -> None:
    encoded = gnp.encode_length_prefixed("Dominics Jabra")
    assert encoded[0] == len("Dominics Jabra")
    assert gnp.decode_length_prefixed(encoded) == "Dominics Jabra"
    assert gnp.decode_null_terminated(b"Jabra\x00junk") == "Jabra"
    with pytest.raises(gnp.GnpError):
        gnp.encode_length_prefixed("")
    with pytest.raises(gnp.GnpError):
        gnp.encode_length_prefixed("x" * 57)
    with pytest.raises(gnp.GnpError):
        gnp.decode_length_prefixed(b"\x05ab")


def test_small_values() -> None:
    assert gnp.decode_anc_mode(b"\x02") is gnp.AncMode.HEAR_THROUGH
    assert gnp.decode_bool(b"\x01") is True
    assert gnp.decode_bool(b"\x00") is False
    for bad in (
        lambda: gnp.decode_anc_mode(b"\x09"),
        lambda: gnp.decode_anc_mode(b""),
        lambda: gnp.decode_bool(b""),
        lambda: gnp.decode_battery_v2(b"\x00"),
        lambda: gnp.decode_battery_v2(b"\x00\xff"),
    ):
        with pytest.raises(gnp.GnpError):
            bad()
