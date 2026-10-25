// AirCrewOps API Client
import {
  DashboardSummary,
  FlightsResponse,
  CrewMember,
  Aircraft,
  DutyPeriod,
  RuleInspectorResponse,
  ADSDiagnostics,
  ADSLabResponse,
  DisruptionPreset,
  DisruptionExecuteResponse,
  FlightLeg,
} from '../types';

const API_BASE = '/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      // fallback
    }
    throw new Error(typeof errorDetail === 'string' ? errorDetail : JSON.stringify(errorDetail));
  }

  return res.json();
}

export const api = {
  // Dashboard & Health
  getDashboardSummary: (): Promise<DashboardSummary> =>
    fetchJson(`${API_BASE}/dashboard/summary`),

  // Flights & B-Tree range query
  getFlights: (params?: {
    origin?: string;
    destination?: string;
    aircraft_tail?: string;
    start_time_utc?: number;
    end_time_utc?: number;
    page?: number;
    page_size?: number;
  }): Promise<FlightsResponse> => {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, val]) => {
        if (val !== undefined && val !== null && val !== '') {
          searchParams.append(key, String(val));
        }
      });
    }
    const query = searchParams.toString();
    return fetchJson(`${API_BASE}/flights${query ? `?${query}` : ''}`);
  },

  createFlight: (flight: Partial<FlightLeg>): Promise<FlightLeg> =>
    fetchJson(`${API_BASE}/flights`, {
      method: 'POST',
      body: JSON.stringify(flight),
    }),

  rescheduleFlight: (
    flightId: string,
    payload: { delay_minutes: number; reason?: string }
  ): Promise<FlightLeg> =>
    fetchJson(`${API_BASE}/flights/${flightId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  // Crew & Schedule
  getCrew: (params?: { role?: string; airport?: string; is_active?: boolean }): Promise<CrewMember[]> => {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, val]) => {
        if (val !== undefined && val !== null && val !== '') {
          searchParams.append(key, String(val));
        }
      });
    }
    const query = searchParams.toString();
    return fetchJson(`${API_BASE}/crew${query ? `?${query}` : ''}`);
  },

  getCrewSchedule: (crewId: string): Promise<DutyPeriod[]> =>
    fetchJson(`${API_BASE}/crew/${crewId}/schedule`),

  // Aircraft & Rotations
  getAircraft: (params?: { aircraft_type?: string; base_airport?: string; is_active?: boolean }): Promise<Aircraft[]> => {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, val]) => {
        if (val !== undefined && val !== null && val !== '') {
          searchParams.append(key, String(val));
        }
      });
    }
    const query = searchParams.toString();
    return fetchJson(`${API_BASE}/aircraft${query ? `?${query}` : ''}`);
  },

  getAircraftRotation: (tailNumber: string): Promise<FlightLeg[]> =>
    fetchJson(`${API_BASE}/aircraft/${tailNumber}/rotation`),

  // Roster Management
  generateRoster: (payload?: {
    horizon_start_utc?: number;
    horizon_end_utc?: number;
    enforce_hard_rules?: boolean;
    disruption_mode?: boolean;
  }): Promise<{ message: string; roster_count: number; unassigned_count: number }> =>
    fetchJson(`${API_BASE}/roster/generate`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    }),

  manualAssign: (payload: {
    flight_number: string;
    captain_id: string;
    first_officer_id: string;
    cabin_crew_ids: string[];
    aircraft_tail: string;
  }): Promise<{ status: string; message: string; assignment: any }> =>
    fetchJson(`${API_BASE}/roster/manual-assign`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Constraints Inspector
  getConstraintsInspector: (): Promise<RuleInspectorResponse> =>
    fetchJson(`${API_BASE}/constraints/inspector`),

  // ADS Laboratory & Diagnostics
  getADSDiagnostics: (): Promise<ADSDiagnostics> =>
    fetchJson(`${API_BASE}/ads/diagnostics`),

  executeADSLabQuery: (payload: {
    structure: 'hash_table' | 'btree' | 'interval_tree' | 'graph';
    operation: string;
    params: Record<string, any>;
  }): Promise<ADSLabResponse> =>
    fetchJson(`${API_BASE}/ads/laboratory/query`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // System Controls
  resetDemo: (datasetProfile: 'demo' | 'test' = 'demo'): Promise<{ message: string; profile: string; flights_count: number }> =>
    fetchJson(`${API_BASE}/system/reset-demo`, {
      method: 'POST',
      body: JSON.stringify({ dataset_profile: datasetProfile }),
    }),

  // Disruptions
  getDisruptionPresets: (): Promise<{ presets: DisruptionPreset[] }> =>
    fetchJson(`${API_BASE}/disruptions/presets`),

  executeDisruption: (payload: {
    scenario_type: string;
    flight_number?: string;
    crew_id?: string;
    aircraft_tail?: string;
    delay_minutes?: number;
    override_captain_id?: string;
    override_aircraft_tail?: string;
  }): Promise<DisruptionExecuteResponse> =>
    fetchJson(`${API_BASE}/disruptions/execute`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
