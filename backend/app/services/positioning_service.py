"""PositioningService for Nova Air Crew Deadhead Route Discovery.

Coordinates crew positioning using the Time-Feasible Flight-Connection Graph (Dijkstra)
to deadhead crew members to their assigned departure airports in compliance with FDTL limits.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backend.app.data_structures.graph import FlightConnectionGraph, PositioningPath
from backend.app.data_structures.rb_interval_tree import RBIntervalTree
from backend.app.models.domain import CrewMember, CrewRole, FlightLeg, PositioningItinerary, RuleProfile
from backend.app.rules.profile_loader import load_rule_profile


class PositioningService:
    """Service for discovering and evaluating crew deadhead positioning routes."""

    def __init__(
        self,
        graph: FlightConnectionGraph,
        rule_profile: Optional[RuleProfile] = None,
    ) -> None:
        self.graph: FlightConnectionGraph = graph
        self.profile: RuleProfile = rule_profile or load_rule_profile()

    def find_positioning_path(
        self,
        origin_airport: str,
        target_airport: str,
        earliest_available_utc: int,
        latest_arrival_utc: Optional[int] = None,
    ) -> Optional[PositioningPath]:
        """Find the minimum-elapsed-time positioning path between two aerodromes."""
        return self.graph.find_shortest_positioning_path(
            origin_airport=origin_airport,
            earliest_available_utc=earliest_available_utc,
            target_airport=target_airport,
            latest_arrival_utc=latest_arrival_utc,
        )

    def find_positioning_itinerary(
        self,
        crew: CrewMember,
        target_airport: str,
        required_arrival_utc: int,
        earliest_available_utc: Optional[int] = None,
    ) -> Optional[PositioningItinerary]:
        """Find a positioning itinerary for a crew member to reach target_airport.

        Returns:
            PositioningItinerary if a valid path exists, or None if already in position
            or if no time-feasible path exists.
        """
        origin = crew.current_airport.strip().upper()
        destination = target_airport.strip().upper()

        # Already at destination
        if origin == destination:
            return None

        # Determine earliest available time
        if earliest_available_utc is not None:
            earliest_dep = earliest_available_utc
        elif crew.last_duty_end_utc is not None:
            rules = (
                self.profile.cabin_crew_rules
                if crew.role == CrewRole.CABIN_CREW
                else self.profile.flight_crew_rules
            )
            earliest_dep = crew.last_duty_end_utc + rules.min_inter_duty_rest_seconds
        else:
            earliest_dep = 0

        path = self.graph.find_shortest_positioning_path(
            origin_airport=origin,
            earliest_available_utc=earliest_dep,
            target_airport=destination,
            latest_arrival_utc=required_arrival_utc,
        )

        if path is None or not path.flights:
            return None

        return PositioningItinerary(
            crew_id=crew.id,
            origin=origin,
            destination=destination,
            flight_legs=[f.flight_number for f in path.flights],
            departure_utc=path.flights[0].departure_utc,
            arrival_utc=path.flights[-1].arrival_utc,
        )
