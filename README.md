<p align="center">
  <img src="custom_components/jabra/brand/logo.png" alt="Jabra" height="64">
</p>

<p align="center">
  <img src="assets/banner.png" alt="ha-jabra: Jabra headsets in Home Assistant over Bluetooth" width="100%">
</p>

<p align="center">
  <a href="https://github.com/3DJupp/ha-jabra/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/3DJupp/ha-jabra/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://hacs.xyz"><img alt="HACS custom" src="https://img.shields.io/badge/HACS-custom-41BDF5"></a>
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2026.3%2B-blue">
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-green">
  <img alt="Status" src="https://img.shields.io/badge/status-alpha-orange">
  <a href="https://ko-fi.com/3djupp"><img alt="Ko-fi" src="https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=ko-fi&logoColor=white"></a>
  <a href="https://buymeacoffee.com/3djupp"><img alt="Buy Me a Coffee" src="https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black"></a>
</p>

# Jabra for Home Assistant

A custom integration that brings Jabra headsets into Home Assistant over **Bluetooth LE**. No MQTT,
no add-on, no cloud and no USB cable: Home Assistant finds the headset by itself, through its own
Bluetooth adapter or your ESPHome Bluetooth proxies.

Target device: **Jabra Evolve2 85**. Other Jabra headsets that advertise the GN Bluetooth service
(`0xFEFF`) are discovered too.

> **Status: alpha.** Tested with automated tests against a simulated headset. The Bluetooth services
> were confirmed on a real Evolve2 85 with nRF Connect, but the integration itself has not run on
> real hardware yet. Feedback welcome.

## What you get

| Entity | Type | Notes |
| --- | --- | --- |
| Battery | sensor | percent, standard Battery Service |
| Firmware | sensor | diagnostic, also shown on the device page |
| Hardware revision | sensor | diagnostic, disabled by default |

The device page also shows serial number, firmware and hardware version.

Planned once verified on hardware (see [docs/PROTOCOL_NOTES.md](docs/PROTOCOL_NOTES.md)): busylight,
renaming the headset, noise control (ANC / HearThrough), sidetone.

## Install

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=3DJupp&repository=ha-jabra&category=integration)

1. In HACS, add `https://github.com/3DJupp/ha-jabra` as a custom repository (type: Integration) and
   install **Jabra**.
2. Restart Home Assistant.
3. Switch the headset on. Home Assistant shows it under **Settings → Devices & services →
   Discovered**. Or add it by hand: **Add integration → Jabra**.

Manual install: copy `custom_components/jabra` into your `config/custom_components/` folder.

Requirements: Home Assistant 2026.3 or newer (for the bundled brand images) and a working Bluetooth
setup (a local adapter or an ESPHome Bluetooth proxy with active connections enabled).

## How it works

* The headset advertises the GN service `0xFEFF`. Home Assistant's Bluetooth integration matches it
  and starts discovery.
* The headset uses a **rotating private address**. The integration therefore identifies it by its
  **serial number** (read once during setup) and finds it again after the address has changed.
* Every polling interval (default 15 minutes, configurable) it connects for a moment, reads the
  standard GATT values (battery, firmware, serial) and disconnects. It never keeps the link open, so
  Jabra Sound+ and your Link dongle keep working in between.
* After a failed update, the next advertisement of the headset triggers an early update (at most
  every two minutes), so values come back soon after you switch the headset on.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| Polling interval | 15 min | 5 to 1440 minutes. Each update is one short connection. |

## Safety by design

* The integration only **reads** standard Bluetooth characteristics. It writes nothing to the
  headset.
* No firmware updates and no factory resets, ever.
* Busylight, renaming and noise control will only be added after the protocol has been verified on
  real hardware with read-only tests, and never with automatic retries of a write.

## Limitations

* While another device holds the headset's Bluetooth LE connection (for example Jabra Sound+ on a
  phone), Home Assistant cannot connect and the entities become unavailable until the next update.
* PIN assignment is not possible: no such setting was found in the protocol.
* Firmware updates stay a manual step in Jabra Direct or Jabra Sound+.

## Troubleshooting

* **Not discovered:** check that the headset is on and in range of an adapter or proxy, and that the
  proxy allows active connections.
* **Unavailable:** close Jabra Sound+ on your phone and wait for the next update, or reload the
  integration.
* **Debug logs:**
  ```yaml
  logger:
    logs:
      custom_components.jabra: debug
  ```
* Diagnostics (serial number and address removed) can be downloaded from the device page.

## Support the project

This integration is a hobby project. If you like it, you can say thanks with a coffee:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/3djupp)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-3djupp-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/3djupp)

Bug reports with diagnostics and debug logs help just as much.

## Development

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check . && mypy && pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md).

## Credits and disclaimer

Protocol knowledge comes from GN Audio's Apache-2.0 property definitions
(`@gnaudio/jabra-properties-definition`) and from [jabridge](https://github.com/Watchdog0x/jabridge)
by Watchdog0x (Apache-2.0). This is an independent community project, not affiliated with or
endorsed by Jabra or GN Audio A/S. Jabra is a trademark of GN Audio A/S; the Jabra logo in
`custom_components/jabra/brand/` is used with permission and stays the property of GN Audio. The
ha-jabra banner and icon are original designs. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Licensed under the [Apache License 2.0](LICENSE).
