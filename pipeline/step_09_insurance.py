"""
Step 09 — Parametric Insurance Payout Trigger Engine
=====================================================
Evaluates district-level parametric catastrophe insurance triggers
based on pre-defined objective meteorological and oceanographic thresholds:
  - Tier 1 (Catastrophic): Wind >= 150 km/h OR (Wind >= 140 km/h AND Surge >= 2.0m) -> 100% Payout
  - Tier 2 (Severe): Wind >= 120 km/h AND Surge >= 1.0m (or Wind >= 135 km/h) -> 60% Payout
  - Tier 3 (Moderate): Wind >= 90 km/h AND Surge >= 0.5m (or Wind >= 110 km/h) -> 30% Payout
  - No Trigger: Below thresholds -> 0% Payout

Goal:
  Enable rapid, pre-agreed liquidity disbursement (within 24 hours of landfall)
  to municipal corporations and emergency disaster response funds without waiting
  for slow months-long physical loss adjusters.

Produces:
  - data/processed/insurance_triggers.json   (district-by-district trigger status and payout amounts)
  - data/processed/insurance_meta.json       (total liquidity unlocked, contract terms, disclaimer)

Usage:
    python pipeline/step_09_insurance.py [--scenario fani_2019] [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from pipeline.utils.logger import get_logger

log = get_logger(__name__)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_scenario(scenario_name: str) -> dict[str, Any]:
    cfg_path = PROJECT_ROOT / "config" / "scenarios" / f"{scenario_name}.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def evaluate_district_tier(
    wind_kmh: float,
    surge_m: float,
    tiers: list[dict[str, Any]],
) -> tuple[str, int, str]:
    """
    Evaluate parametric insurance trigger tier.
    Returns (tier_name, payout_pct, justification).
    """
    # Tier 1
    if (wind_kmh >= 150.0) or (wind_kmh >= 140.0 and surge_m >= 2.0):
        return (
            "Tier 1 — Catastrophic",
            100,
            f"Triggered: Wind {wind_kmh:.1f} km/h (>=140) and Surge {surge_m:.2f}m (>=2.0m)",
        )

    # Tier 2
    if (wind_kmh >= 120.0 and surge_m >= 1.0) or (wind_kmh >= 135.0):
        return (
            "Tier 2 — Severe",
            60,
            f"Triggered: Wind {wind_kmh:.1f} km/h (>=120) and Surge {surge_m:.2f}m (>=1.0m)",
        )

    # Tier 3
    if (wind_kmh >= 90.0 and surge_m >= 0.5) or (wind_kmh >= 110.0):
        return (
            "Tier 3 — Moderate",
            30,
            f"Triggered: Wind {wind_kmh:.1f} km/h (>=90) or sustained tropical storm gale",
        )

    return ("No Trigger", 0, "Hazard values below parametric minimum activation threshold")


def run(scenario: str = "fani_2019", force: bool = False) -> bool:
    """Run Step 09 Parametric Insurance evaluation."""
    triggers_out = PROCESSED_DIR / "insurance_triggers.json"
    meta_out = PROCESSED_DIR / "insurance_meta.json"

    if not force and triggers_out.exists() and meta_out.exists():
        log.info("Insurance trigger outputs already exist; use --force to re-run.")
        return True

    config = load_scenario(scenario)
    cfg_ins = config.get("insurance", {})
    tiers = cfg_ins.get("tiers", [])
    sum_insured_cr = cfg_ins.get("sum_insured_cr", {})
    districts = config.get("districts", ["Puri", "Khordha", "Jagatsinghpur", "Kendrapara", "Cuttack"])

    # Load district wind peaks
    wind_ts_file = PROCESSED_DIR / "wind_district_ts.json"
    district_peak_wind = {}
    if wind_ts_file.exists():
        with open(wind_ts_file) as f:
            w_data = json.load(f)
            for d, entries in w_data.items():
                if entries:
                    district_peak_wind[d] = max(e.get("wind_kmh", 0.0) for e in entries)

    # Load district surge peaks
    surge_ts_file = PROCESSED_DIR / "surge_district_ts.json"
    district_peak_surge = {}
    if surge_ts_file.exists():
        with open(surge_ts_file) as f:
            s_data = json.load(f)
            for d, vals in s_data.items():
                district_peak_surge[d] = vals.get("peak_surge_m", 0.0)

    log.info("Evaluating parametric payout triggers for scenario districts...")
    district_triggers = {}
    total_sum_insured_cr = 0.0
    total_payout_cr = 0.0

    for d in districts:
        w_peak = district_peak_wind.get(d, 110.0)
        s_peak = district_peak_surge.get(d, 0.0)
        sum_ins = sum_insured_cr.get(d, 500.0)
        total_sum_insured_cr += sum_ins

        tier_name, payout_pct, justification = evaluate_district_tier(w_peak, s_peak, tiers)
        payout_cr = (payout_pct / 100.0) * sum_ins
        total_payout_cr += payout_cr

        district_triggers[d] = {
            "district": d,
            "peak_wind_kmh": round(w_peak, 1),
            "peak_surge_m": round(s_peak, 2),
            "sum_insured_inr_cr": sum_ins,
            "trigger_tier": tier_name,
            "payout_percentage": payout_pct,
            "payout_amount_inr_cr": round(payout_cr, 2),
            "status": "DISBURSED" if payout_pct > 0 else "NO_PAYOUT",
            "justification": justification,
        }

    payout_ratio_pct = round((total_payout_cr / total_sum_insured_cr) * 100.0, 1) if total_sum_insured_cr > 0 else 0.0

    insurance_results = {
        "scenario": scenario,
        "label": "ILLUSTRATIVE — for demonstration only (parametric model)",
        "currency": "INR (₹ Crore)",
        "summary": {
            "total_sum_insured_inr_cr": round(total_sum_insured_cr, 2),
            "total_payout_inr_cr": round(total_payout_cr, 2),
            "total_payout_ratio_pct": payout_ratio_pct,
            "districts_triggered_count": sum(1 for d in district_triggers.values() if d["payout_percentage"] > 0),
            "total_districts": len(districts),
            "settlement_timeline": "T+24 Hours (Immediate liquidity post-landfall)",
        },
        "districts": district_triggers,
        "tiers": tiers,
    }

    with open(triggers_out, "w") as f:
        json.dump(insurance_results, f, indent=2)
    log.info(f"Saved insurance triggers to {triggers_out}: ₹{total_payout_cr:.1f} Cr payout triggered ({payout_ratio_pct}%)")

    meta = {
        "scenario": scenario,
        "total_payout_inr_cr": round(total_payout_cr, 2),
        "total_sum_insured_inr_cr": round(total_sum_insured_cr, 2),
        "disclaimer": "Parametric insurance mechanism is illustrative for disaster management proof-of-concept.",
        "oracle_feeds": "NOAA IBTrACS v04r00 (Wind) + INCOIS / CycloneShield Coastal Hydrodynamic Model (Surge)",
    }
    with open(meta_out, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Saved insurance metadata to {meta_out}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 09: Parametric Insurance Payout Trigger Engine")
    parser.add_argument("--scenario", default="fani_2019", help="Scenario name")
    parser.add_argument("--force", action="store_true", help="Force regenerate")
    args = parser.parse_args()

    ok = run(scenario=args.scenario, force=args.force)
    sys.exit(0 if ok else 1)
