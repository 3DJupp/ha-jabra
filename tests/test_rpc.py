from __future__ import annotations

import asyncio

import pytest

from jabra2mqtt.rpc import ConnectionLost, JabridgeClient, RpcError, RpcTimeout

from .conftest import FakeJabridge


async def test_call_returns_result(server: FakeJabridge) -> None:
    client = JabridgeClient(server.path)
    await client.connect()
    try:
        assert await client.call("service.ping") == {"ok": True}
        assert server.calls("service.ping") == [{}]
    finally:
        await client.close()


async def test_error_reply_raises_rpc_error(server: FakeJabridge) -> None:
    server.errors["device.battery"] = (-32603, "no battery")
    client = JabridgeClient(server.path)
    await client.connect()
    try:
        with pytest.raises(RpcError) as info:
            await client.call("device.battery")
        assert info.value.code == -32603
        assert "no battery" in str(info.value)
    finally:
        await client.close()


async def test_notifications_are_queued(server: FakeJabridge) -> None:
    client = JabridgeClient(server.path)
    await client.connect()
    try:
        await client.call("service.ping")
        await server.notify("device.battery.update", {"id": 7})
        note = await asyncio.wait_for(client.notifications.get(), 2)
        assert note.method == "device.battery.update"
        assert note.params == {"id": 7}
    finally:
        await client.close()


async def test_timeout_raises(server: FakeJabridge) -> None:
    server.silent.add("service.ping")
    client = JabridgeClient(server.path, request_timeout=0.2)
    await client.connect()
    try:
        with pytest.raises(RpcTimeout):
            await client.call("service.ping")
    finally:
        await client.close()


async def test_connection_loss_fails_pending_call(server: FakeJabridge) -> None:
    server.silent.add("service.ping")
    client = JabridgeClient(server.path, request_timeout=5)
    await client.connect()
    try:
        pending = asyncio.create_task(client.call("service.ping"))
        await asyncio.sleep(0.1)
        await server.drop_clients()
        with pytest.raises(ConnectionLost):
            await asyncio.wait_for(pending, 2)
        assert client.closed.is_set()
    finally:
        await client.close()


async def test_call_without_connection_raises() -> None:
    client = JabridgeClient("/nonexistent.sock")
    with pytest.raises(ConnectionLost):
        await client.call("service.ping")


async def test_connect_to_missing_socket_raises_oserror() -> None:
    client = JabridgeClient("/nonexistent.sock")
    with pytest.raises(OSError):
        await client.connect()
