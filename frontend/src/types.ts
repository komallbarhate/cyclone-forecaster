// ============================================================
// CycloneShield — TypeScript Type Definitions
// ============================================================

export interface TrackPoint {
  lat: number;
  lon: number;
  time_utc: string;
  hours_to_landfall: number;
  vmax_kt: number;
  vmax_kmh: number;
  mslp_hpa: number;
  rmw_km: number;
  trans_speed_kmh: number;
  trans_direction_deg: number;
}

export interface GeoJSONFeature {
  type: 'Feature';
  geometry: {
    type: string;
    coordinates: any;
  };
  properties: Record<string, any>;
}

export interface GeoJSONFeatureCollection {
  type: 'FeatureCollection';
  features: GeoJSONFeature[];
}

export interface DistrictWindTS {
  [district: string]: Array<{
    time_utc: string;
    hours_to_landfall: number;
    wind_kmh: number;
    wind_category: string;
    distance_km: number;
  }>;
}

export interface InfraAsset {
  id: string;
  name: string;
  type: 'hospital' | 'shelter' | 'substation' | 'road_node';
  lat: number;
  lon: number;
  district: string;
  osm_id?: string;
}

export interface ExposureResult {
  asset_id: string;
  asset_name: string;
  asset_type: string;
  district: string;
  lat: number;
  lon: number;
  max_surge_depth_m: number;
  max_rain_exposed: boolean;
  max_wind_kmh: number;
  first_flood_hour: number | null;
  risk_score: number;
}

export interface CascadeEvent {
  hour: number;
  hours_to_landfall: number;
  time_utc: string;
  asset_id: string;
  asset_name: string;
  asset_type: string;
  district: string;
  event_type: 'substation_failed' | 'power_lost' | 'generator_exhausted' | 'road_cut' | 'isolated' | 'restored';
  details: string;
  lat: number;
  lon: number;
}

export interface CascadeTimeline {
  events: CascadeEvent[];
  resilience_score: number;
  hardening_priorities: Array<{
    asset_id: string;
    asset_name: string;
    impact_score: number;
    protected_assets: number;
    protected_population: number;
  }>;
  district_summary: Record<string, {
    substations_failed: number;
    hospitals_on_generator: number;
    hospitals_isolated: number;
    shelters_isolated: number;
    roads_cut: number;
  }>;
}

export interface InsuranceTrigger {
  district: string;
  max_wind_kmh: number;
  max_surge_m: number;
  tier: string;
  payout_pct: number;
  sum_insured_cr: number;
  liquidity_cr: number;
  triggered: boolean;
  label: string;
}

export interface AdvisoryAction {
  action: string;
  owner: string;
  deadline: string;
  priority: 'IMMEDIATE' | 'URGENT' | 'HIGH' | 'MEDIUM';
}

export interface Advisory {
  district: string;
  language: 'en' | 'hi' | 'or';
  severity: 1 | 2 | 3 | 4 | 5;
  headline: string;
  situation_summary: string;
  top_actions: AdvisoryAction[];
  evacuation_priority: string[];
  hardening_recommendations: string[];
  public_message: string;
  generated_at: string;
  fact_pack_hash: string;
}

export interface ValidationMetrics {
  overall: {
    iou: number;
    precision: number;
    recall: number;
    f1: number;
    observed_area_km2: number;
    modeled_area_km2: number;
  };
  per_district: Record<string, {
    iou: number;
    precision: number;
    recall: number;
    f1: number;
  }>;
  calibration_applied: boolean;
  notes: string;
}

export interface ScenarioConfig {
  name: string;
  basin: string;
  storm_id: string;
  aoi_bbox: [number, number, number, number];
  landfall: {
    lat: number;
    lon: number;
    time_utc: string;
    vmax_kmh: number;
    mslp_hpa: number;
  };
  districts: string[];
  timeline: {
    start_hours: number;
    end_hours: number;
    step_hours: number;
  };
}

export interface KPISummary {
  total_assets_at_risk: number;
  hospitals_losing_power: number;
  shelters_isolated: number;
  people_exposed: number;
  districts_triggered_insurance: number;
  max_surge_m: number;
  max_wind_kmh: number;
  scenario_name: string;
}

export type LayerName = 'track' | 'wind' | 'surge' | 'rainfall' | 'hospitals' | 'shelters' | 'substations' | 'roads';

export type TabName = 'advisory' | 'cascade' | 'validation' | 'insurance' | 'about';

export type Language = 'en' | 'hi' | 'or';

export interface AppState {
  currentHour: number;   // hours_to_landfall
  isPlaying: boolean;
  activeLayers: Set<LayerName>;
  activeTab: TabName;
  selectedDistrict: string;
  language: Language;
  backendAvailable: boolean;
}

export interface DispatchLog {
  timestamp: string;
  district: string;
  authority_type: string;
  message_preview: string;
  dry_run: boolean;
  status: 'sent' | 'queued' | 'failed';
}
