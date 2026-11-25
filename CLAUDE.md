# CLAUDE.md

Project: **ha-jabra**, a Home Assistant custom integration (domain `jabra`, installed through HACS)
for Jabra headsets over Bluetooth LE. Code in `custom_components/jabra/`. Read
`docs/PROTOCOL_NOTES.md` first, then `docs/PLAN.md`.

## Commands

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt   # plus the bluetooth requirements, see .github/workflows/ci.yml
ruff check . && ruff format --check .
mypy
pytest                                  # Bluetooth is mocked: no adapter, no D-Bus, no headset
```

All of these must pass before a commit. CI also runs hassfest and the HACS validation.

## Safety rules (never relax without the owner's explicit decision)

1. Never install firmware and never send reset or firmware update commands. GNP class `0x0F` and
   all `firmwareUpdate*` properties are off limits.
2. Nothing writes to the headset until the GNP framing over BLE has been verified on real hardware
   with read-only queries. Writes then need an explicit entity action, a value validated against the
   last read, and a read-back afterwards.
3. Never retry a write automatically. After an error or timeout, read state again.
4. Connect, read, disconnect. Do not hold the BLE link open; other apps share the headset.
5. Do not commit Jabra binaries, APKs, installers or firmware files. Exception: the Jabra logo files
   in `custom_components/jabra/brand/` (permission from Jabra, see THIRD_PARTY_NOTICES.md).
   Analysis notes go into `docs/` as text, with no vendor code pasted in.

## Conventions

* Home Assistant 2026.3+ (brand images in `brand/`), Python 3.14 for tests, strict mypy, ruff
  (line length 100).
* The headset has a rotating private address. Identity is the serial number (`0x2A25`); the config
  entry unique id is the serial.
* `import voluptuous as vol` is fine: HA 2026.10+ maps it to probatio at import time.
* Avoid HA APIs that changed recently (for example `device_registry.async_get_device`); use
  `dr.async_entries_for_config_entry`.
* Keep `version` in `custom_components/jabra/manifest.json` and `pyproject.toml` identical; the
  release workflow checks it.
* Docs and README are English. The owner (Dominic) speaks German; answer him in German.

## Not verified on hardware

The GATT services and characteristics were confirmed on an Evolve2 85 with nRF Connect
(see `docs/PROTOCOL_NOTES.md`). The integration itself has not run against a real headset yet.
