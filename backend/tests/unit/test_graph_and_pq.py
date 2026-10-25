"""Unit and integration tests for FlightConnectionGraph and SchedulerPriorityQueue."""

import math
import sys
from pathlib import Path
from typing import Any, List, Optional

import pytest

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.data_structures.graph import ConnectionEdge, FlightConnectionGraph, PositioningPath
from backend.app.data_structures.priority_queue import PriorityKey, SchedulePriority, SchedulerPriorityQueue
from backend.app.models.domain import FlightLeg
from backend.app.services.dataset_loader import DatasetLoader


def make_leg(
    flight_number: str,
    origin: str,
    destination: str,
    dep: int,
    arr: int,
    aircraft_tail: str = "VT-NVA",
) -> FlightLeg:
    return FlightLeg(
        flight_number=flight_number,
        origin=origin,
        destination=destination,
        departure_utc=dep,
        arrival_utc=arr,
        aircraft_tail=aircraft_tail,
        required_aircraft_type="A320",
    )


# ==============================================================================
# FlightConnectionGraph Tests
# ==============================================================================


def test_graph_initialization_and_empty_behavior():
    """Verify graph creation, validation of parameters, and empty state."""
    graph = FlightConnectionGraph(min_connection_seconds=1800, max_connection_seconds=36000)
    assert len(graph) == 0
    assert graph.is_empty()
    assert graph.verify_invariants() is True
    assert graph.get_diagnostics()["vertex_count"] == 0

    # Invalid bounds
    with pytest.raises(ValueError, match="Invalid connection window"):
        FlightConnectionGraph(min_connection_seconds=-10, max_connection_seconds=100)
    with pytest.raises(ValueError, match="Invalid connection window"):
        FlightConnectionGraph(min_connection_seconds=5000, max_connection_seconds=2000)
    with pytest.raises(ValueError, match="hop_penalty_seconds must be non-negative"):
        FlightConnectionGraph(hop_penalty_seconds=-100)


def test_edge_weight_computation_and_rejection():
    """Verify edge weight calculation, layover windows, and non-finite rejection."""
    graph = FlightConnectionGraph(
        min_connection_seconds=1800,
        max_connection_seconds=7200,
        hop_penalty_seconds=1800,
    )

    # u: BOM -> DEL [10000, 15000)
    u = make_leg("NV-101", "BOM", "DEL", 10000, 15000)
    # v: DEL -> BLR [17000, 22000) (layover = 2000s, within [1800, 7200])
    v = make_leg("NV-102", "DEL", "BLR", 17000, 22000)

    # Weight = (v.arrival_utc - u.arrival_utc) + hop_penalty = (22000 - 15000) + 1800 = 8800
    weight = graph.compute_edge_weight(u, v)
    assert weight == 8800

    # Incompatible airport transfer: u.dest != w.origin
    w = make_leg("NV-103", "BOM", "CCU", 17000, 22000)
    with pytest.raises(ValueError, match="Incompatible airport transfer"):
        graph.compute_edge_weight(u, w)

    # Layover too short (< 1800s)
    v_too_fast = make_leg("NV-104", "DEL", "BLR", 16000, 21000)
    with pytest.raises(ValueError, match="Connection layover .* outside feasible window"):
        graph.compute_edge_weight(u, v_too_fast)

    # Layover too long (> 7200s)
    v_too_slow = make_leg("NV-105", "DEL", "BLR", 25000, 30000)
    with pytest.raises(ValueError, match="Connection layover .* outside feasible window"):
        graph.compute_edge_weight(u, v_too_slow)

    # Non-finite or negative weight rejection in ConnectionEdge
    with pytest.raises(ValueError, match="Edge weight must be finite and non-negative"):
        ConnectionEdge("A", "B", 100, 200, 50, -10)
    with pytest.raises(ValueError, match="Edge weight must be finite and non-negative"):
        ConnectionEdge("A", "B", 100, 200, 50, float("nan"))  # type: ignore


def test_multi_hop_positioning_path():
    """Verify Dijkstra positioning path across single-hop and multi-hop connections."""
    graph = FlightConnectionGraph(min_connection_seconds=1800, max_connection_seconds=7200, hop_penalty_seconds=1800)

    # Create network:
    # F1: BOM -> DEL [10000, 15000)
    # F2: DEL -> CCU [17000, 22000) (layover = 2000s)
    # F3: CCU -> GAU [24000, 28000) (layover = 2000s)
    # Direct F4: BOM -> CCU [12000, 18000)
    f1 = make_leg("NV-01", "BOM", "DEL", 10000, 15000)
    f2 = make_leg("NV-02", "DEL", "CCU", 17000, 22000)
    f3 = make_leg("NV-03", "CCU", "GAU", 24000, 28000)
    f4 = make_leg("NV-04", "BOM", "CCU", 12000, 18000)

    graph.rebuild_from_flights([f1, f2, f3, f4])
    assert len(graph) == 4
    assert graph.verify_invariants() is True

    # 1. Trivial same-airport query
    same = graph.find_shortest_positioning_path("BOM", 8000, "BOM")
    assert same is not None
    assert same.hop_count == 0
    assert same.total_elapsed_seconds == 0

    # 2. Query BOM -> CCU: Direct F4 (arrives at 18000) vs 2-hop F1->F2 (arrives at 22000)
    # Direct F4 should win
    path_ccu = graph.find_shortest_positioning_path("BOM", 8000, "CCU")
    assert path_ccu is not None
    assert path_ccu.is_direct is True
    assert [f.flight_number for f in path_ccu.flights] == ["NV-04"]
    assert path_ccu.total_elapsed_seconds == 18000 - 8000  # 10000s

    # 3. Query BOM -> GAU: Requires 2 hops via direct F4->F3 or 3 hops F1->F2->F3
    # F4: arrives at CCU at 18000. F3 departs at 24000 (layover = 6000s, feasible!).
    # Total elapsed for F4->F3: 28000 - 8000 = 20000s.
    path_gau = graph.find_shortest_positioning_path("BOM", 8000, "GAU")
    assert path_gau is not None
    assert path_gau.hop_count == 2
    assert [f.flight_number for f in path_gau.flights] == ["NV-04", "NV-03"]
    assert path_gau.total_layover_seconds == 6000
    assert path_gau.total_flight_seconds == (18000 - 12000) + (28000 - 24000)


def test_disconnected_airports_and_temporal_infeasibility():
    """Verify None return when no path exists or arrival deadline is exceeded."""
    graph = FlightConnectionGraph(min_connection_seconds=1800, max_connection_seconds=7200)

    f1 = make_leg("NV-01", "BOM", "DEL", 10000, 15000)
    f2 = make_leg("NV-02", "BLR", "MAA", 12000, 16000)
    graph.rebuild_from_flights([f1, f2])

    # Disconnected airport
    assert graph.find_shortest_positioning_path("BOM", 8000, "MAA") is None

    # Earliest available is after departure
    assert graph.find_shortest_positioning_path("BOM", 11000, "DEL") is None

    # Latest arrival deadline exceeded
    assert graph.find_shortest_positioning_path("BOM", 8000, "DEL", latest_arrival_utc=14000) is None
    assert graph.find_shortest_positioning_path("BOM", 8000, "DEL", latest_arrival_utc=15000) is not None


def test_dynamic_flight_delay_and_cancellation():
    """Verify that update_flight_vertex immediately updates edges without staleness."""
    graph = FlightConnectionGraph(min_connection_seconds=1800, max_connection_seconds=3600)

    # Initial:
    # F1: BOM -> DEL [10000, 12000)
    # F2: DEL -> CCU [14000, 16000) (layover = 2000s, connected!)
    f1 = make_leg("NV-01", "BOM", "DEL", 10000, 12000)
    f2 = make_leg("NV-02", "DEL", "CCU", 14000, 16000)
    graph.rebuild_from_flights([f1, f2])

    assert len(graph.adj["NV-01"]) == 1
    assert graph.find_shortest_positioning_path("BOM", 8000, "CCU") is not None

    # Delay F1 by 1500s: arrives at 13500. Layover to F2 becomes 500s (< 1800s min -> connection breaks!)
    f1_delayed = make_leg("NV-01", "BOM", "DEL", 11500, 13500)
    graph.update_flight_vertex(f1_delayed)

    assert len(graph.adj["NV-01"]) == 0
    assert graph.verify_invariants() is True
    assert graph.find_shortest_positioning_path("BOM", 8000, "CCU") is None

    # Now delay F2 so layover is restored to 2500s: [16000, 18000)
    f2_rescheduled = make_leg("NV-02", "DEL", "CCU", 16000, 18000)
    graph.update_flight_vertex(f2_rescheduled)

    assert len(graph.adj["NV-01"]) == 1
    assert graph.verify_invariants() is True
    res = graph.find_shortest_positioning_path("BOM", 8000, "CCU")
    assert res is not None
    assert [f.flight_number for f in res.flights] == ["NV-01", "NV-02"]

    # Cancel/remove F2
    assert graph.remove_flight("NV-02") is True
    assert len(graph.adj["NV-01"]) == 0
    assert graph.verify_invariants() is True


def test_nova_air_dataset_positioning():
    """Verify connection graph building and positioning on Nova Air test and demo datasets."""
    loader = DatasetLoader()

    # 1. Test Profile
    test_ds = loader.load_from_directory(ROOT_DIR / "data" / "test")
    test_graph = FlightConnectionGraph(min_connection_seconds=1800, max_connection_seconds=43200)
    test_graph.rebuild_from_flights(test_ds.flights)

    assert test_graph.verify_invariants() is True
    t_diag = test_graph.get_diagnostics()
    assert t_diag["vertex_count"] == 14
    assert t_diag["edge_count"] > 0

    # 2. Demo Profile
    demo_ds = loader.load_from_directory(ROOT_DIR / "data")
    demo_graph = FlightConnectionGraph(min_connection_seconds=1800, max_connection_seconds=43200)
    demo_graph.rebuild_from_flights(demo_ds.flights)

    assert demo_graph.verify_invariants() is True
    d_diag = demo_graph.get_diagnostics()
    assert d_diag["vertex_count"] == 36
    assert d_diag["edge_count"] > 10

    # Test positioning between two major hubs (e.g. BOM and DEL)
    earliest_dep = min(f.departure_utc for f in demo_ds.flights)
    path = demo_graph.find_shortest_positioning_path("BOM", earliest_dep, "DEL")
    assert path is not None
    assert path.origin_airport == "BOM"
    assert path.target_airport == "DEL"
    assert len(path.flights) >= 1


# ==============================================================================
# SchedulerPriorityQueue Tests
# ==============================================================================


def test_priority_queue_basic_push_pop():
    """Verify min-heap order across MCV, EDF, slack, and disruption severity."""
    pq: SchedulerPriorityQueue[str] = SchedulerPriorityQueue()
    assert pq.is_empty()
    assert len(pq) == 0

    # Item A: 5 combinations, dep 1000, slack 60, disruption 0
    # Item B: 2 combinations (fewer combinations -> most constrained -> higher priority!)
    # Item C: 2 combinations, earlier dep (500 vs 1000) -> higher priority than B!
    # Item D: 2 combinations, dep 500, tighter slack (30 vs 60) -> higher priority than C!
    # Item E: 2 combinations, dep 500, slack 30, higher disruption severity (3 vs 1, -3 < -1) -> highest!
    item_a = (5, 1000, 60, 0, "NV-A")
    item_b = (2, 1000, 60, 0, "NV-B")
    item_c = (2, 500, 60, 0, "NV-C")
    item_d = (2, 500, 30, -1, "NV-D")
    item_e = (2, 500, 30, -3, "NV-E")

    for item in [item_a, item_b, item_c, item_d, item_e]:
        pq.push(item[4], item, f"payload_{item[4]}")

    assert len(pq) == 5
    assert pq.verify_invariants() is True

    # Expected pop order: E, D, C, B, A
    expected_order = ["NV-E", "NV-D", "NV-C", "NV-B", "NV-A"]
    popped_order: List[str] = []
    while not pq.is_empty():
        fid, key, payload = pq.pop()
        assert pq.verify_invariants() is True
        popped_order.append(fid)

    assert popped_order == expected_order
    assert pq.is_empty()

    with pytest.raises(IndexError, match="empty SchedulerPriorityQueue"):
        pq.pop()


def test_priority_queue_lazy_updates():
    """Verify O(log n) push_or_update with lazy version invalidation."""
    pq: SchedulerPriorityQueue[int] = SchedulerPriorityQueue()

    # Insert NV-101 with low urgency (10 combinations)
    pq.push_or_update("NV-101", (10, 1000, 60, 0, "NV-101"), 1)
    # Insert NV-102 with moderate urgency (5 combinations)
    pq.push_or_update("NV-102", (5, 1000, 60, 0, "NV-102"), 2)

    # NV-102 is currently top
    peeked = pq.peek()
    assert peeked is not None and peeked[0] == "NV-102"
    assert len(pq) == 2

    # Now NV-101 suffers crew disqualification: combinations drops from 10 to 1!
    # Update NV-101 in O(log n)
    pq.push_or_update("NV-101", (1, 1000, 60, 0, "NV-101"), 99)

    # Active size is still 2!
    assert len(pq) == 2
    # But internal capacity has 3 items (1 stale)
    diag = pq.get_diagnostics()
    assert diag["size"] == 2
    assert diag["stale_entries"] == 1

    # NV-101 should now be popped first with payload 99
    fid, key, payload = pq.pop()
    assert fid == "NV-101"
    assert key.feasible_combinations == 1
    assert payload == 99

    # NV-102 is popped next
    fid2, key2, payload2 = pq.pop()
    assert fid2 == "NV-102"
    assert payload2 == 2

    assert pq.is_empty()
