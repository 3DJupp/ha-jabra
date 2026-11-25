# Changelog

## 0.1.0 (unreleased)

* First version of the bridge: battery, charging, firmware, connection, busylight and editable
  settings from jabridge, published through MQTT discovery.
* Home Assistant add-on (`jabra2mqtt`) and Docker image with a bundled, pinned jabridge.
* Read-only mode, retained-command protection, no firmware or reset access by design.
* Tested with a fake jabridge and an in-process MQTT broker. Not yet verified on real hardware.
