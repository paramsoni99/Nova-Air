"""Unit and randomized oracle tests for the Augmented Red-Black Interval Tree."""

import random
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.data_structures.rb_interval_tree import (
    IntervalNode,
    NodeColor,
    RBIntervalTree,
)
from backend.app.services.dataset_loader import DatasetLoader


def test_node_creation_and_sentinel():
    """Verify sentinel node properties and empty tree behavior."""
    tree: RBIntervalTree[Any] = RBIntervalTree()
    assert tree.is_empty()
    assert len(tree) == 0
    assert tree.root == tree.nil
    assert tree.nil.color == NodeColor.BLACK
    assert tree.nil.max_end == -1
    assert tree.nil.left == tree.nil
    assert tree.nil.right == tree.nil
    assert tree.nil.parent == tree.nil
    assert tree.verify_invariants() is True
    assert tree.get_diagnostics()["size"] == 0


def test_insertions_and_rotations():
    """Verify insertion order, coloring, rotations, and max_end augmentation."""
    tree: RBIntervalTree[str] = RBIntervalTree()

    # Insert 5 intervals designed to trigger recoloring and rotations
    # [1000, 2000), [500, 1500), [200, 800), [1500, 2500), [300, 700)
    tree.insert(1000, 2000, "I1", "data-1")
    assert len(tree) == 1
    assert tree.root.color == NodeColor.BLACK
    assert tree.root.max_end == 2000
    assert tree.verify_invariants() is True

    tree.insert(500, 1500, "I2", "data-2")
    assert len(tree) == 2
    assert tree.verify_invariants() is True

    tree.insert(200, 800, "I3", "data-3")  # Triggers right rotation at root or recolor
    assert len(tree) == 3
    assert tree.verify_invariants() is True

    tree.insert(1500, 2500, "I4", "data-4")
    assert len(tree) == 4
    assert tree.verify_invariants() is True

    tree.insert(300, 700, "I5", "data-5")
    assert len(tree) == 5
    assert tree.verify_invariants() is True
    assert tree.root.color == NodeColor.BLACK

    # Verify duplicate key rejection
    with pytest.raises(ValueError, match="Duplicate interval key already exists"):
        tree.insert(1000, 2000, "I1")

    # Verify invalid interval rejection (start >= end)
    with pytest.raises(ValueError, match="Invalid half-open interval"):
        tree.insert(2000, 2000, "BAD_1")
    with pytest.raises(ValueError, match="Invalid half-open interval"):
        tree.insert(3000, 2000, "BAD_2")


def test_deletions_leaf_and_internal_with_rebalancing():
    """Test deletion of leaf nodes, nodes with one child, and nodes with two children."""
    tree: RBIntervalTree[int] = RBIntervalTree()
    intervals = [
        (100, 200, "id1"),
        (50, 150, "id2"),
        (150, 250, "id3"),
        (25, 75, "id4"),
        (75, 125, "id5"),
        (125, 175, "id6"),
        (175, 225, "id7"),
    ]
    for s, e, iid in intervals:
        tree.insert(s, e, iid, s)
        assert tree.verify_invariants() is True

    assert len(tree) == 7

    # Delete leaf node
    assert tree.delete(25, 75, "id4") is True
    assert len(tree) == 6
    assert tree.verify_invariants() is True

    # Delete internal node with two children
    assert tree.delete(100, 200, "id1") is True
    assert len(tree) == 5
    assert tree.verify_invariants() is True

    # Delete non-existent node
    assert tree.delete(999, 1000, "nonexistent") is False
    assert len(tree) == 5

    # Delete remaining nodes down to empty tree
    for s, e, iid in [(50, 150, "id2"), (150, 250, "id3"), (75, 125, "id5"), (125, 175, "id6"), (175, 225, "id7")]:
        assert tree.delete(s, e, iid) is True
        assert tree.verify_invariants() is True

    assert len(tree) == 0
    assert tree.is_empty()
    assert tree.root == tree.nil


def test_verify_invariants_across_300_inserts_and_150_deletes():
    """Rigorously assert invariants after every single insertion (300) and deletion (150)."""
    rng = random.Random(42)
    tree: RBIntervalTree[int] = RBIntervalTree()

    inserted_keys: list[tuple[int, int, str]] = []

    # 1. 300 Insertions
    for i in range(300):
        start = rng.randint(0, 100_000)
        duration = rng.randint(1800, 28800)
        end = start + duration
        iid = f"REQ-{i:04d}"
        key = (start, end, iid)
        inserted_keys.append(key)

        tree.insert(start, end, iid, i)
        assert tree.verify_invariants() is True, f"Invariant violated after insert {i}: key={key}"

    assert len(tree) == 300
    diag = tree.get_diagnostics()
    assert diag["size"] == 300
    assert diag["black_height"] > 0
    assert diag["height"] <= 2 * (diag["black_height"] + 1)

    # 2. 150 Deletions
    rng.shuffle(inserted_keys)
    to_delete = inserted_keys[:150]
    for i, (start, end, iid) in enumerate(to_delete):
        deleted = tree.delete(start, end, iid)
        assert deleted is True, f"Failed to delete existing key ({start}, {end}, {iid})"
        assert tree.verify_invariants() is True, f"Invariant violated after delete {i}: ({start}, {end}, {iid})"

    assert len(tree) == 150
    assert tree.verify_invariants() is True


def test_touching_and_nested_intervals():
    """Verify half-open interval boundary semantics: touching endpoints and nested ranges."""
    tree: RBIntervalTree[str] = RBIntervalTree()

    # Touching intervals: [1000, 2000) and [2000, 3000)
    tree.insert(1000, 2000, "LEG-1")
    tree.insert(2000, 3000, "LEG-2")
    tree.insert(3000, 4000, "LEG-3")

    # [1000, 2000) and [2000, 3000) MUST NOT overlap
    assert tree.find_first_overlap(2000, 2500).interval_id == "LEG-2"
    assert len(tree.find_all_overlaps(2000, 3000)) == 1
    assert tree.find_all_overlaps(2000, 3000)[0].interval_id == "LEG-2"

    # Query with touching boundary [1500, 2000) overlaps LEG-1 only, NOT LEG-2
    overlaps_1500_2000 = [n.interval_id for n in tree.find_all_overlaps(1500, 2000)]
    assert overlaps_1500_2000 == ["LEG-1"]

    # Query with boundary [2000, 2500) overlaps LEG-2 only, NOT LEG-1
    overlaps_2000_2500 = [n.interval_id for n in tree.find_all_overlaps(2000, 2500)]
    assert overlaps_2000_2500 == ["LEG-2"]

    # Nested intervals: [5000, 10000) containing [6000, 7000) and [8000, 9000)
    tree.insert(5000, 10000, "DUTY-BLOCK")
    tree.insert(6000, 7000, "SECTOR-1")
    tree.insert(8000, 9000, "SECTOR-2")

    # Candidate interval [6500, 8500) intersects DUTY-BLOCK, SECTOR-1, and SECTOR-2
    overlaps_nested = [n.interval_id for n in tree.find_all_overlaps(6500, 8500)]
    assert sorted(overlaps_nested) == sorted(["DUTY-BLOCK", "SECTOR-1", "SECTOR-2"])

    # Candidate interval [7200, 7800) intersects DUTY-BLOCK only (in between sectors)
    overlaps_duty_only = [n.interval_id for n in tree.find_all_overlaps(7200, 7800)]
    assert overlaps_duty_only == ["DUTY-BLOCK"]


def test_predecessor_and_successor_duty_lookups():
    """Verify predecessor and successor lookups for rest-gap calculation."""
    tree: RBIntervalTree[str] = RBIntervalTree()

    # Schedule:
    # Duty 1: [1000, 2000)
    # Duty 2: [2500, 3500)
    # Duty 3: [5000, 6000)
    tree.insert(1000, 2000, "DUTY-1")
    tree.insert(2500, 3500, "DUTY-2")
    tree.insert(5000, 6000, "DUTY-3")

    # 1. Candidate flight starts at 2500:
    # Prior duty ending <= 2500 is DUTY-1 (ends at 2000 <= 2500)
    pred_2500 = tree.find_predecessor(2500)
    assert pred_2500 is not None
    assert pred_2500.interval_id == "DUTY-1"
    rest_gap_before = 2500 - pred_2500.end_utc
    assert rest_gap_before == 500

    # Next duty starting >= 2500 is DUTY-2 (starts at 2500 >= 2500)
    succ_2500 = tree.find_successor(2500)
    assert succ_2500 is not None
    assert succ_2500.interval_id == "DUTY-2"

    # 2. Candidate flight [3500, 4500):
    # Predecessor ending <= 3500 is DUTY-2 (ends at 3500 <= 3500)
    pred_3500 = tree.find_predecessor(3500)
    assert pred_3500 is not None
    assert pred_3500.interval_id == "DUTY-2"
    assert 3500 - pred_3500.end_utc == 0  # Zero turnaround / touching

    # Successor starting >= 4500 is DUTY-3 (starts at 5000 >= 4500)
    succ_4500 = tree.find_successor(4500)
    assert succ_4500 is not None
    assert succ_4500.interval_id == "DUTY-3"
    rest_gap_after = succ_4500.start_utc - 4500
    assert rest_gap_after == 500

    # 3. Boundary lookups before first duty and after last duty
    pred_before_all = tree.find_predecessor(500)
    assert pred_before_all is None

    succ_after_all = tree.find_successor(7000)
    assert succ_after_all is None


def test_overlap_queries_first_and_all():
    """Test find_first_overlap and find_all_overlaps across complex interval patterns."""
    tree: RBIntervalTree[int] = RBIntervalTree()

    # Intervals:
    # [10, 20), [15, 25), [20, 30), [40, 50), [45, 60), [70, 80)
    for s, e, iid in [
        (10, 20, "A"),
        (15, 25, "B"),
        (20, 30, "C"),
        (40, 50, "D"),
        (45, 60, "E"),
        (70, 80, "F"),
    ]:
        tree.insert(s, e, iid)

    # 1. Non-overlapping query in gap [30, 40)
    assert tree.find_first_overlap(30, 40) is None
    assert tree.find_all_overlaps(30, 40) == []

    # 2. Query [18, 22) overlaps A ([10, 20)), B ([15, 25)), and C ([20, 30) touches at 20 -> wait: 20 < 22 and 18 < 30 -> overlaps!)
    overlaps = [n.interval_id for n in tree.find_all_overlaps(18, 22)]
    assert overlaps == ["A", "B", "C"]

    # 3. Query [42, 55) overlaps D and E
    overlaps_de = [n.interval_id for n in tree.find_all_overlaps(42, 55)]
    assert overlaps_de == ["D", "E"]

    # 4. Global query spanning all intervals [0, 100)
    all_overlaps = [n.interval_id for n in tree.find_all_overlaps(0, 100)]
    assert all_overlaps == ["A", "B", "C", "D", "E", "F"]


def test_nova_air_duty_and_maintenance_intervals():
    """Index Nova Air aircraft maintenance and flight legs; verify conflict detection."""
    loader = DatasetLoader()
    demo_ds = loader.load_from_directory(ROOT_DIR / "data")

    # Build per-aircraft interval trees for rotation and maintenance conflict checks
    aircraft_trees: dict[str, RBIntervalTree[str]] = {}
    for tail_number in demo_ds.aircraft:
        aircraft_trees[tail_number] = RBIntervalTree()

    # 1. Insert maintenance blocks
    maint_trees: dict[str, RBIntervalTree[str]] = {t: RBIntervalTree() for t in demo_ds.aircraft}
    for mb in demo_ds.maintenance:
        tree = maint_trees[mb.aircraft_tail]
        tree.insert(mb.start_utc, mb.end_utc, mb.id, f"MAINT:{mb.description}")
        assert tree.verify_invariants() is True

    # 2. Insert flight legs and detect any overlap conflicts
    overlap_count = 0
    for leg in demo_ds.flights:
        tree = aircraft_trees[leg.aircraft_tail]
        # Flights should not conflict with scheduled maintenance
        maint_conflict = maint_trees[leg.aircraft_tail].find_first_overlap(leg.departure_utc, leg.arrival_utc)
        assert maint_conflict is None, f"Flight {leg.flight_number} conflicts with maintenance {maint_conflict}"

        # Check for aircraft rotation overlap (e.g. deliberate disruption scenarios)
        flight_conflict = tree.find_first_overlap(leg.departure_utc, leg.arrival_utc)
        if flight_conflict is not None:
            overlap_count += 1

        tree.insert(leg.departure_utc, leg.arrival_utc, leg.flight_number, f"FLIGHT:{leg.flight_number}")
        assert tree.verify_invariants() is True

    # Disruption scenario in demo dataset: exactly NV-135 and NV-108 conflict on VT-NVB
    assert overlap_count > 0, "Expected at least one disruption conflict in demo dataset"
    nvb_conflicts = [n.interval_id for n in aircraft_trees["VT-NVB"].find_all_overlaps(1774980000, 1774984000)]
    assert "NV-135" in nvb_conflicts and "NV-108" in nvb_conflicts

    # 3. Verify deliberate conflict detection:
    # Try querying during VT-NVA's maintenance block
    vta_maint = maint_trees["VT-NVA"]
    maint_block = [m for m in demo_ds.maintenance if m.aircraft_tail == "VT-NVA"][0]

    # Deliberate overlapping interval
    conflict = vta_maint.find_first_overlap(maint_block.start_utc + 300, maint_block.end_utc - 300)
    assert conflict is not None
    assert conflict.interval_id == maint_block.id


def test_randomized_oracle_equivalence():
    """2,000-operation randomized oracle test comparing RBIntervalTree against Python list."""
    rng = random.Random(1337)
    tree: RBIntervalTree[int] = RBIntervalTree()

    # Reference Oracle: list of (start_utc, end_utc, interval_id, data)
    oracle: list[tuple[int, int, str, int]] = []

    next_id = 0

    for step in range(2000):
        action = rng.random()

        if action < 0.40 or len(oracle) < 5:
            # 1. INSERT (40%)
            start = rng.randint(0, 50_000)
            length = rng.randint(100, 5_000)
            end = start + length
            iid = f"RAND-{next_id}"
            next_id += 1

            tree.insert(start, end, iid, step)
            oracle.append((start, end, iid, step))

        elif action < 0.65 and len(oracle) > 0:
            # 2. DELETE (25%)
            idx = rng.randrange(len(oracle))
            start, end, iid, _ = oracle.pop(idx)
            deleted = tree.delete(start, end, iid)
            assert deleted is True

        elif action < 0.85:
            # 3. FIND_FIRST_OVERLAP (20%)
            q_start = rng.randint(0, 50_000)
            q_len = rng.randint(100, 3_000)
            q_end = q_start + q_len

            node = tree.find_first_overlap(q_start, q_end)

            # Brute-force oracle check
            oracle_overlaps = [
                item for item in oracle
                if RBIntervalTree.intervals_overlap(item[0], item[1], q_start, q_end)
            ]

            if not oracle_overlaps:
                assert node is None, f"Tree found {node} but oracle found none for [{q_start}, {q_end})"
            else:
                assert node is not None
                assert RBIntervalTree.intervals_overlap(node.start_utc, node.end_utc, q_start, q_end)

        else:
            # 4. FIND_ALL_OVERLAPS (15%)
            q_start = rng.randint(0, 50_000)
            q_len = rng.randint(100, 5_000)
            q_end = q_start + q_len

            tree_overlaps = tree.find_all_overlaps(q_start, q_end)
            tree_ids = sorted(n.interval_id for n in tree_overlaps)

            oracle_overlaps = sorted(
                item[2] for item in oracle
                if RBIntervalTree.intervals_overlap(item[0], item[1], q_start, q_end)
            )

            assert tree_ids == oracle_overlaps, (
                f"Mismatch at step {step}: tree={tree_ids}, oracle={oracle_overlaps}"
            )

        # Invariant check every 250 steps
        if step % 250 == 0:
            assert len(tree) == len(oracle)
            assert tree.verify_invariants() is True

    # Final exhaustive verification
    assert len(tree) == len(oracle)
    assert tree.verify_invariants() is True
