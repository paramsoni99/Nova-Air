"""ConstraintEngine for Nova Air Aviation Safety and Roster Validation.

This module implements the fail-closed civil aviation constraint evaluation engine
under regulatory profile nova_air_demo_v1 (DGCA CAR Section 7 Series J).

Enforced Rules:
- Crew Hard Rules:
  * CREW-ROLE-01: Crew role matches assignment slot.
  * CREW-QUAL-01: Crew possesses aircraft type qualification.
  * CREW-EXP-01:  Type qualification is unexpired at flight departure.
  * CREW-OVLP-01: No temporal overlap with existing duty/flight reservations in RBIntervalTree.
  * CREW-REST-01: Inter-duty mandatory rest (>= max(43200s, prior_fdp)) before/after duty.
  * CREW-FDP-01:  Maximum daily Flight Duty Period duration and sector count limits.
  * CREW-FT-01:   Maximum daily flight time (airborne seconds) in duty period.
  * CREW-CUM-01:  7-day rolling cumulative flight and duty limits.
  * CREW-POS-01:  Crew location consistency and positioning route feasibility.
- Aircraft Hard Rules:
  * ACFT-STAT-01: Aircraft is active and matches required aircraft type.
  * ACFT-OVLP-01: No temporal overlap with existing flights or maintenance blocks.
  * ACFT-LOC-01:  Aircraft location consistency with origin aerodrome.
  * ACFT-SUCC-01: Minimum turnaround time (TAT) between consecutive legs on same tail.
- Pairing Composition:
  * PAIR-COMP-01: Complete, distinct crew complement for aircraft type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.data_structures.rb_interval_tree import IntervalNode, RBIntervalTree
from backend.app.models.domain import (
    Aircraft,
    CrewMember,
    CrewRole,
    DutyPeriod,
    DutyType,
    FlightLeg,
    PositioningItinerary,
    RuleProfile,
    RuleSeverity,
    RuleViolation,
)
from backend.app.rules.profile_loader import load_rule_profile
from backend.app.services.positioning_service import PositioningService


@dataclass
class ValidationResult:
    """Result of rule validation for a candidate crew or aircraft assignment."""
    is_valid: bool
    violations: List[RuleViolation] = field(default_factory=list)
    soft_score: float = 0.0
    positioning_itinerary: Optional[PositioningItinerary] = None
    is_intra_duty_continuation: bool = False
    projected_duty_interval: Optional[Tuple[int, int]] = None

    def add_violation(self, violation: RuleViolation) -> None:
        self.violations.append(violation)
        if violation.severity == RuleSeverity.HARD:
            self.is_valid = False


class ConstraintEngine:
    """Aviation regulatory and operational constraint validation engine."""

    def __init__(
        self,
        rule_profile: Optional[RuleProfile] = None,
        positioning_service: Optional[PositioningService] = None,
    ) -> None:
        self.profile: RuleProfile = rule_profile or load_rule_profile()
        self.positioning_service: Optional[PositioningService] = positioning_service

    def _get_rules_for_role(self, role: CrewRole | str):
        """Get role-specific regulatory limits from rule profile."""
        role_str = str(role.value if isinstance(role, CrewRole) else role).upper()
        if role_str == CrewRole.CABIN_CREW.value:
            return self.profile.cabin_crew_rules
        return self.profile.flight_crew_rules

    def validate_crew_assignment(
        self,
        crew: CrewMember,
        flight: FlightLeg,
        role: CrewRole | str,
        crew_tree: Optional[RBIntervalTree] = None,
        current_duty: Optional[Dict[str, Any] | DutyPeriod] = None,
    ) -> ValidationResult:
        """Validate candidate crew assignment against all civil aviation and operator rules.

        Handles both intra-duty continuation (extending an active FDP) and starting a new FDP.
        """
        result = ValidationResult(is_valid=True)
        rules = self._get_rules_for_role(crew.role)

        lead_time = rules.report_lead_time_seconds
        release_buf = rules.release_buffer_seconds
        max_fdp = rules.max_daily_fdp_seconds
        max_ft = rules.max_daily_flight_time_seconds
        max_sectors = rules.max_sectors_per_duty
        min_rest = rules.min_inter_duty_rest_seconds

        flight_duration = flight.flight_duration_seconds

        # ----------------------------------------------------------------------
        # 1. CREW-ROLE-01: Crew Role Suitability
        # ----------------------------------------------------------------------
        req_role_str = str(role.value if isinstance(role, CrewRole) else role).upper()
        crew_role_str = str(crew.role.value if isinstance(crew.role, CrewRole) else crew.role).upper()
        if crew_role_str != req_role_str:
            result.add_violation(
                RuleViolation(
                    rule_id="CREW-ROLE-01",
                    severity=RuleSeverity.HARD,
                    message=f"Crew member {crew.id} role '{crew_role_str}' does not match required role '{req_role_str}'",
                    entity_id=crew.id,
                    context={"crew_role": crew_role_str, "required_role": req_role_str},
                )
            )

        # ----------------------------------------------------------------------
        # 2. CREW-QUAL-01 & CREW-EXP-01: Aircraft Type Rating & Expiration
        # ----------------------------------------------------------------------
        req_acft = flight.required_aircraft_type.strip().upper()
        matching_quals = [
            q for q in crew.qualifications
            if q.aircraft_type.strip().upper() == req_acft
        ]

        if not matching_quals:
            # Flight crew must have type rating; cabin crew check if qualifications present
            if crew_role_str in ("CAPTAIN", "FIRST_OFFICER") or crew.qualifications:
                result.add_violation(
                    RuleViolation(
                        rule_id="CREW-QUAL-01",
                        severity=RuleSeverity.HARD,
                        message=f"Crew member {crew.id} lacks aircraft type rating for '{req_acft}'",
                        entity_id=crew.id,
                        context={"required_aircraft_type": req_acft},
                    )
                )
        else:
            active_qual = matching_quals[0]
            if active_qual.valid_until_utc <= flight.departure_utc:
                result.add_violation(
                    RuleViolation(
                        rule_id="CREW-EXP-01",
                        severity=RuleSeverity.HARD,
                        message=(
                            f"Crew member {crew.id} qualification for '{req_acft}' expired at "
                            f"{active_qual.valid_until_utc} UTC (flight departure: {flight.departure_utc} UTC)"
                        ),
                        entity_id=crew.id,
                        context={
                            "valid_until_utc": active_qual.valid_until_utc,
                            "departure_utc": flight.departure_utc,
                        },
                    )
                )

        # ----------------------------------------------------------------------
        # 3. Determine Duty Mode: Intra-Duty Continuation vs. New FDP
        # ----------------------------------------------------------------------
        is_intra_duty = False
        projected_start_report: int
        projected_end_release: int
        projected_flight_time: int
        projected_sectors: int
        prev_duty_id: Optional[str] = None
        prev_release_utc: Optional[int] = None
        prev_fdp_duration: Optional[int] = None

        # Check if active duty context exists (either passed directly or via tree predecessor)
        duty_info = self._extract_duty_context(current_duty, crew_tree, flight.departure_utc)

        if duty_info is not None:
            # Check if intra-duty connection conditions are met
            prev_dest = duty_info.get("last_destination")
            prev_arr_utc = duty_info.get("last_arrival_utc")
            prev_tail = duty_info.get("last_aircraft_tail")
            prev_start = duty_info.get("duty_start_utc")
            prev_ft = duty_info.get("cumulative_flight_seconds", 0)
            prev_sec = duty_info.get("sector_count", 0)
            prev_duty_id = duty_info.get("duty_id")
            prev_release_utc = duty_info.get("duty_end_utc")
            prev_fdp_duration = prev_release_utc - prev_start if prev_release_utc and prev_start else None

            same_tail = (prev_tail is not None and flight.aircraft_tail is not None and prev_tail == flight.aircraft_tail)
            min_conn = (
                rules.min_connection_time_same_aircraft_seconds
                if same_tail
                else rules.min_connection_time_different_aircraft_seconds
            )

            # Check: crew arrives at flight.origin and time since last arrival is less than required rest
            if prev_dest == flight.origin and prev_arr_utc is not None:
                conn_gap = flight.departure_utc - prev_arr_utc
                # If connection gap is less than mandatory rest, this is part of the active duty sequence
                if conn_gap < min_rest:
                    is_intra_duty = True
                    projected_start_report = prev_start
                    projected_end_release = flight.arrival_utc + release_buf
                    projected_flight_time = prev_ft + flight_duration
                    projected_sectors = prev_sec + 1

                    if conn_gap < min_conn:
                        result.add_violation(
                            RuleViolation(
                                rule_id="CREW-REST-01",
                                severity=RuleSeverity.HARD,
                                message=(
                                    f"Intra-duty connection time {conn_gap}s between arrival at {prev_arr_utc} "
                                    f"and departure at {flight.departure_utc} is less than required minimum {min_conn}s"
                                ),
                                entity_id=crew.id,
                                context={"conn_gap_seconds": conn_gap, "min_connection_seconds": min_conn},
                            )
                        )

        if not is_intra_duty:
            # Starting a NEW Flight Duty Period
            projected_start_report = flight.departure_utc - lead_time
            projected_end_release = flight.arrival_utc + release_buf
            projected_flight_time = flight_duration
            projected_sectors = 1

        result.is_intra_duty_continuation = is_intra_duty
        result.projected_duty_interval = (projected_start_report, projected_end_release)
        projected_fdp_duration = projected_end_release - projected_start_report

        # ----------------------------------------------------------------------
        # 4. CREW-POS-01: Crew Location & Deadhead Positioning
        # ----------------------------------------------------------------------
        crew_loc = crew.current_airport.strip().upper()
        if not is_intra_duty and crew_loc != flight.origin:
            if self.positioning_service is not None:
                itinerary = self.positioning_service.find_positioning_itinerary(
                    crew=crew,
                    target_airport=flight.origin,
                    required_arrival_utc=flight.departure_utc - lead_time,
                )
                if itinerary is None:
                    result.add_violation(
                        RuleViolation(
                            rule_id="CREW-POS-01",
                            severity=RuleSeverity.HARD,
                            message=(
                                f"Crew member {crew.id} is located at {crew_loc}, not flight origin {flight.origin}, "
                                f"and no time-feasible positioning route exists arriving by {flight.departure_utc - lead_time} UTC"
                            ),
                            entity_id=crew.id,
                            context={"current_airport": crew_loc, "flight_origin": flight.origin},
                        )
                    )
                else:
                    result.positioning_itinerary = itinerary
                    # Positioning counts towards duty report time
                    pos_report = itinerary.departure_utc - lead_time
                    projected_start_report = min(projected_start_report, pos_report)
                    projected_fdp_duration = projected_end_release - projected_start_report
                    result.projected_duty_interval = (projected_start_report, projected_end_release)
            else:
                result.add_violation(
                    RuleViolation(
                        rule_id="CREW-POS-01",
                        severity=RuleSeverity.HARD,
                        message=(
                            f"Crew member {crew.id} is located at {crew_loc}, not flight origin {flight.origin}, "
                            f"and positioning service is unavailable"
                        ),
                        entity_id=crew.id,
                        context={"current_airport": crew_loc, "flight_origin": flight.origin},
                    )
                )

        # ----------------------------------------------------------------------
        # 5. CREW-OVLP-01: Duty Interval Non-Overlap in RBIntervalTree
        # ----------------------------------------------------------------------
        if crew_tree is not None:
            overlap = crew_tree.find_first_overlap(projected_start_report, projected_end_release)
            if overlap is not None:
                # If extending active duty, overlap with the active duty itself is expected
                if not (is_intra_duty and overlap.interval_id == prev_duty_id):
                    result.add_violation(
                        RuleViolation(
                            rule_id="CREW-OVLP-01",
                            severity=RuleSeverity.HARD,
                            message=(
                                f"Proposed duty interval [{projected_start_report}, {projected_end_release}) overlaps "
                                f"with existing duty {overlap.interval_id} [{overlap.start_utc}, {overlap.end_utc})"
                            ),
                            entity_id=crew.id,
                            context={
                                "overlap_id": overlap.interval_id,
                                "overlap_start": overlap.start_utc,
                                "overlap_end": overlap.end_utc,
                            },
                        )
                    )

        # ----------------------------------------------------------------------
        # 6. CREW-REST-01: Inter-Duty Mandatory Rest
        # ----------------------------------------------------------------------
        if not is_intra_duty:
            # Check predecessor rest (rest before duty)
            prior_end: Optional[int] = None
            prior_fdp: Optional[int] = None
            prior_id: str = "PREVIOUS"

            if crew_tree is not None:
                pred = crew_tree.find_predecessor(projected_start_report)
                if pred is not None:
                    prior_end = pred.end_utc
                    prior_fdp = pred.end_utc - pred.start_utc
                    prior_id = pred.interval_id

            if prior_end is None and prev_release_utc is not None:
                prior_end = prev_release_utc
                prior_fdp = prev_fdp_duration or min_rest
                prior_id = prev_duty_id or "PREVIOUS"

            if prior_end is None and crew.last_duty_end_utc is not None:
                prior_end = crew.last_duty_end_utc
                prior_fdp = min_rest  # default to min_rest if duration not recorded

            if prior_end is not None:
                rest_gap = projected_start_report - prior_end
                req_rest = max(min_rest, prior_fdp if rules.rest_must_equal_prior_fdp_if_greater and prior_fdp else min_rest)
                if rest_gap < req_rest:
                    result.add_violation(
                        RuleViolation(
                            rule_id="CREW-REST-01",
                            severity=RuleSeverity.HARD,
                            message=(
                                f"Insufficient inter-duty rest before duty: {rest_gap}s provided, "
                                f"{req_rest}s required following prior duty {prior_id}"
                            ),
                            entity_id=crew.id,
                            context={
                                "rest_gap_seconds": rest_gap,
                                "required_rest_seconds": req_rest,
                                "prior_duty_id": prior_id,
                            },
                        )
                    )

            # Check successor rest (rest after duty before subsequent duty)
            if crew_tree is not None:
                succ = crew_tree.find_successor(projected_end_release)
                if succ is not None:
                    rest_gap_after = succ.start_utc - projected_end_release
                    req_rest_after = max(
                        min_rest,
                        projected_fdp_duration if rules.rest_must_equal_prior_fdp_if_greater else min_rest,
                    )
                    if rest_gap_after < req_rest_after:
                        result.add_violation(
                            RuleViolation(
                                rule_id="CREW-REST-01",
                                severity=RuleSeverity.HARD,
                                message=(
                                    f"Insufficient inter-duty rest after duty: {rest_gap_after}s provided, "
                                    f"{req_rest_after}s required before subsequent duty {succ.interval_id}"
                                ),
                                entity_id=crew.id,
                                context={
                                    "rest_gap_seconds": rest_gap_after,
                                    "required_rest_seconds": req_rest_after,
                                    "subsequent_duty_id": succ.interval_id,
                                },
                            )
                        )

        # ----------------------------------------------------------------------
        # 7. CREW-FDP-01: Maximum Daily FDP Duration and Sector Limits
        # ----------------------------------------------------------------------
        if projected_fdp_duration > max_fdp:
            result.add_violation(
                RuleViolation(
                    rule_id="CREW-FDP-01",
                    severity=RuleSeverity.HARD,
                    message=(
                        f"Projected FDP duration {projected_fdp_duration}s exceeds maximum daily limit "
                        f"of {max_fdp}s for {crew.role}"
                    ),
                    entity_id=crew.id,
                    context={"projected_fdp_seconds": projected_fdp_duration, "max_fdp_seconds": max_fdp},
                )
            )

        if projected_sectors > max_sectors:
            result.add_violation(
                RuleViolation(
                    rule_id="CREW-FDP-01",
                    severity=RuleSeverity.HARD,
                    message=(
                        f"Projected sector count {projected_sectors} exceeds maximum limit of "
                        f"{max_sectors} sectors per duty for {crew.role}"
                    ),
                    entity_id=crew.id,
                    context={"projected_sectors": projected_sectors, "max_sectors": max_sectors},
                )
            )

        # ----------------------------------------------------------------------
        # 8. CREW-FT-01: Maximum Daily Flight Time
        # ----------------------------------------------------------------------
        if projected_flight_time > max_ft:
            result.add_violation(
                RuleViolation(
                    rule_id="CREW-FT-01",
                    severity=RuleSeverity.HARD,
                    message=(
                        f"Projected daily flight time {projected_flight_time}s exceeds maximum limit "
                        f"of {max_ft}s for {crew.role}"
                    ),
                    entity_id=crew.id,
                    context={"projected_flight_seconds": projected_flight_time, "max_flight_time_seconds": max_ft},
                )
            )

        # ----------------------------------------------------------------------
        # 9. CREW-CUM-01: 7-Day Cumulative Flight and Duty Limits
        # ----------------------------------------------------------------------
        new_cum_ft = crew.cumulative_flight_seconds_7d + flight_duration
        if new_cum_ft > rules.max_7d_flight_time_seconds:
            result.add_violation(
                RuleViolation(
                    rule_id="CREW-CUM-01",
                    severity=RuleSeverity.HARD,
                    message=(
                        f"Cumulative 7-day flight time {new_cum_ft}s exceeds maximum limit of "
                        f"{rules.max_7d_flight_time_seconds}s for {crew.role}"
                    ),
                    entity_id=crew.id,
                    context={
                        "cumulative_flight_seconds": new_cum_ft,
                        "max_limit_seconds": rules.max_7d_flight_time_seconds,
                    },
                )
            )

        duty_increase = (
            (flight.arrival_utc + release_buf - prev_release_utc)
            if is_intra_duty and prev_release_utc is not None
            else projected_fdp_duration
        )
        new_cum_duty = crew.cumulative_duty_seconds_7d + duty_increase
        if new_cum_duty > rules.max_7d_duty_time_seconds:
            result.add_violation(
                RuleViolation(
                    rule_id="CREW-CUM-01",
                    severity=RuleSeverity.HARD,
                    message=(
                        f"Cumulative 7-day duty time {new_cum_duty}s exceeds maximum limit of "
                        f"{rules.max_7d_duty_time_seconds}s for {crew.role}"
                    ),
                    entity_id=crew.id,
                    context={
                        "cumulative_duty_seconds": new_cum_duty,
                        "max_limit_seconds": rules.max_7d_duty_time_seconds,
                    },
                )
            )

        # ----------------------------------------------------------------------
        # Compute Soft Optimization Score if Valid
        # ----------------------------------------------------------------------
        if result.is_valid:
            result.soft_score = self.compute_soft_score(crew, flight, result)

        return result

    def _extract_duty_context(
        self,
        current_duty: Optional[Dict[str, Any] | DutyPeriod],
        crew_tree: Optional[RBIntervalTree],
        flight_departure_utc: int,
    ) -> Optional[Dict[str, Any]]:
        """Extract active duty metadata from explicit context or tree predecessor."""
        if current_duty is not None:
            if isinstance(current_duty, DutyPeriod):
                return {
                    "duty_id": current_duty.id,
                    "duty_start_utc": current_duty.report_utc,
                    "duty_end_utc": current_duty.release_utc,
                    "sector_count": len(current_duty.flight_leg_ids),
                    "cumulative_flight_seconds": current_duty.total_flight_seconds,
                    "last_destination": None,  # Will be resolved if dict or tree
                    "last_arrival_utc": current_duty.release_utc - 1800,
                    "last_aircraft_tail": None,
                }
            elif isinstance(current_duty, dict):
                return current_duty

        if crew_tree is not None:
            pred = crew_tree.find_predecessor(flight_departure_utc)
            if pred is not None and isinstance(pred.data, dict):
                return pred.data

        return None

    def validate_aircraft_assignment(
        self,
        aircraft: Aircraft,
        flight: FlightLeg,
        aircraft_tree: Optional[RBIntervalTree] = None,
        previous_flight: Optional[FlightLeg] = None,
    ) -> ValidationResult:
        """Validate aircraft rotation, status, location, and turnaround time."""
        result = ValidationResult(is_valid=True)

        # 1. ACFT-STAT-01: Status & Type Match
        if not aircraft.is_active:
            result.add_violation(
                RuleViolation(
                    rule_id="ACFT-STAT-01",
                    severity=RuleSeverity.HARD,
                    message=f"Aircraft {aircraft.tail_number} is grounded / inactive",
                    entity_id=aircraft.tail_number,
                    context={"tail_number": aircraft.tail_number, "is_active": False},
                )
            )

        if aircraft.aircraft_type.strip().upper() != flight.required_aircraft_type.strip().upper():
            result.add_violation(
                RuleViolation(
                    rule_id="ACFT-STAT-01",
                    severity=RuleSeverity.HARD,
                    message=(
                        f"Aircraft type '{aircraft.aircraft_type}' does not match flight required "
                        f"type '{flight.required_aircraft_type}'"
                    ),
                    entity_id=aircraft.tail_number,
                    context={
                        "aircraft_type": aircraft.aircraft_type,
                        "required_aircraft_type": flight.required_aircraft_type,
                    },
                )
            )

        # 2. ACFT-OVLP-01: Overlap with Flights or Maintenance Blocks
        if aircraft_tree is not None:
            overlap = aircraft_tree.find_first_overlap(flight.departure_utc, flight.arrival_utc)
            if overlap is not None:
                result.add_violation(
                    RuleViolation(
                        rule_id="ACFT-OVLP-01",
                        severity=RuleSeverity.HARD,
                        message=(
                            f"Flight interval [{flight.departure_utc}, {flight.arrival_utc}) conflicts with "
                            f"existing aircraft activity {overlap.interval_id} [{overlap.start_utc}, {overlap.end_utc})"
                        ),
                        entity_id=aircraft.tail_number,
                        context={
                            "overlap_id": overlap.interval_id,
                            "overlap_start": overlap.start_utc,
                            "overlap_end": overlap.end_utc,
                        },
                    )
                )

        # 3. ACFT-LOC-01: Location Consistency
        if previous_flight is not None:
            if previous_flight.destination != flight.origin:
                result.add_violation(
                    RuleViolation(
                        rule_id="ACFT-LOC-01",
                        severity=RuleSeverity.HARD,
                        message=(
                            f"Aircraft {aircraft.tail_number} arrives at {previous_flight.destination}, "
                            f"cannot depart from {flight.origin}"
                        ),
                        entity_id=aircraft.tail_number,
                        context={"actual_location": previous_flight.destination, "required_origin": flight.origin},
                    )
                )
        else:
            # First scheduled flight on this tail
            if aircraft.home_base != flight.origin:
                result.add_violation(
                    RuleViolation(
                        rule_id="ACFT-LOC-01",
                        severity=RuleSeverity.HARD,
                        message=(
                            f"Aircraft {aircraft.tail_number} is based at {aircraft.home_base}, "
                            f"cannot depart from {flight.origin} without ferry rotation"
                        ),
                        entity_id=aircraft.tail_number,
                        context={"home_base": aircraft.home_base, "flight_origin": flight.origin},
                    )
                )

        # 4. ACFT-SUCC-01: Minimum Turnaround Time (TAT)
        tat_seconds = self.profile.aircraft_turnaround_times_seconds.get(aircraft.aircraft_type, 2700)
        if previous_flight is not None:
            tat_gap = flight.departure_utc - previous_flight.arrival_utc
            if tat_gap < tat_seconds:
                result.add_violation(
                    RuleViolation(
                        rule_id="ACFT-SUCC-01",
                        severity=RuleSeverity.HARD,
                        message=(
                            f"Turnaround time {tat_gap}s between {previous_flight.flight_number} arrival and "
                            f"{flight.flight_number} departure is less than required minimum {tat_seconds}s "
                            f"for {aircraft.aircraft_type}"
                        ),
                        entity_id=aircraft.tail_number,
                        context={
                            "tat_gap_seconds": tat_gap,
                            "required_tat_seconds": tat_seconds,
                            "aircraft_type": aircraft.aircraft_type,
                        },
                    )
                )

        return result

    def validate_pairing(
        self,
        flight: FlightLeg,
        captain: CrewMember,
        first_officer: CrewMember,
        cabin_crew: List[CrewMember],
        aircraft: Aircraft,
        crew_trees: Optional[Dict[str, RBIntervalTree]] = None,
        aircraft_tree: Optional[RBIntervalTree] = None,
        previous_flight: Optional[FlightLeg] = None,
    ) -> ValidationResult:
        """Validate complete flight pairing: complement counts, crew suitability, and aircraft checks."""
        result = ValidationResult(is_valid=True)
        crew_trees = crew_trees or {}

        # 1. PAIR-COMP-01: Check complement requirements
        req_type = flight.required_aircraft_type
        comp_rules = self.profile.crew_complement.get(req_type, {"captains": 1, "first_officers": 1, "cabin_crew": 4})
        req_cpt = comp_rules.get("captains", 1)
        req_fo = comp_rules.get("first_officers", 1)
        req_cc = comp_rules.get("cabin_crew", 4)

        all_crew = [captain, first_officer] + cabin_crew
        crew_ids = [c.id for c in all_crew]

        # Distinctness check
        if len(crew_ids) != len(set(crew_ids)):
            result.add_violation(
                RuleViolation(
                    rule_id="PAIR-COMP-01",
                    severity=RuleSeverity.HARD,
                    message=f"Duplicate crew member assigned to flight {flight.flight_number}",
                    entity_id=flight.flight_number,
                    context={"crew_ids": crew_ids},
                )
            )

        if len(cabin_crew) != req_cc:
            result.add_violation(
                RuleViolation(
                    rule_id="PAIR-COMP-01",
                    severity=RuleSeverity.HARD,
                    message=(
                        f"Flight {flight.flight_number} requires {req_cc} cabin crew, got {len(cabin_crew)}"
                    ),
                    entity_id=flight.flight_number,
                    context={"required_cabin_crew": req_cc, "assigned_cabin_crew": len(cabin_crew)},
                )
            )

        # 2. Validate individual crew members
        cpt_res = self.validate_crew_assignment(captain, flight, CrewRole.CAPTAIN, crew_trees.get(captain.id))
        for v in cpt_res.violations:
            result.add_violation(v)

        fo_res = self.validate_crew_assignment(first_officer, flight, CrewRole.FIRST_OFFICER, crew_trees.get(first_officer.id))
        for v in fo_res.violations:
            result.add_violation(v)

        for cc in cabin_crew:
            cc_res = self.validate_crew_assignment(cc, flight, CrewRole.CABIN_CREW, crew_trees.get(cc.id))
            for v in cc_res.violations:
                result.add_violation(v)

        # 3. Validate aircraft
        if aircraft is not None:
            ac_res = self.validate_aircraft_assignment(aircraft, flight, aircraft_tree, previous_flight)
            for v in ac_res.violations:
                result.add_violation(v)
        else:
            result.add_violation(
                RuleViolation(
                    rule_id="ACFT-STAT-01",
                    severity=RuleSeverity.HARD,
                    message="No aircraft assigned to flight leg",
                    entity_id=flight.flight_number,
                    context={"flight_number": flight.flight_number},
                )
            )

        if result.is_valid:
            result.soft_score = (
                cpt_res.soft_score
                + fo_res.soft_score
                + sum(c.soft_score for c in [self.validate_crew_assignment(cc, flight, CrewRole.CABIN_CREW) for cc in cabin_crew])
            )

        return result

    def compute_soft_score(
        self,
        crew: CrewMember,
        flight: FlightLeg,
        validation_result: Optional[ValidationResult] = None,
    ) -> float:
        """Compute soft optimization score for valid assignments (higher is better)."""
        score = 0.0
        rules = self._get_rules_for_role(crew.role)

        # 1. Home Base Preference (+100.0 for departing from base, +80.0 for returning to base)
        if crew.home_base == flight.origin:
            score += 100.0
        elif crew.home_base == flight.destination:
            score += 80.0

        # 2. Cumulative Workload Balancing (up to +50.0 for balanced flight time)
        max_7d = rules.max_7d_flight_time_seconds
        if max_7d > 0:
            utilization = min(1.0, crew.cumulative_flight_seconds_7d / max_7d)
            score += 50.0 * (1.0 - utilization)

        # 3. Positioning Penalty (-40.0 if deadhead positioning needed)
        if validation_result and validation_result.positioning_itinerary:
            score -= 40.0

        # 4. Intra-Duty Continuation Efficiency (+100.0 for multi-leg pairing continuity)
        if validation_result and validation_result.is_intra_duty_continuation:
            score += 100.0

        return round(score, 2)
