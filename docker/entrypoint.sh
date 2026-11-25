#!/usr/bin/env bash
# Start the bundled jabridge daemon (unless an external socket is configured) and jabra2mqtt.
# If either process exits, stop the other one and exit with its status so that the
# supervisor (Home Assistant or Docker) can restart the whole thing.
set -uo pipefail

PYTHON="${PYTHON:-python}"
JABRIDGE="${JABRIDGE_BIN:-jabridge}"
RUNTIME_DIR="${JABRA2MQTT_RUNTIME_DIR:-/run/jabridge}"

bundled="${JABRA2MQTT_BUNDLED_JABRIDGE:-}"
if [[ -z "$bundled" ]]; then
  bundled=1
  if [[ -f /data/options.json ]] && command -v jq >/dev/null 2>&1; then
    external="$(jq -r '.socket_path // empty' /data/options.json 2>/dev/null || true)"
    [[ -n "$external" ]] && bundled=0
  fi
fi

pids=()
cleanup() {
  trap - EXIT TERM INT
  for pid in "${pids[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
# A signal must end the script (the EXIT trap then stops the children).
trap 'exit 143' TERM
trap 'exit 130' INT
trap cleanup EXIT

if [[ "$bundled" == "1" ]]; then
  mkdir -p "$RUNTIME_DIR"
  export XDG_RUNTIME_DIR="$RUNTIME_DIR"
  export JABRIDGE_SOCKET="$RUNTIME_DIR/jabridge.sock"
  "$JABRIDGE" daemon &
  pids+=("$!")
  for _ in $(seq 1 50); do
    [[ -S "$JABRIDGE_SOCKET" ]] && break
    sleep 0.2
  done
fi

"$PYTHON" -m jabra2mqtt &
pids+=("$!")

wait -n
status=$?
exit "$status"
