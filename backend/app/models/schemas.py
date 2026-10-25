"""Pydantic schemas for Nova Air API request/response validation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

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


class ManualAssignRequest(BaseModel):
    flight_number: str
    captain_id: str
    first_officer_id: str
    cabin_crew_ids: List[str]
    aircraft_tail: Optional[str] = None


class RosterGenerateRequest(BaseModel):
    start_utc: Optional[int] = None
    end_utc: Optional[int] = None
    prioritize_tight_connections: bool = True


class ResetDemoRequest(BaseModel):
    dataset_profile: str = Field(default="demo", description="'demo' or 'test'")


class ADSLaboratoryQueryRequest(BaseModel):
    structure_type: str = Field(..., description="'btree' | 'interval_tree' | 'graph' | 'hash_table'")
    query_params: Dict[str, Any] = Field(default_factory=dict)


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
    default_params: Dict[str, Any] = Field(default_factory=dict)


class DisruptionPresetsResponse(BaseModel):
    presets: List[DisruptionPreset]


class DisruptionExecuteRequest(BaseModel):
    scenario: str = Field(..., description="'A' | 'B' | 'C' | 'D' | 'E' or 'PILOT_SICK' | 'AIRCRAFT_AOG' | 'FLIGHT_DELAY_CASCADE' | 'NO_LEGAL_SOLUTION' | 'INVALID_MANUAL_OVERRIDE'")
    params: Dict[str, Any] = Field(default_factory=dict)


class DisruptionExecuteResponse(BaseModel):
    scenario: str
    scenario_type: str
    success: bool
    message: str
    affected_flights: List[str] = Field(default_factory=list)
    recovered_flights: List[str] = Field(default_factory=list)
    unrecovered_flights: List[str] = Field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = Field(default_factory=list)
    violations: List[RuleViolation] = Field(default_factory=list)
    state_preserved: bool = True
    invariants_verified: bool = True


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
    errors: List[RuleViolation] = Field(default_factory=list)

