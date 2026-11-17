"""
Config Wizard Backend - FastAPI server for the simulation config builder.

Serves:
  - Static frontend files
  - /api/counties  -> GeoJSON county boundaries + population
  - /api/export    -> Assemble and download config.json
"""

import json
import zipfile
import io
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import geopandas as gpd
import requests

try:  # package import and uvicorn main:app from backend/
    from .config_service import ConfigService, ConfigurationError
    from .preset_service import PresetService
except ImportError:
    from config_service import ConfigService, ConfigurationError
    from preset_service import PresetService

app = FastAPI(title="Simulation Config Wizard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # e:/projects/code
DATA_DIR = PROJECT_ROOT / "data"
COUNTIES_DIR = DATA_DIR / "counties"
SHAPEFILE_PATH = COUNTIES_DIR / "cb_2022_us_county_500k.shp"
COUNTY_GEOJSON_CACHE = COUNTIES_DIR / "counties.geojson"
COUNTY_POP_CACHE = COUNTIES_DIR / "county_population.json"
SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_county_500k.zip"

# Census API for population (ACS 5-year, most recent)
CENSUS_POP_URL = "https://api.census.gov/data/2022/acs/acs5"

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Default config template (reference)
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config_local.json"
config_service = ConfigService(PROJECT_ROOT)


def ensure_shapefile():
    """Download county shapefile if not already cached."""
    if SHAPEFILE_PATH.exists():
        return
    COUNTIES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading county shapefile from {SHAPEFILE_URL}...")
    resp = requests.get(SHAPEFILE_URL, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(COUNTIES_DIR)
    print("County shapefile downloaded and extracted.")


def build_county_geojson():
    """
    Convert shapefile to simplified GeoJSON for frontend map.
    Cached to disk so we only do this once.
    """
    if COUNTY_GEOJSON_CACHE.exists():
        return

    ensure_shapefile()
    print("Building county GeoJSON (simplified for web)...")
    gdf = gpd.read_file(SHAPEFILE_PATH)

    # Build 5-digit GEOID from STATEFP + COUNTYFP
    gdf["GEOID"] = gdf["STATEFP"] + gdf["COUNTYFP"]

    # Simplify geometry for faster rendering (tolerance in degrees ~500m)
    gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.005, preserve_topology=True)

    # Keep only needed columns
    gdf = gdf[["GEOID", "STATEFP", "COUNTYFP", "NAMELSAD", "ALAND", "geometry"]]
    gdf = gdf.rename(columns={"NAMELSAD": "name"})

    # Convert ALAND to sq miles for display
    gdf["area_sq_mi"] = (gdf["ALAND"] / 2_589_988).round(1)
    gdf = gdf.drop(columns=["ALAND"])

    gdf.to_file(COUNTY_GEOJSON_CACHE, driver="GeoJSON")
    print(f"County GeoJSON cached: {COUNTY_GEOJSON_CACHE}")


def build_population_lookup():
    """
    Fetch county-level population from Census ACS API.
    Builds a JSON lookup: { "GEOID": population, ... }
    Falls back to a simplified estimate from land area if API fails.
    """
    if COUNTY_POP_CACHE.exists():
        return

    print("Fetching county population data from Census API...")
    pop_data = {}

    try:
        # ACS 5-year: B01003_001E = Total Population
        params = {
            "get": "B01003_001E,NAME",
            "for": "county:*",
        }
        resp = requests.get(CENSUS_POP_URL, params=params, timeout=60)
        resp.raise_for_status()
        rows = resp.json()

        # First row is header: ['B01003_001E', 'NAME', 'state', 'county']
        for row in rows[1:]:
            pop_str, name, state_fips, county_fips = row
            geoid = f"{state_fips}{county_fips}"
            try:
                pop_data[geoid] = int(pop_str)
            except (ValueError, TypeError):
                pop_data[geoid] = 0

        print(f"Loaded population for {len(pop_data)} counties")

    except Exception as e:
        print(f"Census API failed: {e}")
        print("Population data will not be available for county selection cap.")

    COUNTIES_DIR.mkdir(parents=True, exist_ok=True)
    with open(COUNTY_POP_CACHE, "w") as f:
        json.dump(pop_data, f)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    build_county_geojson()
    build_population_lookup()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/counties")
async def get_counties():
    """Return county GeoJSON with population data merged in."""
    if not COUNTY_GEOJSON_CACHE.exists():
        raise HTTPException(500, "County GeoJSON not built yet")

    with open(COUNTY_GEOJSON_CACHE, "r") as f:
        geojson = json.load(f)

    # Merge population
    pop_data = {}
    if COUNTY_POP_CACHE.exists():
        with open(COUNTY_POP_CACHE, "r") as f:
            pop_data = json.load(f)

    for feature in geojson.get("features", []):
        geoid = feature["properties"].get("GEOID", "")
        feature["properties"]["population"] = pop_data.get(geoid, 0)

    return JSONResponse(geojson)


@app.post("/api/export")
async def export_config(request: Request):
    """
    Validate and normalize a complete configuration for download.
    Legacy wizard payloads remain supported with a deprecation diagnostic.
    """
    try:
        form_data = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    try:
        result = config_service.export_submission(form_data)
    except (ConfigurationError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    # Keep the existing frontend download contract; diagnostics are also
    # available as structured JSON from /api/config/prepare.
    headers = {
        "X-Config-Issues": json.dumps(result.issues, ensure_ascii=True),
        "X-Config-Migrations": json.dumps(result.migrations),
    }
    if any(issue['code'] == 'legacy_export_payload' for issue in result.issues):
        headers['X-Config-Input-Format'] = 'legacy-wizard; deprecated'
    return JSONResponse(result.config, headers=headers)


@app.get("/api/defaults")
async def get_defaults():
    """Return default config values for pre-populating the wizard."""
    defaults = get_default_config()
    return JSONResponse(defaults)


def get_default_config():
    """Return a fresh maintained baseline, without execution state."""
    return config_service.load_baseline().config


def assemble_config(form_data: dict) -> dict:
    """Compatibility wrapper for callers expecting an engine configuration."""
    return config_service.export_submission(form_data).config


@app.get("/api/examples")
async def get_examples():
    return {"examples": config_service.list_examples()}


@app.post("/api/config/prepare")
async def prepare_config(request: Request):
    """Prepare config plus compatibility/portability diagnostics, without I/O preflight."""
    try:
        result = config_service.assemble(await request.json())
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"config": result.config, "issues": result.issues,
            "migrations": result.migrations}


@app.get("/api/config/presets")
async def get_config_presets():
    """Curated experiments, including separate survey variants per region."""
    try:
        return {"presets": PresetService(config_service).list()}
    except ConfigurationError as exc:
        raise HTTPException(500, "A registered preset configuration could not be loaded") from exc


@app.get("/api/config/presets/{preset_id}")
async def get_config_preset(preset_id: str):
    try:
        return PresetService(config_service).load(preset_id)
    except KeyError as exc:
        raise HTTPException(404, "Unknown configuration preset") from exc
    except ConfigurationError as exc:
        raise HTTPException(500, "The registered preset configuration could not be loaded") from exc


# ---------------------------------------------------------------------------
# Static file serving (frontend)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
