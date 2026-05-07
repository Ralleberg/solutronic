<p align="center">
  <img src="https://raw.githubusercontent.com/Ralleberg/brands/refs/heads/master/custom_integrations/solutronic/logo.png" width="256" alt="Solutronic Logo">
</p>

# Solutronic Solar Inverter Integration for Home Assistant

This integration allows Home Assistant to retrieve live data from Solutronic SOLPLUS inverters and expose supported values as Home Assistant sensors, including Energy Dashboard compatible production sensors.

![HACS](https://img.shields.io/badge/HACS-custom-blue)

---

## ✨ Features

- Manual inverter IP setup with automatic endpoint detection on common Solutronic ports/paths
- Live AC output power, including total AC power
- Daily, inverter lifetime, and derived total production sensors
- Energy Dashboard compatible energy sensors
- DC voltage/current and grid voltage/current sensors where reported by the inverter
- Efficiency metrics and maximum daily power
- Automatic extraction of:
  - **Model**
  - **Serial number**
  - **Manufacturer**
  - **Firmware version**
- Model-aware entity setup: sensors that are not reported by the inverter are not created on new setups
- Stable fallback behavior during temporary inverter outages

---

## ⚡ Energy Dashboard Sensor

This integration exposes a stable lifetime production sensor based on the inverter telemetry.

### 📈 Recommended Sensor

| Property | Value |
|-----------|--------|
| **Name** | `Solutronic Total production` |
| **Unit** | kWh |
| **Device class** | `energy` |
| **State class** | `total_increasing` |
| **Source** | Inverter telemetry with restart-safe fallback |

The sensor appears automatically after installation and can be used **directly in Home Assistant’s Energy Dashboard** without creating a manual helper.

### 🔗 Unified Device

The energy counter is grouped under the same device as all other Solutronic sensors, so everything appears neatly under a single *Solutronic* device in the UI.

### 💡 Benefit

The integration keeps the lifetime sensor stable across temporary inverter outages and Home Assistant restarts.

---

## 🏡 Supported Models

| Model | Tested | Notes |
|------|:------:|------|
| SOLPLUS 100 | ✅ | Fully supported |
| SOLPLUS 50 | ⚠️ | Expected to work |
| SOLPLUS 35 | ⚠️ | Expected to work |
| SOLPLUS 25 | ✅ | Supported with firmware 2.53 legacy HTML |

If you own another model, please share an `index.html` or `stat.xml` sample to improve compatibility.

---

## 📦 Installation

### Via [HACS](https://hacs.xyz/) (Recommended)

1. Open **HACS → Integrations**
2. Click **⋮ → Custom repositories**
3. Add: `https://github.com/Ralleberg/solutronic` (type: *Integration*)
4. Search for **Solutronic** and install
5. Restart Home Assistant
6. Add the integration via:  
   **Settings → Devices & Services → Add Integration → “Solutronic”**

### Manual Installation

- Copy the folder:
- **custom_components/solutronic**
- into your Home Assistant config directory: 
- **/config/custom_components/solutronic**
- Restart Home Assistant.

---

## ⚡ Configuration

When adding the integration, enter the IP address of the inverter.

Examples (all accepted):

- `192.168.1.1`
- `http://192.168.1.1`

The integration **automatically normalizes the URL**.

---

## 📡 Sensors

Entity names are created in English by default. You can rename them manually in Home Assistant if you prefer local or custom names.

The integration only creates sensors for values reported by the inverter during setup. For example, a SOLPLUS 25 will not create L2/L3 sensors if the inverter only exposes single-phase values.

Common sensors include:

| Sensor name | Description |
|---|---|
| `Total AC power` | Total current AC output power |
| `L1 power` | AC output power for phase L1 |
| `L2 power` | AC output power for phase L2, if reported |
| `L3 power` | AC output power for phase L3, if reported |
| `Grid voltage L1` | Grid voltage for phase L1 |
| `Grid voltage L2` | Grid voltage for phase L2, if reported |
| `Grid voltage L3` | Grid voltage for phase L3, if reported |
| `Grid current L1` | Grid current for phase L1, if reported |
| `DC voltage 1` | DC input voltage 1 |
| `DC voltage 2` | DC input voltage 2, if reported |
| `DC voltage 3` | DC input voltage 3, if reported |
| `DC current 1` | DC input current 1 |
| `DC current 2` | DC input current 2, if reported |
| `DC current 3` | DC input current 3, if reported |
| `Daily production` | Energy produced today |
| `Inverter total` | Lifetime energy reported by the inverter |
| `Total production` | Stable total production sensor for Energy Dashboard use |
| `Maximum power today` | Highest AC output power today |
| `Efficiency` | Current inverter efficiency, if reported |

---

## 📊 Energy Dashboard Setup

Add the following sensors:

| Sensor | Select as |
|---|---|
| `sensor.solutronic_total_production` | Solar production (kWh) ✅ Recommended |
| `sensor.solutronic_daily_production` | Optional daily production |
| `sensor.solutronic_total_ac_power` | Real-time solar power (optional) |

---

## 🐞 Troubleshooting

If sensors do not update:

1. Verify the inverter’s web page works in your browser  
2. Ensure no firewall blocks access on your LAN  
3. Restart the integration via:  
   **Developer Tools → Restart / Reload Integration**
4. If old unsupported entities remain after an update, remove them manually from Home Assistant’s entity registry. Home Assistant does not always delete old registry entries automatically.

---

## ❤️ Credits

Developed for the Home Assistant community.  
Created and maintained by [@Ralleberg](https://github.com/Ralleberg)
