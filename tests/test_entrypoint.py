"""The entrypoint must supervise both processes and propagate failures."""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "docker" / "entrypoint.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def fake_binary(path: Path, body: str) -> Path:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def env_for(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHON": sys.executable,
        "JABRA2MQTT_RUNTIME_DIR": str(tmp_path / "run"),
        **extra,
    }


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_python_failure_stops_jabridge_and_propagates_status(tmp_path: Path) -> None:
    pidfile = tmp_path / "jabridge.pid"
    fake = fake_binary(tmp_path / "jabridge", f'echo $$ > "{pidfile}"\nexec sleep 60')
    # No MQTT host and no Supervisor token: jabra2mqtt exits with code 2.
    env = env_for(
        tmp_path,
        JABRA2MQTT_BUNDLED_JABRIDGE="1",
        JABRIDGE_BIN=str(fake),
    )
    env.pop("SUPERVISOR_TOKEN", None)
    env.pop("JABRA2MQTT_MQTT_HOST", None)
    result = subprocess.run([str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "mqtt_host is required" in result.stderr
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 5
    while pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not pid_alive(pid), "jabridge was left running"


def test_external_mode_does_not_start_jabridge(tmp_path: Path) -> None:
    marker = tmp_path / "started"
    fake = fake_binary(tmp_path / "jabridge", f'touch "{marker}"\nexec sleep 60')
    env = env_for(tmp_path, JABRA2MQTT_BUNDLED_JABRIDGE="0", JABRIDGE_BIN=str(fake))
    env.pop("SUPERVISOR_TOKEN", None)
    env.pop("JABRA2MQTT_MQTT_HOST", None)
    result = subprocess.run([str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert not marker.exists()


def test_sigterm_stops_everything(tmp_path: Path) -> None:
    pidfile = tmp_path / "jabridge.pid"
    fake = fake_binary(tmp_path / "jabridge", f'echo $$ > "{pidfile}"\nexec sleep 60')
    env = env_for(
        tmp_path,
        JABRA2MQTT_BUNDLED_JABRIDGE="1",
        JABRIDGE_BIN=str(fake),
        JABRA2MQTT_MQTT_HOST="127.0.0.1",
        JABRA2MQTT_MQTT_PORT="1",  # nothing listens here; the bridge just keeps retrying
    )
    process = subprocess.Popen([str(ENTRYPOINT)], env=env, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert pidfile.exists()
        pid = int(pidfile.read_text())
        time.sleep(0.5)
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=15)
        deadline = time.monotonic() + 5
        while pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not pid_alive(pid), "jabridge was left running"
    finally:
        if process.poll() is None:
            process.kill()
