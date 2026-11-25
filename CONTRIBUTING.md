# Contributing

1. Use Python 3.14: `python3.14 -m venv .venv && . .venv/bin/activate`.
2. `pip install -r requirements_test.txt`, plus the bluetooth requirements (see the CI workflow).
3. Make your change with tests. `ruff check . && ruff format --check . && mypy && pytest` must pass.
4. Read the safety rules in `CLAUDE.md` before touching anything that talks to the headset.

Hardware reports are very welcome: which headset and firmware, which entities worked, and the
diagnostics download from the device page (serial number and address are removed automatically).
nRF Connect screenshots of the GN service `0xFEFF` help with new models.

Please do not attach Jabra firmware, installers or APKs to issues or pull requests.
