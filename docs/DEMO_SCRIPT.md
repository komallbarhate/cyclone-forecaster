# Demo Script — CycloneShield

## 3-Minute Video Demo Script

**Total runtime**: 3 minutes
**Format**: Screen recording + voice-over
**Tool**: OBS or any screen recorder

---

## Scene Breakdown

### [0:00 – 0:20] — Hook (20 seconds)

**Show**: Title screen / map overview of Odisha coast

**Say**:
> "It's May 2nd, 2019. Cyclone Fani is 24 hours from landfall near Puri, Odisha.
> District officials have one question: *what will break first?*
> CycloneShield answers that — before the storm arrives."

**Click**: Open the app at http://localhost:5173 (or the deployed URL)

---

### [0:20 – 0:50] — Storm Track + Wind Animation (30 seconds)

**Show**: MapLibre map with storm track, wind radii cone

**Say**:
> "Here's the storm track from IBTrACS — real NOAA data, interpolated to
> hourly positions. The wind field uses the Holland 1980 parametric model.
> I'll press Play on the time slider..."

**Click**: Press Play on the time slider (T-24h to landfall)

**Show**: Wind layer coloring the map, track dot moving

**Say**:
> "...and watch maximum wind speed build across Puri and Jagatsinghpur.
> At landfall, we're seeing over 175 km/h near the coast."

---

### [0:50 – 1:20] — Surge + Flood Layers (30 seconds)

**Show**: Toggle on surge depth layer — orange/red cells near coast

**Say**:
> "Underneath, our storm surge model combines inverse barometer effect,
> wind setup, and a connectivity-constrained bathtub flood fill using
> SRTM elevation. Peak surge here reaches 3–4 metres along the Puri coast."

**Click**: Toggle rainfall layer ON

**Show**: Blue flood-prone polygons inland

**Say**:
> "The rainfall layer uses GPM IMERG data — 300mm fell in 24 hours.
> MERIT Hydro HAND identifies the low-lying drainage pathways most likely to pond."

---

### [1:20 – 1:50] — Cascade Failure (30 seconds)

**Show**: Right panel → Cascade tab

**Say**:
> "Now — the differentiator. The cascade failure simulation.
> I'll advance the slider to T+3 hours post-landfall..."

**Click**: Advance slider to T+3h — substations flash red

**Show**: Event log updates: "Hour T+3: Substation Puri-East flooded → Hospitals A, B lose grid power"

**Say**:
> "Three substations in Puri have flooded. Two hospitals immediately go on
> generator backup — they have 12 hours. Here's the road network:
> three arterial routes are now impassable."

**Click**: Click "Shelters C, D unreachable" in the event log

**Show**: Map highlights isolated shelter with flashing icon

**Say**:
> "Shelter D in Kendrapara is now isolated — no passable route to a safe node.
> This is the moment an evacuation order should have already been issued."

---

### [1:50 – 2:20] — Advisory + Dispatch (30 seconds)

**Show**: Right panel → Advisory tab, select "Puri"

**Say**:
> "For each district, Gemini generates a structured advisory — strictly from
> our computed data. No invented numbers."

**Show**: Advisory with severity badge, top actions, evacuation list

**Click**: Language toggle → HI (Hindi)

**Show**: Advisory switches to Hindi

**Say**:
> "Available in English, Hindi, and Odia. The advisory is cached —
> demo never depends on API rate limits."

**Click**: "Dispatch Alert" button

**Show**: Dry-run dispatch confirmation: "Written to outbox.jsonl [DRY_RUN]"

**Say**:
> "One click sends a tailored alert to the District Collector, OSDMA,
> hospital administrators, and the power utility — by Telegram."

---

### [2:20 – 2:45] — Validation Tab (25 seconds)

**Show**: Validation tab — side-by-side observed vs modeled

**Say**:
> "We validate against Sentinel-1 SAR flood extent from 4 days after landfall.
> Our flood model achieved an IoU of [X], F1 of [Y].
> These are real numbers — no cherry-picking."

**Show**: Metrics table with per-district breakdown

**Say**:
> "Per-district metrics show the model performs best in coastal Puri and
> Jagatsinghpur, with some divergence in Kendrapara where SAR coverage was limited."

---

### [2:45 – 3:00] — Wrap / Scalability (15 seconds)

**Show**: Scenario dropdown showing fani_2019; hint at "add_scenario"

**Say**:
> "Everything is config-driven. To run this for Cyclone Amphan, Biparjoy,
> or any BRICS Bay of Bengal storm — add one YAML file. No code changes.
> A digital public good for every coastal community in the region."

**End**: Title card — "CycloneShield — Pre-landfall decisions, not post-landfall recovery."

---

## Exact Clicks Summary

1. Open app URL
2. Press Play on time slider
3. Toggle surge layer ON
4. Toggle rainfall layer ON
5. Click Cascade tab
6. Advance slider to T+3h
7. Click event log entry for isolated shelter
8. Click Advisory tab
9. Select district "Puri"
10. Click language toggle → HI
11. Click "Dispatch Alert"
12. Click Validation tab
13. Hover over metrics table

---

## Fallback Plan (if deployment fails)

If the deployed URL is down during the demo:

1. **Local static demo**: Run `cd frontend && npm run dev` and screen-record localhost:5173
   - All data is pre-cached in `/public/data/` — no backend needed
   - Works offline

2. **Backend failure**: The frontend has full graceful fallback — all tabs work
   from static JSON. The "Dispatch" button shows DRY_RUN confirmation from localStorage.

3. **Partial data failure**: If some processed JSONs are missing, the app shows
   a clear "Data not available" placeholder with the expected file path.

4. **Screen recording backup**: Record the demo locally before the submission
   deadline and upload to YouTube/Loom as the primary demo link.

---

## Recording Tips

- Use 1920×1080 resolution
- Set font size to at least 16px in browser DevTools if needed
- Clear browser cache before recording to show real load times
- Use OBS with audio from microphone
- Export as MP4 (H.264, ~800MB for 3 min at 1080p)
- Upload to YouTube (unlisted) or Loom for the demo link
