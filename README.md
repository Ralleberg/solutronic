<p align="center">
  <img src="https://raw.githubusercontent.com/Ralleberg/brands/refs/heads/master/custom_integrations/solutronic/logo.png" width="256" alt="Solutronic">
</p>

# Solutronic for Home Assistant

<p align="center">
  <a href="https://github.com/Ralleberg/solutronic/releases/latest">
    <img src="https://img.shields.io/github/v/release/Ralleberg/solutronic?style=for-the-badge&amp;label=Release&amp;color=007ec6" alt="Latest published GitHub release">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-97ca00?style=for-the-badge" alt="License: MIT">
  </a>
  <a href="https://github.com/Ralleberg/solutronic/releases">
    <img src="https://img.shields.io/github/downloads/Ralleberg/solutronic/total?style=for-the-badge&amp;label=Asset%20downloads&amp;color=e05d44" alt="GitHub release asset downloads">
  </a>
  <a href="https://www.home-assistant.io/">
    <img src="https://img.shields.io/badge/Home%20Assistant-Integration-41bdf5?style=for-the-badge&amp;logo=homeassistant&amp;logoColor=41bdf5" alt="Home Assistant integration">
  </a>
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=Ralleberg&amp;repository=solutronic&amp;category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open the Solutronic repository in HACS">
  </a>
</p>

A local Home Assistant integration for Solutronic SOLPLUS solar inverters. Monitor
solar production, AC and DC measurements, and device information directly from
the inverter's built-in web interface, with production sensors ready for the
Home Assistant Energy Dashboard.

**v2.0.1** fixes German legacy HTML parsing for the supplied SOLPLUS 55 / firmware
2.65 page. Verified against the user's HTML; physical hardware verification is
pending. It retains the automatic discovery, saved energy-counter state,
diagnostics, and obsolete-device removal introduced in v2.0.0. See the
[v2.0.1 changelog](CHANGELOG.md#201) for details. The release badge above follows
the latest published GitHub release.

[Installation](#installation) · [Configuration](#configuration) ·
[Sensors](#sensors) · [Energy Dashboard](#energy-dashboard) ·
[Troubleshooting](#troubleshooting) · [Changelog](CHANGELOG.md)

## Requirements

- A Solutronic inverter exposing a supported built-in HTTP web interface.
- An IPv4 network connection from Home Assistant to the inverter.
- HACS for the repository button and HACS installation, or use manual installation.

Discovery additionally requires UDP broadcasts to reach the inverter's local
subnet. Manual IP setup remains available when broadcast discovery is unavailable.

## Features

- **Automatic discovery:** find compatible Solutronic devices on the local
  network during setup, with manual IP entry always available.
- **Local monitoring:** read inverter telemetry over HTTP without a cloud account.
- **Energy tracking:** daily production, inverter lifetime energy, and a derived
  total production counter that retains its state across Home Assistant restarts.
- **Supported measurements:** total and per-phase AC power, grid voltage/current,
  DC voltage/current, efficiency, and maximum daily power where available.
- **Efficient polling:** sensor readings and device metadata share one HTTP fetch
  during a normal successful update. Choose a 5, 10, or 30-second update interval.
- **Resilient readings:** retain known energy values through partial responses and
  temporary outages, and exclude invalid numeric telemetry.
- **Device information:** group sensors by inverter with model, firmware, serial
  number, and a link to the detected web interface.
- **Diagnostics:** download connection health and selected readings with IP
  addresses and serial numbers redacted.
- **Localized setup:** Danish, English, and German configuration dialogs.
- **Legacy-device cleanup:** remove obsolete device registrations from the device
  page while the current inverter and its entities remain protected.

## Installation

### HACS

Use the **Open HACS repository** button above to open Solutronic in your Home
Assistant instance, then download it, restart Home Assistant, and add the
integration. HACS must already be installed. To add the repository manually:

1. Open **HACS → menu → Custom repositories**.
2. Add `https://github.com/Ralleberg/solutronic` with category **Integration**.
3. Find **Solutronic** in HACS and download it.
4. Restart Home Assistant.
5. Open **Settings → Devices & Services → Add Integration** and select
   **Solutronic**.

See the [HACS custom repository guide](https://www.hacs.dev/docs/faq/custom_repositories/)
for details.

### Manual installation

1. Download the repository and copy `custom_components/solutronic` into your Home
   Assistant configuration directory:

   ```text
   /config/custom_components/solutronic/
   ```

2. Restart Home Assistant.
3. Add **Solutronic** under **Settings → Devices & Services → Add Integration**.

### Updating an existing installation

Update through HACS, or replace the integration folder for a manual installation,
then restart Home Assistant. Keep the existing integration entry.

Version **2.0.1** preserves config entry versions, sensor unique IDs, names, units,
state classes, and polling options. The derived energy counter is initialized
from the inverter's lifetime reading on its first start without saved state,
matching the previous behavior. Once saved, its state is restored on later starts.

## Configuration

### Automatic discovery

Adding the integration starts a search lasting about three seconds on Home
Assistant's enabled IPv4 network interfaces. Select a discovered inverter or
choose **Enter IP manually**. If the search finds no devices or cannot run, the
manual IP form opens automatically.

The selected device must return valid readings through the integration's HTTP
connection check before it is added. A discovery response alone does not confirm
that its model or firmware is supported.

Once Home Assistant loads the integration, it also searches once after startup
and offers newly discovered devices for confirmation under **Devices & Services**.
Devices already configured at the same IP address are skipped. Installing the
files through HACS alone does not guarantee that Home Assistant loads the
integration before the first setup; use **Add Integration → Solutronic** to start
that first search.

Discovery uses the manufacturer's read-only UDP broadcast on port **33330**, as
specified in [Solutronic protocol B12, section 6.4](https://akkudoktor.net/uploads/short-url/ng5902hjGnFAhPhbrDOjoA9tCGg.pdf).
The search sends two requests per enabled interface and closes its sockets when
finished or cancelled. It does not change inverter settings.

Broadcasts normally stay within the local subnet. VLANs, firewalls, container
networking, a busy UDP port, or firmware without the discovery protocol may
prevent a device from being found. Use manual setup in those cases.

### Manual IP entry

Enter an IPv4 address, for example `192.168.1.50` or `http://192.168.1.50`.
URL-style input is normalized to the IP address. The integration detects the
working HTTP endpoint on ports **8888** or **80**, using `/solutronic/` or `/`.

The inverter must be reachable from Home Assistant. Manual setup also works
across routed networks where broadcast discovery cannot reach the device.
Because entry identity is based on IP, a DHCP reservation is useful for keeping
the inverter at the same address.

### Polling interval

Open the integration's options under **Settings → Devices & Services** to choose
**5**, **10**, or **30 seconds**. The default is **5 seconds**. Changing the interval
reloads the entry through Home Assistant; device metadata updates do not trigger
a reload.

## Sensors

Sensors are grouped under the inverter's device. Names are in English by default
and can be renamed in Home Assistant. Available measurements depend on the model,
firmware, and values returned by its web interface.

| Sensor | Unit | Description |
| --- | --- | --- |
| Total AC power | W | Combined AC output power |
| L1 / L2 / L3 power | W | Output power for each reported phase |
| Grid voltage L1 / L2 / L3 | V | Voltage for each reported phase |
| Grid current L1 | A | Reported AC current |
| DC voltage 1 / 2 / 3 | V | Voltage for each reported DC input |
| DC current 1 / 2 / 3 | A | Current for each reported DC input |
| Daily production | kWh | Energy produced today |
| Inverter total | kWh | Lifetime energy reported by the inverter; diagnostic entity |
| Total production | kWh | Derived total energy for the Energy Dashboard |
| Maximum power today | W | Highest reported AC output power today |
| Efficiency | % | Reported inverter efficiency |

During a successful first setup, only reported measurements are created.
Previously reported capabilities are saved, so a later restart during an outage
or a partial response retains the known sensor set. If no capabilities are known
and the inverter is offline at setup, the integration retains its historical
fallback sensor set.

Invalid numeric values, including non-finite readings and negative energy values,
are excluded. Missing energy fields retain their last valid readings. If a known
AC phase is missing, total AC power is unavailable unless the inverter supplies a
valid aggregate power reading.

During a complete connection outage, known instantaneous measurements fall back
to zero and energy readings retain their last known values. These zeros are
fallback values, not confirmation that the inverter is producing no power.

## Energy Dashboard

Select the inverter's **Total production** sensor as its solar energy source in
the [Home Assistant Energy Dashboard](https://www.home-assistant.io/docs/energy/solar-panels/).
It uses **kWh**, device class **energy**, and state class **total_increasing**, so
an additional integration helper is not required.

Choose the entity belonging to your inverter; its entity ID depends on Home
Assistant's naming and any customizations. **Daily production** and **Total AC
power** are useful for dashboard cards. Use one production energy source per
inverter to avoid counting the same production twice.

The derived counter follows increases in daily energy readings and keeps a
separate saved total and daily baseline for each inverter. State is written
atomically, with saves batched over up to **60 seconds** and flushed during an
integration reload or normal Home Assistant shutdown.

An abrupt power loss can lose the latest unsaved readings. Extended outages
spanning a daily reset may leave production uncounted because the inverter no
longer exposes the missed daily readings.

## Model and firmware compatibility

The integration includes parsers for Solutronic's table-based web pages and the
legacy SOLPLUS basic-menu HTML layout. Compatibility depends on the actual
firmware and page format, as well as the model name.

| Model | Compatibility notes |
| --- | --- |
| SOLPLUS 100 | Primary supported model |
| SOLPLUS 55, firmware 2.65 | German basic-menu HTML tested with the complete user-supplied sample from [issue #6](https://github.com/Ralleberg/solutronic/issues/6); physical hardware verification pending |
| SOLPLUS 50 / 35 | Requires a supported web layout; hardware compatibility was not verified by this update |
| SOLPLUS 25 | Legacy HTML parsing is available, including the firmware 2.53 layout; compatibility with other firmware requires verification |

The German legacy page from issue #6 supplies AC power, grid voltage, DC voltage,
daily energy, and lifetime energy. Its `FW-Release` header also supplies model,
serial number, and firmware. Missing currents, efficiency, maximum power, and
phase-specific measurements are not inferred. Existing English legacy pages and
newer telemetry tables remain supported.

**RS485 scope:** the supplied page shows one inverter identity and one set of
readings. This parser fix does not expose individual SOLPLUS 50/35 slaves or
establish whether the displayed values include other inverters. Per-slave pages
and their selection paths or parameters are needed before adding that support.

German legacy parsing is verified against the user's HTML, including its original
malformed table markup. The English legacy fixture is synthetic. Neither replaces
physical-inverter verification; UDP discovery also still needs hardware testing.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Discovery finds nothing | Try manual IP entry. Check HA's selected network interfaces, subnet, firewall, and UDP port 33330. |
| Manual connection fails | Open the inverter's web page and verify that Home Assistant can reach its IP on HTTP port 8888 or 80. |
| The device responds but setup rejects it | Its page did not provide valid supported telemetry. Include model, firmware, and a sanitized page sample in a bug report. |
| Some measurements are missing | The firmware may not expose them, or the current response may be incomplete. Only supported values are created after a successful first setup. |
| Instantaneous readings stay at zero | Check connection diagnostics to distinguish outage fallback values from live zero readings. |

To retry a configured entry, use **Reload** from its menu under **Settings →
Devices & Services**, or restart Home Assistant.

### Removing an old duplicate device

Earlier integration versions used the inverter's IP address as the device
identifier. Later versions use the integration entry ID. An upgrade from those
older versions can leave an obsolete device and its old entities under the same
integration entry.

After installing this update and restarting Home Assistant:

1. Open **Settings → Devices & Services → Devices** and select the old Solutronic
   device.
2. Check that its entities are the obsolete ones you want to remove.
3. Choose **Delete** from the device's menu and confirm.

Home Assistant removes the selected obsolete device and its associated old
entities. The integration permits this only when the device does not contain
current or loaded entities. The current device remains protected even while the
inverter is offline, as do disabled current sensors and entities belonging to
other entries or integrations. No automatic device deletion occurs on startup.

Keep the working integration entry: deleting that entry would remove the active
inverter too. If deletion is rejected, the selected device still matches a
protected registration or contains protected entities; include diagnostics and
the affected entity IDs in an issue report.

### Reporting an issue

Open an issue in the [GitHub issue tracker](https://github.com/Ralleberg/solutronic/issues)
with the model, firmware version, Home Assistant version, integration version,
and a description of the problem. For a configured entry, download diagnostics
from its menu under **Settings → Devices & Services → Solutronic**.

Diagnostics include connection status, last successful update, failure count,
detected endpoint port/path, supported sensors, selected readings, and energy
counter state. IP addresses and serial numbers are redacted; raw inverter HTML
is not included. If you attach a web-page sample separately, remove identifying
information first.

## Development

The regression suite covers energy storage and restarts, outages, partial
responses, sensor identity, options, HTTP endpoint handling, both HTML parsers,
and UDP discovery and config-flow behavior. Network responses and sockets are
mocked; storage tests use temporary directories.

Tests also cover manual legacy-device removal using Home Assistant's real device
and entity registries, including protection of current and disabled entities.

The 80-test suite has passed locally on Home Assistant **2024.1.6**, **2024.6.4**,
and **2026.10.0**. GitHub Actions is configured to run the same compatibility
matrix, along with Ruff lint and formatting checks. See
[tests/README.md](tests/README.md) for commands and dependency details, and
[CHANGELOG.md](CHANGELOG.md) for changes.

The asset-download badge counts GitHub release assets. It excludes HACS
installations and GitHub-generated source archives.

## License

Distributed under the [MIT License](LICENSE).

## Maintainer

Created and maintained by [@Ralleberg](https://github.com/Ralleberg) for the Home
Assistant community.
