# Regression tests

Run these tests in an isolated Python environment with Home Assistant and
Beautiful Soup installed, using a Python version supported by that HA release:

```sh
python -m unittest discover -s tests -v
```

The suite uses real Home Assistant coordinator, sensor, options-flow and storage
helpers. Config-entry manager calls and most inverter HTTP responses are mocked.
`test_http_encoding.py` serves controlled response bytes from a local loopback HTTP
server to exercise real aiohttp decoding, setup validation, and cached polling.
UDP sockets and network adapters are mocked, including the manufacturer's
documented discovery response. All storage writes use temporary directories;
no running HA installation or physical inverter is accessed. HTTP replay uses
only `127.0.0.1`; no LAN devices are contacted.

Coverage includes saved-counter upgrades and restarts, daily resets, missing
telemetry, outages, entity IDs and capability retention, metadata updates,
options reloads, scheduled saves and shutdown writes, endpoint retry behavior,
invalid numeric readings, incomplete phase data, redacted diagnostics, config
flow error handling, both existing HTML parsers, UDP reply validation, enabled
interface selection, discovery cancellation/socket cleanup, startup scheduling,
manual fallback, and discovery confirmation/HTTP validation. The English legacy
HTML is a synthetic fixture. The German SOLPLUS 55 / firmware 2.65 fixture is the
complete HTML supplied in [issue #6](https://github.com/Ralleberg/solutronic/issues/6),
preserving its spacing, HTML entities, and malformed markup. See
[fixtures/README.md](fixtures/README.md) for provenance and expected readings.
The encoding tests generate ISO-8859-1/Windows-1252 bytes from the existing
issue HTML; these are not captured HTTP responses. The reported traceback is
reproduced before the fix and covered after it. UTF-8, explicit charsets, HTTP
errors, unsupported pages, English legacy pages, and modern tables are covered.
Parser tests do not replace physical-inverter verification. Discovery still
needs a real-inverter smoke test.

Device-removal tests use HA's real device and entity registries in temporary
directories. They verify that user-approved legacy-device deletion removes only
its stale entities, while preserving the active device and sensor IDs, including
disabled current sensors and loaded legacy entities.

The GitHub Actions matrix uses HA 2024.1.6/Python 3.11,
2024.6.4/Python 3.12, and 2026.10.0/Python 3.14. For 2024.6.4, install
`josepy<2` alongside HA to satisfy its older ACME dependency at import time.

Lint and formatting checks use Ruff 0.17.0 and the settings in `pyproject.toml`:

```sh
ruff check custom_components tests
ruff format --check custom_components tests
```
