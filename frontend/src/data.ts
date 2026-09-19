// ============================================================
// CycloneShield — Data Loading Utilities
// Loads pre-computed JSON/GeoJSON from /public/data/
// Falls back gracefully if files are missing.
// ============================================================

import type {
  GeoJSONFeatureCollection,
  CascadeTimeline,
  ValidationMetrics,
  InsuranceTrigger,
  Advisory,
  ScenarioConfig,
  KPISummary,
  DistrictWindTS,
} from './types';

const BASE = import.meta.env.BASE_URL;

async function fetchJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}data/${path}`);
    if (!res.ok) {
      console.warn(`[CycloneShield] Data file not found: ${path} (${res.status})`);
      return null;
    }
    return await res.json() as T;
  } catch (e) {
    console.warn(`[CycloneShield] Failed to load ${path}:`, e);
    return null;
  }
}

// ---- Layer GeoJSON loaders ----

export const loadTrackHourly = () =>
  fetchJSON<GeoJSONFeatureCollection>('track_hourly.geojson');

export const loadWindMax = () =>
  fetchJSON<GeoJSONFeatureCollection>('wind_max.geojson');

export const loadSurgeHourly = () =>
  fetchJSON<GeoJSONFeatureCollection>('surge_hourly.geojson');

export const loadRainfallFlood = () =>
  fetchJSON<GeoJSONFeatureCollection>('rainfall_flood.geojson');

export const loadInfra = () =>
  fetchJSON<GeoJSONFeatureCollection>('infra.geojson');

export const loadSARObserved = () =>
  fetchJSON<GeoJSONFeatureCollection>('sar_observed.geojson');

// ---- Analysis outputs ----

export const loadCascadeTimeline = () =>
  fetchJSON<CascadeTimeline>('cascade_timeline.json');

export const loadValidationMetrics = () =>
  fetchJSON<ValidationMetrics>('metrics.json');

export const loadInsuranceTriggers = () =>
  fetchJSON<InsuranceTrigger[]>('insurance_triggers.json');

export const loadAdvisories = () =>
  fetchJSON<Advisory[]>('advisories.json');

export const loadDistrictWindTS = () =>
  fetchJSON<DistrictWindTS>('wind_district_ts.json');

export const loadKPI = () =>
  fetchJSON<KPISummary>('kpi.json');

// ---- Scenario config ----

export const loadScenarioConfig = () =>
  fetchJSON<ScenarioConfig>('scenario_config.json');

// ---- Check backend availability ----

export async function checkBackend(baseUrl: string = '/api'): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(2000) });
    return res.ok;
  } catch {
    return false;
  }
}

// ---- Helper: filter surge features by hour ----

export function filterSurgeByHour(
  surgeData: GeoJSONFeatureCollection,
  hoursToLandfall: number,
  toleranceHours: number = 0.6,
): GeoJSONFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: surgeData.features.filter((f) => {
      const h = f.properties?.hours_to_landfall ?? 0;
      return Math.abs(h - hoursToLandfall) <= toleranceHours;
    }),
  };
}

// ---- Helper: get track point nearest to hour ----

export function getTrackAtHour(
  trackData: GeoJSONFeatureCollection,
  hoursToLandfall: number,
): GeoJSONFeatureCollection['features'][0] | null {
  if (!trackData?.features?.length) return null;
  return trackData.features.reduce((best, feat) => {
    const h = feat.properties?.hours_to_landfall ?? 0;
    const bestH = best?.properties?.hours_to_landfall ?? 0;
    return Math.abs(h - hoursToLandfall) < Math.abs(bestH - hoursToLandfall) ? feat : best;
  });
}
