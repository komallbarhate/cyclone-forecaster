"""
CycloneShield Pipeline Orchestrator
=====================================
Runs all pipeline steps in sequence with caching.
Each step is idempotent: skip if output already exists unless --force.

Usage:
    python pipeline/build_all.py [--force] [--scenario fani_2019] [--steps 1,2,3]
    python pipeline/build_all.py --help
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.utils.logger import get_logger, setup_file_logger

LOG_PATH = PROJECT_ROOT / "data" / "processed" / "pipeline.log"
log = get_logger(__name__)


def step_01_fetch_track(scenario: str, force: bool) -> bool:
    from pipeline.step_01_fetch_track import run
    return run(scenario=scenario, force=force)


def step_02_wind_field(scenario: str, force: bool) -> bool:
    from pipeline.step_02_wind_field import run
    return run(scenario=scenario, force=force)


def step_03_surge_model(scenario: str, force: bool) -> bool:
    from pipeline.step_03_surge_model import run
    return run(scenario=scenario, force=force)


def step_04_rainfall_model(scenario: str, force: bool) -> bool:
    from pipeline.step_04_rainfall_model import run
    return run(scenario=scenario, force=force)


def step_05_sar_validation(scenario: str, force: bool) -> bool:
    from pipeline.step_05_sar_validation import run
    return run(scenario=scenario, force=force)


def step_06_osm_infra(scenario: str, force: bool) -> bool:
    from pipeline.step_06_osm_infra import run
    return run(scenario=scenario, force=force)


def step_07_exposure(scenario: str, force: bool) -> bool:
    from pipeline.step_07_exposure import run
    return run(scenario=scenario, force=force)


def step_08_cascade(scenario: str, force: bool) -> bool:
    from pipeline.step_08_cascade import run
    return run(scenario=scenario, force=force)


def step_09_insurance(scenario: str, force: bool) -> bool:
    from pipeline.step_09_insurance import run
    return run(scenario=scenario, force=force)


def step_10_advisories(scenario: str, force: bool) -> bool:
    from pipeline.step_10_advisories import run
    return run(scenario=scenario, force=force)


STEPS: list[tuple[str, Callable]] = [
    ("01 Fetch Track (IBTrACS)", step_01_fetch_track),
    ("02 Wind Field (Holland)", step_02_wind_field),
    ("03 Surge Model (physics)", step_03_surge_model),
    ("04 Rainfall Model (IMERG+HAND)", step_04_rainfall_model),
    ("05 SAR Validation (Sentinel-1)", step_05_sar_validation),
    ("06 OSM Infrastructure", step_06_osm_infra),
    ("07 Exposure Analysis", step_07_exposure),
    ("08 Cascade Simulation", step_08_cascade),
    ("09 Insurance Triggers", step_09_insurance),
    ("10 Gemini Advisories", step_10_advisories),
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="CycloneShield Pipeline Orchestrator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        default="fani_2019",
        help="Scenario name (must match a file in config/scenarios/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run all steps even if cached outputs exist",
    )
    parser.add_argument(
        "--steps",
        default=None,
        help="Comma-separated step numbers to run (e.g. 1,2,6). Default: all",
    )
    return parser.parse_args()


def main() -> None:
    """Main orchestrator entry point."""
    args = parse_args()

    # Setup file logger
    setup_file_logger(__name__, LOG_PATH)

    # Determine which steps to run
    if args.steps:
        step_indices = {int(s.strip()) - 1 for s in args.steps.split(",")}
    else:
        step_indices = set(range(len(STEPS)))

    log.info(f"=== CycloneShield Pipeline: scenario={args.scenario} force={args.force} ===")

    results = []
    for i, (step_name, step_fn) in enumerate(STEPS):
        if i not in step_indices:
            log.info(f"  [SKIP] Step {i+1:02d}: {step_name}")
            continue

        log.info(f"  [RUN ] Step {i+1:02d}: {step_name}")
        t0 = time.time()
        try:
            ok = step_fn(scenario=args.scenario, force=args.force)
            elapsed = time.time() - t0
            status = "[OK]" if ok else "[WARN]"
            log.info(f"         {status} ({elapsed:.1f}s)")
            results.append((step_name, ok, elapsed))
        except Exception as e:
            elapsed = time.time() - t0
            log.error(f"         [FAIL] FAILED: {e}")
            results.append((step_name, False, elapsed))

    # Summary
    log.info("\n=== Pipeline Summary ===")
    for name, ok, elapsed in results:
        icon = "[OK]" if ok else "[FAIL]"
        log.info(f"  {icon} {name} ({elapsed:.1f}s)")

    failed = [r for r in results if not r[1]]
    if failed:
        log.warning(f"\n{len(failed)} step(s) failed. Check logs above.")
        sys.exit(1)
    else:
        log.info("\nAll steps completed successfully.")


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    main()
