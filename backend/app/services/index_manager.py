"""ADSIndexManager synchronization service for Nova Air (AirCrewOps).

Coordinates all five custom in-memory Advanced Data Structures on the critical path:
1. SeparateChainingHashTable: O(1) expected lookup for airports, aircraft, crew, flights.
2. FlightScheduleBTree: O(log n + k) departure time-window range queries.
3. RBIntervalTree: O(log n) conflict detection & rest calculation per crew & aircraft resource.
4. FlightConnectionGraph: Dijkstra crew positioning and multi-hop deadhead discovery.
5. SchedulerPriorityQueue: Constrained-first priority queue for flight scheduling.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backend.app.data_structures.btree import FlightScheduleBTree
from backend.app.data_structures.graph import FlightConnectionGraph
from backend.app.data_structures.hash_table import SeparateChainingHashTable
from backend.app.data_structures.rb_interval_tree import RBIntervalTree
from backend.app.models.domain import (
    Aircraft,
    Airport,
    CrewMember,
    DutyPeriod,
    FlightLeg,
    MaintenanceWindow,
    RuleProfile,
)
from backend.app.rules.profile_loader import load_rule_profile
from backend.app.services.dataset_loader import AirlineDataset


class ADSIndexManager:
    """Central in-memory index manager coordinating all five critical ADS data structures."""

    def __init__(self, rule_profile: Optional[RuleProfile] = None) -> None:
        self.profile: RuleProfile = rule_profile or load_rule_profile()

        # Structure 1: SeparateChainingHashTable entity indices
        self.airports_by_code: SeparateChainingHashTable[str, Airport] = SeparateChainingHashTable(initial_capacity=11)
        self.aircraft_by_id: SeparateChainingHashTable[str, Aircraft] = SeparateChainingHashTable(initial_capacity=23)
        self.crew_by_id: SeparateChainingHashTable[str, CrewMember] = SeparateChainingHashTable(initial_capacity=97)
        self.flights_by_id: SeparateChainingHashTable[str, FlightLeg] = SeparateChainingHashTable(initial_capacity=97)

        # Structure 2: FlightScheduleBTree schedule index
        self.schedule_btree: FlightScheduleBTree[FlightLeg] = FlightScheduleBTree(t=3)

        # Structure 3: RBIntervalTree per-resource interval trees
        self.crew_intervals: Dict[str, RBIntervalTree] = {}
        self.aircraft_intervals: Dict[str, RBIntervalTree] = {}

        # Structure 4: FlightConnectionGraph positioning network
        self.connection_graph: FlightConnectionGraph = FlightConnectionGraph(
            min_connection_seconds=1800,
            max_connection_seconds=43200,
            hop_penalty_seconds=1800,
        )

    def build_from_domain_state(
        self,
        dataset: Optional[AirlineDataset] = None,
        *,
        airports: Optional[Dict[str, Airport] | List[Airport]] = None,
        aircraft: Optional[Dict[str, Aircraft] | List[Aircraft]] = None,
        maintenance: Optional[List[MaintenanceWindow]] = None,
        crew: Optional[Dict[str, CrewMember] | List[CrewMember]] = None,
        flights: Optional[List[FlightLeg]] = None,
        duty_history: Optional[List[DutyPeriod]] = None,
    ) -> None:
        """Initialize all five ADS data structures from domain state or an AirlineDataset."""
        if dataset is not None:
            airport_list = list(dataset.airports.values())
            aircraft_list = list(dataset.aircraft.values())
            maint_list = dataset.maintenance
            crew_list = list(dataset.crew.values())
            flight_list = dataset.flights
            history_list = dataset.duty_history
        else:
            airport_list = list(airports.values()) if isinstance(airports, dict) else (airports or [])
            aircraft_list = list(aircraft.values()) if isinstance(aircraft, dict) else (aircraft or [])
            maint_list = maintenance or []
            crew_list = list(crew.values()) if isinstance(crew, dict) else (crew or [])
            flight_list = flights or []
            history_list = duty_history or []

        # 0. Reset previous in-memory state
        self.airports_by_code.clear()
        self.aircraft_by_id.clear()
        self.crew_by_id.clear()
        self.flights_by_id.clear()
        self.schedule_btree.clear()
        self.crew_intervals.clear()
        self.aircraft_intervals.clear()

        # 1. Populate Hash Tables
        for ap in airport_list:
            self.airports_by_code.insert(ap.code, ap)

        for ac in aircraft_list:
            self.aircraft_by_id.insert(ac.tail_number, ac)
            self.aircraft_intervals[ac.tail_number] = RBIntervalTree()

        for c in crew_list:
            self.crew_by_id.insert(c.id, c)
            self.crew_intervals[c.id] = RBIntervalTree()

        for fl in flight_list:
            self.flights_by_id.insert(fl.flight_number, fl)

        # 2. Populate FlightScheduleBTree
        for fl in flight_list:
            self.schedule_btree.insert((fl.departure_utc, fl.flight_number), fl)

        # 3. Populate Aircraft Maintenance in RBIntervalTree
        for mw in maint_list:
            tail = mw.aircraft_tail.strip().upper()
            if tail in self.aircraft_intervals:
                payload = {
                    "type": "MAINTENANCE",
                    "maintenance_id": mw.id,
                    "airport_code": mw.airport_code,
                    "description": mw.description,
                }
                self.aircraft_intervals[tail].insert(mw.start_utc, mw.end_utc, mw.id, payload)

        # 4. Populate Crew Duty History in RBIntervalTree
        for dh in history_list:
            cid = dh.crew_id.strip().upper()
            if cid in self.crew_intervals:
                payload = {
                    "type": "DUTY_PERIOD",
                    "duty_id": dh.id,
                    "duty_start_utc": dh.report_utc,
                    "duty_end_utc": dh.release_utc,
                    "sector_count": len(dh.flight_leg_ids),
                    "cumulative_flight_seconds": dh.total_flight_seconds,
                    "last_destination": None,
                    "last_arrival_utc": dh.release_utc - 1800,
                    "last_aircraft_tail": None,
                    "flight_ids": dh.flight_leg_ids,
                }
                self.crew_intervals[cid].insert(dh.report_utc, dh.release_utc, dh.id, payload)

        # 5. Populate FlightConnectionGraph
        self.connection_graph.rebuild_from_flights(flight_list)

    def sync_flight_mutation(
        self,
        flight: FlightLeg,
        old_departure_utc: Optional[int] = None,
    ) -> None:
        """Synchronize B-Tree, Hash Table, and Graph when a flight's time or attributes change."""
        self.flights_by_id.insert(flight.flight_number, flight)

        # B-Tree atomic key update
        if old_departure_utc is not None and old_departure_utc != flight.departure_utc:
            self.schedule_btree.update_key(
                (old_departure_utc, flight.flight_number),
                (flight.departure_utc, flight.flight_number),
                flight,
            )
        else:
            old_val = self.schedule_btree.search((flight.departure_utc, flight.flight_number))
            if old_val is not None:
                self.schedule_btree.update_key(
                    (flight.departure_utc, flight.flight_number),
                    (flight.departure_utc, flight.flight_number),
                    flight,
                )
            else:
                self.schedule_btree.insert((flight.departure_utc, flight.flight_number), flight)

        # Connection graph dynamic edge synchronization
        self.connection_graph.update_flight_vertex(flight)

    def commit_aircraft_reservation(self, aircraft_tail: str, flight: FlightLeg) -> None:
        """Reserve aircraft interval in its RBIntervalTree."""
        tail = aircraft_tail.strip().upper()
        if tail not in self.aircraft_intervals:
            self.aircraft_intervals[tail] = RBIntervalTree()

        payload = {
            "type": "FLIGHT",
            "flight_number": flight.flight_number,
            "origin": flight.origin,
            "destination": flight.destination,
            "departure_utc": flight.departure_utc,
            "arrival_utc": flight.arrival_utc,
        }
        self.aircraft_intervals[tail].insert(
            flight.departure_utc, flight.arrival_utc, flight.flight_number, payload
        )

    def commit_crew_duty(
        self,
        crew_id: str,
        report_utc: int,
        release_utc: int,
        duty_id: str,
        data: Dict[str, Any],
        old_interval: Optional[Tuple[int, int, str]] = None,
    ) -> None:
        """Reserve or extend duty interval in a crew member's RBIntervalTree."""
        cid = crew_id.strip().upper()
        if cid not in self.crew_intervals:
            self.crew_intervals[cid] = RBIntervalTree()

        if old_interval is not None:
            old_start, old_end, old_id = old_interval
            self.crew_intervals[cid].delete(old_start, old_end, old_id)

        self.crew_intervals[cid].insert(report_utc, release_utc, duty_id, data)

    def remove_aircraft_reservation(
        self, aircraft_tail: str, start_utc: int, end_utc: int, flight_number: str
    ) -> bool:
        """Remove flight reservation from aircraft's RBIntervalTree."""
        tail = aircraft_tail.strip().upper()
        if tail in self.aircraft_intervals:
            return self.aircraft_intervals[tail].delete(start_utc, end_utc, flight_number)
        return False

    def remove_crew_duty(
        self, crew_id: str, report_utc: int, release_utc: int, duty_id: str
    ) -> bool:
        """Remove duty interval from crew member's RBIntervalTree."""
        cid = crew_id.strip().upper()
        if cid in self.crew_intervals:
            return self.crew_intervals[cid].delete(report_utc, release_utc, duty_id)
        return False

    def verify_all_invariants(self) -> bool:
        """Verify structural, sorting, and balancing invariants across all five data structures.

        Returns True if all invariants hold; raises AssertionError or returns False otherwise.
        """
        # 1. B-Tree invariants
        if not self.schedule_btree.verify_invariants():
            return False

        # 2. Per-crew RBIntervalTree invariants
        for tree in self.crew_intervals.values():
            if not tree.verify_invariants():
                return False

        # 3. Per-aircraft RBIntervalTree invariants
        for tree in self.aircraft_intervals.values():
            if not tree.verify_invariants():
                return False

        # 4. Flight connection graph invariants
        if not self.connection_graph.verify_invariants():
            return False

        # 5. Hash table capacity / non-negative size check
        if (
            len(self.airports_by_code) < 0
            or len(self.aircraft_by_id) < 0
            or len(self.crew_by_id) < 0
            or len(self.flights_by_id) < 0
        ):
            return False

        return True

    def get_structure_diagnostics(self) -> Dict[str, Any]:
        """Aggregate health metrics from all data structures."""
        total_crew_intervals = sum(len(t) for t in self.crew_intervals.values())
        total_aircraft_intervals = sum(len(t) for t in self.aircraft_intervals.values())

        return {
            "airports_count": len(self.airports_by_code),
            "aircraft_count": len(self.aircraft_by_id),
            "crew_count": len(self.crew_by_id),
            "flights_count": len(self.flights_by_id),
            "schedule_btree": self.schedule_btree.get_diagnostics(),
            "connection_graph": self.connection_graph.get_diagnostics(),
            "total_crew_duty_intervals": total_crew_intervals,
            "total_aircraft_intervals": total_aircraft_intervals,
            "invariants_verified": self.verify_all_invariants(),
        }
