"""CrewService domain service for Nova Air crew management and schedule inspection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from backend.app.models.domain import CrewMember, CrewRole
from backend.app.services.index_manager import ADSIndexManager
from backend.app.services.persistence_service import PersistenceService


class CrewService:
    """Provides high-level queries and schedule lookups for flight and cabin crew."""

    def __init__(
        self,
        index_manager: ADSIndexManager,
        persistence_service: Optional[PersistenceService] = None,
    ) -> None:
        self.index_manager: ADSIndexManager = index_manager
        self.persistence: Optional[PersistenceService] = persistence_service

    def list_crew(
        self,
        role: Optional[CrewRole | str] = None,
        base: Optional[str] = None,
        current_airport: Optional[str] = None,
        active_only: bool = True,
    ) -> List[CrewMember]:
        """List crew members matching optional filters."""
        all_crew: List[CrewMember] = list(self.index_manager.crew_by_id.values())
        results: List[CrewMember] = []

        target_role = CrewRole(str(role).upper()) if role else None

        for c in all_crew:
            if active_only and not c.is_active:
                continue
            if target_role and c.role != target_role:
                continue
            if base and c.home_base != base.upper():
                continue
            if current_airport and c.current_airport != current_airport.upper():
                continue
            results.append(c)

        results.sort(key=lambda x: x.id)
        return results

    def get_crew_member(self, crew_id: str) -> Optional[CrewMember]:
        """Retrieve crew member by unique ID."""
        return self.index_manager.crew_by_id.get(crew_id.upper())

    def get_crew_schedule(self, crew_id: str) -> Dict[str, Any]:
        """Retrieve active intervals and duty timeline from in-memory RBIntervalTree."""
        cid = crew_id.upper()
        crew = self.get_crew_member(cid)
        if crew is None:
            raise KeyError(f"Crew member '{cid}' not found")

        tree = self.index_manager.crew_intervals.get(cid)
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
            "crew_id": crew.id,
            "name": crew.name,
            "role": crew.role.value,
            "home_base": crew.home_base,
            "current_airport": crew.current_airport,
            "cumulative_flight_seconds_7d": crew.cumulative_flight_seconds_7d,
            "cumulative_duty_seconds_7d": crew.cumulative_duty_seconds_7d,
            "last_duty_end_utc": crew.last_duty_end_utc,
            "is_active": crew.is_active,
            "qualifications": [q.model_dump() for q in crew.qualifications],
            "intervals": intervals,
        }
