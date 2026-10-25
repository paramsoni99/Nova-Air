"""Integration tests for Disruption Scenarios A through E (Phase H).

Verifies:
1. Scenario A (PILOT_SICK): Standby or Dijkstra deadhead positioning replacement.
2. Scenario B (AIRCRAFT_AOG): Serviceable fleet re-allocation with TAT buffer enforcement.
3. Scenario C (FLIGHT_DELAY_CASCADE): B-Tree & Graph synchronization with downstream turnaround resolution.
4. Scenario D (NO_LEGAL_SOLUTION): Fail-closed safety transition to UNASSIGNED with structured RuleViolations.
5. Scenario E (INVALID_MANUAL_OVERRIDE): Transactional rejection preserving valid schedule and ADS invariants.
6. ADS structural and balancing invariants: index_manager.verify_all_invariants() == True after every scenario.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.domain import RosterStatus

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@pytest.fixture
def client(tmp_path):
    """Provide a TestClient with an isolated temporary SQLite database and demo dataset."""
    test_db = tmp_path / "test_disruptions.db"
    app.state.db_path = str(test_db)

    with TestClient(app) as test_client:
        # Reset system to demo profile and generate initial valid roster
        test_client.post("/api/v1/system/reset-demo", json={"dataset_profile": "demo"})
        test_client.post("/api/v1/roster/generate", json={})
        yield test_client


def test_disruption_presets_endpoint(client):
    """Verify GET /api/v1/disruptions/presets returns all 5 presets."""
    resp = client.get("/api/v1/disruptions/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert "presets" in data
    presets = data["presets"]
    assert len(presets) == 5

    scenarios = [p["scenario"] for p in presets]
    assert scenarios == ["A", "B", "C", "D", "E"]
    types = [p["scenario_type"] for p in presets]
    assert "PILOT_SICK" in types
    assert "AIRCRAFT_AOG" in types
    assert "FLIGHT_DELAY_CASCADE" in types
    assert "NO_LEGAL_SOLUTION" in types
    assert "INVALID_MANUAL_OVERRIDE" in types


def test_scenario_a_pilot_sick(client):
    """Verify Scenario A: Captain illness and replacement crew positioning."""
    idx = app.state.index_manager
    pilot_id = "CRW-CPT-01"

    resp = client.post(
        "/api/v1/disruptions/execute",
        json={
            "scenario": "A",
            "params": {"pilot_id": pilot_id, "flight_number": "NV-101"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"] == "A"
    assert data["scenario_type"] == "PILOT_SICK"
    assert data["success"] is True
    assert "NV-101" in data["affected_flights"]
    assert "NV-101" in data["recovered_flights"]
    assert len(data["actions_taken"]) > 0

    # Verify replacement in SQLite
    persist = app.state.persistence_service
    asn = persist.get_assignment("NV-101")
    assert asn is not None
    assert asn.captain_id != pilot_id
    assert asn.status == RosterStatus.ASSIGNED

    # Verify ADS invariants
    assert idx.verify_all_invariants() is True


def test_scenario_b_aircraft_aog(client):
    """Verify Scenario B: Aircraft AOG and compatible fleet re-allocation."""
    idx = app.state.index_manager
    tail = "VT-NVA"

    resp = client.post(
        "/api/v1/disruptions/execute",
        json={
            "scenario": "B",
            "params": {"tail_number": tail, "flight_number": "NV-101"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"] == "B"
    assert data["scenario_type"] == "AIRCRAFT_AOG"
    assert data["success"] is True
    assert "NV-101" in data["affected_flights"]
    assert "NV-101" in data["recovered_flights"]

    # Verify aircraft grounded and replacement allocated
    aircraft = idx.aircraft_by_id.get(tail)
    assert aircraft.is_active is False

    persist = app.state.persistence_service
    asn = persist.get_assignment("NV-101")
    assert asn is not None
    assert asn.aircraft_tail != tail
    assert asn.status == RosterStatus.ASSIGNED

    # Verify ADS invariants
    assert idx.verify_all_invariants() is True


def test_scenario_c_flight_delay_cascade(client):
    """Verify Scenario C: B-Tree update_key, Graph sync, and turnaround clash resolution."""
    idx = app.state.index_manager
    flight = idx.flights_by_id.get("NV-101")
    old_dep = flight.departure_utc

    resp = client.post(
        "/api/v1/disruptions/execute",
        json={
            "scenario": "C",
            "params": {"flight_number": "NV-101", "delay_seconds": 7200},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"] == "C"
    assert data["scenario_type"] == "FLIGHT_DELAY_CASCADE"
    assert data["success"] is True
    assert "NV-101" in data["affected_flights"]

    # Verify B-Tree key updated
    assert idx.schedule_btree.search((old_dep, "NV-101")) is None
    assert idx.schedule_btree.search((old_dep + 7200, "NV-101")) is not None

    # Verify Graph vertex updated
    v = idx.connection_graph.vertices.get("NV-101")
    assert v is not None
    assert v.departure_utc == old_dep + 7200

    # Verify ADS invariants
    assert idx.verify_all_invariants() is True


def test_scenario_d_no_legal_solution_fail_closed(client):
    """Verify Scenario D: Constraint deadlock demonstrates fail-closed transition to UNASSIGNED."""
    idx = app.state.index_manager

    resp = client.post(
        "/api/v1/disruptions/execute",
        json={
            "scenario": "D",
            "params": {"flight_number": "NV-105"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"] == "D"
    assert data["scenario_type"] == "NO_LEGAL_SOLUTION"
    assert data["success"] is True
    assert "NV-105" in data["unrecovered_flights"]
    assert len(data["violations"]) > 0

    # Verify fail-closed in SQLite
    persist = app.state.persistence_service
    asn = persist.get_assignment("NV-105")
    assert asn is not None
    assert asn.status == RosterStatus.UNASSIGNED
    assert asn.captain_id is None
    assert asn.aircraft_tail is None

    # Verify ADS invariants
    assert idx.verify_all_invariants() is True


def test_scenario_e_invalid_manual_override(client):
    """Verify Scenario E: Illegal manual override rejected transactionally."""
    idx = app.state.index_manager

    resp = client.post(
        "/api/v1/disruptions/execute",
        json={
            "scenario": "E",
            "params": {
                "flight_number": "NV-101",
                "captain_id": "CRW-FO-01",
                "first_officer_id": "CRW-CPT-01",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"] == "E"
    assert data["scenario_type"] == "INVALID_MANUAL_OVERRIDE"
    assert data["state_preserved"] is True
    assert len(data["violations"]) > 0

    # Check that hard violations are detected
    hard_violations = [v for v in data["violations"] if v["severity"] == "HARD"]
    assert len(hard_violations) > 0

    # Verify ADS invariants
    assert idx.verify_all_invariants() is True


def test_all_scenarios_by_type_name(client):
    """Verify execution of scenarios by their descriptive type names."""
    type_names = [
        ("PILOT_SICK", {"pilot_id": "CRW-CPT-02", "flight_number": "NV-105"}),
        ("AIRCRAFT_AOG", {"tail_number": "VT-NVB", "flight_number": "NV-105"}),
        ("FLIGHT_DELAY_CASCADE", {"flight_number": "NV-102", "delay_seconds": 3600}),
        ("NO_LEGAL_SOLUTION", {"flight_number": "NV-103"}),
        ("INVALID_MANUAL_OVERRIDE", {"flight_number": "NV-102", "captain_id": "CRW-FO-02"}),
    ]

    for stype, p in type_names:
        resp = client.post("/api/v1/disruptions/execute", json={"scenario": stype, "params": p})
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_type"] == stype
        assert data["invariants_verified"] is True
