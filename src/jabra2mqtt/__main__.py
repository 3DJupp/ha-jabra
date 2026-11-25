"""Entry point: `python -m jabra2mqtt`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys

from . import __version__
from .bridge import Bridge
from .config import load_config
from .mqtt import MqttAdapter
from .supervisor import resolve_mqtt

log = logging.getLogger("jabra2mqtt")


async def run() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = await resolve_mqtt(cfg, os.environ)
    log.info("jabra2mqtt %s starting, jabridge socket %s", __version__, cfg.socket_path)

    holder: dict[str, Bridge] = {}

    adapter = MqttAdapter(
        cfg,
        on_connect=lambda: holder["bridge"].request_republish(),
        on_command=lambda topic, payload: holder["bridge"].submit_command(topic, payload),
    )
    bridge = Bridge(cfg, adapter)
    holder["bridge"] = bridge

    stop = asyncio.Event()

    async def wait_for_stop() -> None:
        await stop.wait()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    tasks = [
        asyncio.create_task(adapter.run(), name="mqtt"),
        asyncio.create_task(bridge.run(), name="bridge"),
    ]
    waiter = asyncio.create_task(wait_for_stop())
    done, _ = await asyncio.wait([*tasks, waiter], return_when=asyncio.FIRST_COMPLETED)
    for task in tasks:
        task.cancel()
    # Bounded: a broker that never acknowledges DISCONNECT must not block shutdown.
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
    for task in done:
        if task is not waiter and task.exception():
            raise task.exception()  # type: ignore[misc]


def main() -> None:
    try:
        asyncio.run(run())
    except ValueError as err:
        print(f"configuration error: {err}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
