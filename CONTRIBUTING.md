# Contributing

1. `pip install -e ".[dev]"`
2. Make your change with tests. `ruff check . && ruff format --check . && mypy && pytest` must pass.
3. Hardware reports are very welcome: follow `docs/HARDWARE_TESTING.md` and open an issue with the
   output of `jabridge debug` (check it before sharing) and which entities worked.

Please do not attach Jabra firmware, installers or APKs to issues or pull requests.
