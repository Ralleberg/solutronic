<p align="center">
  <img src="custom_components/solutronic_inverter/logo.png" width="200" alt="Solutronic Logo">
</p>

# Solutronic Solar Inverter Integration for Home Assistant

Denne integration gør det muligt at hente data direkte fra Solutronic SOLPLUS invertere og vise dem som sensorer i Home Assistant, inkl. understøttelse af Energy Dashboard.

---

## ✨ Funktioner

- Automatisk eller manuel konfiguration af inverter IP-adresse
- Live AC-effekt (PAC og samlet total PAC_TOTAL)
- Energi i dag (ET) og total energi (EG) — **kompatibel med Home Assistant Energy Dashboard**
- DC spændinger, DC strømme, netspændinger pr. fase
- Effektivitet og maksimal effekt i dag
- Automatisk udtræk af:
  - **Model**
  - **Manufacturer**
  - **Firmware-version**
- Stabil fejl-tolerance → data forbliver synligt selv hvis inverteren midlertidigt ikke svarer

---

## 🏡 Understøttede modeller

| Model | Testet | Noter |
|------|:------:|------|
| SOLPLUS 100 | ✅ | Fuldt understøttet |
| SOLPLUS 50 | ⚠️ | Forventes at virke |
| SOLPLUS 35 | ⚠️ | Forventes at virke |

Hvis du har en anden model, del gerne en `index.html`/`stat.xml` så tilføjer vi understøttelse.

---

## 📦 Installation

### Via [HACS](https://hacs.xyz/) (Anbefalet)

1. Åbn **HACS → Integrations**
2. Tryk på **⋮** → **Custom repositories**
3. Tilføj: https://github.com/Ralleberg/solutronic_inverter som *Integration*
4. Søg efter **Solutronic Inverter** og installer
5. Genstart Home Assistant
6. Tilføj integrationen via:
**Indstillinger → Enheder & Tjenester → Tilføj integration → "Solutronic Inverter"**

### Manuel installation

Kopiér mappen: custom_components/solutronic_inverter
til: /config/custom_components/solutronic_inverter

Genstart Home Assistant.

---

## ⚡ Konfiguration

Når du tilføjer integrationen, angiv IP-adressen på din inverter.

Du kan skrive:
192.168.1.1
192.168.1.1:8888
http://192.168.1.1/solutronic/

Integrationens URL-håndtering **normaliserer automatisk** formatet.

---

## 📊 Energy Dashboard Opsætning

Tilføj følgende sensorer:

| Sensor | Vælg som |
|---|---|
| `sensor.solutronic_dagens_produktion` | Solar production (kWh) |
| `sensor.solutronic_total_produktion` | Lifetime total (kWh) |

`PAC_TOTAL` kan tilføjes som **Real-time solar power**.

---

## 🐞 Fejlfinding

Hvis sensorer ikke opdaterer:

1. Kontroller at inverterens web-interface svarer i browseren
2. Tjek firewall på din computer / router
3. Genstart integrationen via:
   Developer Tools → **Reload Integration**

---

## 🤝 Bidrag

PR’s er meget velkomne!  
Især:
- Nye modeller
- Oversættelser
- Lovelace UI-kort

---

## ❤️ Credits

Udviklet til det åbne Home Assistant community.

