"""Time-Feasible Flight-Connection Graph with Dijkstra Positioning Search.

This module implements Structure 4 of the AirCrewOps Advanced Data Structures:
an explicit directed multigraph (FlightConnectionGraph) indexing active Nova Air
flight legs as vertices and feasible airport transfers as directed edges.

Key Design Principles:
1. Vertex: FlightLeg entity with arrival and departure timestamps in UTC epoch seconds.
2. Directed Edge (u -> v): Feasible transfer where u.destination == v.origin and
   min_connection_seconds <= v.departure_utc - u.arrival_utc <= max_connection_seconds.
3. Edge Weight: Non-negative elapsed time (v.arrival_utc - u.arrival_utc) + hop_penalty_seconds.
   Negative or non-finite weights are strictly rejected.
4. Dynamic Synchronization: rebuild_from_flights and update_flight_vertex ensure that
   delays and edits refresh incident edges immediately without leaving stale connections.
5. Dijkstra Positioning: find_shortest_positioning_path finds minimum-elapsed-time
   crew positioning paths using an ephemeral virtual source without mutating shared graph vertices.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.models.domain import FlightLeg


@dataclass(frozen=True)
class ConnectionEdge:
    """Directed connection from flight u to flight v."""
    from_flight_id: str
    to_flight_id: str
    departure_utc: int
    arrival_utc: int
    layover_seconds: int
    weight: int

    def __post_init__(self) -> None:
        if math.isnan(self.weight) or math.isinf(self.weight) or self.weight < 0:
            raise ValueError(f"Edge weight must be finite and non-negative, got {self.weight}")


@dataclass
class PositioningPath:
    """Result of crew deadhead positioning search."""
    origin_airport: str
    target_airport: str
    flights: List[FlightLeg]
    total_elapsed_seconds: int
    total_flight_seconds: int
    total_layover_seconds: int
    total_weight: int
    hop_count: int

    @property
    def is_direct(self) -> bool:
        return self.hop_count == 1


class FlightConnectionGraph:
    """Time-feasible directed connection graph for Nova Air flight legs."""

    def __init__(
        self,
        min_connection_seconds: int = 1800,  # 30 minutes minimum turnaround/transfer
        max_connection_seconds: int = 43200,  # 12 hours maximum layover
        hop_penalty_seconds: int = 1800,     # 30 minutes penalty per layover transfer
    ) -> None:
        if min_connection_seconds < 0 or max_connection_seconds < min_connection_seconds:
            raise ValueError("Invalid connection window bounds")
        if hop_penalty_seconds < 0:
            raise ValueError("hop_penalty_seconds must be non-negative")

        self.min_connection_seconds: int = min_connection_seconds
        self.max_connection_seconds: int = max_connection_seconds
        self.hop_penalty_seconds: int = hop_penalty_seconds

        # Vertices: flight_id -> FlightLeg
        self.vertices: Dict[str, FlightLeg] = {}
        # Forward Adjacency: flight_id -> list of outgoing ConnectionEdge
        self.adj: Dict[str, List[ConnectionEdge]] = {}
        # Reverse Adjacency: flight_id -> set of predecessor flight_ids
        self.incoming: Dict[str, Set[str]] = {}

        # Airport index helpers: airport -> list of flight_ids
        self._flights_by_origin: Dict[str, Set[str]] = {}
        self._flights_by_dest: Dict[str, Set[str]] = {}

    def __len__(self) -> int:
        return len(self.vertices)

    def is_empty(self) -> bool:
        return len(self.vertices) == 0

    def compute_edge_weight(self, u: FlightLeg, v: FlightLeg) -> int:
        """Compute connection edge weight: total elapsed time + hop penalty.

        Raises:
            ValueError: If connection is infeasible, negative, or non-finite.
        """
        if u.destination != v.origin:
            raise ValueError(f"Incompatible airport transfer: {u.destination} != {v.origin}")

        layover = v.departure_utc - u.arrival_utc
        if not (self.min_connection_seconds <= layover <= self.max_connection_seconds):
            raise ValueError(
                f"Connection layover {layover}s outside feasible window "
                f"[{self.min_connection_seconds}, {self.max_connection_seconds}]"
            )

        elapsed = v.arrival_utc - u.arrival_utc
        weight = elapsed + self.hop_penalty_seconds
        if math.isnan(weight) or math.isinf(weight) or weight < 0:
            raise ValueError(f"Invalid edge weight computed: {weight}")
        return weight

    def _index_flight_airport(self, flight: FlightLeg) -> None:
        """Register flight in origin/destination airport lookup tables."""
        fid = flight.flight_number
        self._flights_by_origin.setdefault(flight.origin, set()).add(fid)
        self._flights_by_dest.setdefault(flight.destination, set()).add(fid)

    def _unindex_flight_airport(self, flight: FlightLeg) -> None:
        """Remove flight from origin/destination airport lookup tables."""
        fid = flight.flight_number
        if flight.origin in self._flights_by_origin:
            self._flights_by_origin[flight.origin].discard(fid)
            if not self._flights_by_origin[flight.origin]:
                del self._flights_by_origin[flight.origin]
        if flight.destination in self._flights_by_dest:
            self._flights_by_dest[flight.destination].discard(fid)
            if not self._flights_by_dest[flight.destination]:
                del self._flights_by_dest[flight.destination]

    def add_flight(self, flight: FlightLeg) -> None:
        """Add or replace a flight vertex and construct incident connection edges."""
        fid = flight.flight_number
        if fid in self.vertices:
            self.remove_flight(fid)

        self.vertices[fid] = flight
        self.adj[fid] = []
        self.incoming[fid] = set()
        self._index_flight_airport(flight)

        # 1. Connect existing flights arriving at flight.origin to this new flight
        predecessor_ids = self._flights_by_dest.get(flight.origin, set())
        for pred_id in predecessor_ids:
            if pred_id == fid:
                continue
            pred = self.vertices[pred_id]
            layover = flight.departure_utc - pred.arrival_utc
            if self.min_connection_seconds <= layover <= self.max_connection_seconds:
                weight = (flight.arrival_utc - pred.arrival_utc) + self.hop_penalty_seconds
                edge = ConnectionEdge(
                    from_flight_id=pred_id,
                    to_flight_id=fid,
                    departure_utc=flight.departure_utc,
                    arrival_utc=flight.arrival_utc,
                    layover_seconds=layover,
                    weight=weight,
                )
                self.adj[pred_id].append(edge)
                self.incoming[fid].add(pred_id)

        # 2. Connect this new flight to existing flights departing from flight.destination
        successor_ids = self._flights_by_origin.get(flight.destination, set())
        for succ_id in successor_ids:
            if succ_id == fid:
                continue
            succ = self.vertices[succ_id]
            layover = succ.departure_utc - flight.arrival_utc
            if self.min_connection_seconds <= layover <= self.max_connection_seconds:
                weight = (succ.arrival_utc - flight.arrival_utc) + self.hop_penalty_seconds
                edge = ConnectionEdge(
                    from_flight_id=fid,
                    to_flight_id=succ_id,
                    departure_utc=succ.departure_utc,
                    arrival_utc=succ.arrival_utc,
                    layover_seconds=layover,
                    weight=weight,
                )
                self.adj[fid].append(edge)
                self.incoming[succ_id].add(fid)

    def remove_flight(self, flight_id: str) -> bool:
        """Remove a flight vertex and all its incoming and outgoing edges."""
        if flight_id not in self.vertices:
            return False

        flight = self.vertices[flight_id]
        self._unindex_flight_airport(flight)

        # Remove outgoing edges: clean incoming sets of successors
        for edge in self.adj.get(flight_id, []):
            if edge.to_flight_id in self.incoming:
                self.incoming[edge.to_flight_id].discard(flight_id)

        # Remove incoming edges: clean adj lists of predecessors
        for pred_id in self.incoming.get(flight_id, set()):
            if pred_id in self.adj:
                self.adj[pred_id] = [e for e in self.adj[pred_id] if e.to_flight_id != flight_id]

        del self.vertices[flight_id]
        del self.adj[flight_id]
        del self.incoming[flight_id]
        return True

    def update_flight_vertex(self, flight: FlightLeg) -> None:
        """Update a flight leg (e.g. after delay or gate change) and refresh incident edges."""
        self.add_flight(flight)

    def rebuild_from_flights(self, flights: List[FlightLeg]) -> None:
        """Reconstruct the entire graph from a list of flight legs."""
        self.vertices.clear()
        self.adj.clear()
        self.incoming.clear()
        self._flights_by_origin.clear()
        self._flights_by_dest.clear()

        for flight in flights:
            self.add_flight(flight)

    def find_shortest_positioning_path(
        self,
        origin_airport: str,
        earliest_available_utc: int,
        target_airport: str,
        latest_arrival_utc: Optional[int] = None,
    ) -> Optional[PositioningPath]:
        """Find minimum-elapsed-time positioning path using Dijkstra with virtual source.

        Args:
            origin_airport: Departure aerodrome code (e.g. 'BOM').
            earliest_available_utc: Epoch seconds when crew is available to depart.
            target_airport: Destination aerodrome code (e.g. 'DEL').
            latest_arrival_utc: Optional deadline by which crew must arrive.

        Returns:
            PositioningPath containing the flight legs and time breakdown, or None if no path.
        """
        origin_norm = origin_airport.strip().upper()
        target_norm = target_airport.strip().upper()

        if origin_norm == target_norm:
            return PositioningPath(
                origin_airport=origin_norm,
                target_airport=target_norm,
                flights=[],
                total_elapsed_seconds=0,
                total_flight_seconds=0,
                total_layover_seconds=0,
                total_weight=0,
                hop_count=0,
            )

        # Seed Dijkstra from ephemeral virtual source
        # Min-heap items: (cumulative_weight, arrival_utc, flight_id, path_flight_ids)
        pq: List[Tuple[int, int, str, List[str]]] = []

        candidate_first_flights = self._flights_by_origin.get(origin_norm, set())
        for fid in candidate_first_flights:
            f = self.vertices[fid]
            if f.departure_utc >= earliest_available_utc:
                if latest_arrival_utc is not None and f.arrival_utc > latest_arrival_utc:
                    continue
                # Initial weight: elapsed time from availability to arrival of first leg
                initial_weight = f.arrival_utc - earliest_available_utc
                heapq.heappush(pq, (initial_weight, f.arrival_utc, fid, [fid]))

        # Best distance map: flight_id -> minimum cumulative weight
        best_dist: Dict[str, int] = {}
        best_target_path: Optional[PositioningPath] = None
        min_target_weight: int = 1 << 62

        while pq:
            curr_weight, curr_arr, curr_fid, path = heapq.heappop(pq)

            if curr_fid in best_dist and best_dist[curr_fid] <= curr_weight:
                continue
            best_dist[curr_fid] = curr_weight

            curr_flight = self.vertices[curr_fid]

            # Check if this flight reached the target aerodrome
            if curr_flight.destination == target_norm:
                if curr_weight < min_target_weight:
                    min_target_weight = curr_weight
                    flight_objs = [self.vertices[f_id] for f_id in path]
                    tot_flight = sum(f.flight_duration_seconds for f in flight_objs)
                    tot_layover = sum(
                        flight_objs[i + 1].departure_utc - flight_objs[i].arrival_utc
                        for i in range(len(flight_objs) - 1)
                    )
                    tot_elapsed = curr_flight.arrival_utc - earliest_available_utc

                    best_target_path = PositioningPath(
                        origin_airport=origin_norm,
                        target_airport=target_norm,
                        flights=flight_objs,
                        total_elapsed_seconds=tot_elapsed,
                        total_flight_seconds=tot_flight,
                        total_layover_seconds=tot_layover,
                        total_weight=curr_weight,
                        hop_count=len(flight_objs),
                    )
                # Since edge weights are strictly positive, the first target reached via Dijkstra
                # is optimal for non-delayed departures. Return immediately.
                return best_target_path

            # Explore outgoing connection edges
            for edge in self.adj.get(curr_fid, []):
                next_fid = edge.to_flight_id
                next_flight = self.vertices[next_fid]

                if latest_arrival_utc is not None and next_flight.arrival_utc > latest_arrival_utc:
                    continue

                new_weight = curr_weight + edge.weight
                if next_fid not in best_dist or new_weight < best_dist[next_fid]:
                    heapq.heappush(pq, (new_weight, next_flight.arrival_utc, next_fid, path + [next_fid]))

        return best_target_path

    def get_diagnostics(self) -> Dict[str, Any]:
        """Compute graph structural and topological metrics."""
        total_vertices = len(self.vertices)
        total_edges = sum(len(edges) for edges in self.adj.values())
        out_degrees = [len(edges) for edges in self.adj.values()] if total_vertices > 0 else [0]

        return {
            "vertex_count": total_vertices,
            "edge_count": total_edges,
            "min_connection_seconds": self.min_connection_seconds,
            "max_connection_seconds": self.max_connection_seconds,
            "hop_penalty_seconds": self.hop_penalty_seconds,
            "avg_out_degree": round(total_edges / max(1, total_vertices), 2),
            "max_out_degree": max(out_degrees),
            "invariants_valid": self.verify_invariants(),
        }

    def verify_invariants(self) -> bool:
        """Verify graph structural, topological, and weight invariants."""
        # 1. Vertex consistency
        for fid, flight in self.vertices.items():
            if fid != flight.flight_number:
                return False
            if fid not in self.adj or fid not in self.incoming:
                return False

        # 2. Edge consistency
        for u_id, edges in self.adj.items():
            if u_id not in self.vertices:
                return False
            u = self.vertices[u_id]
            for edge in edges:
                if edge.from_flight_id != u_id:
                    return False
                v_id = edge.to_flight_id
                if v_id not in self.vertices:
                    return False
                v = self.vertices[v_id]
                # Connection feasibility
                if u.destination != v.origin:
                    return False
                layover = v.departure_utc - u.arrival_utc
                if not (self.min_connection_seconds <= layover <= self.max_connection_seconds):
                    return False
                # Weight validity
                expected_weight = (v.arrival_utc - u.arrival_utc) + self.hop_penalty_seconds
                if edge.weight != expected_weight or edge.weight < 0:
                    return False
                # Reverse adjacency consistency
                if u_id not in self.incoming.get(v_id, set()):
                    return False

        # 3. Reverse index consistency
        for v_id, preds in self.incoming.items():
            if v_id not in self.vertices:
                return False
            for p_id in preds:
                if p_id not in self.vertices:
                    return False
                if not any(e.to_flight_id == v_id for e in self.adj.get(p_id, [])):
                    return False

        return True
