# Protocol notes

Findings for a native Home Assistant integration (no MQTT, no jabridge daemon). Text notes only; no
vendor code is copied into this repository.

## Sources

| Source | License | Used for |
| --- | --- | --- |
| npm `@gnaudio/jabra-properties-definition` 14.8.0 (GN Audio) | Apache-2.0 | Read/write recipes for ~435 device properties |
| jabridge (Watchdog0x) | Apache-2.0 | GNP framing over USB HID, device detection |
| Jabra Sound+ 5.21 for Android, bundled device definition JSON | Jabra EULA | Device names and feature flags (facts only) |
| developer.jabra.com | Jabra SDK license | Overview only; the SDKs themselves are not used |

The official Jabra SDKs (.NET, JS, JabraCLI) are not used: their license forbids redistribution
outside a "Developer Application", derivative works and use with copyleft software, and JS/.NET
expect a partner key in production. JabraCLI on Linux is x64 only.

## Evolve2 85

* Internal name "loki". USB product ids `0x24B9` (UC) and `0x24BB` (MS), vendor `0x0B0E`.
  `0x24BA` appears for the UC "Data" variant (jLink firmware demo).
* Feature flags in Sound+: renaming supported, manual busylight supported, firmware update
  supported, single battery, protocol GNP, dongle Jabra Link 380.

## Properties relevant for Home Assistant

GNP command/subcommand pairs from the Apache-2.0 property definitions (read and write unless noted):

| Property | GNP | Value |
| --- | --- | --- |
| `deviceName` (asset tag) | 19 / 91 | UTF-8, length prefixed |
| `bluetoothName` | 19 / 86 | UTF-8, null terminated |
| `busyStatePresence` | 18 / 8 | bool; write sends a presence/busy object |
| `inCallBusyLightEnabled` | see definitions | bool |
| `batteryLevelV2` | 18 / 2 (read) | flags byte, primary level in percent, ... |
| `isBatteryLow` | see definitions | bool |
| `ancMode` | 19 / 135 | off, anc, hearThrough, hearThroughMix |
| `hearThroughLevel`, `sidetoneEnabled`, `sidetoneLevel` | see definitions | |
| `firmwareVersion` | read only | string |
| `gatt.batteryLevel` | standard GATT 180F / 2A19 | percent, read and notify |

Not found: any PIN or passkey property. Firmware update properties exist but stay out of scope
(safety rule 1).

## Transports

* **USB HID** (cable or Link dongle): GNP framed in HID reports, as implemented by jabridge.
* **Bluetooth**: Sound+ contains a GNP communicator for BLE (GATT service with a GNP data
  characteristic, notifications enabled) and an RFCOMM client (SPP UUID plus Qualcomm-range vendor
  UUIDs `00001107-D102-11E1-9B23-00025B00A5A5`, `00670067-D102-11E1-9B23-00025B00A5A5`).
  Which one the Evolve2 85 uses is open.

### nRF Connect result (Evolve2 85, 25.11.2026)

Connected over BLE without bonding. Primary services: Generic Access `0x1800`, Generic Attribute
`0x1801`, Device Information `0x180A`, Battery `0x180F` and `0xFEFF`. `0xFEFF` is the 16-bit member
UUID assigned to GN Netcom (Jabra), so it is the candidate for GNP over BLE. Battery level is
available through the standard Battery Service (`0x2A19`, read + notify).

Characteristics of `0xFEFF` (no bonding needed to see them):

| Characteristic | Properties | Likely role |
| --- | --- | --- |
| `8b5b80c0-ac6d-11e4-baef-0002a5d5c51b` | indicate, read, write, write without response | GNP request/response channel |
| `cacdf71a-fbe7-412b-91ec-045d2aeb7950` | indicate | second GNP channel or events |
| `80405498-28ed-4022-924f-900acb30ff10` | notify | events |

The first two UUIDs also appear as string constants in Sound+, which supports the GNP-over-BLE
reading. Device Information (`0x180A`) offers serial, manufacturer, system id, firmware and hardware
revision (read).

Open: the exact GNP framing over BLE (jabridge's USB frame is `dst src seq flags|len class op
payload` after the HID report id, host destination `0x08`, query flag `0x40`) and whether writes
need bonding. First test is a read-only battery query (class `0x12`, op `0x02`).

### Earlier plan for the live check

With nRF Connect on a phone (Sound+ closed): connect to the Evolve2 85 and record all GATT services
and characteristics with their properties (read, write, notify). A vendor service with a
write + notify characteristic means GNP over BLE, which Home Assistant can reach through its own
Bluetooth stack and ESPHome Bluetooth proxies (active connections).
