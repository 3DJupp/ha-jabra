# CLAUDE.md

Project: **ha-jabra** (Python package `jabra2mqtt`). Bridges a local `jabridge` service
(Jabra headsets on Linux, JSON-RPC over a Unix socket) to Home Assistant via MQTT discovery.
Read `docs/ARCHITECTURE.md` first, then `docs/PLAN.md` for the roadmap.

## Commands

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy
pytest                      # unit tests, fake jabridge socket, in-process MQTT broker (amqtt)
```

All of these must pass before a commit. CI runs them on Python 3.11 to 3.13.

## Safety rules (never relax without the owner's explicit decision)

1. Never install firmware and never call reset methods (`device.reset*`, `firmware*`). There is a
   test that fails if the bridge calls them.
2. Writes only for settings jabridge reports as editable AND `support.state == available`, with the
   complete `target` and the previous value from the latest `settings.list`.
3. Never retry a write automatically. After an error or timeout, read state again.
4. Ignore retained MQTT command messages (they would replay old writes).
5. Do not commit Jabra binaries, APKs, installers or firmware files. Exception: the Jabra logo files in
   `assets/brand/` (permission from Jabra, see THIRD_PARTY_NOTICES.md). Analysis notes go into
   `docs/` as text, with no vendor code pasted in.
6. The jabridge socket is unauthenticated. Never expose it on a network.

## Conventions

* Python 3.11+, asyncio, strict mypy, ruff (line length 100).
* Test fixtures in `tests/conftest.py` are synthetic and follow the field names in jabridge's
  `daemon/ipc/handler.go`. Replace them with captured data once real hardware output exists.
* Keep `version` in `pyproject.toml`, `src/jabra2mqtt/__init__.py` and `jabra2mqtt/config.yaml`
  identical; the release workflow checks it.
* Home Assistant discovery uses `default_entity_id`, not the deprecated `object_id`.
* Docs and README are English. The owner (Dominic) speaks German; answer him in German.

## Not verified on hardware

Nothing here has run against a real Jabra device or a real Home Assistant OS yet. See
`docs/HARDWARE_TESTING.md` for the checklist and record results there.
