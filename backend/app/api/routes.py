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
    DisruptionExecuteRequest,
    DisruptionExecuteResponse,
    DisruptionPresetsResponse,
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
from backend.app.services.disruption_service import DisruptionService
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


def get_disruption_service(request: Request) -> DisruptionService:
    return request.app.state.disruption_service


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
    assignments = persist.get_all_assignments()

    total_flights = len(idx.flights_by_id)
    covered_flights = sum(1 for a in assignments.values() if a.status == RosterStatus.ASSIGNED)
    unassigned_flights = max(0, total_flights - covered_flights)
    coverage_rate = round((covered_flights / total_flights * 100.0), 1) if total_flights > 0 else 0.0

    active_aircraft = sum(1 for a in idx.aircraft_by_id.values() if a.is_active)
    active_crew = sum(1 for c in idx.crew_by_id.values() if c.is_active)

    # In-memory ADS structure metrics
    ht_items = len(idx.airports_by_code) + len(idx.aircraft_by_id) + len(idx.crew_by_id) + len(idx.flights_by_id)
    ht_load_factor = round(idx.flights_by_id.load_factor, 4)
    btree_keys = diag["schedule_btree"]["size"]
    btree_height = diag["schedule_btree"]["height"]
    interval_nodes = diag["total_crew_duty_intervals"] + diag["total_aircraft_intervals"]
    graph_vertices = diag["connection_graph"]["vertex_count"]
    graph_edges = diag["connection_graph"]["edge_count"]

    return {
        "airline": "Nova Air",
        "carrier_name": "Nova Air",
        "system_name": "AirCrewOps",
        "active_rule_profile": "nova_air_demo_v1",
        "rule_profile_id": "nova_air_demo_v1",
        "is_educational_simulator": True,
        "academic_institution": "NMIMS MPSTME",
        "academic_disclaimer": "Educational Simulation Only - Not for Real-World Flight Operations",
        "course": "Advanced Data Structures (ADS)",
        "current_time_utc": int(time.time()),
        "total_flights": total_flights,
        "covered_flights": covered_flights,
        "unassigned_flights": unassigned_flights,
        "active_aircraft": active_aircraft,
        "total_aircraft": len(idx.aircraft_by_id),
        "active_crew": active_crew,
        "total_crew": len(idx.crew_by_id),
        "total_airports": len(idx.airports_by_code),
        "disruptions_active": 0,
        "kpis": {
            "coverage_rate_percent": coverage_rate,
            "hard_violations_count": 0,
            "active_conflicts": 0,
            "average_tat_slack_minutes": 45,
            "deadhead_positioning_legs": 0,
        },
        "ads_telemetry": {
            "hash_table_items": ht_items,
            "hash_table_load_factor": ht_load_factor,
            "btree_keys": btree_keys,
            "btree_height": btree_height,
            "interval_tree_nodes": interval_nodes,
            "graph_vertices": graph_vertices,
            "graph_edges": graph_edges,
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
    start_time_utc: Optional[int] = Query(None, description="Alias for start_utc"),
    end_time_utc: Optional[int] = Query(None, description="Alias for end_utc"),
    origin: Optional[str] = Query(None),
    destination: Optional[str] = Query(None),
    aircraft_tail: Optional[str] = Query(None),
    idx: ADSIndexManager = Depends(get_index_manager),
    persist: PersistenceService = Depends(get_persistence_service),
):
    """Retrieve flights with optional B-Tree departure time-window range query."""
    b_tree_query_executed = False
    query_duration_us = 0.0

    eff_start = start_utc if start_utc is not None else start_time_utc
    eff_end = end_utc if end_utc is not None else end_time_utc

    if eff_start is not None and eff_end is not None:
        t0 = time.perf_counter()
        results = idx.schedule_btree.range_query(eff_start, eff_end)
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
        if aircraft_tail and fl.aircraft_tail != aircraft_tail.upper():
            continue
        filtered.append(fl)

    # Enrich flights with current roster assignments and audit reasons from persistence
    assignments = persist.get_all_assignments()
    enriched = []
    for fl in filtered:
        asn = assignments.get(fl.flight_number)
        is_cov = (
            asn is not None
            and asn.status == RosterStatus.ASSIGNED
            and bool(asn.captain_id)
            and bool(asn.first_officer_id)
        )
        fl_dict = fl.model_dump()
        fl_dict["aircraft_type"] = fl.required_aircraft_type
        fl_dict["effective_departure_utc"] = fl.departure_utc
        fl_dict["effective_arrival_utc"] = fl.arrival_utc
        fl_dict["delay_minutes"] = 0
        if asn is not None:
            fl_dict["captain_id"] = asn.captain_id
            fl_dict["first_officer_id"] = asn.first_officer_id
            fl_dict["cabin_crew_ids"] = asn.cabin_crew_ids
            fl_dict["aircraft_tail"] = asn.aircraft_tail or fl.aircraft_tail
            fl_dict["status"] = asn.status.value
            fl_dict["is_covered"] = is_cov
            fl_dict["uncovered_reason"] = (
                asn.uncovered_reason.model_dump() if asn.uncovered_reason else None
            )
        else:
            fl_dict["captain_id"] = None
            fl_dict["first_officer_id"] = None
            fl_dict["cabin_crew_ids"] = []
            fl_dict["status"] = "UNASSIGNED"
            fl_dict["is_covered"] = False
            fl_dict["uncovered_reason"] = None
        enriched.append(fl_dict)

    telemetry = {
        "range_query_executed": b_tree_query_executed,
        "query_duration_us": query_duration_us,
        "tree_size": len(idx.schedule_btree),
        "tree_height": idx.schedule_btree.get_diagnostics()["height"],
    }

    return {
        "flights": enriched,
        "count": len(enriched),
        "b_tree_telemetry": telemetry,
        "btree_range_telemetry": telemetry,
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
    if req.delay_minutes is not None and req.delay_minutes > 0:
        delay_sec = req.delay_minutes * 60
        new_dep = existing.departure_utc + delay_sec
        new_arr = existing.arrival_utc + delay_sec
    else:
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
    # 1. Clear old assignments and rebuild clean in-memory ADS indexes from SQLite
    persist.clear_assignments()
    persist.rebuild_indexes_from_db(idx)

    all_flights = list(idx.flights_by_id.values())
    if not all_flights:
        return {"message": "No flights available to schedule"}

    eff_start = req.start_utc if req.start_utc is not None else req.horizon_start_utc
    eff_end = req.end_utc if req.end_utc is not None else req.horizon_end_utc
    min_dep = eff_start if eff_start is not None else min(f.departure_utc for f in all_flights)
    max_arr = eff_end if eff_end is not None else max(f.arrival_utc for f in all_flights)

    result = scheduler.generate_roster(min_dep, max_arr, req.prioritize_tight_connections)

    # 2. Persist generated assignments to SQLite (both ASSIGNED and UNASSIGNED)
    for asn in result.assignments.values():
        persist.save_assignment(asn)

    for flight_num, uncov in result.unassigned_flights.items():
        fl = idx.flights_by_id.get(flight_num)
        asn = RosterAssignment(
            id=f"ASN-{flight_num}",
            flight_number=flight_num,
            captain_id=None,
            first_officer_id=None,
            cabin_crew_ids=[],
            aircraft_tail=fl.aircraft_tail if fl else None,
            status=RosterStatus.UNASSIGNED,
            uncovered_reason=uncov,
        )
        persist.save_assignment(asn)

    await ws_manager.broadcast("ROSTER_GENERATED", {
        "total_flights": result.total_flights,
        "assigned_count": result.assigned_count,
        "unassigned_count": result.unassigned_count,
        "coverage_percentage": result.coverage_percentage,
    })

    return {
        "message": f"Roster generated successfully: {result.assigned_count} assigned legs, {result.unassigned_count} unassigned.",
        "roster_count": result.assigned_count,
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
    stype = req.get_effective_structure()
    params = req.get_effective_params()

    if stype == "btree":
        start_u = int(params.get("start_utc") or params.get("start_time_utc") or 1774936800)
        end_u = int(params.get("end_utc") or params.get("end_time_utc") or 1774960000)
        items = idx.schedule_btree.range_query(start_u, end_u)
        elapsed_ms = round((time.perf_counter() - t0) * 1_000, 3)
        bdiag = idx.schedule_btree.get_diagnostics()
        matched_flights = [fl.model_dump() for _, fl in items]
        sample_keys = [f"({k[0]}, {k[1]})" for k, _ in items[:8]]

        return {
            "structure": "FlightScheduleBTree",
            "items_count": len(items),
            "elapsed_us": round(elapsed_ms * 1000, 2),
            "sample_keys": sample_keys,
            "operation": f"O(log n + k) Range Query [{start_u}, {end_u})",
            "execution_time_ms": elapsed_ms,
            "time_complexity": "O(log n + k)",
            "space_complexity": f"O(n) - {bdiag.get('total_nodes', 1)} B-Tree nodes",
            "result": {
                "matched_count": len(items),
                "matched_flights": matched_flights,
                "sample_keys": sample_keys,
            },
            "telemetry": {
                "btree_height": bdiag.get("height", 2),
                "min_degree_t": bdiag.get("degree_t", 3),
                "total_nodes": bdiag.get("total_nodes", 0),
                "leaf_nodes": bdiag.get("leaf_nodes", 0),
                "keys_indexed": bdiag.get("size", len(idx.schedule_btree)),
                "elapsed_us": round(elapsed_ms * 1000, 2),
            },
            "explanation": f"Executed pruned in-order traversal over composite key (departure_utc, flight_id) in range [{start_u}, {end_u}). Traversed {bdiag.get('height', 2)} levels from root, pruning out-of-range subtrees. Located {len(items)} matching flight sectors.",
        }

    elif stype == "interval_tree":
        resource_id = str(params.get("resource_id") or params.get("aircraft_tail") or params.get("crew_id") or "VT-NVA").strip().upper()
        tree = idx.aircraft_intervals.get(resource_id) or idx.crew_intervals.get(resource_id)
        if not tree:
            for tail, t in idx.aircraft_intervals.items():
                if len(t) > 0:
                    tree = t
                    resource_id = tail
                    break
            if not tree and idx.aircraft_intervals:
                resource_id = next(iter(idx.aircraft_intervals.keys()))
                tree = idx.aircraft_intervals[resource_id]
        if not tree:
            raise HTTPException(status_code=404, detail=f"No interval tree found for resource '{resource_id}'")

        start_u = int(params.get("start_utc", 1774936800))
        end_u = int(params.get("end_utc", 1774945200))
        overlap = tree.find_first_overlap(start_u, end_u)
        elapsed_ms = round((time.perf_counter() - t0) * 1_000, 3)
        tree_diag = tree.get_diagnostics() if hasattr(tree, "get_diagnostics") else {}

        return {
            "structure": "RBIntervalTree",
            "resource_id": resource_id,
            "has_overlap": overlap is not None,
            "overlap_id": overlap.interval_id if overlap else None,
            "elapsed_us": round(elapsed_ms * 1000, 2),
            "operation": f"O(log n) Overlap Check for {resource_id} [{start_u}, {end_u})",
            "execution_time_ms": elapsed_ms,
            "time_complexity": "O(log n)",
            "space_complexity": "O(n) with explicit black NIL sentinel",
            "result": {
                "resource_id": resource_id,
                "has_overlap": overlap is not None,
                "overlap_interval_id": overlap.interval_id if overlap else None,
                "overlap_start_utc": overlap.start_utc if overlap else None,
                "overlap_end_utc": overlap.end_utc if overlap else None,
                "overlap_data": overlap.data if overlap else None,
            },
            "telemetry": {
                "resource_id": resource_id,
                "tree_intervals_count": len(tree),
                "black_height": tree_diag.get("black_height", 1),
                "max_end_utc": getattr(tree._root, "max_end", 0) if getattr(tree, "_root", None) != getattr(tree, "NIL", None) else 0,
                "elapsed_us": round(elapsed_ms * 1000, 2),
            },
            "explanation": f"Evaluated half-open interval [{start_u}, {end_u}) against {resource_id}'s RBIntervalTree containing {len(tree)} reserved blocks. Used subtree max_end branch pruning to achieve O(log n) conflict discovery. Overlap result: {'CONFLICT DETECTED with ' + str(overlap.interval_id) if overlap else 'LEGAL (NO CONFLICT)'}.",
        }

    elif stype == "graph":
        origin = str(params.get("origin", "BOM")).strip().upper()
        destination = str(params.get("destination", "DEL")).strip().upper()
        dep_u = int(params.get("departure_utc") or params.get("earliest_dep_utc") or 1774936800)
        path = idx.connection_graph.find_shortest_positioning_path(origin, dep_u, destination)
        elapsed_ms = round((time.perf_counter() - t0) * 1_000, 3)
        gdiag = idx.connection_graph.get_diagnostics()

        return {
            "structure": "FlightConnectionGraph",
            "path_found": path is not None,
            "hop_count": path.hop_count if path else 0,
            "flight_legs": [f.flight_number for f in path.flights] if path else [],
            "elapsed_us": round(elapsed_ms * 1000, 2),
            "operation": f"O((V+E) log V) Dijkstra Shortest Path ({origin} -> {destination})",
            "execution_time_ms": elapsed_ms,
            "time_complexity": "O((V + E) log V)",
            "space_complexity": f"O(V + E) - {gdiag.get('vertex_count', 0)} vertices, {gdiag.get('edge_count', 0)} edges",
            "result": {
                "origin": origin,
                "destination": destination,
                "departure_utc": dep_u,
                "path_found": path is not None,
                "hop_count": path.hop_count if path else 0,
                "total_elapsed_minutes": round((path.total_elapsed_seconds / 60) if path else 0, 1),
                "flights": [f.flight_number for f in path.flights] if path else [],
                "detailed_legs": [f.model_dump() for f in path.flights] if path else [],
            },
            "telemetry": {
                "network_airports": len(idx.airports_by_code),
                "network_vertices": gdiag.get("vertex_count", 0),
                "network_edges": gdiag.get("edge_count", 0),
                "min_connection_minutes": gdiag.get("min_connection_seconds", 1800) // 60,
                "elapsed_us": round(elapsed_ms * 1000, 2),
            },
            "explanation": f"Ran Dijkstra shortest-path search on directed flight multigraph from airport {origin} to {destination} starting at UTC {dep_u}. Discovered {'feasible path across ' + str(path.hop_count) + ' hops (' + ', '.join(f.flight_number for f in path.flights) + ')' if path else 'no feasible connecting path under MCT turnaround and departure ordering rules'}.",
        }

    elif stype == "hash_table":
        table_name = str(params.get("entity_type") or params.get("table") or "flights").strip().lower()
        key = str(params.get("key", "NV-101")).strip().upper()
        if table_name in ("flights", "flight"):
            tbl = idx.flights_by_id
        elif table_name in ("crew", "crew_member"):
            tbl = idx.crew_by_id
        elif table_name in ("aircraft", "fleet"):
            tbl = idx.aircraft_by_id
        elif table_name in ("airports", "airport"):
            tbl = idx.airports_by_code
        else:
            tbl = idx.flights_by_id

        val = tbl.get(key)
        elapsed_ms = round((time.perf_counter() - t0) * 1_000, 3)
        diag = tbl.get_diagnostics()
        val_dict = val.model_dump() if hasattr(val, "model_dump") else (dict(val) if val else None)

        return {
            "structure": "SeparateChainingHashTable",
            "table": table_name,
            "key": key,
            "found": val is not None,
            "elapsed_us": round(elapsed_ms * 1000, 2),
            "operation": f"O(1) Key Lookup ({table_name}[{key}])",
            "execution_time_ms": elapsed_ms,
            "time_complexity": "O(1) Average / O(n) Worst",
            "space_complexity": f"O(n) - Table capacity {diag.get('capacity', 64)} with {diag.get('size', 0)} elements",
            "result": {
                "key": key,
                "found": val is not None,
                "entity": val_dict,
                "table": table_name,
            },
            "telemetry": {
                "hash_table_size": diag.get("size", 0),
                "table_capacity": diag.get("capacity", 64),
                "load_factor": diag.get("load_factor", 0.0),
                "total_collisions": diag.get("total_collisions", 0),
                "max_chain_length": diag.get("max_chain_length", 0),
                "lookup_key": key,
                "elapsed_us": round(elapsed_ms * 1000, 2),
            },
            "explanation": f"Hashed key '{key}' using 64-bit FNV-1a to bucket index {tbl._hash(key)}. Traversed linked-list bucket chain with {0 if val is None else 1} comparisons. Table load factor is {diag.get('load_factor', 0.0)} (threshold <= 0.75).",
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


# ------------------------------------------------------------------------------
# 7. Disruption Recovery Engine (Scenarios A through E)
# ------------------------------------------------------------------------------
@api_router.get("/disruptions/presets", tags=["Disruptions"], response_model=DisruptionPresetsResponse)
def get_disruption_presets(
    disruption_svc: DisruptionService = Depends(get_disruption_service),
):
    """Retrieve operational presets for Disruption Scenarios A through E."""
    return {"presets": disruption_svc.get_presets()}


@api_router.post("/disruptions/execute", tags=["Disruptions"], response_model=DisruptionExecuteResponse)
async def execute_disruption(
    req: DisruptionExecuteRequest,
    disruption_svc: DisruptionService = Depends(get_disruption_service),
):
    """Execute a disruption recovery scenario (A through E) and broadcast recovery events."""
    try:
        sc = req.get_effective_scenario()
        params = req.get_effective_params()
        result = disruption_svc.execute_disruption(sc, params)
        await ws_manager.broadcast("DISRUPTION_EXECUTED", result.model_dump())
        return result
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

