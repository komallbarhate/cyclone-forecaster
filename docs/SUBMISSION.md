# Submission Brief — CycloneShield

## Challenge
Build with AI: Code for Communities — Track 5 (BRICS / Bay of Bengal)

---

## Brief Description (~150 words)

CycloneShield is an AI-powered pre-landfall decision-support platform that
shifts cyclone response from post-disaster recovery to predictive action.

Using freely available data — NOAA IBTrACS tracks, Sentinel-1 SAR imagery,
GPM IMERG rainfall, and OpenStreetMap infrastructure — CycloneShield runs a
physics-informed storm surge model, simulates cascading infrastructure failures,
and generates multilingual early-warning advisories via Gemini AI.

For Cyclone Fani (3 May 2019, Odisha), the platform identifies which substations
flood first, which hospitals lose grid power and when, which evacuation routes
become impassable, and which districts trigger parametric insurance payouts —
all 24 hours before landfall.

Validated against Sentinel-1 observed flood extent (IoU: [TBD], F1: [TBD]),
CycloneShield is fully config-driven and region-agnostic, enabling any BRICS
Bay of Bengal coastal state to run the same pipeline with a single YAML file.
It runs on free-tier infrastructure and shares all model artifacts as a
digital public good.

---

## Extended Description (~500 words)

### The Problem

When Cyclone Fani made landfall near Puri, Odisha on 3 May 2019 at 175 km/h,
it was one of the strongest storms to strike the Indian subcontinent in decades.
Remarkably, only 64 lives were lost — a testament to India's mass evacuation
infrastructure. But 1.5 million people were displaced, the power grid was
devastated for weeks, and thousands of hospitals and shelters were cut off.

The gap is not in evacuation alerts — those exist. The gap is in *decision intelligence*:
which specific assets will fail, in what order, with what cascading consequences?
Disaster management authorities currently lack pre-landfall visibility into:
- Which substations and hospitals will be inundated and when
- Which evacuation routes will become impassable
- Which districts should receive priority resources
- When parametric insurance payouts will be triggered

### The Solution

CycloneShield answers these questions 24–72 hours before landfall using a
multi-layer AI and physics-informed pipeline:

**1. Physics-informed hazard modelling**: A Holland (1980) parametric wind
field drives a simplified but defensible storm surge model (inverse barometer +
wind setup + connectivity-constrained bathtub propagation using SRTM elevation).
GPM IMERG rainfall combined with MERIT Hydro HAND identifies flood-prone pathways.

**2. Infrastructure exposure and cascade simulation**: OpenStreetMap substations,
hospitals, shelters, and road networks are ingested via osmnx. A NetworkX
multigraph simulates hour-by-hour cascade failures: when substations flood,
hospitals go on generator backup; when generators exhaust, they lose power;
when roads flood, shelters become isolated. The platform outputs a named,
timestamped event timeline.

**3. AI-generated multilingual advisories**: For each district, Gemini receives
a structured "fact pack" of computed values and generates a schema-validated
advisory in English, Hindi, and Odia — with post-generation number-checking
to ensure no hallucinated values. Advisories are cached by input hash so the
demo is never dependent on API rate limits.

**4. Parametric insurance triggers**: Configurable tier tables based on modelled
wind speed and surge depth produce automatic trigger signals per district, with
liquidity estimates. Clearly labelled as illustrative.

**5. Automated dispatch**: A Telegram bot (default DRY_RUN=true for safety) sends
authority-tailored alerts to District Collectors, OSDMA, hospital administrators,
and power utilities.

**Validation**: The surge model is validated against Sentinel-1 SAR observed
flood extent using IoU, precision, recall, and F1 — reported honestly, with
a documented calibration step if initial metrics are weak.

### BRICS Scalability

CycloneShield is designed as a **digital public good**:
- Every parameter for a cyclone scenario lives in a single YAML file
- All data sources are open and free
- The model pipeline is containerisable and shareable
- Any BRICS Bay of Bengal state (Bangladesh, Myanmar, Sri Lanka, Thailand)
  can run the same code by adding one scenario config

### Technology

Python (FastAPI, osmnx, networkx, rasterio, scikit-learn, pydantic) |
React + Vite + MapLibre GL JS + Tailwind | Gemini API | Free hosting (Vercel/Render)

All source code is MIT licensed and publicly available on GitHub.

---

*All numbers in this submission are computed from real data. Assumptions are
explicitly documented in docs/LIMITATIONS.md and labelled in the UI.*
