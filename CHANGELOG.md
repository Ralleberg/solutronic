# Changelog

## 2.0.2

- Fix `UnicodeDecodeError` before HTML parsing when older firmware sends Western
  European bytes without a usable charset. Preserve normal HTTP charset and
  UTF-8 decoding; on decode failure, reuse the response body with Windows-1252
  and ISO-8859-1 fallbacks without another request or dropped bytes.
- Add HTTP byte-replay tests for issue #6 setup, polling, German readings,
  existing English legacy pages and newer tables. Preserve sensor identity and
  saved energy state. Verified with an encoded version of the supplied HTML and
  the reported traceback; physical verification on Pocket74's setup is pending.
- Individual RS485 slave support remains outside this patch. The new captures
  contain binary port-33330 traffic, not HTTP pages or HTML measurement mappings.

## 2.0.1

- Parse German legacy SOLPLUS labels and the spaced `FW-Release` metadata header
  from issue #6's SOLPLUS 55 / firmware 2.65 HTML. Preserve English legacy parsing,
  modern tables, sensor identity, and persisted energy state. The sample reports
  AC power without individual phases; do not invent phase or slave
  measurements. Verified against user-supplied HTML, pending hardware confirmation.

## 2.0.0

- Allow manual removal of obsolete Solutronic devices and their stale entities
  from HA's device page. Protect the current device, current sensor IDs, disabled
  current sensors, loaded entities, and entities owned by other entries/integrations.
- Add read-only Solutronic UDP discovery during setup and after HA startup when
  the integration is loaded, with manual IP fallback and HTTP validation before
  creating an entry. Retain IP-based identity and skip already configured devices.
- Fetch telemetry and device metadata from the same HTTP response.
- Persist the derived energy counter, daily baseline and known sensor capabilities
  using atomic, batched Home Assistant storage writes.
- Keep valid energy values through partial responses and integration reloads.
- Reject non-finite numeric telemetry and negative energy readings; avoid summing
  incomplete phase data as if it were total AC power.
- Fix options-flow compatibility with newer Home Assistant, preserve unrelated
  options and validate polling settings.
- Use HA-managed entry reloads for settings changes and avoid reloads caused by
  metadata updates.
- Link to the discovered inverter port/path and expose the device serial number
  in its dedicated registry field.
- Add redacted diagnostics with connection health and last successful update.
- Add regression tests and a GitHub Actions compatibility matrix, with code
  formatting and lint checks.

Existing config entry versions, sensor unique IDs, names, units and state classes
are preserved. The existing complete-outage fallback remains unchanged. No new
inverter model support is claimed by this update.
