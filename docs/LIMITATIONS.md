# Scientific Limitations and Caveats

> This document is part of CycloneShield's commitment to scientific honesty.
> Every limitation documented here is also surfaced in the UI.

---

## 1. Surge Model Limitations

### 1.1 No Full Hydrodynamic Solver
CycloneShield uses a **simplified physics-informed surge model**, not a full
hydrodynamic solver like ADCIRC, Delft3D, or SCHISM. The key simplifications are:

- **No wave setup**: wave radiation stress contribution to total water level is neglected.
- **No inundation dynamics**: the bathtub model does not simulate momentum, flow velocity, or drainage. It is a static envelope estimate.
- **No non-linear surge-tide interaction**: tide and surge are linearly superimposed.
- **No riverine interaction**: freshwater discharge from rivers during the event is not modelled.

**Impact**: The model may over-predict flood extent in areas with good drainage and
under-predict in areas with blocked drainage or tidal rivers. Coastal areas with
complex bathymetry will have lower accuracy.

### 1.2 DEM Accuracy & Surface Model (DSM) Caveat
The Copernicus GLO-30 DEM (30m resolution) used for flood propagation and HAND computation is a **Digital Surface Model (DSM)**, not a bare-earth Digital Terrain Model (DTM).
- Elevations represent the top reflective surface, which includes forest canopy (e.g. coastal Casuarina plantations and mangrove belts) and built structures.
- In low-lying coastal areas, vegetation canopy artificially inflates ground elevation by several metres, potentially attenuating modeled inland surge penetration.

### 1.3 Bathymetry Proxy
Shelf depth and fetch are **assumed constants** (15m, 60km) over the shallow coastal shelf off Odisha. In reality, bathymetry varies along the coast.

### 1.4 Astronomical Tide Assumption
Tidal phase at landfall is assumed to be high tide (1.2m above MSL). The actual astronomical tide at 02:40 UTC on 3 May 2019 was near high tide based on INCOIS tidal climatology for Paradip/Puri.

### 1.5 Inland Attenuation Parameter
The 0.10 m/km inland attenuation coefficient is an empirical hydrodynamic dissipation proxy calibrated against Sentinel-1 observed residual inundation.

---

## 2. Wind Field Limitations

### 2.1 Simplified Asymmetry
Translation-speed asymmetry is applied as an additive correction. Real storm asymmetry varies with internal vortex dynamics.

### 2.2 Boundary Layer & Surface Wind Factor
The Holland (1980) model produces gradient winds. Surface winds are reduced using Harper et al. (2010) WMO surface wind factor (0.93 for 1-minute sustained winds).

### 2.3 Interpolation
IBTrACS cubic spline interpolation assumes smooth evolution between 3-hourly observations.

---

## 3. SAR Validation Limitations

### 3.1 Sentinel-1 Mosaicked Frames & Acquisition Timing
Sentinel-1 Radiometrically Terrain Corrected (RTC) swaths from Microsoft Planetary Computer:
- **Pre-event Mosaicked Scenes**:
  - `S1A_IW_GRDH_1SDV_20190422T000501_20190422T000530_026895_030652_rtc` (Acquired: `2019-04-22 00:05:16 UTC`, **-266.58h** baseline)
  - `S1A_IW_GRDH_1SDV_20190422T000436_20190422T000501_026895_030652_rtc` (northern adjacent frame)
- **Post-event Mosaicked Scenes**:
  - `S1A_IW_GRDH_1SDV_20190504T000512_20190504T000537_027070_030CB5_rtc` (Acquired: `2019-05-04 00:05:25 UTC`, **+21.42h** post-landfall)
  - `S1A_IW_GRDH_1SDV_20190504T000447_20190504T000512_027070_030CB5_rtc` (Acquired: `2019-05-04 00:05:00 UTC`, **+21.42h**, northern contiguous frame)

### 3.2 Spatial Coverage & Validation Bounding Box
- **Combined AOI Coverage**: Mosaicking adjacent frames provides **46.14%** coverage of the full scenario AOI bbox `[84.9, 19.6, 86.5, 20.7]`, covering the entire north-south latitude extent (19.60°N to 20.70°N) across longitudes 85.7618°E to 86.5000°E.
- **Dedicated Validation Bounding Box**: Because combined coverage is under 80% (single orbital track cannot span 1.6° longitude), all SAR validation metrics (IoU, precision, recall, F1) are strictly evaluated over the **Validation Box: `[85.7618, 19.6000, 86.5000, 20.7000]`**. Western inland districts (western Khordha, western Cuttack, interior Chilika) outside this swath are excluded from SAR metric calculations.

### 3.3 Residual Inundation vs Peak Surge
- The post-event SAR overpass occurred **~21.4 hours after landfall**. Peak storm surge occurred at landfall (~02:40 UTC 3 May) and receded with tidal ebb and gravitational drainage over 12–18 hours.
- Sentinel-1 observes **residual waterlogging and persistent ponding**, not peak surge height.

### 3.4 Urban & Vegetation Backscatter Effects
- Built structures cause radar double-bounce reflections that elevate backscatter, masking floodwaters beneath rooftops or in narrow alleys. Mangroves similarly attenuate C-band radar.

### 3.5 RTC Radiometric Units: Linear Power to Decibels (dB)
- Sentinel-1 RTC images from Planetary Computer provide normalized radar cross section ($\gamma^0$) in **linear power units**.
- Values must be converted to decibels via $\sigma^0 \text{ [dB]} = 10 \times \log_{10}(\gamma^0)$ before applying change detection thresholds ($\Delta \sigma^0 < -3.0$ dB, $\sigma^0 < -16.0$ dB). Using raw linear values without logarithmic transformation would completely invalidate thresholding.

---

## 4. Rainfall & Population Model Limitations

### 4.1 CHIRPS Precipitation Resolution
- Rainfall forcing utilizes CHIRPS v2.0 daily precipitation at **0.05° (~5.5 km)** spatial resolution.
- Event accumulation is computed across 2–4 May 2019 (`chirps-v2.0.2019.05.02.tif`, `2019.05.03`, `2019.05.04`).
- Because of the ~5 km grid, local convective rain cells, sub-grid orographic enhancement, and micro-drainage channels cannot be resolved, producing smoothed flood-susceptibility pathways.

### 4.2 HAND Elevation Approximation
- HAND (Height Above Nearest Drainage) derived from Copernicus GLO-30 DEM provides a static structural indicator of drainage proximity rather than unsteady hydrodynamic routing. Infiltration capacity and culvert infrastructure are unmodeled.

### 4.3 WorldPop Population Layer Specifications
- Population exposure is calculated from WorldPop 2019 India unconstrained count raster:
  - Exact File: `ind_ppp_2019_1km_Aggregated.tif`
  - Version: `WorldPop Global 2000-2020 1km unconstrained`
  - Year: `2019`
  - Spatial Resolution: `30 arc-seconds (~1 km at the equator)`
  - AOI Total Population: **10,866,029** residents
- Disaggregation does not capture diurnal commuter shifts or pre-landfall evacuations conducted by the Odisha State Disaster Management Authority (OSDMA).

---

## 5. Cascade Failure Limitations

### 5.1 Network Completeness & Temporal Mismatch
The road and critical infrastructure network is extracted from OpenStreetMap (OSM) via the Overpass API.
- **Temporal Mismatch**: The OSM snapshot is September 2026, not May 2019 (the time of Cyclone Fani landfall). Infrastructure constructed or modified between 2019 and 2026 is reflected in the dataset, while historical 2019-specific assets that were subsequently decommissioned or re-tagged may differ.
- **Spatial Completeness**: OSM completeness in rural Odisha is partial. While major substations, arterial roads (trunk, primary, secondary), and major hospitals are well-mapped, rural health posts, unpaved local connectors, and informal evacuation pathways may be under-represented.

### 5.2 Generator Assumption
The 12-hour generator backup assumption for hospitals is the default and may not
reflect actual generator status, fuel availability, or maintenance condition.

### 5.3 No Repair / Restoration
The cascade model simulates failure but not restoration. In practice, utilities
begin emergency repairs during and after the event.

### 5.4 Substation Failure Thresholds
Wind and flood thresholds for substation failure are based on engineering
guidelines and have not been validated against Fani's observed outage data.

---

## 6. Advisory Generation Limitations

### 6.1 LLM Hallucination Risk
Despite strict prompting and post-validation, Gemini may occasionally produce
numbers that don't match the fact pack exactly. The number-check validator
catches these and flags (or regenerates) the response. Cached advisories that
passed validation are retained.

### 6.2 Translation Quality
Gemini-generated Hindi and Odia translations have not been reviewed by a
native speaker. They should be considered machine-translated and verified
before real operational use.

### 6.3 Not a Real Operational System
The advisory generation is a **proof of concept**. Real operational use would
require integration with verified authority contact databases, authentication,
and a formal escalation protocol.

---

## 7. Insurance Model Limitations

### 7.1 Illustrative Only
The parametric insurance tier table, sum insured values, and all payout
calculations are **purely illustrative**. They are labelled "ASSUMPTION" or
"ILLUSTRATIVE" throughout the UI and code.

### 7.2 No Actuarial Calibration
A real parametric product would require actuarial calibration against historical
loss data, which is beyond the scope of this hackathon demo.

---

## 8. General Limitations

| Limitation | Impact | Recommended Improvement |
|-----------|--------|------------------------|
| 500m grid resolution | Misses sub-km features | 100m grid with cloud compute |
| Single event scenario | May not generalise | Test on 3+ historical events |
| No real-time data ingestion | Demo uses pre-computed data | Streaming pipeline integration |
| No population vulnerability | Risk score is hazard-only | Add vulnerability indices (NDVI, housing type) |
| No dynamic ocean forcing | No SST, ocean heat content | Couple with ROMS or similar |
| English/Hindi/Odia only | May miss local dialects | Add Bengali, Telugu |
