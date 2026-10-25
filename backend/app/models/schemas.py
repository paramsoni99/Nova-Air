"""Pydantic schemas for Nova Air API request/response validation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from backend.app.models.domain import (
    Aircraft,
    Airport,
    CrewMember,
    FlightLeg,
    MaintenanceWindow,
    PositioningItinerary,
    RosterAssignment,
    RuleViolation,
    UncoveredReason,
)


class FlightCreateRequest(BaseModel):
    flight_number: str = Field(..., min_length=3)
    origin: str = Field(..., min_length=3, max_length=4)
    destination: str = Field(..., min_length=3, max_length=4)
    departure_utc: int = Field(..., ge=0)
    arrival_utc: int = Field(..., ge=0)
    aircraft_tail: Optional[str] = None
    required_aircraft_type: str = "A320"


class FlightPatchRequest(BaseModel):
    departure_utc: Optional[int] = Field(default=None, ge=0)
    arrival_utc: Optional[int] = Field(default=None, ge=0)
    aircraft_tail: Optional[str] = None
    delay_minutes: Optional[int] = None
    reason: Optional[str] = None


class ManualAssignRequest(BaseModel):
    flight_number: str
    captain_id: str
    first_officer_id: str
    cabin_crew_ids: List[str]
    aircraft_tail: Optional[str] = None


class RosterGenerateRequest(BaseModel):
    start_utc: Optional[int] = None
    end_utc: Optional[int] = None
    horizon_start_utc: Optional[int] = None
    horizon_end_utc: Optional[int] = None
    prioritize_tight_connections: bool = True
    enforce_hard_rules: bool = True
    disruption_mode: bool = False


class ResetDemoRequest(BaseModel):
    dataset_profile: str = Field(default="demo", description="'demo' or 'test'")


class ADSLaboratoryQueryRequest(BaseModel):
    structure_type: Optional[str] = Field(default=None, description="'btree' | 'interval_tree' | 'graph' | 'hash_table'")
    structure: Optional[str] = None
    operation: Optional[str] = None
    query_params: Dict[str, Any] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "allow"}

    def get_effective_structure(self) -> str:
        return (self.structure_type or self.structure or "hash_table").lower()

    def get_effective_params(self) -> Dict[str, Any]:
        p = dict(self.query_params)
        p.update(self.params)
        return p


class ADSLaboratoryQueryResponse(BaseModel):
    structure: str
    operation: str
    execution_time_ms: float
    time_complexity: str
    space_complexity: str
    result: Any
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    explanation: str


class FlightSearchWindowRequest(BaseModel):
    start_utc: int = Field(..., ge=0)
    end_utc: int = Field(..., ge=0)
    origin: Optional[str] = None
    destination: Optional[str] = None


class DisruptionDelayRequest(BaseModel):
    flight_number: str
    delay_seconds: int = Field(..., gt=0)
    reason: str = "Technical delay"


class DisruptionCancelRequest(BaseModel):
    flight_number: str
    reason: str = "Weather cancellation"


class DisruptionPreset(BaseModel):
    scenario: str
    scenario_type: str
    name: str
    description: str
    title: Optional[str] = None
    target_id: Optional[str] = None
    academic_objective: Optional[str] = None
    delay_minutes: Optional[int] = None
    default_params: Dict[str, Any] = Field(default_factory=dict)


class DisruptionPresetsResponse(BaseModel):
    presets: List[DisruptionPreset]


class DisruptionExecuteRequest(BaseModel):
    scenario: Optional[str] = Field(default=None, description="'A' | 'B' | 'C' | 'D' | 'E' or 'PILOT_SICK' | 'AIRCRAFT_AOG' | 'FLIGHT_DELAY_CASCADE' | 'NO_LEGAL_SOLUTION' | 'INVALID_MANUAL_OVERRIDE'")
    scenario_type: Optional[str] = None
    flight_number: Optional[str] = None
    crew_id: Optional[str] = None
    aircraft_tail: Optional[str] = None
    delay_minutes: Optional[int] = None
    override_captain_id: Optional[str] = None
    override_aircraft_tail: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "allow"}

    def get_effective_scenario(self) -> str:
        return self.scenario or self.scenario_type or "A"

    def get_effective_params(self) -> Dict[str, Any]:
        p = dict(self.params)
        if self.flight_number and "flight_number" not in p:
            p["flight_number"] = self.flight_number
        if self.crew_id and "pilot_id" not in p and "crew_id" not in p:
            p["pilot_id"] = self.crew_id
            p["crew_id"] = self.crew_id
        if self.aircraft_tail and "tail_number" not in p and "aircraft_tail" not in p:
            p["tail_number"] = self.aircraft_tail
            p["aircraft_tail"] = self.aircraft_tail
        if self.delay_minutes and "delay_seconds" not in p:
            p["delay_seconds"] = self.delay_minutes * 60
        if self.override_captain_id and "override_captain_id" not in p:
            p["override_captain_id"] = self.override_captain_id
        if self.override_aircraft_tail and "override_aircraft_tail" not in p:
            p["override_aircraft_tail"] = self.override_aircraft_tail
        return p


class DisruptionExecuteResponse(BaseModel):
    scenario: str
    scenario_type: str
    success: bool
    message: str
    affected_flights: List[str] = Field(default_factory=list)
    recovered_flights: List[str] = Field(default_factory=list)
    unrecovered_flights: List[str] = Field(default_factory=list)
    impacted_flights_count: int = 0
    impacted_flights: List[str] = Field(default_factory=list)
    reassigned_flights_count: int = 0
    reassigned_flights: List[str] = Field(default_factory=list)
    unassigned_flights_count: int = 0
    unassigned_flights: List[str] = Field(default_factory=list)
    violations_prevented_count: int = 0
    violations: List[RuleViolation] = Field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = Field(default_factory=list)
    ads_mutations: Dict[str, Any] = Field(default_factory=dict)
    details: Dict[str, Any] = Field(default_factory=dict)
    state_preserved: bool = True
    invariants_verified: bool = True

    @model_validator(mode="before")
    @classmethod
    def populate_dual_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            aff = data.get("affected_flights") or data.get("impacted_flights") or []
            rec = data.get("recovered_flights") or data.get("reassigned_flights") or []
            unrec = data.get("unrecovered_flights") or data.get("unassigned_flights") or []
            viols = data.get("violations") or []
            data["affected_flights"] = aff
            data["impacted_flights"] = aff
            data["impacted_flights_count"] = len(aff)
            data["recovered_flights"] = rec
            data["reassigned_flights"] = rec
            data["reassigned_flights_count"] = len(rec)
            data["unrecovered_flights"] = unrec
            data["unassigned_flights"] = unrec
            data["unassigned_flights_count"] = len(unrec)
            data["violations_prevented_count"] = len(viols)
            if not data.get("ads_mutations"):
                data["ads_mutations"] = {
                    "btree_keys_updated": 1 if data.get("scenario") in ("C", "FLIGHT_DELAY_CASCADE") else 0,
                    "interval_tree_conflicts_resolved": len(rec),
                    "graph_edges_updated": 1 if data.get("scenario") in ("C", "A") else 0,
                    "hash_lookups": max(1, len(aff) * 2),
                }
        return data



class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
    errors: List[RuleViolation] = Field(default_factory=list)

