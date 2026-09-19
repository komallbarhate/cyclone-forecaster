# Data Sources

This document lists all data sources used by CycloneShield,
their licenses, access methods, and any known limitations.

---

## 1. Cyclone Track — IBTrACS v04r00

| Field | Detail |
|-------|--------|
| **Name** | International Best Track Archive for Climate Stewardship (IBTrACS) |
| **Version** | v04r00 |
| **Agency** | NOAA National Centers for Environmental Information (NCEI) |
| **URL** | https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r00/access/csv/ |
| **File used** | `ibtracs.NI.list.v04r00.csv` (North Indian Ocean basin) |
| **Storm SID** | `2019153N11090` (Cyclone Fani) |
| **License** | Public domain (NOAA open data) |
| **Citation** | Knapp, K.R., et al. (2010). The International Best Track Archive for Climate Stewardship (IBTrACS). *Bull. Amer. Meteor. Soc.*, 91, 363-376. https://doi.org/10.1175/2009BAMS2755.1 |
| **Variables used** | ISO_TIME, LAT, LON, WMO_WIND (kt), WMO_PRES (hPa), STORM_SPEED, STORM_DIR |
| **Limitations** | 3-hourly resolution; interpolated to 1-hourly for the model. RMW not always available; estimated from Holland (1980) empirical relation where missing. |

### Fani Track Summary (from IBTrACS)
- **Landfall**: 3 May 2019, ~02:40 UTC (08:10 IST), near Puri, Odisha
- **Landfall position**: ~19.85°N, 85.85°E
- **Landfall intensity**: ~175 km/h (1-min sustained; converted from kt in IBTrACS)
- **Minimum MSLP**: ~932 hPa
- **Source**: IMD Cyclone e-Atlas 2019; NOAA IBTrACS v04r00
- **IMD reference**: https://mausam.imd.gov.in/responsive/cycloneinfo.php

---

## 2. IMD Best Track (supplementary)

| Field | Detail |
|-------|--------|
| **Name** | India Meteorological Department Cyclone e-Atlas |
| **URL** | https://mausam.imd.gov.in/responsive/cycloneinfo.php |
| **Used for** | Landfall time, position, and intensity cross-check; track error validation |
| **License** | Government of India open data |
| **Note** | IMD reports 3-min sustained winds; IBTrACS stores 1-min. Conversion factor 0.88 applied where necessary. |

---

## 3. Sentinel-1 SAR (Flood Validation)

| Field | Detail |
|-------|--------|
| **Name** | Copernicus Sentinel-1 SAR (IW mode, VV/VH polarisation) |
| **Provider** | European Space Agency (ESA) / Copernicus |
| **Access** | Google Earth Engine: `COPERNICUS/S1_GRD` |
| **License** | Copernicus Sentinel free and open data policy |
| **Pre-event window** | 25–30 April 2019 |
| **Post-event window** | 4–10 May 2019 |
| **Processing** | Speckle filtering (7x7 Lee), VV/VH backscatter change detection, Otsu thresholding, permanent water masked via JRC Global Surface Water, steep slopes masked via SRTM-derived slope |
| **Citation** | Copernicus Open Access Hub; ESA (2014). Sentinel-1 ESA's Radar Observatory Mission for GMES Operational Services. |
| **Limitations** | SAR flood detection is affected by urban shadow, vegetation, and wind-roughened water. Accuracy decreases in forested areas. See LIMITATIONS.md. |

---

## 4. GPM IMERG (Rainfall)

| Field | Detail |
|-------|--------|
| **Name** | NASA Global Precipitation Measurement (GPM) Integrated Multi-satellitE Retrievals for GPM (IMERG) |
| **Version** | Late Run v06 (30-min, 0.1° resolution) |
| **Access** | Google Earth Engine: `NASA/GPM_L3/IMERG_V06` |
| **License** | NASA open data |
| **Event window** | 30 April – 6 May 2019 |
| **Citation** | Huffman, G.J., et al. (2019). NASA Global Precipitation Measurement (GPM) Integrated Multi-satellitE Retrievals for GPM (IMERG). |
| **Limitations** | 0.1° spatial resolution (~11km) — coarser than the model grid. Underestimates convective rainfall at sub-grid scales. |

---

## 5. SRTM Digital Elevation Model

| Field | Detail |
|-------|--------|
| **Name** | Shuttle Radar Topography Mission (SRTM) v3 |
| **Resolution** | 30m (1 arc-second) |
| **Access** | Google Earth Engine: `USGS/SRTMGL1_003` |
| **License** | Public domain (NASA/USGS) |
| **Used for** | Elevation data for surge bathtub propagation |
| **Limitations** | ~±10m vertical accuracy in forested or urban areas. Represents surface elevation (DSM), not bare-earth (DTM). Coastal accuracy may be reduced. |

---

## 6. MERIT Hydro HAND

| Field | Detail |
|-------|--------|
| **Name** | MERIT Hydro — Height Above Nearest Drainage (HAND) |
| **Access** | Google Earth Engine: `MERIT/Hydro/v1_0_1` |
| **License** | CC BY-NC 4.0 |
| **Used for** | Flood-prone area classification in rainfall model |
| **Citation** | Yamazaki, D., et al. (2019). MERIT Hydro. *Geophysical Research Letters*. https://doi.org/10.1029/2019GL081871 |
| **Limitations** | HAND approach is a static approximation; does not account for dynamic routing or drainage capacity. |

---

## 7. JRC Global Surface Water (Permanent Water Mask)

| Field | Detail |
|-------|--------|
| **Name** | JRC Monthly Water History |
| **Access** | Google Earth Engine: `JRC/GSW1_4/GlobalSurfaceWater` |
| **License** | Free for non-commercial use |
| **Used for** | Masking permanent water bodies in SAR flood detection |
| **Citation** | Pekel, J.F., et al. (2016). High-resolution mapping of global surface water. *Nature*. https://doi.org/10.1038/nature20584 |

---

## 8. OpenStreetMap (Infrastructure)

| Field | Detail |
|-------|--------|
| **Name** | OpenStreetMap |
| **Access** | `osmnx` library (Overpass API) |
| **License** | Open Database License (ODbL) |
| **Extracted features** | Hospitals, clinics, schools, community centres, substations, power lines, primary/secondary/trunk roads, district boundaries |
| **Snapshot date** | Downloaded during pipeline run (cached to `data/raw/`) |
| **Citation** | © OpenStreetMap contributors |
| **Limitations** | OSM completeness varies. Odisha infrastructure may be under-mapped in rural areas. Generator presence at hospitals is an assumption. |

---

## 9. Gemini API (Advisory Generation)

| Field | Detail |
|-------|--------|
| **Name** | Google Gemini (generative AI) |
| **Model** | `gemini-2.5-flash` (default; configurable via GEMINI_MODEL env var) |
| **License** | Google AI usage terms |
| **Used for** | Structured multilingual advisory generation (EN/HI/OR) |
| **Caching** | All responses cached by SHA-256 hash of input fact pack |
| **Note** | The model generates text; all numerical content is sourced from the pipeline fact pack. Outputs are validated against a Pydantic schema. |

---

## 10. WorldPop / GHSL (Population)

| Field | Detail |
|-------|--------|
| **Name** | WorldPop 2019 / Global Human Settlement Layer (GHSL) |
| **Access** | Google Earth Engine |
| **License** | CC BY 4.0 |
| **Used for** | Population-at-risk estimates in KPI header |
| **Fallback** | Census of India 2011 district totals (labelled ASSUMPTION if used) |
| **Citation** | WorldPop (2018). Population. University of Southampton. https://doi.org/10.5258/SOTON/WP00670 |

---

## Assumptions Log

All model assumptions are documented here and labelled in the UI.

| ID | Parameter | Value | Basis | Labelled? |
|----|-----------|-------|-------|-----------|
| A01 | RMW (radius of maximum winds) | 35 km | Holland (1980) empirical formula with Fani MSLP | Yes |
| A02 | Shelf depth (bathymetry proxy) | 15 m | Representative Bay of Bengal off Odisha | Yes |
| A03 | Fetch for wind setup | 500 km | Approximate open-water fetch | Yes |
| A04 | Astronomical tide at landfall | 1.2 m | Representative high tide; INCOIS climatology | Yes |
| A05 | Inland attenuation | 0.1 m/km | Calibratable parameter; initial estimate | Yes |
| A06 | Hospital generator backup | 12 h | Standard assumption; no verified data | Yes |
| A07 | Sum insured per district | Table in YAML | Illustrative; for parametric demo only | Yes |
| A08 | Wind setup coefficient | 0.0003 | Empirical estimate; calibrated for ~2m max setup | Yes |
| A09 | OSM generator presence | None | Conservatively assumed absent | Yes |
| A10 | Census population | 2011 census | Latest available; actual 2019 pop higher | Yes |
