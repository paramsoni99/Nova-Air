// AirCrewOps — Nova Air Domain & API Types

export type NavTab = 
  | 'overview' 
  | 'schedule' 
  | 'roster' 
  | 'crew' 
  | 'fleet' 
  | 'constraints' 
  | 'disruptions' 
  | 'laboratory';

export interface Airport {
  iata_code: string;
  name: string;
  city: string;
  country: string;
  timezone_offset_utc: number;
  latitude: number;
  longitude: number;
  is_hub: boolean;
  curfew_start_hour?: number | null;
  curfew_end_hour?: number | null;
}

export interface Aircraft {
  tail_number: string;
  aircraft_type: string;
  home_base: string;
  total_flight_hours: number;
  seating_capacity: number;
  is_active: boolean;
  current_location?: string;
}

export interface CrewQualification {
  aircraft_type: string;
  valid_until_utc: number;
}

export interface CrewMember {
  id: string;
  name: string;
  role: 'CAPTAIN' | 'FIRST_OFFICER' | 'CABIN_CREW';
  home_base: string;
  current_location: string;
  is_active: boolean;
  qualifications: CrewQualification[];
  cumulative_flight_hours_7d?: number;
  cumulative_duty_hours_7d?: number;
  last_duty_release_utc?: number;
}

export interface FlightLeg {
  flight_number: string;
  origin: string;
  destination: string;
  departure_utc: number;
  arrival_utc: number;
  aircraft_type: string;
  aircraft_tail?: string | null;
  effective_departure_utc?: number;
  effective_arrival_utc?: number;
  delay_minutes?: number;
  status?: string;
  captain_id?: string | null;
  first_officer_id?: string | null;
  cabin_crew_ids?: string[];
  is_covered?: boolean;
  uncovered_reason?: UncoveredReason | null;
}

export interface DutyPeriod {
  duty_id: string;
  crew_id: string;
  report_utc: number;
  release_utc: number;
  duty_type: string;
  flight_numbers: string[];
}

export interface RosterAssignment {
  assignment_id: string;
  flight_number: string;
  captain_id: string;
  first_officer_id: string;
  cabin_crew_ids: string[];
  aircraft_tail: string;
  created_at_utc: number;
  status: 'ASSIGNED' | 'UNASSIGNED';
  soft_penalty_score?: number;
  soft_penalty_breakdown?: Record<string, number>;
  uncovered_reason?: UncoveredReason | null;
}

export interface RuleViolation {
  rule_id: string;
  severity: 'HARD' | 'SOFT';
  message: string;
  entity_id: string;
  context: Record<string, any>;
}

export interface UncoveredReason {
  flight_number?: string;
  primary_cause: string;
  summary: string;
  aircraft_violations: RuleViolation[];
  crew_violations: RuleViolation[];
  details: Record<string, any>;
}

export interface DashboardSummary {
  system_name: string;
  carrier_name: string;
  rule_profile_id: string;
  academic_disclaimer: string;
  current_time_utc: number;
  total_flights: number;
  covered_flights: number;
  unassigned_flights: number;
  active_aircraft: number;
  active_crew: number;
  disruptions_active: number;
  kpis: {
    coverage_rate_percent: number;
    hard_violations_count: number;
    active_conflicts: number;
    average_tat_slack_minutes: number;
    deadhead_positioning_legs: number;
  };
  ads_telemetry: {
    hash_table_items: number;
    hash_table_load_factor: number;
    btree_keys: number;
    btree_height: number;
    interval_tree_nodes: number;
    graph_vertices: number;
    graph_edges: number;
  };
}

export interface BTreeRangeTelemetry {
  start_time_utc: number;
  end_time_utc: number;
  total_matching_flights: number;
  range_nodes_visited: number;
  key_comparisons: number;
  height: number;
}

export interface FlightsResponse {
  total: number;
  page: number;
  page_size: number;
  flights: FlightLeg[];
  btree_range_telemetry?: BTreeRangeTelemetry | null;
}

export interface RuleProfileParam {
  parameter_id: string;
  name: string;
  value: any;
  unit: string;
  classification: 'STATUTORY_DGCA_BASELINE' | 'OPERATOR_POLICY' | 'DEMO_ASSUMPTION';
  citation: string;
  description: string;
}

export interface RuleInspectorResponse {
  profile_id: string;
  name: string;
  effective_date: string;
  academic_disclaimer: string;
  regulatory_source: string;
  rules_count: number;
  parameters: RuleProfileParam[];
}

export interface DisruptionPreset {
  scenario_type: 'PILOT_SICK' | 'AIRCRAFT_AOG' | 'FLIGHT_DELAY_CASCADE' | 'NO_LEGAL_SOLUTION' | 'INVALID_MANUAL_OVERRIDE';
  title: string;
  description: string;
  target_id: string;
  delay_minutes?: number;
  academic_objective: string;
}

export interface DisruptionExecuteResponse {
  success: boolean;
  scenario: string;
  target_id: string;
  message: string;
  impacted_flights_count: number;
  impacted_flights: string[];
  reassigned_flights_count: number;
  reassigned_flights: string[];
  unassigned_flights_count: number;
  unassigned_flights: string[];
  violations_prevented_count: number;
  violations: RuleViolation[];
  ads_mutations: {
    btree_keys_updated?: number;
    interval_tree_conflicts_resolved?: number;
    graph_edges_updated?: number;
    hash_lookups?: number;
  };
  details: Record<string, any>;
}

export interface WebSocketEvent {
  event_type: string;
  timestamp_utc: number;
  payload: Record<string, any>;
}

export interface ADSDiagnostics {
  hash_table: {
    size: number;
    capacity: number;
    load_factor: number;
    collision_count: number;
    max_chain_length: number;
  };
  btree: {
    keys_count: number;
    height: number;
    min_degree: number;
    node_count: number;
  };
  interval_tree: {
    aircraft_trees_count: number;
    crew_trees_count: number;
    total_intervals: number;
    black_height_consistent: boolean;
  };
  graph: {
    airports_count: number;
    flights_count: number;
    edges_count: number;
    average_degree: number;
  };
  priority_queue: {
    size: number;
    heap_invariant_verified: boolean;
  };
}

export interface ADSLabResponse {
  structure: string;
  operation: string;
  execution_time_ms: number;
  time_complexity: string;
  space_complexity: string;
  result: any;
  telemetry: Record<string, any>;
  explanation: string;
}
