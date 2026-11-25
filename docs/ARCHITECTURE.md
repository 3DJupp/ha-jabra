# Architecture

```
Jabra device --USB HID--> jabridge daemon --JSON-RPC (Unix socket)--> jabra2mqtt --MQTT--> Home Assistant
```

## Components (src/jabra2mqtt)

| Module | Role |
| --- | --- |
| `rpc.py` | Async JSON-RPC 2.0 client, newline-delimited JSON, per-request timeouts, notification queue |
| `models.py` | Tolerant parsers for `devices.list`, `settings.list`, battery, features |
| `discovery.py` | Builds Home Assistant discovery payloads and state documents |
| `bridge.py` | Session loop, refresh, command handling, reconnect, write safety |
| `mqtt.py` | aiomqtt adapter: birth/will, reconnect, command intake, HA birth message |
| `supervisor.py` | Reads MQTT credentials from the add-on Supervisor |
| `config.py` | Add-on options file and `JABRA2MQTT_*` environment variables |

## jabridge IPC used

`service.ping`, `subscribe`, `devices.list`, `device.select`, `device.features`,
`settings.list`, `settings.set`, `device.busylight`. Events (`device.*`, `sound.changed`) only
trigger a refresh; the stream is not treated as complete.

Reply fields come from `daemon/ipc/handler.go` in jabridge (`DeviceInfo`, `BatteryInfo`,
`SettingInfo`, `SettingTarget`). Settings values and choices are strings.

## Data flow

1. `Bridge.run` connects, pings, subscribes and calls `refresh(full=True)`.
2. `refresh` reads `devices.list` (battery and firmware are inline). Per device it re-reads
   features, settings and busylight mode when needed (first time, after attach/detach events,
   after errors, every `settings_interval`).
3. Discovery configs are retained and only republished when they change, when MQTT reconnects or
   when Home Assistant announces `online` on `homeassistant/status`.
4. Commands arrive on `<base>/<slug>/set/busylight` and `<base>/<slug>/set/setting/<key>`. They are
   validated against the latest settings snapshot, then sent as one call. No retry.

## MQTT topics

| Topic | Content | Retained |
| --- | --- | --- |
| `<base>/bridge/status` | `online` / `offline` (last will) | yes |
| `<base>/<slug>/availability` | `online` / `offline` | yes |
| `<base>/<slug>/state` | JSON state document | yes |
| `<base>/<slug>/set/busylight` | command: `on` / `off` (`auto`) | no, retained ones are ignored |
| `<base>/<slug>/set/setting/<key>` | command: one of the setting's choices | no, retained ones are ignored |
| `<discovery_prefix>/<component>/jabra2mqtt_<slug>/<object>/config` | discovery payload | yes |

`<slug>` is the lowercase serial number (or `<name>_<pid>` when there is none).

## Device selection

jabridge reads settings and busylight for the currently selected device only. The bridge calls
`device.select` before reading or writing a device that is not selected and remembers the selection
locally. A second client (the jabridge TUI) can change the selection; the next refresh corrects it.

## Container

`docker/entrypoint.sh` starts the bundled `jabridge daemon` (unless `socket_path` or
`JABRA2MQTT_BUNDLED_JABRIDGE=0` selects an external one), then `python -m jabra2mqtt`. If either
process exits, the other is stopped and the status is propagated, so the supervisor restarts both.
