"""
Pytest configuration and shared fixtures for CycloneShield tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# ---- Fixtures ----------------------------------------------------------------


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def scenario_config() -> dict:
    """Load the Fani 2019 scenario config as a dict."""
    import yaml
    config_path = PROJECT_ROOT / "config" / "scenarios" / "fani_2019.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def processed_dir() -> Path:
    """Return the processed data directory."""
    d = PROJECT_ROOT / "data" / "processed"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def sample_track_points() -> list[dict[str, Any]]:
    """
    Return a minimal sample of track points for unit testing.
    These are simplified/representative values, NOT real IBTrACS data.
    Used only to test interpolation and wind field logic.
    """
    return [
        {"lat": 9.5, "lon": 84.0, "vmax_kt": 35, "mslp_hpa": 998, "time_utc": "2019-04-26T00:00:00Z"},
        {"lat": 10.5, "lon": 84.5, "vmax_kt": 55, "mslp_hpa": 980, "time_utc": "2019-04-28T00:00:00Z"},
        {"lat": 13.0, "lon": 84.9, "vmax_kt": 95, "mslp_hpa": 940, "time_utc": "2019-05-01T00:00:00Z"},
        {"lat": 19.85, "lon": 85.85, "vmax_kt": 95, "mslp_hpa": 932, "time_utc": "2019-05-03T02:40:00Z"},  # landfall
        {"lat": 21.5, "lon": 85.5, "vmax_kt": 45, "mslp_hpa": 968, "time_utc": "2019-05-04T00:00:00Z"},
    ]


@pytest.fixture(scope="session")
def sample_bbox() -> list[float]:
    """Return the Fani AOI bounding box."""
    return [84.9, 19.6, 86.5, 20.7]


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "gee: mark test as requiring GEE auth (skip without)")
    config.addinivalue_line("markers", "gemini: mark test as requiring Gemini API key")
    config.addinivalue_line("markers", "slow: mark test as slow (data download)")
