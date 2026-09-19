# Methodology

This document describes the scientific and computational methods used in
CycloneShield. All assumptions are explicitly documented and labelled.

---

## 1. Track Processing

**Source**: IBTrACS v04r00 (3-hourly observations)
**Method**: Cubic spline interpolation to 1-hourly timestamps
**Outputs**: `track_hourly.geojson` — hourly positions with Vmax (kt), MSLP (hPa), RMW (km)

**RMW estimation** (when missing from IBTrACS):
```
RMW = (1.119 × 10^−3) × exp(0.0423 × Vmax) × (MSLP^−2.026)    [Willoughby & Rahn 2004]
```
Fallback: fixed RMW from scenario YAML (labelled ASSUMPTION if used).

---

## 2. Holland (1980) Parametric Wind Field

**Reference**: Holland, G.J. (1980). An analytic model of the wind and pressure profiles in hurricanes. *Mon. Wea. Rev.*, 108, 1212–1218.

**Gradient wind formula**:
```
V(r) = sqrt( (B/ρ) × (Rmax/r)^B × (Pn - Pc) × exp(-(Rmax/r)^B) + (r × f/2)^2 ) - (r × f/2)
```
where:
- B = Holland B parameter (estimated from MSLP drop)
- ρ = air density (1.15 kg/m³)
- r = distance from storm centre
- Rmax = radius of maximum winds
- Pn = environmental pressure (1010 hPa)
- Pc = central pressure
- f = Coriolis parameter

**Translation-speed asymmetry**: add 20% of translation vector to right-of-track wind, subtract from left.

**Output**: max sustained wind speed per grid cell (500m resolution over AOI).

---

## 3. Storm Surge Model

A **simplified physics-informed model**, not a full hydrodynamic solver (see LIMITATIONS.md).

### 3.1 Total Water Level
```
TWL = Inverse_Barometer + Wind_Setup + Astronomical_Tide
```

**Inverse Barometer** (IB):
```
IB = 0.01 × (1010 - Pc)    [m; 1 hPa drop → 0.01 m rise; Pugh 1987]
```

**Wind Setup** (WS):
```
WS = Cw × U10² × F / (g × d)
```
where:
- Cw = wind setup coefficient (0.0003; ASSUMPTION A08)
- U10 = 10-m wind speed at coast (m/s)
- F = fetch (500 km; ASSUMPTION A03)
- g = 9.81 m/s²
- d = shelf depth (15 m; ASSUMPTION A02)

**Astronomical Tide**: 1.2 m (ASSUMPTION A04; worst-case representative high tide for Odisha coast based on INCOIS climatology).

### 3.2 Inland Flood Propagation (Bathtub + Connectivity)
Starting from the coastline:
1. Identify all coastal grid cells where TWL > land elevation (SRTM)
2. Use a connectivity-constrained bathtub: only flood cells hydrologically
   connected to the sea (4-connected flood fill at TWL)
3. Flood depth = TWL − elevation (non-negative)
4. Apply inland attenuation: 0.1 m/km from coast (ASSUMPTION A05)
5. Cap at max_inland_km = 30 km

**Temporal variation**: TWL scales with wind speed / pressure drop along the hourly track. Output is hourly surge depth polygons from T-24h to T+24h.

---

## 4. Rainfall Flood Model

**Data**: GPM IMERG (0.1°, 30-min) accumulated over 30 April – 6 May 2019.

**HAND classification**:
- MERIT Hydro HAND < 5 m → flood-prone (pluvial/fluvial ponding likely)
- Combined with flow accumulation > 1000 upstream cells → damage pathways

**Output**:
- `rainfall_flood.geojson` — flood-prone polygon layer
- `rainfall_pathways.geojson` — high-flow damage pathway lines

---

## 5. SAR Flood Validation

**Data**: Sentinel-1 IW GRD (VV/VH), pre-event (25–30 Apr 2019) and post-event (4–10 May 2019).

**Processing**:
1. Speckle filter: 7×7 Lee filter
2. Compute ratio: post_VV / pre_VV (dB difference)
3. Threshold: Otsu algorithm on the ratio histogram (or fixed −16 dB; configurable)
4. Mask permanent water: JRC Global Surface Water (occurrence > 80%)
5. Mask steep slopes: SRTM slope > 5°
6. Result: observed flood extent polygon

**Metrics (per-district and overall)**:
- **IoU** = |observed ∩ modeled| / |observed ∪ modeled|
- **Precision** = |observed ∩ modeled| / |modeled|
- **Recall** = |observed ∩ modeled| / |observed|
- **F1** = 2 × Precision × Recall / (Precision + Recall)

If IoU < 0.3, a small calibration of the surge attenuation parameter (A05)
is performed and results reported as "before/after calibration".

---

## 6. Exposure Analysis

For each infrastructure asset:

| Attribute | Computation |
|-----------|-------------|
| `max_surge_depth_m` | Max hourly surge depth at asset location |
| `max_rain_depth_bool` | Whether asset is in HAND < 5 m flood-prone zone |
| `max_wind_kmh` | Max wind speed from Holland field at asset |
| `first_flood_hour` | First hour when flood depth > 0 at asset |
| `risk_score` | Weighted composite score (0–100) — formula below |

**Risk Score Formula** (documented; labelled in UI):
```
risk_score = min(100, 
    40 × min(surge_depth/3.0, 1.0) +        # surge depth weight 40%
    30 × min(wind_kmh/200.0, 1.0) +          # wind speed weight 30%
    20 × (1 if rainfall_exposed else 0) +     # rainfall exposure 20%
    10 × (1 if first_flood_hour < -6 else 0) # early flooding 10%
)
```

---

## 7. Cascade Failure Simulation

**Graph model**: `networkx.MultiGraph`

**Nodes**:
- Substations (S), Hospitals (H), Shelters (E), District HQ (D — safe nodes)

**Edges**:
- Dependency: H/E → nearest S (power dependency; generator_backup_hours=12)
- Road: OSM drive network (edges weighted by travel time)

**Hour-by-hour simulation** (T-24h to T+24h):
1. For each substation: fail if surge_depth > 0.5m OR wind > 120 km/h
2. For each hospital/shelter dependent on a failed substation:
   - Mark as "on generator" immediately after substation fails
   - After generator_backup_hours: mark as "no power"
3. For each road edge: remove if max flood depth > 0.3m
4. Compute shortest path from each hospital/shelter to any safe node (D)
5. If no path exists: mark as "isolated"
6. Log event: `{hour, asset_name, event_type, district}`

**Resilience Score**:
```
resilience = (total_hours_all_assets_operational) / (total_possible_hours)
```

**Hardening Priorities**:
- For each substation or road segment: compute how many people/assets
  would remain connected if it were hardened (betweenness-impact ranking)

---

## 8. Parametric Insurance

**Basis**: Maximum modeled wind speed and surge depth per district.

**Tier table** (illustrative — labelled ASSUMPTION):

| Tier | Wind (km/h) | Surge (m) | Payout |
|------|-------------|-----------|--------|
| Catastrophic | ≥ 150 | ≥ 2.0 | 100% |
| Severe | ≥ 120 | ≥ 1.0 | 60% |
| Moderate | ≥ 90 | ≥ 0.5 | 30% |
| No trigger | < 90 | < 0.5 | 0% |

**Output**: Triggered tier, payout percentage, and liquidity estimate
(= sum_insured × payout_pct; sum_insured is an illustrative ASSUMPTION).

---

## 9. Gemini Advisory Generation

**Approach**: Strictly data-grounded, schema-validated advisory.

1. **Fact pack assembly**: JSON dict of computed values only
   (no free text; all numbers from pipeline outputs)
2. **System prompt**: Requires JSON output conforming to Pydantic schema;
   prohibits inventing numbers not in the fact pack
3. **Schema** (Pydantic):
   - `headline`, `severity` (1–5), `situation_summary`
   - `top_actions`: list of `{action, owner, deadline, priority}`
   - `evacuation_priority`: ordered list of areas
   - `hardening_recommendations`: list of infrastructure actions
   - `public_message`: short plain-language message
4. **Post-validation**: regex scan for numeric tokens in output;
   each must appear in the fact pack ± 5% tolerance
5. **Languages**: EN → HI → OR (separate calls, same fact pack)
6. **Caching**: SHA-256 hash of fact pack → advisory_cache/{hash}_{lang}.json

---

## 10. Alert Dispatch

**Channel**: Telegram Bot API (HTTP POST to sendMessage)
**Default**: `DRY_RUN=true` — logs message to outbox.jsonl without sending
**Authority types and message templates**:
- **District Collector**: Full situation report + top actions + evacuation priority
- **SDMA/OSDMA**: Aggregate district summary + insurance status
- **Hospital administrators**: Power/isolation status + preparation checklist
- **Power utility**: Substation failure forecast + timing

**Outbox**: All dispatch attempts (real or dry-run) written to `data/processed/outbox.jsonl`.
