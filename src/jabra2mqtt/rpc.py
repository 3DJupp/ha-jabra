"""Async JSON-RPC 2.0 client for the jabridge Unix socket (newline-delimited JSON)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# jabridge answers a single device list in one line; leave generous headroom.
_LINE_LIMIT = 8 * 1024 * 1024
_NOTIFICATION_QUEUE_SIZE = 256


class RpcError(Exception):
    """The service answered with a JSON-RPC error object."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{message} (code {code})")
        self.code = code
        self.message = message


class ConnectionLost(Exception):
    """The socket closed or a request could not be sent."""


class RpcTimeout(Exception):
    """No answer within the timeout. The remote side may still have acted."""


@dataclass(frozen=True)
class Notification:
    method: str
    params: Any


class JabridgeClient:
    def __init__(self, path: str, *, request_timeout: float = 10.0) -> None:
        self._path = path
        self._request_timeout = request_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self.notifications: asyncio.Queue[Notification] = asyncio.Queue(
            maxsize=_NOTIFICATION_QUEUE_SIZE
        )
        self.closed = asyncio.Event()

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(
            self._path, limit=_LINE_LIMIT
        )
        self.closed.clear()
        self._read_task = asyncio.create_task(self._read_loop(), name="jabridge-reader")

    async def close(self) -> None:
        self.closed.set()
        if self._read_task is not None:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._read_task
            self._read_task = None
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
        self._fail_pending(ConnectionLost("client closed"))

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        if self._writer is None or self.closed.is_set():
            raise ConnectionLost("not connected")
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params:
            message["params"] = params
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            data = (json.dumps(message, separators=(",", ":")) + "\n").encode()
            try:
                async with self._write_lock:
                    self._writer.write(data)
                    await self._writer.drain()
            except (OSError, ConnectionError) as err:
                raise ConnectionLost(str(err)) from err
            try:
                return await asyncio.wait_for(
                    future, timeout if timeout is not None else self._request_timeout
                )
            except TimeoutError as err:
                raise RpcTimeout(f"{method} timed out") from err
        finally:
            self._pending.pop(request_id, None)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                self._dispatch(line)
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError) as err:
            log.warning("jabridge reader stopped: %s", err)
        finally:
            self.closed.set()
            self._fail_pending(ConnectionLost("connection closed"))

    def _dispatch(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            log.warning("ignoring malformed line from jabridge")
            return
        if not isinstance(message, dict):
            return
        message_id = message.get("id")
        if message_id is not None and isinstance(message_id, int):
            future = self._pending.get(message_id)
            if future is None or future.done():
                return
            error = message.get("error")
            if error:
                future.set_exception(
                    RpcError(int(error.get("code", 0)), str(error.get("message", "")))
                )
            else:
                future.set_result(message.get("result"))
            return
        method = message.get("method")
        if isinstance(method, str):
            notification = Notification(method, message.get("params"))
            if self.notifications.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    self.notifications.get_nowait()
            self.notifications.put_nowait(notification)

    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
