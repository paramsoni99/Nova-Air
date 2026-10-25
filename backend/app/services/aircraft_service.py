"""AircraftService domain service for Nova Air fleet management and rotation inspection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from backend.app.models.domain import Aircraft
from backend.app.services.index_manager import ADSIndexManager
from backend.app.services.persistence_service import PersistenceService


class AircraftService:
    """Provides high-level queries and rotation timeline lookups for Nova Air fleet."""

    def __init__(
        self,
        index_manager: ADSIndexManager,
        persistence_service: Optional[PersistenceService] = None,
    ) -> None:
        self.index_manager: ADSIndexManager = index_manager
        self.persistence: Optional[PersistenceService] = persistence_service

    def list_aircraft(
        self,
        aircraft_type: Optional[str] = None,
        home_base: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Aircraft]:
        """List aircraft matching optional filters."""
        all_ac: List[Aircraft] = list(self.index_manager.aircraft_by_id.values())
        results: List[Aircraft] = []

        for ac in all_ac:
            if active_only and not ac.is_active:
                continue
            if aircraft_type and ac.aircraft_type.upper() != aircraft_type.upper():
                continue
            if home_base and ac.home_base != home_base.upper():
                continue
            results.append(ac)

        results.sort(key=lambda x: x.tail_number)
        return results

    def get_aircraft(self, tail_number: str) -> Optional[Aircraft]:
        """Retrieve aircraft by registration tail number."""
        return self.index_manager.aircraft_by_id.get(tail_number.upper())

    def get_aircraft_rotation(self, tail_number: str) -> Dict[str, Any]:
        """Retrieve active flight and maintenance timeline from in-memory RBIntervalTree."""
        tail = tail_number.upper()
        ac = self.get_aircraft(tail)
        if ac is None:
            raise KeyError(f"Aircraft '{tail}' not found")

        tree = self.index_manager.aircraft_intervals.get(tail)
        intervals: List[Dict[str, Any]] = []
        if tree is not None:
            for node in tree.inorder_traversal():
                intervals.append({
                    "interval_id": node.interval_id,
                    "start_utc": node.start_utc,
                    "end_utc": node.end_utc,
                    "duration_seconds": node.end_utc - node.start_utc,
                    "data": node.data,
                })

        return {
            "tail_number": ac.tail_number,
            "aircraft_type": ac.aircraft_type,
            "home_base": ac.home_base,
            "seating_capacity": ac.seating_capacity,
            "total_flight_hours": ac.total_flight_hours,
            "is_active": ac.is_active,
            "intervals": intervals,
        }
