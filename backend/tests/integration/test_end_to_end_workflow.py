"""AirCrewOps — Full-Stack End-to-End Operational Lifecycle Integration Tests.

Validates the full system operational lifecycle under rule profile `nova_air_demo_v1`:
1. Reset Demo (nova_air_demo_v1)
2. Generate Roster via Priority Queue
3. Verify B-Tree Chronological Departure Window Queries & Telemetry
4. Verify ADS Laboratory Telemetry & Complexity Probes
5. Execute Disruption Scenarios A, B, C, D, and E with Invariant Verification
6. Verify SQLite Cold Restart Invariant Equivalence
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.persistence_service import PersistenceService
from backend.app.services.index_manager import ADSIndexManager
from backend.app.rules.profile_loader import load_rule_profile


@pytest.fixture
def test_client():
    """Create test client with lifespan initialization."""
    with TestClient(app) as client:
        yield client


def test_full_lifecycle_e2e(test_client: TestClient):
    """Execute complete operational lifecycle from demo reset through disruption recovery and cold restart."""
    # 1. Reset Demo
    reset_res = test_client.post("/api/v1/system/reset-demo", json={"dataset_profile": "demo"})
    assert reset_res.status_code == 200, f"Reset demo failed: {reset_res.text}"
    reset_data = reset_res.json()
    assert reset_data["profile"] == "demo"
    assert reset_data["flight_count"] >= 36

    # Verify Dashboard Summary
    dash_res = test_client.get("/api/v1/dashboard/summary")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert dash_data["total_flights"] >= 36
    assert dash_data["total_aircraft"] >= 8
    assert dash_data["total_crew"] >= 40

    # 2. Generate Roster
    roster_res = test_client.post("/api/v1/roster/generate", json={"enforce_hard_rules": True})
    assert roster_res.status_code == 200, f"Roster generation failed: {roster_res.text}"
    roster_data = roster_res.json()
    assert roster_data["assigned_count"] > 0
    assert roster_data["assigned_count"] + roster_data["unassigned_count"] >= 36

    # 3. Verify B-Tree Chronological Range Search
    flights_res = test_client.get("/api/v1/flights")
    assert flights_res.status_code == 200
    all_flights = flights_res.json()["flights"]
    assert len(all_flights) >= 36

    # Pick a 12-hour window anchored on the first departure
    first_dep = all_flights[0]["departure_utc"]
    window_end = first_dep + 12 * 3600

    range_res = test_client.get(f"/api/v1/flights?start_utc={first_dep}&end_utc={window_end}")
    assert range_res.status_code == 200
    range_data = range_res.json()
    assert "b_tree_telemetry" in range_data
    telemetry = range_data["b_tree_telemetry"]
    assert telemetry["range_query_executed"] is True
    assert telemetry["tree_size"] >= 36
    assert telemetry["tree_height"] >= 1
    assert len(range_data["flights"]) > 0

    # Verify matching flights fall within window
    for f in range_data["flights"]:
        dep = f.get("effective_departure_utc") or f["departure_utc"]
        assert first_dep <= dep < window_end

    # 4. Verify ADS Laboratory Probes across all 4 structures
    # Probe 4.1: SeparateChainingHashTable
    ht_probe = test_client.post(
        "/api/v1/ads/laboratory/query",
        json={"structure_type": "hash_table", "query_params": {"key": "NV-101", "table": "flights"}},
    )
    assert ht_probe.status_code == 200
    assert ht_probe.json()["structure"] == "SeparateChainingHashTable"
    assert ht_probe.json()["found"] is True

    # Probe 4.2: FlightScheduleBTree
    btree_probe = test_client.post(
        "/api/v1/ads/laboratory/query",
        json={"structure_type": "btree", "query_params": {"start_utc": first_dep, "end_utc": window_end}},
    )
    assert btree_probe.status_code == 200
    assert btree_probe.json()["structure"] == "FlightScheduleBTree"
    assert btree_probe.json()["items_count"] == len(range_data["flights"])

    # Probe 4.3: RBIntervalTree
    interval_probe = test_client.post(
        "/api/v1/ads/laboratory/query",
        json={
            "structure_type": "interval_tree",
            "query_params": {"resource_id": "VT-NVA", "start_utc": first_dep, "end_utc": first_dep + 7200},
        },
    )
    assert interval_probe.status_code == 200
    assert interval_probe.json()["structure"] == "RBIntervalTree"

    # Probe 4.4: FlightConnectionGraph
    graph_probe = test_client.post(
        "/api/v1/ads/laboratory/query",
        json={
            "structure_type": "graph",
            "query_params": {"origin": "BOM", "destination": "DEL", "departure_utc": first_dep},
        },
    )
    assert graph_probe.status_code == 200
    assert graph_probe.json()["structure"] == "FlightConnectionGraph"

    # 5. Execute Disruption Scenarios A through E
    # Scenario A: PILOT_SICK
    res_a = test_client.post(
        "/api/v1/disruptions/execute",
        json={"scenario": "A", "params": {"pilot_id": "CRW-CPT-01", "flight_number": "NV-101"}},
    )
    assert res_a.status_code == 200
    assert res_a.json()["scenario"] == "A"
    assert res_a.json()["scenario_type"] == "PILOT_SICK"
    assert res_a.json()["success"] is True

    # Scenario B: AIRCRAFT_AOG
    res_b = test_client.post(
        "/api/v1/disruptions/execute",
        json={"scenario": "B", "params": {"tail_number": "VT-NVA", "flight_number": "NV-101"}},
    )
    assert res_b.status_code == 200
    assert res_b.json()["scenario"] == "B"
    assert res_b.json()["scenario_type"] == "AIRCRAFT_AOG"
    assert res_b.json()["success"] is True

    # Scenario C: FLIGHT_DELAY_CASCADE
    res_c = test_client.post(
        "/api/v1/disruptions/execute",
        json={"scenario": "C", "params": {"flight_number": "NV-101", "delay_seconds": 7200}},
    )
    assert res_c.status_code == 200
    assert res_c.json()["scenario"] == "C"
    assert res_c.json()["scenario_type"] == "FLIGHT_DELAY_CASCADE"
    assert res_c.json()["success"] is True

    # Scenario D: NO_LEGAL_SOLUTION (Fail-Closed)
    res_d = test_client.post(
        "/api/v1/disruptions/execute",
        json={"scenario": "D", "params": {"flight_number": "NV-105"}},
    )
    assert res_d.status_code == 200
    assert res_d.json()["scenario"] == "D"
    assert res_d.json()["scenario_type"] == "NO_LEGAL_SOLUTION"
    assert res_d.json()["success"] is True
    assert "NV-105" in res_d.json()["unrecovered_flights"]

    # Scenario E: INVALID_MANUAL_OVERRIDE (Rollback)
    res_e = test_client.post(
        "/api/v1/disruptions/execute",
        json={
            "scenario": "E",
            "params": {"flight_number": "NV-101", "captain_id": "CRW-FO-01", "first_officer_id": "CRW-CPT-01"},
        },
    )
    assert res_e.status_code == 200
    assert res_e.json()["scenario"] == "E"
    assert res_e.json()["scenario_type"] == "INVALID_MANUAL_OVERRIDE"
    assert res_e.json()["state_preserved"] is True
    assert len(res_e.json()["violations"]) > 0

    # Invariant Verification across all in-memory structures
    index_mgr: ADSIndexManager = app.state.index_manager
    assert index_mgr.verify_all_invariants() is True

    # 6. Verify SQLite Cold Restart Invariant Equivalence
    # Rebuild indexes on a fresh index manager directly from the live persistence database
    persist: PersistenceService = app.state.persistence_service
    rebuilt_mgr = ADSIndexManager()
    persist.rebuild_indexes_from_db(rebuilt_mgr)

    # Assert invariant equivalence
    assert rebuilt_mgr.verify_all_invariants() is True
    assert len(rebuilt_mgr.schedule_btree) == len(index_mgr.schedule_btree)
    assert len(rebuilt_mgr.flights_by_id) == len(index_mgr.flights_by_id)
    assert len(rebuilt_mgr.aircraft_by_id) == len(index_mgr.aircraft_by_id)
    assert len(rebuilt_mgr.crew_by_id) == len(index_mgr.crew_by_id)
