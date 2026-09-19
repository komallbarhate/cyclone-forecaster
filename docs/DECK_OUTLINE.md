# Deck Outline — CycloneShield

## 10-Slide Presentation

Export target: PDF ≤ 5 MB | 16:9 format | Dark control-room theme

---

## Slide 1 — Title

**Title**: CycloneShield
**Subtitle**: Pre-landfall Decisions, Not Post-landfall Recovery
**Visual**: Satellite image of Odisha coast with storm spiral overlay
**Bottom**: "Build with AI: Code for Communities | Track 5 BRICS/Bay of Bengal"

---

## Slide 2 — The Problem

**Headline**: "64 lives saved. 1.5 million displaced. The gap is decision intelligence."

**Body**:
- Cyclone Fani (2019): India's best evacuation — but power grid down for weeks
- Authorities knew the storm was coming. They didn't know *what would break first*
- No pre-landfall visibility into: which substations flood, which hospitals lose power,
  which evacuation routes fail, when insurance pays out

**Visual**: Before/after satellite images of Puri coastline; power outage map

---

## Slide 3 — The Insight

**Headline**: "Every infrastructure failure is predictable. We just haven't connected the dots."

**Three insights**:
1. Cyclone physics are well-understood — storm surge can be modelled hours before landfall
2. Infrastructure failure cascades deterministically — if we know the graph, we can simulate it
3. AI can translate raw numbers into actionable authority guidance at scale

**Visual**: Cascade graph diagram (substations → hospitals → roads)

---

## Slide 4 — The Solution

**Headline**: CycloneShield — 5 Capabilities in One Pipeline

**Grid layout**:
- 🌊 Storm Surge Maps (physics-informed, hourly)
- ⚡ Cascade Failure Timeline (NetworkX simulation)
- 📋 AI Advisories (Gemini, EN/HI/OR, schema-validated)
- 💰 Parametric Insurance Triggers (per district, real-time)
- 📱 Authority Dispatch (Telegram, tailored by role)

**Visual**: App screenshot — map with all layers active

---

## Slide 5 — Live Demo

**Headline**: "T-24h before Fani's landfall — here's what we knew"

**Screenshot 1**: Storm track + wind field over Odisha coast
**Screenshot 2**: Surge depth layer — Puri coast flooded 3–4m
**Screenshot 3**: Cascade timeline — "Hour T+3: Substation Puri-East → Hospitals A, B on generator"
**Screenshot 4**: Gemini advisory in Odia for Puri District Collector

**Caption**: All data from open sources. All numbers computed, not assumed.

---

## Slide 6 — Architecture

**Headline**: Fully open, config-driven, free-tier

**Mermaid/diagram** (simplified):
```
IBTrACS → Wind Field → Storm Surge   }
GPM IMERG → HAND Model              } → Cascade Graph → Gemini Advisory → Dispatch
OSM → Road + Power Network          }
Sentinel-1 SAR (Validation)
```

**Key callouts**:
- Pre-computed offline → demo never breaks
- Config-driven: one YAML per scenario
- Free hosting: Vercel + Render

---

## Slide 7 — Honest Validation

**Headline**: "We validate our model against satellite data. Here are the real numbers."

**Table**:
| Metric | Overall | Puri | Khordha | Jagatsinghpur |
|--------|---------|------|---------|---------------|
| IoU | [X] | [X] | [X] | [X] |
| Precision | [X] | [X] | [X] | [X] |
| Recall | [X] | [X] | [X] | [X] |
| F1 | [X] | [X] | [X] | [X] |

**Note**: Values populated from metrics.json after pipeline run.

**Visual**: Side-by-side: Sentinel-1 observed flood extent vs modelled surge extent

**Callout**: "Known limitations: simplified surge model, 30m DEM, SAR temporal gap — all documented in LIMITATIONS.md"

---

## Slide 8 — Cascade + Insurance Example

**Headline**: "The cascade failure timeline — minute by minute"

**Timeline visual**:
```
T+0h  Landfall: Puri coast — surge 3.8m
T+2h  Substation Puri-East flooded (depth 1.2m > 0.5m threshold)
T+2h  Hospitals A, B switch to generator (12h backup clock starts)
T+3h  Road NH-316 impassable — Kendrapara shelter isolated
T+14h Generator exhaustion: Hospitals A, B lose power
T+18h Generator exhaustion: Hospital C loses power
```

**Insurance callout**:
- Puri: Tier 1 Catastrophic (wind 175 km/h, surge 3.8m) → 100% payout trigger
- Khordha: Tier 2 Severe → 60% payout trigger

---

## Slide 9 — BRICS Scale & Roadmap

**Headline**: "One config file. Any Bay of Bengal cyclone. Any BRICS coastal state."

**Map**: Bay of Bengal with Bangladesh, Myanmar, Sri Lanka, Thailand marked

**To add a new scenario**:
```yaml
# config/scenarios/amphan_2020.yaml
name: "Cyclone Amphan 2020"
aoi_bbox: [87.5, 21.0, 90.0, 23.5]  # West Bengal / Bangladesh
landfall:
  time_utc: "2020-05-20T12:30:00Z"
  ...
```

**Roadmap**:
- Real-time data ingestion (Open-Meteo, IMD API)
- Multi-hazard extension (heat, flood)
- Mobile app for field workers
- Integration with NDMA/OSDMA systems

---

## Slide 10 — The Ask

**Headline**: "Help us protect 100 million Bay of Bengal coastal residents"

**What we've built**: Working end-to-end prototype with real data, real validation
**What we need**: Deployment resources, domain expert partnerships, IMD/NDMA integration

**Open source**: MIT License | github.com/[YOUR_USERNAME]/cycloneshield
**Demo**: [YOUR_DEMO_URL]

**Quote**: "Shift from post-landfall recovery to pre-landfall action."

**Team**: [Your name] | [Contact] | [Country]

---

## Export Instructions

1. Build these slides in Google Slides or PowerPoint with dark background (#0F172A)
2. Use Inter or Roboto font, white text, accent colour #38BDF8 (sky blue)
3. Export as PDF: File → Download → PDF Document
4. Verify file size < 5 MB (compress images if needed)
5. Screenshot app at each stage and insert into Slides 5, 7, 8
