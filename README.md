# CycloneShield 🌀 — Cyclone Impact & Infrastructure Vulnerability Forecaster

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Track 5 BRICS](https://img.shields.io/badge/Hackathon-Track%205%20BRICS-green.svg)]()

> **"Pre-landfall decisions, not post-landfall recovery."**

AI-powered predictive risk and vulnerability platform for the **"Build with AI: Code for Communities"** hackathon — Track 5 (BRICS / Bay of Bengal).

Powered by Google Earth Engine satellite feeds, real-time meteorological data, and Gemini multimodal reasoning.

---

## 🎯 Problem

When a cyclone like **Fani** (3 May 2019) strikes the Odisha coast with 175 km/h winds, disaster management authorities have ~72 hours. Current tools show track forecasts. They don't answer: *Which substations will flood? When will Hospital X lose power? Which road is the last evacuation route? When does insurance pay out?*

## 💡 Solution

CycloneShield runs **48 hours before landfall** and produces:
- 🌊 Storm surge flood maps (hourly, physics-informed)
- 🏥 Infrastructure exposure & cascade failure timeline
- 🚨 AI-generated evacuation advisories (EN / Hindi / Odia)
- 💰 Parametric insurance trigger signals
- 📡 Automated early-warning dispatch to district authorities

## 🖼️ Screenshots

*(Demo screenshots / GIF will be embedded here after Phase 6)*

## 🏗️ Architecture

```
IBTrACS Track → Holland Wind Field → Storm Surge (bathtub)
                                   ↘
GPM IMERG Rainfall → HAND/Flow     → Exposure Analysis → Cascade Graph
                                   ↗                    ↓
Sentinel-1 SAR (Validation)        ← OSM Infrastructure  → Gemini Advisories
                                                          ↓
                                                   FastAPI Backend
                                                          ↓
                                              React + MapLibre Frontend
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full Mermaid diagram.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node 18+
- Google Earth Engine account (free, non-commercial)
- Gemini API key (free tier)

### Setup
```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/cycloneshield.git
cd cycloneshield

# 2. Install deps and configure
make setup

# 3. Authenticate GEE (one-time)
earthengine authenticate

# 4. Copy env and fill in keys
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# 5. Run full pipeline (offline data prep)
make data

# 6. Start backend
make api

# 7. Start frontend dev server
make web
```

### Demo (no GEE needed)
The frontend runs fully in static mode from pre-cached data:
```bash
cd frontend && npm install && npm run dev
# Open http://localhost:5173
```

## 📊 Validation Results (Cyclone Fani 2019)

*(Numbers will be populated from metrics.json after Phase 2)*

| Metric | Value |
|--------|-------|
| Flood Extent IoU | TBD |
| Precision | TBD |
| Recall | TBD |
| F1 Score | TBD |
| Track Error vs IMD | TBD km |

## 📁 Repository Structure

```
cycloneshield/
├── config/scenarios/fani_2019.yaml   # Scenario config
├── pipeline/                          # Offline data pipeline
│   ├── 01_fetch_track.py             # IBTrACS track fetch
│   ├── 02_wind_field.py              # Holland wind field
│   ├── 03_surge_model.py             # Storm surge model
│   ├── 04_rainfall_model.py          # Rainfall flood model
│   ├── 05_sar_validation.py          # SAR validation
│   ├── 06_osm_infra.py               # OSM infrastructure
│   ├── 07_exposure.py                # Exposure analysis
│   ├── 08_cascade.py                 # Cascade failure simulation
│   ├── 09_insurance.py               # Parametric insurance
│   └── 10_advisories.py              # Gemini advisories
├── backend/                           # FastAPI backend
├── frontend/                          # React + Vite frontend
├── data/processed/                    # Pre-computed outputs (git-committed)
├── docs/                              # Documentation
└── tests/                             # Test suite
```

## 🌍 BRICS Interoperability

CycloneShield is designed as a **digital public good**:
- Region-agnostic: add any cyclone basin scenario via `config/scenarios/<name>.yaml`
- All data sources are open (IBTrACS, OpenStreetMap, GEE non-commercial, Open-Meteo)
- Model artifacts are freely shareable
- Deployable on free-tier infrastructure

## ⚠️ Limitations

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for honest scientific caveats, including:
- Simplified surge model (no full hydrodynamic solver)
- DEM accuracy limitations (SRTM 30m)
- SAR validation limitations
- Insurance parameters are illustrative assumptions

## 📄 Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data Sources](docs/DATA_SOURCES.md)
- [Methodology](docs/METHODOLOGY.md)
- [Limitations](docs/LIMITATIONS.md)
- [Demo Script](docs/DEMO_SCRIPT.md)

## 📜 License

MIT — see [LICENSE](LICENSE)

## 🙏 Acknowledgments

- NOAA IBTrACS for cyclone track data
- India Meteorological Department (IMD) for Fani best track
- Google Earth Engine (non-commercial license)
- OpenStreetMap contributors
- Copernicus/ESA for Sentinel-1 SAR
