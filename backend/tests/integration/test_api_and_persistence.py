"""Integration tests for FastAPI endpoints, SQLite persistence, and WebSocket broadcasting.

Verifies:
1. Cold-restart index rebuild equivalence between persistent SQLite and in-memory ADS structures.
2. HTTP 422 atomic rollback on invalid manual assignments without mutating SQLite or memory.
3. Flight delay B-Tree key update and Connection Graph synchronization.
4. WebSocket real-time operational event delivery.
5. End-to-end REST routes under /api/v1 (health, summary, flights, crew, aircraft, roster, laboratory).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.domain import FlightLeg, RosterAssignment, RosterStatus
from backend.app.services.index_manager import ADSIndexManager
from backend.app.services.persistence_service import PersistenceService

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@pytest.fixture
def client(tmp_path):
    """Provide a TestClient with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_aircrewops.db"
    app.state.db_path = str(test_db)

    # Use TestClient as context manager to invoke lifespan (startup and shutdown)
    with TestClient(app) as test_client:
        # Seed test profile for fast tests
        test_client.post("/api/v1/system/reset-demo", json={"dataset_profile": "test"})
        yield test_client


def test_cold_restart_index_rebuild_equivalence(tmp_path):
    """Verify that a cold restart rebuilds identical, invariant-valid ADS data structures from SQLite."""
    db_file = tmp_path / "cold_restart.db"
    persist = PersistenceService(db_path=db_file)
    persist.seed_from_csv(ROOT_DIR / "data" / "test", profile="test")

    # First in-memory build
    idx1 = ADSIndexManager()
    persist.rebuild_indexes_from_db(idx1)
    assert idx1.verify_all_invariants() is True

    # Simulate process termination & cold restart into fresh ADSIndexManager
    idx2 = ADSIndexManager()
    persist.rebuild_indexes_from_db(idx2)
    assert idx2.verify_all_invariants() is True

    # Check structural and semantic equivalence
    assert len(idx1.flights_by_id) == len(idx2.flights_by_id) == 14
    assert len(idx1.crew_by_id) == len(idx2.crew_by_id) == 22
    assert len(idx1.aircraft_by_id) == len(idx2.aircraft_by_id) == 4
    assert len(idx1.schedule_btree) == len(idx2.schedule_btree) == 14

    # Exact B-Tree ordered flight key equivalence
    btree_keys_1 = [k for k, _ in idx1.schedule_btree.inorder_traversal()]
    btree_keys_2 = [k for k, _ in idx2.schedule_btree.inorder_traversal()]
    assert btree_keys_1 == btree_keys_2

    # Graph vertices and edges equivalence
    assert len(idx1.connection_graph) == len(idx2.connection_graph) == 14
    assert len(idx1.connection_graph.adj) == len(idx2.connection_graph.adj)


def test_dashboard_summary_and_health(client):
    """Verify GET /api/v1/health and GET /api/v1/dashboard/summary responses."""
    # Health probe
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    h_data = health_resp.json()
    assert h_data["status"] == "ok"
    assert h_data["airline"] == "Nova Air"
    assert h_data["is_educational_simulator"] is True

    # Summary
    sum_resp = client.get("/api/v1/dashboard/summary")
    assert sum_resp.status_code == 200
    s_data = sum_resp.json()
    assert s_data["airline"] == "Nova Air"
    assert s_data["active_rule_profile"] == "nova_air_demo_v1"
    assert s_data["is_educational_simulator"] is True
    assert s_data["total_flights"] == 14
    assert s_data["total_crew"] == 22
    assert s_data["total_aircraft"] == 4
    assert s_data["ads_telemetry"]["invariants_verified"] is True


def test_b_tree_flight_search_window(client):
    """Verify B-Tree time-window range query via GET /api/v1/flights."""
    # Full schedule
    resp_all = client.get("/api/v1/flights")
    assert resp_all.status_code == 200
    assert resp_all.json()["count"] == 14

    # Window query: between 1774936800 and 1774950000
    start_u = 1774936800
    end_u = 1774950000
    resp_win = client.get(f"/api/v1/flights?start_utc={start_u}&end_utc={end_u}")
    assert resp_win.status_code == 200
    w_data = resp_win.json()
    assert w_data["b_tree_telemetry"]["range_query_executed"] is True
    assert w_data["b_tree_telemetry"]["query_duration_us"] >= 0.0
    for fl in w_data["flights"]:
        assert start_u <= fl["departure_utc"] <= end_u


def test_http_422_atomic_rollback_on_invalid_manual_assignment(client):
    """Verify HTTP 422 with RuleViolation details on invalid manual assignment without mutating state."""
    idx = app.state.index_manager
    persist = app.state.persistence_service

    # Snapshot state before attempt
    cpt_tree_len_before = len(idx.crew_intervals["CRW-CPT-04"])
    ac_tree_len_before = len(idx.aircraft_intervals["VT-NVA"])

    # CRW-CPT-04 only has A320 rating; try to assign to ATR72 flight NV-107
    invalid_payload = {
        "flight_number": "NV-107",  # ATR72 leg
        "captain_id": "CRW-CPT-04",  # Lacks ATR72 rating
        "first_officer_id": "CRW-FO-01",
        "cabin_crew_ids": ["CRW-CAB-01", "CRW-CAB-02"],
        "aircraft_tail": "VT-NVE",
    }

    resp = client.post("/api/v1/roster/manual-assign", json=invalid_payload)
    assert resp.status_code == 422
    data = resp.json()["detail"]
    assert "violations" in data
    assert any(v["rule_id"] == "CREW-QUAL-01" for v in data["violations"])

    # Verify atomic rollback: no state changes in SQLite or in-memory interval trees
    assert persist.get_assignment("NV-107") is None
    assert len(idx.crew_intervals["CRW-CPT-04"]) == cpt_tree_len_before
    assert len(idx.aircraft_intervals["VT-NVA"]) == ac_tree_len_before
    assert idx.verify_all_invariants() is True


def test_flight_delay_btree_and_graph_synchronization(client):
    """Verify flight reschedule PATCH updates B-Tree key, Connection Graph, and SQLite atomically."""
    idx = app.state.index_manager
    persist = app.state.persistence_service

    fl = idx.flights_by_id.get("NV-101")
    assert fl is not None
    old_dep = fl.departure_utc
    new_dep = old_dep + 3600
    new_arr = fl.arrival_utc + 3600

    resp = client.patch(
        "/api/v1/flights/NV-101",
        json={"departure_utc": new_dep, "arrival_utc": new_arr},
    )
    assert resp.status_code == 200
    p_data = resp.json()
    assert p_data["departure_utc"] == new_dep
    assert p_data["arrival_utc"] == new_arr

    # 1. B-Tree atomic key verification
    assert idx.schedule_btree.search((old_dep, "NV-101")) is None
    assert idx.schedule_btree.search((new_dep, "NV-101")) is not None

    # 2. Graph vertex verification
    assert idx.connection_graph.vertices["NV-101"].departure_utc == new_dep

    # 3. SQLite verification
    sql_fl = persist.get_flight("NV-101")
    assert sql_fl is not None
    assert sql_fl.departure_utc == new_dep

    assert idx.verify_all_invariants() is True


def test_websocket_event_delivery(client):
    """Verify live event broadcasting over WebSocket /ws/events."""
    with client.websocket_connect("/ws/events") as ws:
        # Create a new flight to trigger FLIGHT_CREATED broadcast
        new_fl_payload = {
            "flight_number": "NV-999",
            "origin": "BOM",
            "destination": "DEL",
            "departure_utc": 1774980000,
            "arrival_utc": 1774988000,
            "aircraft_tail": "VT-NVA",
            "required_aircraft_type": "A320",
        }
        create_resp = client.post("/api/v1/flights", json=new_fl_payload)
        assert create_resp.status_code == 201

        # Receive WebSocket message
        msg = ws.receive_json()
        assert msg["event"] == "FLIGHT_CREATED"
        assert msg["data"]["flight_number"] == "NV-999"


def test_ads_laboratory_interactive_queries(client):
    """Verify POST /api/v1/ads/laboratory/query for all four structure types."""
    # 1. B-Tree query
    b_resp = client.post(
        "/api/v1/ads/laboratory/query",
        json={"structure_type": "btree", "query_params": {"start_utc": 1774936800, "end_utc": 1774960000}},
    )
    assert b_resp.status_code == 200
    assert b_resp.json()["structure"] == "FlightScheduleBTree"
    assert b_resp.json()["items_count"] > 0

    # 2. Graph query
    g_resp = client.post(
        "/api/v1/ads/laboratory/query",
        json={"structure_type": "graph", "query_params": {"origin": "BOM", "destination": "DEL", "departure_utc": 1774936800}},
    )
    assert g_resp.status_code == 200
    assert g_resp.json()["structure"] == "FlightConnectionGraph"

    # 3. Hash table query
    h_resp = client.post(
        "/api/v1/ads/laboratory/query",
        json={"structure_type": "hash_table", "query_params": {"table": "crew", "key": "CRW-CPT-01"}},
    )
    assert h_resp.status_code == 200
    assert h_resp.json()["found"] is True

    # 4. Interval tree query
    i_resp = client.post(
        "/api/v1/ads/laboratory/query",
        json={"structure_type": "interval_tree", "query_params": {"resource_id": "VT-NVA", "start_utc": 1774980000, "end_utc": 1774990000}},
    )
    assert i_resp.status_code == 200
    assert i_resp.json()["structure"] == "RBIntervalTree"


def test_crew_and_aircraft_endpoints(client):
    """Verify GET /api/v1/crew, crew schedule, GET /api/v1/aircraft, and rotation endpoints."""
    # List crew
    c_resp = client.get("/api/v1/crew?role=CAPTAIN")
    assert c_resp.status_code == 200
    assert len(c_resp.json()["crew"]) > 0

    # Crew schedule
    s_resp = client.get("/api/v1/crew/CRW-CPT-01/schedule")
    assert s_resp.status_code == 200
    assert s_resp.json()["crew_id"] == "CRW-CPT-01"

    # List aircraft
    a_resp = client.get("/api/v1/aircraft?aircraft_type=A320")
    assert a_resp.status_code == 200
    assert len(a_resp.json()["aircraft"]) > 0

    # Aircraft rotation
    r_resp = client.get("/api/v1/aircraft/VT-NVA/rotation")
    assert r_resp.status_code == 200
    assert r_resp.json()["tail_number"] == "VT-NVA"
    assert "intervals" in r_resp.json()
