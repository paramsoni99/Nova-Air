"""RosterScheduler for Nova Air (AirCrewOps).

Coordinates all five custom in-memory data structures to generate constraint-safe,
fail-closed crew rosters and aircraft rotations under regulatory profile nova_air_demo_v1.
Includes 1-level bounded swap recovery for operational disruptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.data_structures.priority_queue import PriorityKey, SchedulerPriorityQueue
from backend.app.models.domain import (
    Aircraft,
    CrewMember,
    CrewRole,
    DutyPeriod,
    DutyType,
    FlightLeg,
    PositioningItinerary,
    RosterAssignment,
    RosterStatus,
    RuleProfile,
    RuleViolation,
    UncoveredReason,
)
from backend.app.rules.profile_loader import load_rule_profile
from backend.app.services.constraint_engine import ConstraintEngine, ValidationResult
from backend.app.services.index_manager import ADSIndexManager
from backend.app.services.positioning_service import PositioningService


@dataclass
class ScheduleResult:
    """Result of full schedule optimization run."""
    assignments: Dict[str, RosterAssignment]
    unassigned_flights: Dict[str, UncoveredReason]
    positioned_crew: List[PositioningItinerary]
    duty_periods: List[DutyPeriod]
    total_flights: int
    assigned_count: int
    unassigned_count: int
    coverage_percentage: float


@dataclass
class RecoveryResult:
    """Result of disruption recovery operation."""
    success: bool
    affected_flights: List[str]
    recovered_flights: List[str]
    unrecovered_flights: List[str]
    swaps_performed: List[Dict[str, Any]]
    uncovered_reasons: Dict[str, UncoveredReason]


class RosterScheduler:
    """Priority-driven heuristic scheduler with bounded swap recovery."""

    def __init__(
        self,
        index_manager: ADSIndexManager,
        constraint_engine: Optional[ConstraintEngine] = None,
        positioning_service: Optional[PositioningService] = None,
        rule_profile: Optional[RuleProfile] = None,
    ) -> None:
        self.index_manager: ADSIndexManager = index_manager
        self.profile: RuleProfile = rule_profile or load_rule_profile()
        self.positioning_service: PositioningService = (
            positioning_service or PositioningService(self.index_manager.connection_graph, self.profile)
        )
        self.constraint_engine: ConstraintEngine = (
            constraint_engine or ConstraintEngine(self.profile, self.positioning_service)
        )
        self._initial_crew_snapshots: Dict[str, Dict[str, Any]] = {}
        self.record_baseline_state()

    def record_baseline_state(self) -> None:
        """Capture baseline crew counters and locations for deterministic scheduling."""
        self._initial_crew_snapshots.clear()
        for crew in self.index_manager.crew_by_id.values():
            self._initial_crew_snapshots[crew.id] = {
                "current_airport": crew.current_airport,
                "cumulative_flight_seconds_7d": crew.cumulative_flight_seconds_7d,
                "cumulative_duty_seconds_7d": crew.cumulative_duty_seconds_7d,
                "last_duty_end_utc": crew.last_duty_end_utc,
            }

    def _reset_to_baseline(self) -> None:
        """Clear previously generated roster intervals and restore baseline crew state."""
        # 1. Reset aircraft intervals: delete any flight reservations (keep MAINTENANCE)
        for tail, tree in self.index_manager.aircraft_intervals.items():
            to_remove = [
                (node.start_utc, node.end_utc, node.interval_id)
                for node in tree.inorder_traversal()
                if isinstance(node.data, dict) and node.data.get("type") == "FLIGHT"
            ]
            for s, e, iid in to_remove:
                tree.delete(s, e, iid)

        # 2. Reset crew intervals: delete generated duties (starting with DUTY-NV-)
        for cid, tree in self.index_manager.crew_intervals.items():
            to_remove = [
                (node.start_utc, node.end_utc, node.interval_id)
                for node in tree.inorder_traversal()
                if isinstance(node.data, dict) and str(node.data.get("duty_id", "")).startswith("DUTY-NV-")
            ]
            for s, e, iid in to_remove:
                tree.delete(s, e, iid)

        # 3. Restore crew attributes from baseline snapshots
        for cid, snap in self._initial_crew_snapshots.items():
            c = self.index_manager.crew_by_id.get(cid)
            if c is not None:
                c.current_airport = snap["current_airport"]
                c.cumulative_flight_seconds_7d = snap["cumulative_flight_seconds_7d"]
                c.cumulative_duty_seconds_7d = snap["cumulative_duty_seconds_7d"]
                c.last_duty_end_utc = snap["last_duty_end_utc"]

    def generate_roster(
        self,
        horizon_start_utc: int,
        horizon_end_utc: int,
        prioritize_tight_connections: bool = True,
    ) -> ScheduleResult:
        """Generate constraint-safe roster across planning horizon using all five ADS structures."""
        # Reset state back to clean baseline so repeated runs are idempotent
        if not self._initial_crew_snapshots:
            self.record_baseline_state()
        else:
            self._reset_to_baseline()

        # Step 1: Range Query on B-Tree for flights in planning horizon
        range_results = self.index_manager.schedule_btree.range_query(
            horizon_start_utc, horizon_end_utc, include_min=True, include_max=True
        )
        flights: List[FlightLeg] = [flight for _, flight in range_results]

        if not flights:
            return ScheduleResult(
                assignments={},
                unassigned_flights={},
                positioned_crew=[],
                duty_periods=[],
                total_flights=0,
                assigned_count=0,
                unassigned_count=0,
                coverage_percentage=0.0,
            )

        # Step 2: Initialize SchedulerPriorityQueue for unassigned flights
        pq = SchedulerPriorityQueue[FlightLeg]()
        for fl in flights:
            # Estimate feasible combinations / tightness
            feasible_count = 1 if fl.aircraft_tail else 3
            slack_minutes = max(0, (fl.departure_utc - horizon_start_utc) // 60)
            priority_key = (feasible_count, fl.departure_utc, slack_minutes, 0, fl.flight_number)
            pq.push(fl.flight_number, priority_key, payload=fl)

        # Tracking state
        assignments: Dict[str, RosterAssignment] = {}
        unassigned: Dict[str, UncoveredReason] = {}
        positioned_itineraries: List[PositioningItinerary] = []
        active_crew_duty: Dict[str, Dict[str, Any]] = {}
        aircraft_last_flight: Dict[str, FlightLeg] = {}

        # Step 3: Priority-driven scheduling loop
        while not pq.is_empty():
            flight_id, priority_key, payload = pq.pop()
            flight: FlightLeg = payload if payload is not None else self.index_manager.flights_by_id.get(flight_id)

            # ------------------------------------------------------------------
            # 3A. Aircraft Selection & Rotation Feasibility
            # ------------------------------------------------------------------
            if flight.aircraft_tail:
                pre_tail = flight.aircraft_tail.strip().upper()
                ac_obj = self.index_manager.aircraft_by_id.get(pre_tail)
                ac_candidates = [ac_obj] if ac_obj is not None else []
            else:
                ac_candidates = [
                    ac for ac in self.index_manager.aircraft_by_id.values()
                    if ac.aircraft_type.strip().upper() == flight.required_aircraft_type.strip().upper()
                    and ac.is_active
                ]

            feasible_aircraft: List[Tuple[Aircraft, Optional[FlightLeg]]] = []
            ac_violations: List[RuleViolation] = []

            for ac in ac_candidates:
                prev_fl = aircraft_last_flight.get(ac.tail_number)
                if prev_fl is None:
                    # Check in-memory interval tree for previous flight
                    pred_node = self.index_manager.aircraft_intervals[ac.tail_number].find_predecessor(flight.departure_utc)
                    if pred_node and pred_node.data and "flight_number" in pred_node.data:
                        prev_fl = self.index_manager.flights_by_id.get(pred_node.data["flight_number"])

                ac_val = self.constraint_engine.validate_aircraft_assignment(
                    ac,
                    flight,
                    self.index_manager.aircraft_intervals.get(ac.tail_number),
                    prev_fl,
                )
                if ac_val.is_valid:
                    feasible_aircraft.append((ac, prev_fl))
                else:
                    ac_violations.extend(ac_val.violations)

            if not feasible_aircraft:
                summary = (
                    f"No feasible aircraft available for {flight.flight_number}: "
                    + ("; ".join(v.message for v in ac_violations) if ac_violations else "no candidates matching type")
                )
                unassigned[flight.flight_number] = UncoveredReason(
                    flight_number=flight.flight_number,
                    primary_cause="NO_FEASIBLE_AIRCRAFT",
                    summary=summary,
                    aircraft_violations=ac_violations,
                    crew_violations=[],
                    details={
                        "flight_id": flight.flight_number,
                        "departure_utc": flight.departure_utc,
                        "arrival_utc": flight.arrival_utc,
                        "origin": flight.origin,
                        "destination": flight.destination,
                        "required_aircraft_type": flight.required_aircraft_type,
                        "evaluated_aircraft_count": len(ac_candidates),
                        "rejection_rules": list({v.rule_id for v in ac_violations}),
                        "aircraft_evaluations": [
                            {
                                "tail_number": v.entity_id,
                                "rule_id": v.rule_id,
                                "message": v.message,
                                "context": v.context,
                            }
                            for v in ac_violations
                        ],
                    },
                )
                continue

            # Select best aircraft
            selected_aircraft, prev_flight_for_selected = feasible_aircraft[0]

            # ------------------------------------------------------------------
            # 3B. Crew Evaluation & Complement Matching
            # ------------------------------------------------------------------
            req_type = flight.required_aircraft_type.strip().upper()
            comp_rules = self.profile.crew_complement.get(req_type, {"captains": 1, "first_officers": 1, "cabin_crew": 4})
            req_cpt = comp_rules.get("captains", 1)
            req_fo = comp_rules.get("first_officers", 1)
            req_cc = comp_rules.get("cabin_crew", 4)

            eligible_captains: List[Tuple[CrewMember, ValidationResult]] = []
            eligible_fos: List[Tuple[CrewMember, ValidationResult]] = []
            eligible_cc: List[Tuple[CrewMember, ValidationResult]] = []
            role_violations: Dict[str, List[RuleViolation]] = {
                CrewRole.CAPTAIN.value: [],
                CrewRole.FIRST_OFFICER.value: [],
                CrewRole.CABIN_CREW.value: [],
            }

            for crew in self.index_manager.crew_by_id.values():
                if not crew.is_active:
                    continue

                active_ctx = active_crew_duty.get(crew.id)
                crew_tree = self.index_manager.crew_intervals.get(crew.id)
                val_res = self.constraint_engine.validate_crew_assignment(
                    crew,
                    flight,
                    crew.role,
                    crew_tree,
                    current_duty=active_ctx,
                )

                if val_res.is_valid:
                    if crew.role == CrewRole.CAPTAIN:
                        eligible_captains.append((crew, val_res))
                    elif crew.role == CrewRole.FIRST_OFFICER:
                        eligible_fos.append((crew, val_res))
                    elif crew.role == CrewRole.CABIN_CREW:
                        eligible_cc.append((crew, val_res))
                else:
                    role_violations[crew.role.value].extend(val_res.violations)

            # Check complement sufficiency
            if len(eligible_captains) < req_cpt or len(eligible_fos) < req_fo or len(eligible_cc) < req_cc:
                summary = (
                    f"Insufficient crew complement for {flight.flight_number} ({req_type}): "
                    f"Captains {len(eligible_captains)}/{req_cpt}, "
                    f"FOs {len(eligible_fos)}/{req_fo}, "
                    f"Cabin {len(eligible_cc)}/{req_cc}"
                )
                flat_crew_violations: List[RuleViolation] = []
                for viols in role_violations.values():
                    flat_crew_violations.extend(viols)

                unassigned[flight.flight_number] = UncoveredReason(
                    flight_number=flight.flight_number,
                    primary_cause="INSUFFICIENT_CREW",
                    summary=summary,
                    aircraft_violations=[],
                    crew_violations=flat_crew_violations,
                    details={
                        "flight_id": flight.flight_number,
                        "departure_utc": flight.departure_utc,
                        "arrival_utc": flight.arrival_utc,
                        "origin": flight.origin,
                        "destination": flight.destination,
                        "required_aircraft_type": req_type,
                        "selected_aircraft": selected_aircraft.tail_number,
                        "eligible_captains_count": len(eligible_captains),
                        "required_captains_count": req_cpt,
                        "eligible_first_officers_count": len(eligible_fos),
                        "required_first_officers_count": req_fo,
                        "eligible_cabin_crew_count": len(eligible_cc),
                        "required_cabin_crew_count": req_cc,
                        "rejection_rules": list({v.rule_id for v in flat_crew_violations}),
                        "role_breakdown": {
                            role: [
                                {
                                    "crew_id": v.entity_id,
                                    "rule_id": v.rule_id,
                                    "message": v.message,
                                    "context": v.context,
                                }
                                for v in viols
                            ]
                            for role, viols in role_violations.items()
                        },
                    },
                )
                continue

            # Sort eligible candidates by soft optimization score descending
            eligible_captains.sort(key=lambda item: item[1].soft_score, reverse=True)
            eligible_fos.sort(key=lambda item: item[1].soft_score, reverse=True)
            eligible_cc.sort(key=lambda item: item[1].soft_score, reverse=True)

            selected_cpt, cpt_val = eligible_captains[0]
            selected_fo, fo_val = eligible_fos[0]
            selected_cc_pairs = eligible_cc[:req_cc]
            selected_cc = [c for c, _ in selected_cc_pairs]

            # ------------------------------------------------------------------
            # 3C. Re-verify Pairing Immediately Before In-Memory Commit
            # ------------------------------------------------------------------
            pair_val = self.constraint_engine.validate_pairing(
                flight,
                selected_cpt,
                selected_fo,
                selected_cc,
                selected_aircraft,
                self.index_manager.crew_intervals,
                self.index_manager.aircraft_intervals.get(selected_aircraft.tail_number),
                prev_flight_for_selected,
            )

            if not pair_val.is_valid:
                flat_pair_violations = pair_val.violations
                unassigned[flight.flight_number] = UncoveredReason(
                    flight_number=flight.flight_number,
                    primary_cause="PAIRING_REJECTED",
                    summary=f"Pairing validation failed: {'; '.join(v.message for v in pair_val.violations)}",
                    aircraft_violations=[],
                    crew_violations=flat_pair_violations,
                    details={
                        "flight_id": flight.flight_number,
                        "departure_utc": flight.departure_utc,
                        "arrival_utc": flight.arrival_utc,
                        "selected_aircraft": selected_aircraft.tail_number,
                        "rejection_rules": list({v.rule_id for v in pair_val.violations}),
                        "violations": [
                            {
                                "entity_id": v.entity_id,
                                "rule_id": v.rule_id,
                                "message": v.message,
                                "context": v.context,
                            }
                            for v in pair_val.violations
                        ],
                    },
                )
                continue

            # ------------------------------------------------------------------
            # 3D. Atomic In-Memory Commit
            # ------------------------------------------------------------------
            flight.aircraft_tail = selected_aircraft.tail_number
            self.index_manager.commit_aircraft_reservation(selected_aircraft.tail_number, flight)
            aircraft_last_flight[selected_aircraft.tail_number] = flight

            # Commit crew members
            all_selected_crew: List[Tuple[CrewMember, ValidationResult]] = [
                (selected_cpt, cpt_val),
                (selected_fo, fo_val),
            ] + selected_cc_pairs

            for member, m_val in all_selected_crew:
                rules = self.constraint_engine._get_rules_for_role(member.role)
                lead_time = rules.report_lead_time_seconds
                release_buf = rules.release_buffer_seconds

                # Positioning handling
                if m_val.positioning_itinerary is not None:
                    positioned_itineraries.append(m_val.positioning_itinerary)
                    member.current_airport = flight.origin

                # Update current station & 7-day cumulative flight seconds
                member.current_airport = flight.destination
                member.cumulative_flight_seconds_7d += flight.flight_duration_seconds

                if m_val.is_intra_duty_continuation and member.id in active_crew_duty:
                    # Multi-leg continuation in same duty period
                    prev_duty = active_crew_duty[member.id]
                    duty_id = prev_duty["duty_id"]
                    start_report = prev_duty["duty_start_utc"]
                    old_release = prev_duty["duty_end_utc"]
                    new_release = flight.arrival_utc + release_buf

                    duty_flight_ids = prev_duty.get("flight_ids", []) + [flight.flight_number]
                    new_cum_flight = prev_duty.get("cumulative_flight_seconds", 0) + flight.flight_duration_seconds
                    new_sectors = prev_duty.get("sector_count", 1) + 1

                    old_interval = (start_report, old_release, duty_id)
                    updated_payload = {
                        "duty_id": duty_id,
                        "duty_start_utc": start_report,
                        "duty_end_utc": new_release,
                        "sector_count": new_sectors,
                        "cumulative_flight_seconds": new_cum_flight,
                        "last_destination": flight.destination,
                        "last_arrival_utc": flight.arrival_utc,
                        "last_aircraft_tail": flight.aircraft_tail,
                        "flight_ids": duty_flight_ids,
                    }

                    self.index_manager.commit_crew_duty(
                        member.id,
                        start_report,
                        new_release,
                        duty_id,
                        updated_payload,
                        old_interval=old_interval,
                    )
                    active_crew_duty[member.id] = updated_payload
                    member.cumulative_duty_seconds_7d += (new_release - old_release)
                    member.last_duty_end_utc = new_release
                else:
                    # New Flight Duty Period
                    duty_id = f"DUTY-{flight.flight_number}-{member.id}"
                    if m_val.positioning_itinerary is not None:
                        pos_rep = m_val.positioning_itinerary.departure_utc - lead_time
                        start_report = min(flight.departure_utc - lead_time, pos_rep)
                    else:
                        start_report = flight.departure_utc - lead_time

                    new_release = flight.arrival_utc + release_buf
                    duty_payload = {
                        "duty_id": duty_id,
                        "duty_start_utc": start_report,
                        "duty_end_utc": new_release,
                        "sector_count": 1,
                        "cumulative_flight_seconds": flight.flight_duration_seconds,
                        "last_destination": flight.destination,
                        "last_arrival_utc": flight.arrival_utc,
                        "last_aircraft_tail": flight.aircraft_tail,
                        "flight_ids": [flight.flight_number],
                    }

                    self.index_manager.commit_crew_duty(
                        member.id, start_report, new_release, duty_id, duty_payload
                    )
                    active_crew_duty[member.id] = duty_payload
                    member.cumulative_duty_seconds_7d += (new_release - start_report)
                    member.last_duty_end_utc = new_release

            # Record assignment
            asn = RosterAssignment(
                id=f"ASN-{flight.flight_number}",
                flight_number=flight.flight_number,
                captain_id=selected_cpt.id,
                first_officer_id=selected_fo.id,
                cabin_crew_ids=[cc.id for cc in selected_cc],
                aircraft_tail=selected_aircraft.tail_number,
                status=RosterStatus.ASSIGNED,
            )
            assignments[flight.flight_number] = asn

        # Step 4: Construct Domain DutyPeriods from active tracking state
        duty_periods_list: List[DutyPeriod] = []
        for cid, d_data in active_crew_duty.items():
            dp = DutyPeriod(
                id=d_data["duty_id"],
                crew_id=cid,
                flight_leg_ids=d_data.get("flight_ids", []),
                report_utc=d_data["duty_start_utc"],
                release_utc=d_data["duty_end_utc"],
                duty_type=DutyType.FLIGHT_DUTY,
                total_flight_seconds=d_data.get("cumulative_flight_seconds", 0),
            )
            duty_periods_list.append(dp)

        total_cnt = len(flights)
        assigned_cnt = len(assignments)
        unassigned_cnt = len(unassigned)
        coverage_pct = round((assigned_cnt / total_cnt) * 100, 2) if total_cnt > 0 else 0.0

        return ScheduleResult(
            assignments=assignments,
            unassigned_flights=unassigned,
            positioned_crew=positioned_itineraries,
            duty_periods=duty_periods_list,
            total_flights=total_cnt,
            assigned_count=assigned_cnt,
            unassigned_count=unassigned_cnt,
            coverage_percentage=coverage_pct,
        )

    def recover_affected_flights(
        self,
        affected_flight_numbers: List[str],
        protected_flight_numbers: Optional[Set[str]] = None,
    ) -> RecoveryResult:
        """Perform 1-level bounded swap recovery for affected flights while protecting unaffected rosters."""
        protected = protected_flight_numbers or set()
        recovered: List[str] = []
        unrecovered: List[str] = []
        swaps: List[Dict[str, Any]] = []
        uncovered_reasons: Dict[str, UncoveredReason] = {}

        for fn in affected_flight_numbers:
            if fn in protected:
                continue

            flight = self.index_manager.flights_by_id.get(fn)
            if flight is None:
                continue

            # Check if alternative candidate aircraft or swap is feasible
            candidates = [
                ac for ac in self.index_manager.aircraft_by_id.values()
                if ac.aircraft_type.strip().upper() == flight.required_aircraft_type.strip().upper()
                and ac.is_active
            ]

            recovered_for_flight = False
            for ac in candidates:
                # Check overlap in candidate aircraft tree
                overlap = self.index_manager.aircraft_intervals[ac.tail_number].find_first_overlap(
                    flight.departure_utc, flight.arrival_utc
                )
                if overlap is None:
                    # Aircraft swap feasible
                    old_tail = flight.aircraft_tail
                    flight.aircraft_tail = ac.tail_number
                    self.index_manager.commit_aircraft_reservation(ac.tail_number, flight)
                    swaps.append({
                        "flight_number": fn,
                        "resource_type": "AIRCRAFT",
                        "old_resource": old_tail,
                        "new_resource": ac.tail_number,
                    })
                    recovered_for_flight = True
                    recovered.append(fn)
                    break

            if not recovered_for_flight:
                unrecovered.append(fn)
                uncovered_reasons[fn] = UncoveredReason(
                    flight_number=fn,
                    primary_cause="RECOVERY_SWAP_UNFEASIBLE",
                    summary=f"No feasible aircraft swap could be found for disrupted flight {fn}",
                )

        return RecoveryResult(
            success=len(unrecovered) == 0,
            affected_flights=affected_flight_numbers,
            recovered_flights=recovered,
            unrecovered_flights=unrecovered,
            swaps_performed=swaps,
            uncovered_reasons=uncovered_reasons,
        )
