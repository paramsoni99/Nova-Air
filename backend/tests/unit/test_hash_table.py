"""Unit and randomized oracle test suite for SeparateChainingHashTable."""

import random
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from backend.app.data_structures.hash_table import HashNode, SeparateChainingHashTable
from backend.app.services.dataset_loader import DatasetLoader


def test_hash_node_representation():
    """Verify HashNode initialization and representation."""
    node = HashNode("BOM", "Mumbai")
    assert node.key == "BOM"
    assert node.value == "Mumbai"
    assert node.next is None
    assert "BOM" in repr(node)


def test_basic_crud_operations():
    """Test basic put, get, update, contains, and remove operations."""
    ht: SeparateChainingHashTable[str, str] = SeparateChainingHashTable(initial_capacity=11)
    assert len(ht) == 0
    assert ht.get("BOM") is None
    assert "BOM" not in ht

    # Put and get
    ht.put("BOM", "Mumbai")
    ht.put("DEL", "New Delhi")
    ht.put("BLR", "Bengaluru")
    assert len(ht) == 3
    assert ht.get("BOM") == "Mumbai"
    assert ht.get("DEL") == "New Delhi"
    assert ht.get("BLR") == "Bengaluru"
    assert "BOM" in ht
    assert "HYD" not in ht

    # Update existing key
    ht.put("BOM", "Chhatrapati Shivaji Maharaj")
    assert len(ht) == 3
    assert ht.get("BOM") == "Chhatrapati Shivaji Maharaj"

    # Dunder syntax
    ht["HYD"] = "Hyderabad"
    assert len(ht) == 4
    assert ht["HYD"] == "Hyderabad"
    with pytest.raises(KeyError):
        _ = ht["UNKNOWN"]

    # Pop and Remove
    assert ht.pop("BLR") == "Bengaluru"
    assert len(ht) == 3
    assert "BLR" not in ht
    assert ht.pop("NONEXISTENT", default="DEF") == "DEF"

    del ht["DEL"]
    assert len(ht) == 2
    assert "DEL" not in ht

    with pytest.raises(KeyError):
        ht.remove("DEL")

    # Invariants
    assert ht.verify_invariants() is True


def test_forced_collisions_and_chain_deletions():
    """Test head, middle, and tail deletions on forced collision chains."""
    # Force collision by creating table with capacity 1 and max_load_factor high
    ht: SeparateChainingHashTable[str, int] = SeparateChainingHashTable(initial_capacity=1, max_load_factor=10.0)
    # With capacity 11 (smallest prime), find 3 keys that hash to the exact same bucket
    target_bucket = ht._hash("key_0")
    colliding_keys = ["key_0"]

    candidate = 1
    while len(colliding_keys) < 4:
        cand_key = f"key_{candidate}"
        if ht._hash(cand_key) == target_bucket:
            colliding_keys.append(cand_key)
        candidate += 1

    # Insert 4 colliding keys: [k3 -> k2 -> k1 -> k0]
    for idx, k in enumerate(colliding_keys):
        ht.put(k, idx * 100)

    assert len(ht) == 4
    diag = ht.get_diagnostics()
    assert diag["max_chain_length"] >= 4
    assert ht.verify_invariants() is True

    # 1. Delete Head (the most recently inserted node: colliding_keys[3])
    head_key = colliding_keys[3]
    assert ht.remove(head_key) == 300
    assert len(ht) == 3
    assert head_key not in ht
    assert ht.verify_invariants() is True

    # 2. Delete Middle (colliding_keys[1])
    mid_key = colliding_keys[1]
    assert ht.remove(mid_key) == 100
    assert len(ht) == 2
    assert mid_key not in ht
    assert ht.verify_invariants() is True

    # 3. Delete Tail (the earliest inserted node: colliding_keys[0])
    tail_key = colliding_keys[0]
    assert ht.remove(tail_key) == 0
    assert len(ht) == 1
    assert tail_key not in ht
    assert ht.verify_invariants() is True

    # 4. Delete the sole remaining node (colliding_keys[2])
    last_key = colliding_keys[2]
    assert ht.remove(last_key) == 200
    assert len(ht) == 0
    assert ht.verify_invariants() is True


def test_dynamic_resizing_and_rehashing():
    """Test dynamic expansion across 500 insertions and verify all keys remain retrievable."""
    ht: SeparateChainingHashTable[str, int] = SeparateChainingHashTable(initial_capacity=11, max_load_factor=0.75)
    initial_cap = ht.capacity

    n = 500
    for i in range(n):
        ht.put(f"item_{i:04d}", i)

    assert len(ht) == n
    assert ht.capacity > initial_cap
    assert ht.load_factor <= 0.75

    # Verify all 500 items are still retrievable
    for i in range(n):
        assert ht.get(f"item_{i:04d}") == i

    assert ht.verify_invariants() is True

    # Check keys(), values(), items()
    keys = ht.keys()
    values = ht.values()
    items = ht.items()
    assert len(keys) == n
    assert len(values) == n
    assert len(items) == n
    assert sum(values) == sum(range(n))


def test_nova_air_dataset_indexing():
    """Load Nova Air datasets and index all airports, aircraft, crew, and flights into hash tables."""
    loader = DatasetLoader()
    demo_ds = loader.load_from_directory(ROOT_DIR / "data")

    # 1. Airports index
    airports_ht: SeparateChainingHashTable[str, Any] = SeparateChainingHashTable()
    for code, ap in demo_ds.airports.items():
        airports_ht.put(code, ap)
    assert len(airports_ht) == 7
    assert airports_ht.get("BOM").city == "Mumbai"
    assert airports_ht.get("DEL").is_hub is True
    assert airports_ht.verify_invariants() is True

    # 2. Aircraft index
    aircraft_ht: SeparateChainingHashTable[str, Any] = SeparateChainingHashTable()
    for tail, ac in demo_ds.aircraft.items():
        aircraft_ht.put(tail, ac)
    assert len(aircraft_ht) == 8
    assert aircraft_ht.get("VT-NVA").aircraft_type == "A320"
    assert aircraft_ht.get("VT-NVE").aircraft_type == "ATR72"
    assert aircraft_ht.verify_invariants() is True

    # 3. Crew index
    crew_ht: SeparateChainingHashTable[str, Any] = SeparateChainingHashTable()
    for cid, member in demo_ds.crew.items():
        crew_ht.put(cid, member)
    assert len(crew_ht) == 42
    assert crew_ht.get("CRW-CPT-01").name == "Capt. Vikram Malhotra"
    assert crew_ht.verify_invariants() is True

    # 4. Flights index
    flights_ht: SeparateChainingHashTable[str, Any] = SeparateChainingHashTable()
    for f in demo_ds.flights:
        flights_ht.put(f.flight_number, f)
    assert len(flights_ht) == 36
    assert flights_ht.get("NV-101").origin == "BOM"
    assert flights_ht.get("NV-136").destination == "GOI"
    assert flights_ht.verify_invariants() is True

    # Print and verify diagnostics on flights index
    diag = flights_ht.get_diagnostics()
    assert diag["size"] == 36
    assert diag["capacity"] >= 47
    assert diag["load_factor"] < 0.75
    assert diag["max_chain_length"] >= 1


def test_randomized_oracle_equivalence():
    """Run 5,000 randomized operations against a standard Python dict oracle."""
    rng = random.Random(42)
    ht: SeparateChainingHashTable[str, int] = SeparateChainingHashTable(initial_capacity=11, max_load_factor=0.75)
    oracle: dict[str, int] = {}

    keys_pool = [f"key_{i:03d}" for i in range(150)]
    operations = ["put", "get", "remove", "contains", "len"]

    for step in range(5000):
        op = rng.choice(operations)
        k = rng.choice(keys_pool)

        if op == "put":
            val = rng.randint(0, 10000)
            ht.put(k, val)
            oracle[k] = val
        elif op == "get":
            assert ht.get(k) == oracle.get(k)
        elif op == "contains":
            assert (k in ht) == (k in oracle)
        elif op == "remove":
            if k in oracle:
                oracle_val = oracle.pop(k)
                ht_val = ht.remove(k)
                assert ht_val == oracle_val
            else:
                with pytest.raises(KeyError):
                    ht.remove(k)
        elif op == "len":
            assert len(ht) == len(oracle)

        # Invariant check every 500 steps
        if (step + 1) % 500 == 0:
            assert ht.verify_invariants() is True
            assert sorted(ht.keys()) == sorted(oracle.keys())
            assert sorted(ht.values()) == sorted(oracle.values())

    # Final assertion
    assert ht.verify_invariants() is True
    assert len(ht) == len(oracle)
    assert sorted(ht.items()) == sorted(oracle.items())
