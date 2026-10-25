"""Repeatable ADS scaling benchmark suite for Nova Air (AirCrewOps).

Benchmarks all custom in-memory data structures across scaling workloads N in {100, 500, 1000, 2500}:
1. SeparateChainingHashTable lookups vs load factor and chain length.
2. FlightScheduleBTree 3-hour window range queries vs O(N) linear scan.
3. RBIntervalTree overlap queries vs O(N) brute-force scan.
4. FlightConnectionGraph Dijkstra positioning searches across scaling flight networks.

Outputs empirical timing and operation counters to benchmarks/latest_benchmark_results.json.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.data_structures.hash_table import SeparateChainingHashTable
from backend.app.data_structures.btree import FlightScheduleBTree
from backend.app.data_structures.rb_interval_tree import RBIntervalTree
from backend.app.data_structures.graph import FlightConnectionGraph
from backend.app.models.domain import FlightLeg
from scripts.generate_dataset import generate_benchmark_profile


def benchmark_hash_table(flights_data: List[Dict[str, Any]], lookups_count: int = 1000) -> Dict[str, Any]:
    """Benchmark SeparateChainingHashTable insert and lookup performance."""
    ht: SeparateChainingHashTable[str, Dict[str, Any]] = SeparateChainingHashTable(initial_capacity=11, max_load_factor=0.75)
    keys = [f["flight_number"] for f in flights_data]

    # Measure insert time
    t0 = time.perf_counter()
    for f in flights_data:
        ht.put(f["flight_number"], f)
    insert_duration_ms = (time.perf_counter() - t0) * 1000.0

    diag = ht.get_diagnostics()

    # Measure lookup time
    random.seed(42)
    sample_keys = [random.choice(keys) for _ in range(lookups_count)]
    t1 = time.perf_counter()
    hits = 0
    for k in sample_keys:
        if ht.get(k) is not None:
            hits += 1
    lookup_duration_ms = (time.perf_counter() - t1) * 1000.0
    lookup_latency_us = (lookup_duration_ms * 1000.0) / lookups_count

    # Compare with native Python dict baseline
    py_dict = {f["flight_number"]: f for f in flights_data}
    t2 = time.perf_counter()
    for k in sample_keys:
        _ = py_dict.get(k)
    py_lookup_duration_ms = (time.perf_counter() - t2) * 1000.0

    return {
        "n_items": len(flights_data),
        "capacity": diag["capacity"],
        "load_factor": diag["load_factor"],
        "max_chain_length": diag["max_chain_length"],
        "occupied_buckets": diag["occupied_buckets"],
        "insert_time_ms": round(insert_duration_ms, 3),
        "lookup_count": lookups_count,
        "lookup_total_ms": round(lookup_duration_ms, 3),
        "avg_lookup_latency_us": round(lookup_latency_us, 3),
        "py_dict_lookup_total_ms": round(py_lookup_duration_ms, 3),
    }


def benchmark_btree(flights_data: List[Dict[str, Any]], queries_count: int = 100) -> Dict[str, Any]:
    """Benchmark FlightScheduleBTree range queries vs O(N) linear list scan."""
    btree: FlightScheduleBTree[Dict[str, Any]] = FlightScheduleBTree(t=3)

    t0 = time.perf_counter()
    for f in flights_data:
        btree.insert((f["departure_utc"], f["flight_number"]), f)
    insert_duration_ms = (time.perf_counter() - t0) * 1000.0

    # Pick query windows of 3 hours (10800 seconds)
    deps = [f["departure_utc"] for f in flights_data]
    min_dep = min(deps)
    max_dep = max(deps)
    window_duration = 3 * 3600

    random.seed(42)
    sample_windows = []
    for _ in range(queries_count):
        start = random.randint(min_dep, max(min_dep, max_dep - window_duration))
        sample_windows.append((start, start + window_duration))

    # B-Tree range query timing
    t1 = time.perf_counter()
    btree_results_count = 0
    for w_start, w_end in sample_windows:
        res = btree.range_query(w_start, w_end)
        btree_results_count += len(res)
    btree_duration_ms = (time.perf_counter() - t1) * 1000.0
    avg_btree_query_us = (btree_duration_ms * 1000.0) / queries_count

    # Linear list scan timing baseline (O(N))
    t2 = time.perf_counter()
    linear_results_count = 0
    for w_start, w_end in sample_windows:
        matched = [f for f in flights_data if w_start <= f["departure_utc"] <= w_end]
        linear_results_count += len(matched)
    linear_duration_ms = (time.perf_counter() - t2) * 1000.0
    avg_linear_query_us = (linear_duration_ms * 1000.0) / queries_count

    speedup = linear_duration_ms / btree_duration_ms if btree_duration_ms > 0 else 1.0

    return {
        "n_items": len(flights_data),
        "tree_size": len(btree),
        "insert_time_ms": round(insert_duration_ms, 3),
        "queries_count": queries_count,
        "window_duration_seconds": window_duration,
        "btree_total_ms": round(btree_duration_ms, 3),
        "avg_btree_query_us": round(avg_btree_query_us, 3),
        "linear_total_ms": round(linear_duration_ms, 3),
        "avg_linear_query_us": round(avg_linear_query_us, 3),
        "speedup_factor": round(speedup, 2),
    }


def benchmark_interval_tree(flights_data: List[Dict[str, Any]], queries_count: int = 100) -> Dict[str, Any]:
    """Benchmark RBIntervalTree find_all_overlaps vs O(N) brute force scan."""
    itree: RBIntervalTree[Dict[str, Any]] = RBIntervalTree()

    t0 = time.perf_counter()
    for f in flights_data:
        itree.insert(f["departure_utc"], f["arrival_utc"], f["flight_number"], f)
    insert_duration_ms = (time.perf_counter() - t0) * 1000.0

    deps = [f["departure_utc"] for f in flights_data]
    min_dep = min(deps)
    max_dep = max(deps)
    query_duration = 2 * 3600  # 2-hour window test

    random.seed(42)
    sample_queries = []
    for _ in range(queries_count):
        q_start = random.randint(min_dep, max(min_dep, max_dep - query_duration))
        sample_queries.append((q_start, q_start + query_duration))

    # RBIntervalTree overlap search
    t1 = time.perf_counter()
    tree_overlap_count = 0
    for q_start, q_end in sample_queries:
        overlaps = itree.find_all_overlaps(q_start, q_end)
        tree_overlap_count += len(overlaps)
    itree_duration_ms = (time.perf_counter() - t1) * 1000.0
    avg_itree_query_us = (itree_duration_ms * 1000.0) / queries_count

    # Brute force scan baseline (O(N))
    t2 = time.perf_counter()
    bf_overlap_count = 0
    for q_start, q_end in sample_queries:
        # Half open [q_start, q_end) overlapping [dep, arr) iff max(q_start, dep) < min(q_end, arr)
        bf_matches = [
            f for f in flights_data
            if max(q_start, f["departure_utc"]) < min(q_end, f["arrival_utc"])
        ]
        bf_overlap_count += len(bf_matches)
    bf_duration_ms = (time.perf_counter() - t2) * 1000.0
    avg_bf_query_us = (bf_duration_ms * 1000.0) / queries_count

    speedup = bf_duration_ms / itree_duration_ms if itree_duration_ms > 0 else 1.0

    return {
        "n_items": len(flights_data),
        "tree_size": len(itree),
        "insert_time_ms": round(insert_duration_ms, 3),
        "queries_count": queries_count,
        "itree_total_ms": round(itree_duration_ms, 3),
        "avg_itree_query_us": round(avg_itree_query_us, 3),
        "brute_force_total_ms": round(bf_duration_ms, 3),
        "avg_bf_query_us": round(avg_bf_query_us, 3),
        "speedup_factor": round(speedup, 2),
    }


def benchmark_graph(flights_data: List[Dict[str, Any]], searches_count: int = 50) -> Dict[str, Any]:
    """Benchmark FlightConnectionGraph Dijkstra positioning searches across scaling flight networks."""
    graph = FlightConnectionGraph(
        min_connection_seconds=45 * 60,
        max_connection_seconds=240 * 60,
        hop_penalty_seconds=30 * 60,
    )

    # Convert flight dicts to FlightLeg domain models
    legs = [
        FlightLeg(
            flight_number=f["flight_number"],
            origin=f["origin"],
            destination=f["destination"],
            departure_utc=f["departure_utc"],
            arrival_utc=f["arrival_utc"],
            aircraft_tail=f.get("aircraft_tail", "VT-NVA"),
            required_aircraft_type=f.get("required_aircraft_type", "A320"),
        )
        for f in flights_data
    ]

    t0 = time.perf_counter()
    graph.rebuild_from_flights(legs)
    build_duration_ms = (time.perf_counter() - t0) * 1000.0

    # Pick origin/destination airport pairs
    airports = sorted(list({leg.origin for leg in legs} | {leg.destination for leg in legs}))
    deps = [leg.departure_utc for leg in legs]
    min_dep = min(deps)

    random.seed(42)
    pairs = []
    for _ in range(searches_count):
        orig, dest = random.sample(airports, 2)
        pairs.append((orig, dest))

    t1 = time.perf_counter()
    paths_found = 0
    for orig, dest in pairs:
        path = graph.find_shortest_positioning_path(orig, min_dep, dest)
        if path is not None:
            paths_found += 1
    dijkstra_duration_ms = (time.perf_counter() - t1) * 1000.0
    avg_dijkstra_us = (dijkstra_duration_ms * 1000.0) / searches_count

    diag = graph.get_diagnostics()

    return {
        "n_flights": len(flights_data),
        "vertex_count": diag["vertex_count"],
        "edge_count": diag["edge_count"],
        "avg_out_degree": diag["avg_out_degree"],
        "max_out_degree": diag["max_out_degree"],
        "build_duration_ms": round(build_duration_ms, 3),
        "searches_count": searches_count,
        "paths_found": paths_found,
        "dijkstra_total_ms": round(dijkstra_duration_ms, 3),
        "avg_dijkstra_us": round(avg_dijkstra_us, 3),
    }


def run_all_benchmarks(scales: List[int] = [100, 500, 1000, 2500]) -> Dict[str, Any]:
    """Execute complete benchmark suite across all scaling workloads."""
    print("=" * 80)
    print("AirCrewOps | Nova Air Advanced Data Structures Scaling Benchmark Suite")
    print(f"Workload scales N in {scales}")
    print("=" * 80)

    results: Dict[str, Any] = {
        "metadata": {
            "timestamp": int(time.time()),
            "python_version": sys.version,
            "scales": scales,
        },
        "hash_table": {},
        "btree": {},
        "interval_tree": {},
        "graph": {},
    }

    for scale in scales:
        print(f"\n---> Generating synthetic benchmark dataset with scale N={scale}...")
        _airports, _aircraft, _mnt, _crew, _quals, flights, _duties = generate_benchmark_profile(scale=scale, seed=42)
        print(f"Generated {len(flights)} flight legs. Running ADS benchmarks...")

        # 1. Hash Table
        ht_res = benchmark_hash_table(flights, lookups_count=1000)
        results["hash_table"][str(scale)] = ht_res
        print(f"  [HashTable] N={scale:4d}: Load={ht_res['load_factor']:.2f}, MaxChain={ht_res['max_chain_length']}, "
              f"AvgLookup={ht_res['avg_lookup_latency_us']:.2f} us")

        # 2. B-Tree
        btree_res = benchmark_btree(flights, queries_count=100)
        results["btree"][str(scale)] = btree_res
        print(f"  [B-Tree]    N={scale:4d}: 3h RangeQuery={btree_res['avg_btree_query_us']:.2f} us vs "
              f"Linear={btree_res['avg_linear_query_us']:.2f} us (Speedup: {btree_res['speedup_factor']}x)")

        # 3. Interval Tree
        itree_res = benchmark_interval_tree(flights, queries_count=100)
        results["interval_tree"][str(scale)] = itree_res
        print(f"  [Interval]  N={scale:4d}: OverlapQuery={itree_res['avg_itree_query_us']:.2f} us vs "
              f"BruteForce={itree_res['avg_bf_query_us']:.2f} us (Speedup: {itree_res['speedup_factor']}x)")

        # 4. Graph Dijkstra
        graph_res = benchmark_graph(flights, searches_count=50)
        results["graph"][str(scale)] = graph_res
        print(f"  [Graph]     N={scale:4d}: Vertices={graph_res['vertex_count']}, Edges={graph_res['edge_count']}, "
              f"AvgDijkstra={graph_res['avg_dijkstra_us']:.2f} us")

    # Save to JSON
    output_path = REPO_ROOT / "benchmarks" / "latest_benchmark_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n[OK] Benchmark results written to {output_path}")
    return results


if __name__ == "__main__":
    run_all_benchmarks()
