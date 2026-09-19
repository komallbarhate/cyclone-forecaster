# CycloneShield Architecture

## Overview

CycloneShield is a pre-landfall decision-support platform for cyclone-prone
coastal communities. It ingests freely available data (IBTrACS, Sentinel-1,
GPM IMERG, OpenStreetMap), runs a physics-informed pipeline, and outputs:

- Storm surge and rainfall flood maps (hourly)
- Infrastructure exposure and cascade failure timeline
- AI-generated multilingual advisories
- Parametric insurance triggers
- Automated early-warning dispatch

## System Architecture

```mermaid
flowchart TD
    %% Data Sources
    subgraph Sources["📡 Data Sources (Free, Open)"]
        S1[IBTrACS v04r00\nNOAA CSV]
        S2[Sentinel-1 SAR\nGEE]
        S3[GPM IMERG\nGEE]
        S4[SRTM / GLO-30 DEM\nGEE]
        S5[MERIT Hydro HAND\nGEE]
        S6[OpenStreetMap\nosmnx]
        S7[Gemini API\nGoogle AI]
    end

    %% Offline Pipeline
    subgraph Pipeline["⚙️ Offline Pipeline (precomputed → data/processed/)"]
        P1[01_fetch_track.py\nIBTrACS → hourly track\nVmax · MSLP · RMW]
        P2[02_wind_field.py\nHolland 1980 parametric\nTranslation asymmetry]
        P3[03_surge_model.py\nInverse barometer\nWind setup · Bathtub flood]
        P4[04_rainfall_model.py\nGPM IMERG\nMERIT HAND · flow accum]
        P5[05_sar_validation.py\nSentinel-1 change detection\nIoU · F1 · per-district]
        P6[06_osm_infra.py\nHospitals · Shelters\nSubstations · Roads]
        P7[07_exposure.py\nMax depth · wind · risk score]
        P8[08_cascade.py\nNetworkX multigraph\nHour-by-hour simulation]
        P9[09_insurance.py\nParametric tier table\nDistrict triggers]
        P10[10_advisories.py\nGemini fact-pack\nEN / HI / OR]
    end

    %% Outputs
    subgraph Outputs["💾 Cached Outputs (data/processed/)"]
        O1[track_hourly.geojson]
        O2[wind_max.geojson\ndistrict_wind_ts.json]
        O3[surge_hourly.geojson\nsurge_max.geojson]
        O4[rainfall_flood.geojson]
        O5[sar_observed.geojson\nmetrics.json]
        O6[infra.geojson]
        O7[exposure.json]
        O8[cascade_timeline.json\nresilience.json]
        O9[insurance_triggers.json]
        O10[advisories.json\nadvisory_cache/]
        O11[outbox.jsonl]
    end

    %% Backend
    subgraph Backend["🔌 FastAPI Backend (optional)"]
        B1["/scenarios"]
        B2["/timeline"]
        B3["/layers/{name}"]
        B4["/exposure"]
        B5["/cascade"]
        B6["/advisories"]
        B7["/insurance"]
        B8["/validation"]
        B9["/dispatch"]
        B10["/health"]
    end

    %% Frontend
    subgraph Frontend["🖥️ React + Vite + MapLibre Frontend"]
        F1[MapView\nTime slider · Track animation\nSurge · Rain · Infra layers]
        F2[Advisory Panel\nEN/HI/OR · Dispatch button]
        F3[Cascade Timeline\nEvent log · Hardening priorities]
        F4[Validation Panel\nObserved vs Modeled · Metrics]
        F5[Insurance Panel\nDistrict trigger table]
        F6[KPI Header\nAssets at risk · People exposed]
    end

    %% Dispatch
    TG[📱 Telegram\nDRY_RUN=true]

    %% Flow
    S1 --> P1
    S2 --> P5
    S3 --> P4
    S4 --> P3
    S5 --> P4
    S6 --> P6
    S7 --> P10

    P1 --> P2 --> P3 --> O3
    P1 --> O1
    P2 --> O2
    P4 --> O4
    P5 --> O5
    P6 --> O6
    P3 & P4 & P6 --> P7 --> O7
    P7 --> P8 --> O8
    P8 --> P9 --> O9
    O7 & O8 & O9 --> P10 --> O10
    P10 --> O11 --> TG

    O1 & O2 & O3 & O4 & O5 & O6 & O7 & O8 & O9 & O10 --> Backend
    Backend --> Frontend
    O1 & O2 & O3 & O4 & O5 & O6 & O7 & O8 & O9 & O10 -.->|Static mode| Frontend
```

## Key Design Principles

### 1. Demo Never Breaks
All GEE and Gemini outputs are pre-computed and cached to `data/processed/`.
The frontend runs in **static mode** loading directly from `/public/data/`.
No runtime dependency on GEE quota or Gemini rate limits.

### 2. No Fabricated Numbers
Every figure in the UI, advisories, or README is computed from data.
Assumptions are documented in code and labelled in the UI.

### 3. Region-Agnostic
A new cyclone scenario requires only a new `config/scenarios/<name>.yaml`.
No code changes needed to add a BRICS Bay of Bengal scenario.

### 4. Free-Tier Throughout
| Component | Service | Cost |
|-----------|---------|------|
| Track data | IBTrACS (NOAA CSV) | Free |
| SAR imagery | Sentinel-1 via GEE | Free (non-commercial) |
| Rainfall | GPM IMERG via GEE | Free (non-commercial) |
| DEM | SRTM/GLO-30 via GEE | Free (non-commercial) |
| Infrastructure | OpenStreetMap | Free (ODbL) |
| AI advisories | Gemini API free tier | Free |
| Frontend hosting | Vercel/Netlify | Free |
| Backend hosting | Render free tier | Free |

## Data Flow Timing

```
T-72h: Pipeline runs offline (once)
T-24h: Cached outputs available → Frontend shows pre-landfall forecast
T+00h: Landfall simulation moment in the slider
T+24h: Post-landfall flood extent from SAR (validation)
```

## Cascade Graph Model

The cascade failure model uses a `networkx.MultiGraph`:

- **Nodes**: substations, hospitals, shelters, district HQ (safe nodes)
- **Edges (dependency)**: hospital ← nearest substation (with generator backup time)
- **Edges (road)**: OSM drive network with flood/wind failure conditions
- **Simulation**: hour-by-hour from T-24h to T+24h
  1. Mark substations failed if flood depth > threshold OR wind > threshold
  2. Hospitals/shelters lose grid power if substation failed AND generator hours elapsed
  3. Remove road edges if flood depth > vehicle-passable threshold
  4. Compute reachability: can any isolated asset reach a safe node?
  5. Log events to cascade_timeline.json

## Advisory Generation

Gemini advisory pipeline:
1. Assemble **fact pack** (JSON): only computed numbers from pipeline
2. Hash fact pack → check cache
3. Call Gemini with strict system prompt (JSON schema output required)
4. Validate output schema (Pydantic)
5. Number-check: every numeric value in output must appear in fact pack
6. Generate in EN → HI → OR (separate calls)
7. Cache all responses by hash

## Limitations

See [LIMITATIONS.md](LIMITATIONS.md) for full scientific caveats.
