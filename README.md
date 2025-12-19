<p align="center">
  <img src="https://raw.githubusercontent.com/Ralleberg/brands/refs/heads/master/custom_integrations/solutronic/logo.png" width="256" alt="Solutronic Logo">
</p>

# Solutronic Solar Inverter Integration for Home Assistant

This integration allows Home Assistant to retrieve live data from Solutronic SOLPLUS inverters and expose them as sensors — including **full support for the Home Assistant Energy Dashboard**.

---

## ✨ Features

- Automatic or manual inverter IP discovery
- Live AC output power:
  - `PAC` (instant power)
  - `PAC_TOTAL` (sum of all available phases)
- Daily (`ET`) and lifetime (`EG`) production sensors  
- Automatic energy integration (kWh) directly from inverter output  
  → **no manual helpers required**
- DC voltages, DC currents, and AC phase voltages
- Efficiency metrics and maximum daily power
- Automatic extraction of:
  - **Model**
  - **Manufacturer**
  - **Firmware version**
- Stable and fault-tolerant — sensors remain available even when the inverter is offline (e.g., at night)

---

## ⚡ Automatic Energy Calculation

This integration automatically creates an **energy counter sensor** based on the inverter’s reported AC output (`PAC_TOTAL`).

### 📈 Automatically Generated Sensor

| Property | Value |
|-----------|--------|
| **Name** | `Solutronic total produktion` |
| **Unit** | kWh |
| **Device class** | `energy` |
| **State class** | `total_increasing` |
| **Integration method** | Trapezoidal (accurate over time) |

The energy sensor appears automatically after installation and can be used **directly in Home Assistant’s Energy Dashboard** without creating a manual *Integration Helper*.

### 🔗 Unified Device

The energy counter is grouped under the same device as all other Solutronic sensors, so everything appears neatly under a single *Solutronic* device in the UI.

### 💡 Benefit

The integration performs the energy accumulation internally using Home Assistant’s own integration platform, ensuring accurate daily and lifetime tracking — even across restarts.

---

## 🏡 Supported Models

| Model | Tested | Notes |
|------|:------:|------|
| SOLPLUS 100 | ✅ | Fully supported |
| SOLPLUS 50 | ⚠️ | Expected to work |
| SOLPLUS 35 | ⚠️ | Expected to work |

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

## 📊 Energy Dashboard Setup

Add the following sensors:

| Sensor | Select as |
|---|---|
| `sensor.solutronic_total_produktion` | Solar production (kWh) ✅ Recommended |
| `sensor.solutronic_dagens_produktion` | Optional daily production |
| `sensor.solutronic_samlet_ac_effekt` | Real-time solar power (optional) |

---

## 🐞 Troubleshooting

If sensors do not update:

1. Verify the inverter’s web page works in your browser  
2. Ensure no firewall blocks access on your LAN  
3. Restart the integration via:  
   **Developer Tools → Restart / Reload Integration**

---

## 🌐 Docker Network Mode Notes

Auto-reconnect requires ARP visibility.

| Network Mode | Auto-Reconnect | Notes |
|---|---|---|
| Home Assistant OS | ✅ Works |
| Supervised | ✅ Works |
| Docker (host network) | ✅ Works |
| Docker (bridge network) | ⚠️ Disabled — MAC address not visible |

When running in Docker bridge mode, the integration will still work,  
but you must manually update the inverter IP if it changes (e.g., via DHCP).

---

## ❤️ Credits

Developed for the Home Assistant community.  
Created and maintained by [@Ralleberg](https://github.com/Ralleberg)