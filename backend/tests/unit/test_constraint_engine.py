"""Comprehensive unit tests for ConstraintEngine and PositioningService.

Verifies all DGCA CAR Section 7 Series J hard constraint rejections, intra-duty
FDP continuation, deadhead positioning, and full crew complement pairing validation.
"""

import sys
from pathlib import Path
from typing import List

import pytest

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.data_structures.graph import FlightConnectionGraph
from backend.app.data_structures.rb_interval_tree import RBIntervalTree
from backend.app.models.domain import (
    Aircraft,
    CrewMember,
    CrewQualification,
    CrewRole,
    FlightLeg,
    RuleSeverity,
)
from backend.app.rules.profile_loader import load_rule_profile
from backend.app.services.constraint_engine import ConstraintEngine, ValidationResult
from backend.app.services.positioning_service import PositioningService


@pytest.fixture
def profile():
    return load_rule_profile("nova_air_demo_v1")


@pytest.fixture
def engine(profile):
    return ConstraintEngine(rule_profile=profile)


def make_qual(acft: str = "A320", valid_until: int = 1800000000) -> CrewQualification:
    return CrewQualification(aircraft_type=acft, valid_until_utc=valid_until)


def make_crew(
    id: str = "CRW-01",
    role: CrewRole = CrewRole.CAPTAIN,
    home: str = "BOM",
    current: str = "BOM",
    quals: List[CrewQualification] = None,
    cum_ft_7d: int = 0,
    cum_duty_7d: int = 0,
    last_duty_end: int = None,
) -> CrewMember:
    if quals is None:
        quals = [make_qual("A320")]
    return CrewMember(
        id=id,
        name=f"Pilot {id}",
        role=role,
        home_base=home,
        current_airport=current,
        qualifications=quals,
        cumulative_flight_seconds_7d=cum_ft_7d,
        cumulative_duty_seconds_7d=cum_duty_7d,
        last_duty_end_utc=last_duty_end,
        is_active=True,
    )


def make_flight(
    flight_number: str = "NV-101",
    origin: str = "BOM",
    dest: str = "DEL",
    dep: int = 1774936800,
    arr: int = 1774945200,
    tail: str = "VT-NVA",
    req_type: str = "A320",
) -> FlightLeg:
    return FlightLeg(
        flight_number=flight_number,
        origin=origin,
        destination=dest,
        departure_utc=dep,
        arrival_utc=arr,
        aircraft_tail=tail,
        required_aircraft_type=req_type,
    )


def make_aircraft(
    tail: str = "VT-NVA",
    acft_type: str = "A320",
    home: str = "BOM",
    is_active: bool = True,
) -> Aircraft:
    return Aircraft(
        tail_number=tail,
        aircraft_type=acft_type,
        home_base=home,
        seating_capacity=180 if acft_type == "A320" else 72,
        is_active=is_active,
    )


# ==============================================================================
# Mandatory Rejection Tests (11 Rules)
# ==============================================================================


def test_crew_role_mismatch_rejection(engine):
    """Rule CREW-ROLE-01: Reject candidate with incompatible role."""
    fo = make_crew(id="FO-01", role=CrewRole.FIRST_OFFICER)
    flight = make_flight()

    # Try assigning First Officer to Captain slot
    res = engine.validate_crew_assignment(fo, flight, role=CrewRole.CAPTAIN)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-ROLE-01" for v in res.violations)

    # Try assigning Cabin Crew to First Officer slot
    cc = make_crew(id="CC-01", role=CrewRole.CABIN_CREW)
    res2 = engine.validate_crew_assignment(cc, flight, role=CrewRole.FIRST_OFFICER)
    assert res2.is_valid is False
    assert any(v.rule_id == "CREW-ROLE-01" for v in res2.violations)


def test_crew_missing_qualification_rejection(engine):
    """Rule CREW-QUAL-01: Reject pilot without required aircraft type rating."""
    atr_captain = make_crew(id="CPT-01", quals=[make_qual("ATR72")])
    flight_a320 = make_flight(req_type="A320")

    res = engine.validate_crew_assignment(atr_captain, flight_a320, role=CrewRole.CAPTAIN)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-QUAL-01" for v in res.violations)


def test_crew_expired_qualification_rejection(engine):
    """Rule CREW-EXP-01: Reject pilot with expired rating on departure date."""
    dep_time = 1774936800
    expired_qual = make_qual("A320", valid_until=dep_time - 3600)  # Expired 1h before departure
    cpt = make_crew(id="CPT-01", quals=[expired_qual])
    flight = make_flight(dep=dep_time)

    res = engine.validate_crew_assignment(cpt, flight, role=CrewRole.CAPTAIN)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-EXP-01" for v in res.violations)


def test_crew_overlap_rejection(engine):
    """Rule CREW-OVLP-01: Reject assignment overlapping existing duty in RBIntervalTree."""
    cpt = make_crew()
    flight = make_flight(dep=1774936800, arr=1774945200)

    # Crew member already has duty [dep - 7200, dep + 3600)
    tree: RBIntervalTree[str] = RBIntervalTree()
    tree.insert(flight.departure_utc - 7200, flight.departure_utc + 3600, "DUTY-PREV")

    res = engine.validate_crew_assignment(cpt, flight, role=CrewRole.CAPTAIN, crew_tree=tree)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-OVLP-01" for v in res.violations)


def test_crew_insufficient_rest_rejection(engine):
    """Rule CREW-REST-01: Enforce mandatory inter-duty rest (>= 43200s or prior FDP)."""
    cpt = make_crew()
    dep_time = 1774936800
    report_time = dep_time - 3600
    flight = make_flight(dep=dep_time, arr=dep_time + 7200)

    # 1. Prior duty ended only 6 hours (21600s) before report time (< 43200s)
    tree: RBIntervalTree[str] = RBIntervalTree()
    tree.insert(report_time - 40000, report_time - 21600, "DUTY-SHORT-REST")

    res = engine.validate_crew_assignment(cpt, flight, role=CrewRole.CAPTAIN, crew_tree=tree)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-REST-01" for v in res.violations)

    # 2. Prior duty was a long 14-hour duty (50400s). Rest must equal prior FDP (50400s)!
    # Rest provided = 46000s (> 43200 min rest, but < 50400 prior FDP)
    tree_long: RBIntervalTree[str] = RBIntervalTree()
    tree_long.insert(report_time - 96400, report_time - 46000, "DUTY-LONG-FDP")

    res2 = engine.validate_crew_assignment(cpt, flight, role=CrewRole.CAPTAIN, crew_tree=tree_long)
    assert res2.is_valid is False
    assert any(v.rule_id == "CREW-REST-01" for v in res2.violations)


def test_crew_max_fdp_and_sector_rejection(engine):
    """Rule CREW-FDP-01: Enforce max daily FDP duration (45000s) and max sectors (4 for FC)."""
    cpt = make_crew()

    # Flight duration 42000s + report lead (3600s) + release buffer (1800s) = 47400s > 45000s!
    flight_too_long = make_flight(dep=1774936800, arr=1774936800 + 42000)

    res = engine.validate_crew_assignment(cpt, flight_too_long, role=CrewRole.CAPTAIN)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-FDP-01" for v in res.violations)

    # Exceeding sectors: Already performed 4 sectors, candidate would be 5th sector (> 4 for flight crew)
    active_duty = {
        "duty_id": "DUTY-4SEC",
        "duty_start_utc": 1774900000,
        "duty_end_utc": 1774930000,
        "sector_count": 4,
        "cumulative_flight_seconds": 18000,
        "last_destination": "BOM",
        "last_arrival_utc": 1774928200,
        "last_aircraft_tail": "VT-NVA",
    }
    flight_next = make_flight(origin="BOM", dep=1774932000, arr=1774937000)
    res_sec = engine.validate_crew_assignment(cpt, flight_next, role=CrewRole.CAPTAIN, current_duty=active_duty)
    assert res_sec.is_valid is False
    assert any(v.rule_id == "CREW-FDP-01" for v in res_sec.violations)


def test_crew_max_daily_flight_time_rejection(engine):
    """Rule CREW-FT-01: Enforce max daily flight time (28800s for Flight Crew)."""
    cpt = make_crew()
    # Flight airborne duration 30000s > 28800s
    flight = make_flight(dep=1774900000, arr=1774900000 + 30000)

    res = engine.validate_crew_assignment(cpt, flight, role=CrewRole.CAPTAIN)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-FT-01" for v in res.violations)


def test_crew_cumulative_7d_limits_rejection(engine):
    """Rule CREW-CUM-01: Enforce 7-day cumulative flight time (126000s) and duty time (216000s)."""
    # Pilot already has 124000s flight time; candidate flight adds 7200s -> 131200s > 126000s!
    cpt_near_limit = make_crew(cum_ft_7d=124000, cum_duty_7d=180000)
    flight = make_flight(dep=1774900000, arr=1774907200)

    res = engine.validate_crew_assignment(cpt_near_limit, flight, role=CrewRole.CAPTAIN)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-CUM-01" for v in res.violations)

    # Pilot near 7d duty limit: 212000s duty; candidate duty is 12600s -> 224600s > 216000s!
    cpt_duty_limit = make_crew(cum_ft_7d=50000, cum_duty_7d=212000)
    res_duty = engine.validate_crew_assignment(cpt_duty_limit, flight, role=CrewRole.CAPTAIN)
    assert res_duty.is_valid is False
    assert any(v.rule_id == "CREW-CUM-01" for v in res_duty.violations)


def test_crew_location_and_positioning_rejection(engine):
    """Rule CREW-POS-01: Reject crew member at wrong location when no positioning path exists."""
    # Crew is in CCU, flight departs from BOM
    cpt_away = make_crew(current="CCU")
    flight = make_flight(origin="BOM")

    # Engine without positioning service
    res = engine.validate_crew_assignment(cpt_away, flight, role=CrewRole.CAPTAIN)
    assert res.is_valid is False
    assert any(v.rule_id == "CREW-POS-01" for v in res.violations)


def test_aircraft_overlap_rejection(engine):
    """Rule ACFT-OVLP-01: Reject aircraft with overlapping flight or maintenance block."""
    acft = make_aircraft()
    flight = make_flight(dep=1774936800, arr=1774945200)

    # Aircraft tree has existing maintenance block overlapping flight
    acft_tree: RBIntervalTree[str] = RBIntervalTree()
    acft_tree.insert(flight.departure_utc - 1000, flight.arrival_utc + 1000, "MNT-01")

    res = engine.validate_aircraft_assignment(acft, flight, aircraft_tree=acft_tree)
    assert res.is_valid is False
    assert any(v.rule_id == "ACFT-OVLP-01" for v in res.violations)


def test_aircraft_turnaround_time_rejection(engine):
    """Rule ACFT-SUCC-01: Enforce minimum aircraft turnaround time (A320 = 2700s, ATR72 = 1800s)."""
    acft = make_aircraft(acft_type="A320")

    # Leg 1 arrives at 1774940000
    leg1 = make_flight(flight_number="NV-01", origin="BOM", dest="DEL", dep=1774930000, arr=1774940000)
    # Leg 2 departs at 1774941500 (gap = 1500s < 2700s required TAT for A320!)
    leg2 = make_flight(flight_number="NV-02", origin="DEL", dest="BLR", dep=1774941500, arr=1774950000)

    res = engine.validate_aircraft_assignment(acft, leg2, previous_flight=leg1)
    assert res.is_valid is False
    assert any(v.rule_id == "ACFT-SUCC-01" for v in res.violations)


# ==============================================================================
# Valid Assignment & Pairing Tests
# ==============================================================================


def test_valid_single_leg_fdp_and_soft_score(engine):
    """Verify completely valid single-leg assignment and soft score computation."""
    cpt = make_crew(home="BOM", current="BOM", cum_ft_7d=36000)
    flight = make_flight(origin="BOM", dest="DEL", dep=1774936800, arr=1774944000)

    res = engine.validate_crew_assignment(cpt, flight, role=CrewRole.CAPTAIN)
    assert res.is_valid is True
    assert len(res.violations) == 0
    assert res.is_intra_duty_continuation is False
    assert res.soft_score > 100.0  # +100 for home base match + workload balance


def test_valid_multi_leg_intra_fdp_continuation(engine):
    """Verify consecutive legs within the same FDP with valid intra-duty turnaround buffer."""
    cpt = make_crew(home="BOM", current="BOM")

    # Leg 1: BOM -> DEL [10000, 15000) on VT-NVA
    # Intra-duty turnaround on same aircraft requires 1800s (30m)
    # Leg 2: DEL -> BLR [17000, 22000) on VT-NVA (gap = 2000s >= 1800s!)
    active_duty = {
        "duty_id": "DUTY-LEG1",
        "duty_start_utc": 10000 - 3600,
        "duty_end_utc": 15000 + 1800,
        "sector_count": 1,
        "cumulative_flight_seconds": 5000,
        "last_destination": "DEL",
        "last_arrival_utc": 15000,
        "last_aircraft_tail": "VT-NVA",
    }

    leg2 = make_flight(origin="DEL", dest="BLR", dep=17000, arr=22000, tail="VT-NVA")
    res = engine.validate_crew_assignment(cpt, leg2, role=CrewRole.CAPTAIN, current_duty=active_duty)

    assert res.is_valid is True
    assert res.is_intra_duty_continuation is True
    # Projected duty should span from Leg 1 report (6400) to Leg 2 release (23800)
    assert res.projected_duty_interval == (6400, 23800)


def test_valid_positioned_assignment(engine):
    """Verify automatic positioning route discovery and assignment validation."""
    # Build a flight graph with positioning route: CCU -> DEL [10000, 15000)
    graph = FlightConnectionGraph(min_connection_seconds=1800, max_connection_seconds=7200)
    pos_flight = make_flight(flight_number="NV-POS-1", origin="CCU", dest="DEL", dep=10000, arr=15000)
    graph.add_flight(pos_flight)

    pos_service = PositioningService(graph=graph, rule_profile=engine.profile)
    engine_with_pos = ConstraintEngine(rule_profile=engine.profile, positioning_service=pos_service)

    # Crew member is in CCU
    cpt = make_crew(current="CCU", home="DEL")
    # Operating flight departs from DEL at 20000 (arrives at DEL at 15000, report time is 16400 -> fits!)
    op_flight = make_flight(origin="DEL", dest="BOM", dep=20000, arr=25000)

    res = engine_with_pos.validate_crew_assignment(cpt, op_flight, role=CrewRole.CAPTAIN)
    assert res.is_valid is True
    assert res.positioning_itinerary is not None
    assert res.positioning_itinerary.flight_legs == ["NV-POS-1"]


def test_pairing_composition_validation(engine):
    """Rule PAIR-COMP-01: Verify complete crew complement (1 CPT, 1 FO, 4 Cabin for A320)."""
    flight = make_flight(req_type="A320")
    acft = make_aircraft(acft_type="A320")

    cpt = make_crew(id="CPT-1", role=CrewRole.CAPTAIN)
    fo = make_crew(id="FO-1", role=CrewRole.FIRST_OFFICER)
    cc1 = make_crew(id="CC-1", role=CrewRole.CABIN_CREW)
    cc2 = make_crew(id="CC-2", role=CrewRole.CABIN_CREW)
    cc3 = make_crew(id="CC-3", role=CrewRole.CABIN_CREW)
    cc4 = make_crew(id="CC-4", role=CrewRole.CABIN_CREW)

    # 1. Valid complement: 1 CPT, 1 FO, 4 CC
    res_valid = engine.validate_pairing(flight, cpt, fo, [cc1, cc2, cc3, cc4], acft)
    assert res_valid.is_valid is True

    # 2. Incomplete cabin crew (only 3 assigned instead of 4)
    res_missing_cc = engine.validate_pairing(flight, cpt, fo, [cc1, cc2, cc3], acft)
    assert res_missing_cc.is_valid is False
    assert any(v.rule_id == "PAIR-COMP-01" for v in res_missing_cc.violations)

    # 3. Duplicate crew member assigned as both Captain and First Officer
    res_dup = engine.validate_pairing(flight, cpt, cpt, [cc1, cc2, cc3, cc4], acft)
    assert res_dup.is_valid is False
    assert any(v.rule_id == "PAIR-COMP-01" for v in res_dup.violations)
