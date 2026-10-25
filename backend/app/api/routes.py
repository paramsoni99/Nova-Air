"""FastAPI REST routes for Nova Air Operations Control Center (AirCrewOps)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.models.domain import (
    Aircraft,
    Airport,
    CrewMember,
    CrewRole,
    FlightLeg,
    RosterAssignment,
    RosterStatus,
    RuleViolation,
)
from backend.app.models.schemas import (
    ADSLaboratoryQueryRequest,
    APIResponse,
    FlightCreateRequest,
    FlightPatchRequest,
    ManualAssignRequest,
    ResetDemoRequest,
    RosterGenerateRequest,
)
from backend.app.rules.profile_loader import load_rule_profile
from backend.app.services.aircraft_service import AircraftService
from backend.app.services.constraint_engine import ConstraintEngine
from backend.app.services.crew_service import CrewService
from backend.app.services.index_manager import ADSIndexManager
from backend.app.services.persistence_service import PersistenceService
from backend.app.services.positioning_service import PositioningService
from backend.app.services.roster_scheduler import RosterScheduler
from backend.app.websocket.manager import ws_manager

api_router = APIRouter()


# ------------------------------------------------------------------------------
# Dependency injection helpers
# ------------------------------------------------------------------------------
def get_index_manager(request: Request) -> ADSIndexManager:
    return request.app.state.index_manager


def get_persistence_service(request: Request) -> PersistenceService:
    return request.app.state.persistence_service


def get_constraint_engine(request: Request) -> ConstraintEngine:
    return request.app.state.constraint_engine


def get_roster_scheduler(request: Request) -> RosterScheduler:
    return request.app.state.roster_scheduler


def get_crew_service(request: Request) -> CrewService:
    return request.app.state.crew_service


def get_aircraft_service(request: Request) -> AircraftService:
    return request.app.state.aircraft_service


# ------------------------------------------------------------------------------
# 1. Health & Dashboard
# ------------------------------------------------------------------------------
@api_router.get("/health", tags=["System"])
def get_health(request: Request):
    """Liveness probe & application metadata."""
    start_time = getattr(request.app.state, "start_time", time.time())
    return {
        "status": "ok",
        "airline": "Nova Air",
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - start_time, 2),
        "is_educational_simulator": True,
    }


@api_router.get("/dashboard/summary", tags=["Dashboard"])
def get_dashboard_summary(
    idx: ADSIndexManager = Depends(get_index_manager),
    persist: PersistenceService = Depends(get_persistence_service),
):
    """Dashboard operational metrics, active rule profile, and ADS statistics."""
    diag = idx.get_structure_diagnostics()
    return {
        "airline": "Nova Air",
        "active_rule_profile": "nova_air_demo_v1",
        "is_educational_simulator": True,
        "academic_institution": "NMIMS MPSTME",
        "course": "Advanced Data Structures (ADS)",
        "total_flights": len(idx.flights_by_id),
        "total_crew": len(idx.crew_by_id),
        "total_aircraft": len(idx.aircraft_by_id),
        "total_airports": len(idx.airports_by_code),
        "ads_telemetry": {
            "schedule_btree": diag["schedule_btree"],
            "connection_graph": diag["connection_graph"],
            "total_crew_duty_intervals": diag["total_crew_duty_intervals"],
            "total_aircraft_intervals": diag["total_aircraft_intervals"],
            "invariants_verified": diag["invariants_verified"],
        },
    }


# ------------------------------------------------------------------------------
# 2. Flight Schedule Endpoints (B-Tree + Connection Graph synchronization)
# ------------------------------------------------------------------------------
@api_router.get("/flights", tags=["Flights"])
def list_flights(
    start_utc: Optional[int] = Query(None, description="Start departure timestamp (UTC epoch seconds)"),
    end_utc: Optional[int] = Query(None, description="End departure timestamp (UTC epoch seconds)"),
    origin: Optional[str] = Query(None),
    destination: Optional[str] = Query(None),
    idx: ADSIndexManager = Depends(get_index_manager),
):
    """Retrieve flights with optional B-Tree departure time-window range query."""
    b_tree_query_executed = False
    query_duration_us = 0.0

    if start_utc is not None and end_utc is not None:
        t0 = time.perf_counter()
        results = idx.schedule_btree.range_query(start_utc, end_utc)
        query_duration_us = round((time.perf_counter() - t0) * 1_000_000, 2)
        flights = [fl for _, fl in results]
        b_tree_query_executed = True
    else:
        flights = list(idx.flights_by_id.values())
        flights.sort(key=lambda x: (x.departure_utc, x.flight_number))

    # Apply secondary filters if requested
    filtered = []
    for fl in flights:
        if origin and fl.origin != origin.upper():
            continue
        if destination and fl.destination != destination.upper():
            continue
        filtered.append(fl)

    return {
        "flights": filtered,
        "count": len(filtered),
        "b_tree_telemetry": {
            "range_query_executed": b_tree_query_executed,
            "query_duration_us": query_duration_us,
            "tree_size": len(idx.schedule_btree),
            "tree_height": idx.schedule_btree.get_diagnostics()["height"],
        },
    }


@api_router.post("/flights", status_code=status.HTTP_201_CREATED, tags=["Flights"])
async def create_flight(
    req: FlightCreateRequest,
    idx: ADSIndexManager = Depends(get_index_manager),
    persist: PersistenceService = Depends(get_persistence_service),
):
    """Create a new flight leg, synchronize B-Tree and Graph, and persist to SQLite."""
    if idx.flights_by_id.get(req.flight_number):
        raise HTTPException(status_code=400, detail=f"Flight '{req.flight_number}' already exists")

    flight = FlightLeg(
        flight_number=req.flight_number,
        origin=req.origin,
        destination=req.destination,
        departure_utc=req.departure_utc,
        arrival_utc=req.arrival_utc,
        aircraft_tail=req.aircraft_tail,
        required_aircraft_type=req.required_aircraft_type,
    )

    persist.save_flight(flight)
    idx.sync_flight_mutation(flight)
    await ws_manager.broadcast("FLIGHT_CREATED", flight.model_dump())
    return flight


@api_router.patch("/flights/{flight_id}", tags=["Flights"])
async def update_flight(
    flight_id: str,
    req: FlightPatchRequest,
    idx: ADSIndexManager = Depends(get_index_manager),
    persist: PersistenceService = Depends(get_persistence_service),
):
    """Update flight departure/arrival or tail, dynamically synchronizing B-Tree and Graph."""
    fid = flight_id.upper()
    existing = idx.flights_by_id.get(fid)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Flight '{fid}' not found")

    old_dep = existing.departure_utc
    new_dep = req.departure_utc if req.departure_utc is not None else existing.departure_utc
    new_arr = req.arrival_utc if req.arrival_utc is not None else existing.arrival_utc
    new_tail = req.aircraft_tail if req.aircraft_tail is not None else existing.aircraft_tail

    updated_flight = FlightLeg(
        flight_number=fid,
        origin=existing.origin,
        destination=existing.destination,
        departure_utc=new_dep,
        arrival_utc=new_arr,
        aircraft_tail=new_tail,
        required_aircraft_type=existing.required_aircraft_type,
    )

    persist.save_flight(updated_flight)
    idx.sync_flight_mutation(updated_flight, old_departure_utc=old_dep)
    await ws_manager.broadcast("FLIGHT_UPDATED", updated_flight.model_dump())
    return updated_flight


# ------------------------------------------------------------------------------
# 3. Crew & Aircraft Endpoints
# ------------------------------------------------------------------------------
@api_router.get("/crew", tags=["Crew"])
def list_crew(
    role: Optional[str] = Query(None),
    base: Optional[str] = Query(None),
    current_airport: Optional[str] = Query(None),
    active_only: bool = Query(True),
    crew_svc: CrewService = Depends(get_crew_service),
):
    """List crew members matching criteria."""
    members = crew_svc.list_crew(role, base, current_airport, active_only)
    return {"crew": members, "count": len(members)}


@api_router.get("/crew/{crew_id}/schedule", tags=["Crew"])
def get_crew_schedule(
    crew_id: str,
    crew_svc: CrewService = Depends(get_crew_service),
):
    """Get active duty periods, intervals, and qualifications for a crew member."""
    try:
        return crew_svc.get_crew_schedule(crew_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@api_router.get("/aircraft", tags=["Aircraft"])
def list_aircraft(
    aircraft_type: Optional[str] = Query(None),
    home_base: Optional[str] = Query(None),
    active_only: bool = Query(True),
    ac_svc: AircraftService = Depends(get_aircraft_service),
):
    """List fleet aircraft matching criteria."""
    fleet = ac_svc.list_aircraft(aircraft_type, home_base, active_only)
    return {"aircraft": fleet, "count": len(fleet)}


@api_router.get("/aircraft/{aircraft_id}/rotation", tags=["Aircraft"])
def get_aircraft_rotation(
    aircraft_id: str,
    ac_svc: AircraftService = Depends(get_aircraft_service),
):
    """Get rotation timeline, maintenance blocks, and flight assignments for an aircraft."""
    try:
        return ac_svc.get_aircraft_rotation(aircraft_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------------------
# 4. Rostering & Manual Assignment (with Fail-Closed Atomic Rollback)
# ------------------------------------------------------------------------------
@api_router.post("/roster/generate", tags=["Rostering"])
async def generate_roster(
    req: RosterGenerateRequest,
    scheduler: RosterScheduler = Depends(get_roster_scheduler),
    idx: ADSIndexManager = Depends(get_index_manager),
    persist: PersistenceService = Depends(get_persistence_service),
):
    """Execute priority-driven roster generation across planning horizon."""
    all_flights = list(idx.flights_by_id.values())
    if not all_flights:
        return {"message": "No flights available to schedule"}

    min_dep = req.start_utc if req.start_utc is not None else min(f.departure_utc for f in all_flights)
    max_arr = req.end_utc if req.end_utc is not None else max(f.arrival_utc for f in all_flights)

    result = scheduler.generate_roster(min_dep, max_arr, req.prioritize_tight_connections)

    # Persist generated assignments to SQLite
    for asn in result.assignments.values():
        persist.save_assignment(asn)

    await ws_manager.broadcast("ROSTER_GENERATED", {
        "total_flights": result.total_flights,
        "assigned_count": result.assigned_count,
        "unassigned_count": result.unassigned_count,
        "coverage_percentage": result.coverage_percentage,
    })

    return {
        "total_flights": result.total_flights,
        "assigned_count": result.assigned_count,
        "unassigned_count": result.unassigned_count,
        "coverage_percentage": result.coverage_percentage,
        "assignments": result.assignments,
        "unassigned_flights": result.unassigned_flights,
        "positioned_crew_count": len(result.positioned_crew),
    }


@api_router.post("/roster/manual-assign", tags=["Rostering"])
async def manual_assign(
    req: ManualAssignRequest,
    idx: ADSIndexManager = Depends(get_index_manager),
    ce: ConstraintEngine = Depends(get_constraint_engine),
    persist: PersistenceService = Depends(get_persistence_service),
):
    """Validate and manually assign crew/aircraft to flight leg with HTTP 422 atomic rollback."""
    fid = req.flight_number.upper()
    flight = idx.flights_by_id.get(fid)
    if flight is None:
        raise HTTPException(status_code=404, detail=f"Flight '{fid}' not found")

    cpt = idx.crew_by_id.get(req.captain_id.upper())
    if cpt is None:
        raise HTTPException(status_code=404, detail=f"Captain '{req.captain_id}' not found")

    fo = idx.crew_by_id.get(req.first_officer_id.upper())
    if fo is None:
        raise HTTPException(status_code=404, detail=f"First Officer '{req.first_officer_id}' not found")

    cabin_crew: List[CrewMember] = []
    for cc_id in req.cabin_crew_ids:
        cc = idx.crew_by_id.get(cc_id.upper())
        if cc is None:
            raise HTTPException(status_code=404, detail=f"Cabin crew '{cc_id}' not found")
        cabin_crew.append(cc)

    tail = (req.aircraft_tail or flight.aircraft_tail or "").upper()
    aircraft = idx.aircraft_by_id.get(tail)
    if aircraft is None:
        raise HTTPException(status_code=404, detail=f"Aircraft '{tail}' not found")

    # Validate complete pairing against civil aviation constraints
    prev_flight = None
    pred_node = idx.aircraft_intervals[aircraft.tail_number].find_predecessor(flight.departure_utc)
    if pred_node and pred_node.data and "flight_number" in pred_node.data:
        prev_flight = idx.flights_by_id.get(pred_node.data["flight_number"])

    val_res = ce.validate_pairing(
        flight,
        cpt,
        fo,
        cabin_crew,
        aircraft,
        idx.crew_intervals,
        idx.aircraft_intervals.get(aircraft.tail_number),
        prev_flight,
    )

    if not val_res.is_valid:
        # FAIL-CLOSED: Return HTTP 422 without mutating state
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Manual assignment failed civil aviation safety validation",
                "violations": [v.model_dump() for v in val_res.violations],
            },
        )

    # Valid: Commit assignment atomically
    assignment = RosterAssignment(
        id=f"ASN-{flight.flight_number}",
        flight_number=flight.flight_number,
        captain_id=cpt.id,
        first_officer_id=fo.id,
        cabin_crew_ids=[c.id for c in cabin_crew],
        aircraft_tail=aircraft.tail_number,
        status=RosterStatus.ASSIGNED,
    )

    flight.aircraft_tail = aircraft.tail_number
    persist.save_assignment(assignment)
    persist.save_flight(flight)
    idx.commit_aircraft_reservation(aircraft.tail_number, flight)

    # Commit crew duty reservations
    lead_time = ce.profile.flight_crew_rules.report_lead_time_seconds
    release_buf = ce.profile.flight_crew_rules.release_buffer_seconds
    for member in [cpt, fo] + cabin_crew:
        duty_id = f"DUTY-MANUAL-{flight.flight_number}-{member.id}"
        idx.commit_crew_duty(
            member.id,
            flight.departure_utc - lead_time,
            flight.arrival_utc + release_buf,
            duty_id,
            {"flight_ids": [flight.flight_number]},
        )

    await ws_manager.broadcast("ROSTER_ASSIGNED", assignment.model_dump())
    return assignment


# ------------------------------------------------------------------------------
# 5. ADS Diagnostics & Laboratory Query Endpoint
# ------------------------------------------------------------------------------
@api_router.get("/constraints/inspector", tags=["Constraints"])
def inspect_constraints():
    """Inspect active regulatory parameters and civil aviation rules under profile nova_air_demo_v1."""
    profile = load_rule_profile()
    return profile


@api_router.get("/ads/diagnostics", tags=["ADS Laboratory"])
def get_ads_diagnostics(idx: ADSIndexManager = Depends(get_index_manager)):
    """Comprehensive health, tree balancing, and performance telemetry across all five ADS structures."""
    return idx.get_structure_diagnostics()


@api_router.post("/ads/laboratory/query", tags=["ADS Laboratory"])
def query_ads_laboratory(
    req: ADSLaboratoryQueryRequest,
    idx: ADSIndexManager = Depends(get_index_manager),
):
    """Execute live interactive query against custom ADS structures with precise timing."""
    t0 = time.perf_counter()
    stype = req.structure_type.lower()
    params = req.query_params

    if stype == "btree":
        start_u = int(params.get("start_utc", 0))
        end_u = int(params.get("end_utc", 2_000_000_000))
        items = idx.schedule_btree.range_query(start_u, end_u)
        elapsed_us = round((time.perf_counter() - t0) * 1_000_000, 2)
        return {
            "structure": "FlightScheduleBTree",
            "items_count": len(items),
            "elapsed_us": elapsed_us,
            "sample_keys": [str(k) for k, _ in items[:5]],
        }

    elif stype == "interval_tree":
        resource_id = str(params.get("resource_id", "VT-NVA")).upper()
        tree = idx.aircraft_intervals.get(resource_id) or idx.crew_intervals.get(resource_id)
        if not tree:
            raise HTTPException(status_code=404, detail=f"No interval tree found for resource '{resource_id}'")
        start_u = int(params.get("start_utc", 0))
        end_u = int(params.get("end_utc", 2_000_000_000))
        overlap = tree.find_first_overlap(start_u, end_u)
        elapsed_us = round((time.perf_counter() - t0) * 1_000_000, 2)
        return {
            "structure": "RBIntervalTree",
            "resource_id": resource_id,
            "has_overlap": overlap is not None,
            "overlap_id": overlap.interval_id if overlap else None,
            "elapsed_us": elapsed_us,
        }

    elif stype == "graph":
        origin = str(params.get("origin", "BOM")).upper()
        destination = str(params.get("destination", "DEL")).upper()
        dep_u = int(params.get("departure_utc", 1774936800))
        path = idx.connection_graph.find_shortest_positioning_path(origin, dep_u, destination)
        elapsed_us = round((time.perf_counter() - t0) * 1_000_000, 2)
        return {
            "structure": "FlightConnectionGraph",
            "path_found": path is not None,
            "hop_count": path.hop_count if path else 0,
            "elapsed_us": elapsed_us,
            "flight_legs": [f.flight_number for f in path.flights] if path else [],
        }

    elif stype == "hash_table":
        table_name = str(params.get("table", "crew")).lower()
        key = str(params.get("key", "CRW-CPT-01")).upper()
        tbl = idx.crew_by_id if table_name == "crew" else idx.flights_by_id
        val = tbl.get(key)
        elapsed_us = round((time.perf_counter() - t0) * 1_000_000, 2)
        return {
            "structure": "SeparateChainingHashTable",
            "table": table_name,
            "key": key,
            "found": val is not None,
            "elapsed_us": elapsed_us,
        }

    raise HTTPException(status_code=400, detail=f"Unsupported structure type '{stype}'")


# ------------------------------------------------------------------------------
# 6. System Reset Endpoint
# ------------------------------------------------------------------------------
@api_router.post("/system/reset-demo", tags=["System"])
async def reset_demo(
    req: ResetDemoRequest,
    idx: ADSIndexManager = Depends(get_index_manager),
    persist: PersistenceService = Depends(get_persistence_service),
):
    """Reset database and re-initialize in-memory ADS structures from demo or test profile."""
    profile = req.dataset_profile.lower()
    data_dir = "data/test" if profile == "test" else "data"

    persist.seed_from_csv(data_dir, profile=profile, clear_existing=True)
    persist.rebuild_indexes_from_db(idx)

    await ws_manager.broadcast("SYSTEM_RESET", {"profile": profile})
    return {
        "success": True,
        "message": f"Successfully reset system to '{profile}' dataset profile",
        "profile": profile,
        "flight_count": len(idx.flights_by_id),
        "crew_count": len(idx.crew_by_id),
        "aircraft_count": len(idx.aircraft_by_id),
    }
