"""
CycloneShield FastAPI Backend — Skeleton (Phase 0)
====================================================
Full implementation in Phase 5. This skeleton provides all routes
so the frontend can be developed against it from Phase 6.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="CycloneShield API",
    description="Cyclone Impact & Infrastructure Vulnerability Forecaster",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/scenarios")
async def scenarios() -> dict:
    """Return list of available scenarios."""
    return {"scenarios": [settings.default_scenario], "default": settings.default_scenario}


@app.get("/timeline")
async def timeline(scenario: str = "fani_2019") -> dict:
    """Return the storm track timeline for a scenario."""
    return {"status": "not_implemented", "phase": 5}


@app.get("/layers/{layer_name}")
async def get_layer(layer_name: str, scenario: str = "fani_2019") -> dict:
    """Return a GeoJSON layer by name."""
    return {"status": "not_implemented", "layer": layer_name, "phase": 5}


@app.get("/exposure")
async def exposure(scenario: str = "fani_2019") -> dict:
    """Return infrastructure exposure analysis."""
    return {"status": "not_implemented", "phase": 5}


@app.get("/cascade")
async def cascade(scenario: str = "fani_2019") -> dict:
    """Return cascade failure timeline."""
    return {"status": "not_implemented", "phase": 5}


@app.get("/advisories")
async def advisories(scenario: str = "fani_2019", district: str | None = None, lang: str = "en") -> dict:
    """Return Gemini-generated advisories."""
    return {"status": "not_implemented", "phase": 5}


@app.get("/insurance")
async def insurance(scenario: str = "fani_2019") -> dict:
    """Return parametric insurance trigger results."""
    return {"status": "not_implemented", "phase": 5}


@app.get("/validation")
async def validation(scenario: str = "fani_2019") -> dict:
    """Return SAR validation metrics."""
    return {"status": "not_implemented", "phase": 5}


@app.post("/dispatch")
async def dispatch(payload: dict) -> dict:
    """Dispatch alert to Telegram (DRY_RUN by default)."""
    return {"status": "not_implemented", "phase": 5}
