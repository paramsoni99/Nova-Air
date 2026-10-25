"""Domain models for Nova Air (AirCrewOps).

Enforces half-open UTC intervals [start_utc, end_utc) and strict validation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class AircraftType(str, Enum):
    A320 = "A320"
    ATR72 = "ATR72"


class CrewRole(str, Enum):
    CAPTAIN = "CAPTAIN"
    FIRST_OFFICER = "FIRST_OFFICER"
    CABIN_CREW = "CABIN_CREW"


class DutyType(str, Enum):
    FLIGHT_DUTY = "FLIGHT_DUTY"
    STANDBY = "STANDBY"
    POSITIONING = "POSITIONING"


class RosterStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    UNASSIGNED = "UNASSIGNED"


class RuleSeverity(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class Airport(BaseModel):
    code: str = Field(..., min_length=3, max_length=4, description="IATA/ICAO code, e.g. BOM")
    name: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    country: str = Field(default="India")
    timezone_offset_seconds: int = Field(default=19800, description="UTC offset in seconds (e.g. 19800 for +05:30 IST)")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    is_hub: bool = Field(default=False)
    curfew_start_hour_utc: Optional[int] = Field(default=None, ge=0, le=23)
    curfew_end_hour_utc: Optional[int] = Field(default=None, ge=0, le=23)

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


class Aircraft(BaseModel):
    tail_number: str = Field(..., min_length=3, description="Aircraft registration, e.g. VT-NVA")
    aircraft_type: str = Field(..., description="Aircraft type code, e.g. A320 or ATR72")
    home_base: str = Field(..., min_length=3, max_length=4, description="Home base airport code")
    seating_capacity: int = Field(..., gt=0)
    total_flight_hours: float = Field(default=0.0, ge=0.0)
    is_active: bool = Field(default=True)

    @field_validator("tail_number", "home_base")
    @classmethod
    def uppercase_strings(cls, v: str) -> str:
        return v.strip().upper()


class MaintenanceWindow(BaseModel):
    id: str = Field(..., min_length=1)
    aircraft_tail: str = Field(..., min_length=3)
    airport_code: str = Field(..., min_length=3, max_length=4)
    start_utc: int = Field(..., ge=0, description="Start timestamp in UTC epoch seconds")
    end_utc: int = Field(..., ge=0, description="End timestamp in UTC epoch seconds")
    description: str = Field(default="Scheduled maintenance check")

    @model_validator(mode="after")
    def validate_half_open_interval(self) -> MaintenanceWindow:
        if self.start_utc >= self.end_utc:
            raise ValueError(f"Invalid interval: start_utc ({self.start_utc}) must be strictly less than end_utc ({self.end_utc})")
        return self


class CrewQualification(BaseModel):
    aircraft_type: str = Field(..., min_length=1)
    valid_until_utc: int = Field(..., ge=0, description="Expiration in UTC epoch seconds")

    @field_validator("aircraft_type")
    @classmethod
    def uppercase_type(cls, v: str) -> str:
        return v.strip().upper()


class CrewMember(BaseModel):
    id: str = Field(..., min_length=1, description="Unique Crew ID, e.g. CRW-101")
    name: str = Field(..., min_length=1)
    role: CrewRole
    home_base: str = Field(..., min_length=3, max_length=4)
    current_airport: str = Field(..., min_length=3, max_length=4)
    qualifications: List[CrewQualification] = Field(default_factory=list)
    cumulative_flight_seconds_7d: int = Field(default=0, ge=0)
    cumulative_duty_seconds_7d: int = Field(default=0, ge=0)
    last_duty_end_utc: Optional[int] = Field(default=None, ge=0)
    is_active: bool = Field(default=True)

    @field_validator("id", "home_base", "current_airport")
    @classmethod
    def uppercase_strings(cls, v: str) -> str:
        return v.strip().upper()

    def has_valid_rating(self, aircraft_type: str, at_utc: int) -> bool:
        normalized = aircraft_type.strip().upper()
        return any(
            q.aircraft_type == normalized and q.valid_until_utc > at_utc
            for q in self.qualifications
        )


class FlightLeg(BaseModel):
    flight_number: str = Field(..., min_length=3, description="Flight number, e.g. NV-101")
    origin: str = Field(..., min_length=3, max_length=4)
    destination: str = Field(..., min_length=3, max_length=4)
    departure_utc: int = Field(..., ge=0, description="Scheduled departure in UTC epoch seconds")
    arrival_utc: int = Field(..., ge=0, description="Scheduled arrival in UTC epoch seconds")
    aircraft_tail: Optional[str] = Field(default=None)
    required_aircraft_type: str = Field(default="A320")

    @field_validator("flight_number", "origin", "destination")
    @classmethod
    def uppercase_strings(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_flight_parameters(self) -> FlightLeg:
        if self.departure_utc >= self.arrival_utc:
            raise ValueError(f"departure_utc ({self.departure_utc}) must be strictly less than arrival_utc ({self.arrival_utc})")
        if self.origin == self.destination:
            raise ValueError(f"Origin and destination cannot be identical ({self.origin})")
        return self

    @property
    def flight_duration_seconds(self) -> int:
        return self.arrival_utc - self.departure_utc


class DutyPeriod(BaseModel):
    id: str = Field(..., min_length=1)
    crew_id: str = Field(..., min_length=1)
    flight_leg_ids: List[str] = Field(default_factory=list)
    report_utc: int = Field(..., ge=0)
    release_utc: int = Field(..., ge=0)
    duty_type: DutyType = Field(default=DutyType.FLIGHT_DUTY)
    total_flight_seconds: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_duty_interval(self) -> DutyPeriod:
        if self.report_utc >= self.release_utc:
            raise ValueError(f"report_utc ({self.report_utc}) must be strictly less than release_utc ({self.release_utc})")
        return self

    @property
    def duration_seconds(self) -> int:
        return self.release_utc - self.report_utc


class RosterAssignment(BaseModel):
    id: str = Field(..., min_length=1)
    flight_number: str = Field(..., min_length=3)
    captain_id: Optional[str] = Field(default=None)
    first_officer_id: Optional[str] = Field(default=None)
    cabin_crew_ids: List[str] = Field(default_factory=list)
    aircraft_tail: Optional[str] = Field(default=None)
    status: RosterStatus = Field(default=RosterStatus.UNASSIGNED)


class PositioningItinerary(BaseModel):
    crew_id: str = Field(..., min_length=1)
    origin: str = Field(..., min_length=3, max_length=4)
    destination: str = Field(..., min_length=3, max_length=4)
    flight_legs: List[str] = Field(default_factory=list)
    departure_utc: int = Field(..., ge=0)
    arrival_utc: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_itinerary_interval(self) -> PositioningItinerary:
        if self.departure_utc >= self.arrival_utc:
            raise ValueError(f"departure_utc ({self.departure_utc}) must be strictly less than arrival_utc ({self.arrival_utc})")
        return self


class RuleViolation(BaseModel):
    rule_id: str
    severity: RuleSeverity
    message: str
    entity_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class UncoveredReason(BaseModel):
    flight_number: str
    primary_cause: str
    summary: str
    aircraft_violations: List[RuleViolation] = Field(default_factory=list)
    crew_violations: Dict[str, List[RuleViolation]] = Field(default_factory=dict)
    details: Dict[str, Any] = Field(default_factory=dict)


class FlightCrewRules(BaseModel):
    roles: List[str]
    max_daily_flight_time_seconds: int
    max_daily_fdp_seconds: int
    max_sectors_per_duty: int
    report_lead_time_seconds: int
    release_buffer_seconds: int
    min_connection_time_different_aircraft_seconds: int
    min_connection_time_same_aircraft_seconds: int
    min_inter_duty_rest_seconds: int
    rest_must_equal_prior_fdp_if_greater: bool
    max_7d_flight_time_seconds: int
    max_7d_duty_time_seconds: int
    max_consecutive_duty_days: int


class CabinCrewRules(BaseModel):
    roles: List[str]
    max_daily_flight_time_seconds: int
    max_daily_fdp_seconds: int
    max_sectors_per_duty: int
    report_lead_time_seconds: int
    release_buffer_seconds: int
    min_connection_time_different_aircraft_seconds: int
    min_connection_time_same_aircraft_seconds: int
    min_inter_duty_rest_seconds: int
    rest_must_equal_prior_fdp_if_greater: bool
    max_7d_flight_time_seconds: int
    max_7d_duty_time_seconds: int
    max_consecutive_duty_days: int


class RuleProfile(BaseModel):
    profile_id: str
    airline_name: str
    version: str
    description: str
    flight_crew_rules: FlightCrewRules
    cabin_crew_rules: CabinCrewRules
    aircraft_turnaround_times_seconds: Dict[str, int]
    crew_complement: Dict[str, Dict[str, int]]
