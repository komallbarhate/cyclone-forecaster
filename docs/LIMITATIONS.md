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

### 1.2 DEM Accuracy
The SRTM 30m DEM used for flood propagation has:
- **±10 m vertical RMSE** in forested and urban areas
- It represents the **Digital Surface Model** (DSM), not bare earth — trees and
  buildings inflate elevation readings, potentially under-predicting flood extent.
- Coastal mangroves are particularly problematic (high DSM, low bare-earth elevation).

### 1.3 Bathymetry Proxy
Shelf depth and fetch are **assumed constants** (15m, 500km) over the entire
AOI. In reality, these vary spatially. A proper model would use GEBCO or
NGDC bathymetry.

### 1.4 Astronomical Tide Assumption
Tidal phase at landfall is assumed to be high tide (1.2m). The actual tidal
state at 02:40 UTC on 3 May 2019 was not retrieved from a real-time tidal model.
This is documented as **ASSUMPTION A04**. The INCOIS tidal prediction service
would provide the exact value; integration is a recommended improvement.

### 1.5 Inland Attenuation Parameter
The 0.1 m/km inland attenuation coefficient is empirically estimated, not
derived from a validated hydrodynamic model. It is a **calibratable parameter**
exposed in the scenario YAML.

---

## 2. Wind Field Limitations

### 2.1 Simplified Asymmetry
Translation-speed asymmetry is applied as a simple additive correction to the
right-of-track quadrant. This is a known simplification; real storm asymmetry
is more complex and varies with storm structure.

### 2.2 No Boundary Layer Effects
The Holland (1980) model produces gradient winds. Surface winds are typically
~80% of gradient winds over water and lower over land due to friction. The
model applies a constant correction factor but does not simulate the land-sea
roughness transition.

### 2.3 Rapid Intensification / Weakening Not Captured
The IBTrACS interpolation assumes smooth linear change between observations.
Rapid intensification events between observations will not be captured.

---

## 3. SAR Validation Limitations

### 3.1 Sentinel-1 Acquisition Timing & Landfall Offsets
Sentinel-1 Radiometrically Terrain Corrected (RTC) scenes from Microsoft Planetary Computer:
- **Pre-event Scene**: `S1A_IW_GRDH_1SDV_20190422T000501_20190422T000530_026895_030652_rtc`
  - Acquisition Time: `2019-04-22 00:05:16 UTC`
  - Offset from Landfall (`2019-05-03 02:40:00 UTC`): **-266.58 hours** (-11.1 days baseline)
- **Post-event Scene**: `S1A_IW_GRDH_1SDV_20190504T000512_20190504T000537_027070_030CB5_rtc`
  - Acquisition Time: `2019-05-04 00:05:25 UTC`
  - Offset from Landfall (`2019-05-03 02:40:00 UTC`): **+21.42 hours** (~21 h post-landfall)
- **Adjacent Post-event Scene in 3–5 May Window**:
  - `S1A_IW_GRDH_1SDV_20190504T000447_20190504T000512_027070_030CB5_rtc`
  - Acquisition Time: `2019-05-04 00:05:00 UTC` (+21.42 h offset; northern contiguous frame on the same descending orbital pass, bbox `[86.027, 20.234, 88.711, 22.164]`).

### 3.2 Spatial Coverage Caveat (Single Orbit Swath)
- **Joint AOI Coverage**: Exactly **44.65%** of the project AOI bbox `[84.9, 19.6, 86.5, 20.7]` is covered by **both** pre- and post-event Sentinel-1 swaths (spatial intersection: longitudes 85.76°E to 86.50°E, latitudes 19.60°N to 20.66°N).
- A single Sentinel-1 frame cannot cover the entire 1.6° longitude extent; western portions of the AOI (western Khordha, western Cuttack, interior Chilika lagoon) fall outside this orbit track.
- Validation metrics (IoU, Precision, Recall, F1) apply **only to the 44.65% covered area** containing the primary Puri coastal landfall zone and Jagatsinghpur.

### 3.3 Residual Inundation vs Peak Surge
- The post-event SAR scene was captured **~21.4 hours after landfall**. Transient storm surge floodwaters typically peak near landfall and drain within 12–18 hours following tidal ebb and topographic outflow.
- Consequently, Sentinel-1 change detection observes **residual inundation and waterlogging**, not the transient peak surge envelope. Validation metrics evaluate the model's agreement against persistent post-event standing water.

### 3.4 Urban & Vegetation Backscatter Attenuation
- SAR backscatter in dense urban settlements (double-bounce effects) and tall mangrove canopy can mask water signatures, leading to potential false negatives in dense built environments.

### 3.5 Thresholding & Projection
- Change detection applies a fixed backscatter drop threshold ($\Delta \sigma^0 < -3.0$ dB) and absolute water threshold ($\sigma^0 < -16.0$ dB) with JRC Global Surface Water permanent water masking (excluding permanent water bodies like Chilika Lake and open ocean).
- Comparison with the model grid involves resampling the native 10m/30m SAR resolution to the 500m simulation grid.

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
