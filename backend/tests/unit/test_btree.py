"""Unit and randomized oracle test suite for FlightScheduleBTree."""

import random
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from backend.app.data_structures.btree import BTreeNode, FlightScheduleBTree
from backend.app.services.dataset_loader import DatasetLoader


def test_btree_node_creation():
    """Verify BTreeNode initialization."""
    node: BTreeNode[str] = BTreeNode(leaf=True)
    assert node.leaf is True
    assert len(node.keys) == 0
    assert len(node.values) == 0
    assert len(node.children) == 0


def test_btree_insert_and_split():
    """Verify B-Tree insertions with root splitting and height growth (t=2, 2t-1=3 max keys)."""
    btree: FlightScheduleBTree[str] = FlightScheduleBTree(t=2)
    assert len(btree) == 0
    assert btree.is_empty() is True

    # Insert 3 keys (fills root: 2*2 - 1 = 3)
    btree.insert((100, "NV-101"), "Flight 101")
    btree.insert((200, "NV-102"), "Flight 102")
    btree.insert((300, "NV-103"), "Flight 103")

    assert len(btree) == 3
    assert btree.verify_invariants() is True
    assert btree.get_diagnostics()["height"] == 0

    # 4th key triggers split of root
    btree.insert((400, "NV-104"), "Flight 104")
    assert len(btree) == 4
    assert btree.verify_invariants() is True
    assert btree.get_diagnostics()["height"] == 1

    # Insert more keys to trigger non-root child splits
    for t_sec in [50, 150, 250, 350, 450, 500, 600]:
        btree.insert((t_sec, f"NV-{t_sec}"), f"Flight {t_sec}")
        assert btree.verify_invariants() is True

    assert len(btree) == 11
    # Verify all keys are retrievable
    assert btree.search((50, "NV-50")) == "Flight 50"
    assert btree.search((200, "NV-102")) == "Flight 102"
    assert btree.search((600, "NV-600")) == "Flight 600"
    assert btree.search((999, "NV-999")) is None


def test_flight_id_tie_breaking():
    """Verify identical departure timestamps are broken deterministically by flight_id."""
    btree: FlightScheduleBTree[str] = FlightScheduleBTree(t=3)
    same_time = 1774915200

    flights = ["NV-300", "NV-100", "NV-200", "NV-400", "NV-050"]
    for f in flights:
        btree.insert((same_time, f), f"Details for {f}")

    assert len(btree) == 5
    assert btree.verify_invariants() is True

    # In-order traversal must be sorted by flight_id when timestamps are equal
    inorder = btree.inorder_traversal()
    expected_order = sorted([(same_time, f) for f in flights])
    assert [k for k, _ in inorder] == expected_order


def test_btree_deletions_leaf_and_internal():
    """Verify B-Tree deletions including borrow from sibling, merge, and root shrinkage."""
    btree: FlightScheduleBTree[int] = FlightScheduleBTree(t=2)

    # Insert 10 elements
    keys = [(i * 10, f"NV-{i}") for i in range(1, 11)]
    for k in keys:
        btree.insert(k, k[0])

    assert len(btree) == 10
    assert btree.verify_invariants() is True

    # 1. Delete leaf node key without underflow
    assert btree.delete((10, "NV-1")) is True
    assert len(btree) == 9
    assert btree.search((10, "NV-1")) is None
    assert btree.verify_invariants() is True

    # 2. Delete internal node key (predecessor/successor replacement)
    root_key = btree._root.keys[0]
    assert btree.delete(root_key) is True
    assert len(btree) == 8
    assert btree.search(root_key) is None
    assert btree.verify_invariants() is True

    # 3. Delete non-existent key returns False
    assert btree.delete((999, "NV-999")) is False
    assert len(btree) == 8

    # 4. Sequentially delete all remaining keys and assert invariants at every step
    remaining = btree.keys()
    for rk in remaining:
        assert btree.delete(rk) is True
        assert btree.verify_invariants() is True

    assert len(btree) == 0
    assert btree.is_empty() is True


def test_update_key_atomic_flight_reschedule():
    """Test update_key atomic delete + insert when a flight is delayed."""
    btree: FlightScheduleBTree[str] = FlightScheduleBTree(t=3)

    old_key = (3600, "NV-101")
    new_key = (7200, "NV-101")

    btree.insert(old_key, "BOM -> DEL Scheduled 01:00")
    btree.insert((4000, "NV-102"), "DEL -> BLR Scheduled 01:06")
    btree.insert((5000, "NV-103"), "BLR -> BOM Scheduled 01:23")

    assert len(btree) == 3
    assert btree.search(old_key) is not None

    # Reschedule / Delay NV-101
    btree.update_key(old_key, new_key, "BOM -> DEL Delayed 02:00")

    assert len(btree) == 3
    assert btree.search(old_key) is None
    assert btree.search(new_key) == "BOM -> DEL Delayed 02:00"
    assert btree.verify_invariants() is True

    # Check order
    inorder_keys = btree.keys()
    assert inorder_keys == [(4000, "NV-102"), (5000, "NV-103"), (7200, "NV-101")]

    # Updating non-existent key raises KeyError
    with pytest.raises(KeyError):
        btree.update_key((9999, "NV-999"), (10000, "NV-999"))


def test_range_queries_inclusive_exclusive():
    """Verify range_query inclusive and exclusive boundaries."""
    btree: FlightScheduleBTree[str] = FlightScheduleBTree(t=3)

    timestamps = [1000, 2000, 3000, 4000, 5000, 6000, 7000]
    for ts in timestamps:
        btree.insert((ts, f"NV-{ts}"), f"Flight at {ts}")

    assert len(btree) == 7

    # 1. Both inclusive: [2000, 5000] -> 2000, 3000, 4000, 5000
    res = btree.range_query(2000, 5000, include_min=True, include_max=True)
    assert [k[0] for k, _ in res] == [2000, 3000, 4000, 5000]

    # 2. Left inclusive, right exclusive: [2000, 5000) -> 2000, 3000, 4000
    res = btree.range_query(2000, 5000, include_min=True, include_max=False)
    assert [k[0] for k, _ in res] == [2000, 3000, 4000]

    # 3. Left exclusive, right inclusive: (2000, 5000] -> 3000, 4000, 5000
    res = btree.range_query(2000, 5000, include_min=False, include_max=True)
    assert [k[0] for k, _ in res] == [3000, 4000, 5000]

    # 4. Both exclusive: (2000, 5000) -> 3000, 4000
    res = btree.range_query(2000, 5000, include_min=False, include_max=False)
    assert [k[0] for k, _ in res] == [3000, 4000]

    # 5. Out of bounds range
    res = btree.range_query(8000, 9000)
    assert res == []

    # 6. Inverted range
    res = btree.range_query(5000, 2000)
    assert res == []


def test_nova_air_schedule_indexing():
    """Load Nova Air demo schedule and test departure window queries and diagnostics."""
    loader = DatasetLoader()
    demo_ds = loader.load_from_directory(ROOT_DIR / "data")

    schedule_btree: FlightScheduleBTree[Any] = FlightScheduleBTree(t=3)
    for leg in demo_ds.flights:
        key = (leg.departure_utc, leg.flight_number)
        schedule_btree.insert(key, leg)

    assert len(schedule_btree) == 36
    assert schedule_btree.verify_invariants() is True

    # Diagnostics
    diag = schedule_btree.get_diagnostics()
    assert diag["size"] == 36
    assert diag["degree_t"] == 3
    assert diag["height"] >= 1
    assert diag["total_nodes"] > 1

    # Time-window query: query first 12 hours from base departure
    min_dep = min(f.departure_utc for f in demo_ds.flights)
    window_end = min_dep + 12 * 3600
    window_flights = schedule_btree.range_query(min_dep, window_end, include_min=True, include_max=True)

    expected = [
        (f.departure_utc, f.flight_number)
        for f in demo_ds.flights
        if min_dep <= f.departure_utc <= window_end
    ]
    expected.sort()
    actual = [k for k, _ in window_flights]
    assert actual == expected


def test_randomized_oracle_equivalence():
    """Run 2,000 randomized operations against a sorted Python list oracle."""
    rng = random.Random(42)
    btree: FlightScheduleBTree[int] = FlightScheduleBTree(t=3)
    oracle: dict[Tuple[int, str], int] = {}

    timestamps_pool = [1000 + i * 100 for i in range(50)]
    flights_pool = [f"NV-{i:03d}" for i in range(25)]

    operations = ["insert", "search", "delete", "range_query"]

    for step in range(2000):
        op = rng.choice(operations)
        k = (rng.choice(timestamps_pool), rng.choice(flights_pool))

        if op == "insert":
            val = rng.randint(0, 100000)
            btree.insert(k, val)
            oracle[k] = val
        elif op == "search":
            assert btree.search(k) == oracle.get(k)
        elif op == "delete":
            if k in oracle:
                del oracle[k]
                assert btree.delete(k) is True
            else:
                assert btree.delete(k) is False
        elif op == "range_query":
            t1 = rng.choice(timestamps_pool)
            t2 = rng.choice(timestamps_pool)
            min_t, max_t = min(t1, t2), max(t1, t2)
            inc_min = rng.choice([True, False])
            inc_max = rng.choice([True, False])

            results = btree.range_query(min_t, max_t, include_min=inc_min, include_max=inc_max)

            # Oracle range query
            oracle_results = []
            for (ts, fid), val in oracle.items():
                in_range = True
                if inc_min:
                    if ts < min_t:
                        in_range = False
                else:
                    if ts <= min_t:
                        in_range = False

                if inc_max:
                    if ts > max_t:
                        in_range = False
                else:
                    if ts >= max_t:
                        in_range = False

                if in_range:
                    oracle_results.append(((ts, fid), val))

            oracle_results.sort(key=lambda x: x[0])
            assert [r[0] for r in results] == [r[0] for r in oracle_results]

        # Periodic structural invariant check
        if (step + 1) % 400 == 0:
            assert btree.verify_invariants() is True
            assert len(btree) == len(oracle)
            assert [k for k, _ in btree.inorder_traversal()] == sorted(oracle.keys())

    # Final assertion
    assert btree.verify_invariants() is True
    assert len(btree) == len(oracle)
    assert btree.keys() == sorted(oracle.keys())
