<p align="center">
  <img src="https://github.com/Ralleberg/solutronic_inverter/blob/main/custom_components/solutronic_inverter/banner.png?raw=true" width="800" alt="Solutronic Inverter Banner">
</p>

# Solutronic Inverter Integration for Home Assistant

This integration retrieves real-time operational data from **Solutronic SOLPLUS / Solutronic AG** solar inverters and exposes it as sensors in Home Assistant.  
The data can be used in dashboards, the Energy panel, automations, and history graphs.

> **Status:** Stable and under active improvement.

---

## ✨ Features

- Live power readings (PAC, PACL1, PACL2, PACL3)
- DC voltage and DC current measurements
- Daily and total energy production (ET / EG)
- Efficiency percentage (ETA)
- Automatically calculated **Total AC Power (PAC_TOTAL)**
- Configurable update interval via UI (5 / 10 / 30 seconds)
- Graceful fallback handling (no `unknown` values during temporary outages)
- Full compatibility with **Home Assistant Energy Dashboard**

---

## 🔧 Requirements

| Component | Minimum Version |
|----------|----------------|
| Home Assistant | **2024.5.0** or newer |
| Solutronic Inverter | Must expose a local web interface (`/solutronic/` on port `8888`) |

---

## 📦 Installation

### ✅ Recommended: Install via HACS

1. Open **HACS → Integrations**
2. Click **⋮ → Custom repositories**
3. Add: https://github.com/Ralleberg/solutronic_inverter as *Integration*
4. Search for **Solutronic Inverter** and install
5. Restart Home Assistant
6. Go to:
**Settings → Devices & Services → Add Integration → Solutronic**
7. Enter the IP address of your inverter

---

### 📁 Manual Installation

1. Download or clone this repository
2. Copy: as *Integration*
4. Search for **Solutronic Inverter** and install
5. Restart Home Assistant
6. Go to:
**Settings → Devices & Services → Add Integration → Solutronic**
7. Enter the IP address of your inverter

---

### 📁 Manual Installation

1. Download or clone this repository
2. Copy: custom_components/solutronic_inverter into your Home Assistant config folder at: /config/custom_components/solutronic_inverter
3. Restart Home Assistant
4. Add the integration via the UI

---

## ⚙️ Configuration

Only the **IP address** of the inverter is required.

**Example:**
192.168.1.1

You can change the update interval after installation:

**Settings → Devices & Services → Solutronic Inverter → Configure**

| Interval | Use Case |
|---------|-----------|
| **5 sec** | Live dashboard / active monitoring |
| **10 sec** | Recommended normal operation |
| **30 sec** | Reduced network / low power mode |

---