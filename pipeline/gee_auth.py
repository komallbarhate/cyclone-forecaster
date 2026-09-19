"""
GEE Authentication Check Script
=================================
Run this script to verify Google Earth Engine authentication status.
Prints clear instructions if auth is missing or fails.

Usage:
    python pipeline/gee_auth.py
"""

from __future__ import annotations

import sys
from pipeline.utils.logger import get_logger

log = get_logger(__name__)

GEE_SETUP_INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════╗
║           Google Earth Engine Setup Instructions             ║
╠══════════════════════════════════════════════════════════════╣
║  GEE is required for:                                        ║
║    - Sentinel-1 SAR flood validation (Phase 2)               ║
║    - GPM IMERG rainfall data (Phase 2)                       ║
║    - SRTM/GLO-30 DEM for surge model (Phase 2)               ║
║    - Population data (WorldPop/GHSL) (KPI header)            ║
║                                                              ║
║  NOTE: For the demo, all GEE outputs are pre-cached.         ║
║  GEE is only needed if you want to re-run data prep.         ║
║                                                              ║
║  Setup steps:                                                ║
║  1. Create account: https://earthengine.google.com/          ║
║  2. Install: pip install earthengine-api                     ║
║  3. Authenticate: earthengine authenticate                   ║
║  4. Or set GEE_SERVICE_ACCOUNT + GEE_PRIVATE_KEY_FILE in .env║
╚══════════════════════════════════════════════════════════════╝
"""


def check_gee_auth() -> bool:
    """
    Attempt to initialize GEE and verify connectivity.

    Returns
    -------
    bool
        True if GEE is authenticated and responsive, False otherwise.
    """
    try:
        import ee  # type: ignore[import]
    except ImportError:
        log.warning("earthengine-api not installed. Run: pip install earthengine-api")
        return False

    try:
        # Try service account auth first
        import os
        sa = os.environ.get("GEE_SERVICE_ACCOUNT")
        key_file = os.environ.get("GEE_PRIVATE_KEY_FILE")
        project = os.environ.get("GEE_PROJECT")

        if sa and key_file:
            credentials = ee.ServiceAccountCredentials(sa, key_file)
            ee.Initialize(credentials, project=project)
            log.info("✅ GEE authenticated via service account")
        else:
            ee.Initialize(project=project)
            log.info("✅ GEE authenticated via OAuth")

        # Quick connectivity test
        test_img = ee.Image("USGS/SRTMGL1_003")
        info = test_img.getInfo()
        if info:
            log.info("✅ GEE connectivity test passed (SRTM image metadata fetched)")
            return True

    except Exception as e:
        log.warning(f"GEE auth check failed: {e}")
        log.warning("GEE is not required for the static demo (all data is pre-cached)")
        print(GEE_SETUP_INSTRUCTIONS)

    return False


if __name__ == "__main__":
    # Load .env if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    ok = check_gee_auth()
    if not ok:
        log.info("GEE auth not configured — demo will use cached data. Pipeline re-run requires GEE.")
        sys.exit(0)  # Non-fatal: don't break `make setup`
    log.info("GEE setup complete.")
    sys.exit(0)
