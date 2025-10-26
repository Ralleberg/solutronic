<p align="center">
  <img src="custom_components/solutronic/logo.png" width="200" alt="Solutronic Logo">
</p>

# Solutronic Solar Inverter Integration for Home Assistant

This integration allows Home Assistant to retrieve live data from Solutronic SOLPLUS inverters and expose them as sensors, including full support for the **Home Assistant Energy Dashboard**.

---

## ✨ Features

- Automatic or manual inverter IP discovery
- Live AC output power:
  - `PAC` (instant power)
  - `PAC_TOTAL` (sum of all available phases)
- Daily energy (ET) and lifetime energy (EG)  
  → **compatible with the Home Assistant Energy Dashboard**
- DC voltages, DC currents, and AC phase voltages
- Efficiency metrics and maximum power today
- Automatic extraction of:
  - **Model**
  - **Manufacturer**
  - **Firmware version**
- Stable fault-tolerance → sensors remain available even when the inverter temporarily goes offline (e.g., at night)

---

## 🏡 Supported Models

| Model | Tested | Notes |
|------|:------:|------|
| SOLPLUS 100 | ✅ | Fully supported |
| SOLPLUS 50 | ⚠️ | Expected to work |
| SOLPLUS 35 | ⚠️ | Expected to work |

If you have another model, please share an `index.html` / `stat.xml` sample for compatibility support.

---

## 📦 Installation

### Via [HACS](https://hacs.xyz/) (Recommended)

1. Open **HACS → Integrations**
2. Click **⋮** → **Custom repositories**
3. Add: https://github.com/Ralleberg/solutronic (Select *Integration*)
4. Search for **Solutronic Inverter** and install
5. Restart Home Assistant
6. Add the integration via:  
**Settings → Devices & Services → Add Integration → "Solutronic Inverter"**

### Manual Installation

Copy the folder:

**custom_components/solutronic**
into: **/config/custom_components/solutronic**


Restart Home Assistant.

---

## ⚡ Configuration

When adding the integration, enter the IP address of the inverter.

Examples (all accepted):

- `192.168.1.1`
- `http://192.168.1.1`

The integration **automatically normalizes the URL**.

---

## 📊 Energy Dashboard Setup

Add the following sensors:

| Sensor | Select as |
|---|---|
| `sensor.solutronic_dagens_produktion` | Solar production (kWh) |
| `sensor.solutronic_total_produktion` | Lifetime production (kWh) - ✅ Best results in energy dashboard |

Optionally add:

| Sensor | Use as |
|---|---|
| `sensor.solutronic_samlet_ac_effekt` (PAC_TOTAL) | Real-time solar power |

---

## 🐞 Troubleshooting

If sensors do not update:

1. Verify the inverter web page works in your browser
2. Ensure no firewall is blocking LAN access
3. Restart the integration:
   → **Developer Tools → Restart / Reload Integration**

---

## 🌐 Docker Network Mode Considerations

Automatic IP re-discovery (auto-reconnect) requires ARP visibility.

| Network Mode | Auto-Reconnect | Notes |
|---|---|---|
| Home Assistant OS | ✅ Works |
| Supervised | ✅ Works |
| Docker (host network) | ✅ Works |
| Docker (bridge network) | ⚠️ Disabled — MAC cannot be resolved |

If running in Docker bridge mode, the integration will still work,  
but **you must manually update the inverter IP** if it changes (e.g., DHCP renew).

---

## ❤️ Credits

Developed for the Home Assistant community.