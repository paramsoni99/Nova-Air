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
)


class FlightSearchWindowRequest(BaseModel):
    start_utc: int = Field(..., ge=0)
    end_utc: int = Field(..., ge=0)
    origin: Optional[str] = None
    destination: Optional[str] = None


class ScheduleRunRequest(BaseModel):
    profile_id: str = "nova_air_demo_v1"
    start_utc: int = Field(..., ge=0)
    end_utc: int = Field(..., ge=0)
    prioritize_tight_connections: bool = True


class DisruptionDelayRequest(BaseModel):
    flight_number: str
    delay_seconds: int = Field(..., gt=0)
    reason: str = "Technical delay"


class DisruptionCancelRequest(BaseModel):
    flight_number: str
    reason: str = "Weather cancellation"


class AssignCrewRequest(BaseModel):
    flight_number: str
    captain_id: Optional[str] = None
    first_officer_id: Optional[str] = None
    cabin_crew_ids: List[str] = Field(default_factory=list)


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
    errors: List[RuleViolation] = Field(default_factory=list)
