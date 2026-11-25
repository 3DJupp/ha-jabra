# Changelog

## 0.2.0 (unreleased)

* Rebuilt as a Home Assistant custom integration (HACS) over Bluetooth LE. The MQTT bridge,
  the add-on and the Docker image are gone.
* Bluetooth discovery through the GN service `0xFEFF`, config flow with confirmation, manual setup
  and an options flow for the polling interval.
* Sensors: battery, firmware, hardware revision. Device info with serial number and versions.
* Finds the headset by serial number although its private Bluetooth address rotates.
* Connect, read, disconnect: no permanent link, nothing is written to the headset.
* Jabra brand images bundled (HA 2026.3+), diagnostics with redacted serial and address.
* GNP codec prepared for busylight, renaming and noise control; not used until verified.

## 0.1.0 (never released)

* MQTT bridge around jabridge with a Home Assistant add-on. Replaced by 0.2.0.
