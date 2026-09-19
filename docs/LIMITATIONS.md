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

### 3.1 Temporal Gap
The post-event SAR image is typically available 4–10 days after landfall, not
immediately. Standing water that drained before the overpass is not detected.
This causes systematic under-estimation of observed flood extent.

### 3.2 Urban/Vegetation Effects
SAR backscatter in urban areas (double-bounce) and dense vegetation can mask
flood signatures. Flooded buildings may not show reduced backscatter.

### 3.3 Thresholding
The Otsu threshold for flood detection is computed from the image histogram.
In scenes with low flood fraction, Otsu may perform poorly. The threshold is
configurable and should be validated against known flood polygons.

### 3.4 Projection and Resolution
The GEE computation uses a 30m native SAR resolution. Comparison with the
500m surge model grid involves spatial aggregation that affects metrics.

---

## 4. Rainfall Model Limitations

### 4.1 GPM IMERG Resolution
GPM IMERG has 0.1° (~11km) spatial resolution. Sub-grid rainfall variability
is not captured, which affects flood-prone area identification.

### 4.2 HAND Approach
The HAND (Height Above Nearest Drainage) approach is a static indicator of
flood susceptibility, not a dynamic flood model. It does not simulate drainage
capacity, soil infiltration, or antecedent moisture conditions.

---

## 5. Cascade Failure Limitations

### 5.1 Network Completeness
The road and infrastructure network depends on OSM coverage. Rural OSM coverage
in Odisha may miss informal roads and paths used for evacuation.

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
