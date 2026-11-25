# Jabra to MQTT

Publishes Jabra headsets to Home Assistant through MQTT discovery: battery, charging, firmware,
connection, busylight and the settings the headset allows to be changed.

## Before you start

1. Plug the Jabra headset (or Link dongle) into the Home Assistant host with a USB cable.
2. Set up MQTT. The **Mosquitto broker** add-on works out of the box; credentials are taken from the
   Supervisor automatically.
3. Start the add-on and check its log. You should see `connected to jabridge` and the number of
   devices found.

The device then appears in **Settings → Devices & services → MQTT**.

## Options

| Option | Meaning |
| --- | --- |
| Allow changes | Let Home Assistant change busylight and settings. Off = read-only. |
| Offer busylight mode "auto" | Needs PipeWire call detection, which the add-on does not have. Leave off. |
| Poll interval | Seconds between battery and connection reads. |
| Settings refresh | Seconds between settings reads. |
| MQTT base topic | Prefix for state and command topics. Default `jabra2mqtt`. |
| Device serial | Only manage this device. |
| External jabridge socket | Use a jabridge you run elsewhere and mounted into the add-on. Empty = bundled jabridge. |
| Log level | `debug`, `info`, `warning`, `error`. |

## Why does the add-on need full access?

jabridge talks to the headset through `/dev/hidraw*` and `/sys/class/hidraw`. Home Assistant
cannot map device nodes that do not exist yet, so the add-on requests full device access for now.
This will be narrowed once it has been verified on real hardware.

## What the add-on never does

It never installs firmware and never factory-resets a device. Settings are only written when jabridge
reports them as editable and available.

## Troubleshooting

* **No devices**: check `ls /dev/hidraw*` on the host (Terminal add-on) and that the headset is
  powered on. For Link dongles, pair the headset first.
* **Entities unavailable**: jabridge is not reachable or the headset was unplugged.
* **Open an issue** with the add-on log set to `debug` (remove serial numbers first):
  <https://github.com/3DJupp/ha-jabra/issues>
