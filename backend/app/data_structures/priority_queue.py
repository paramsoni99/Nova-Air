"""Scheduler Priority Queue for Nova Air Constrained-First Flight Scheduling.

This module implements Structure 5 of the AirCrewOps Advanced Data Structures:
a deterministic binary min-heap priority queue (SchedulerPriorityQueue) designed
for ordering unassigned flight legs by scheduling tightness and disruption urgency.

Key Design Principles:
1. Multi-Criterion Scheduling Priority:
   Keyed by: (feasible_combinations, departure_utc, slack_minutes, -disruption_severity, flight_id)
   - feasible_combinations: fewest legal crew combinations first (Most Constrained Variable / MCV).
   - departure_utc: earliest departure first (Earliest Deadline First / EDF).
   - slack_minutes: tightest turnaround slack first.
   - -disruption_severity: highest disruption severity first (negated for min-heap ordering).
   - flight_id: deterministic lexicographical tie-breaker (e.g. 'NV-101').
2. Lazy Version Invalidation:
   Supports O(log n) push_or_update by tracking latest_version_by_flight_id. Obsolete versions
   are lazily discarded during pop() and peek(), avoiding expensive O(n) heap searches.
3. Pure In-Memory ADS:
   Implements a custom list-based binary min-heap with explicit sift-up and sift-down operations,
   avoiding Python built-in substitutes on the critical path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Generic, List, NamedTuple, Optional, Tuple, TypeVar, Union

V = TypeVar("V")


class PriorityKey(NamedTuple):
    """5-tuple priority key for Nova Air scheduler ordering."""
    feasible_combinations: int
    departure_utc: int
    slack_minutes: int
    neg_disruption_severity: int
    flight_id: str

    @classmethod
    def from_tuple(
        cls,
        t: Tuple[int, int, int, int, str] | PriorityKey | SchedulePriority,
    ) -> PriorityKey:
        if isinstance(t, PriorityKey):
            return t
        if isinstance(t, SchedulePriority):
            return cls(
                feasible_combinations=t.feasible_combinations,
                departure_utc=t.departure_utc,
                slack_minutes=t.slack_minutes,
                neg_disruption_severity=t.neg_disruption_severity,
                flight_id=t.flight_id,
            )
        return cls(*t)


@dataclass(order=True)
class SchedulePriority:
    """Convenience dataclass for constructing scheduler priority keys."""
    feasible_combinations: int
    departure_utc: int
    slack_minutes: int
    neg_disruption_severity: int
    flight_id: str

    def to_key(self) -> PriorityKey:
        return PriorityKey(
            self.feasible_combinations,
            self.departure_utc,
            self.slack_minutes,
            self.neg_disruption_severity,
            self.flight_id,
        )


@dataclass
class _HeapItem(Generic[V]):
    """Internal heap node storing priority key, version, and payload."""
    key: PriorityKey
    version: int
    flight_id: str
    payload: Optional[V] = None

    def __lt__(self, other: _HeapItem[V]) -> bool:
        return self.key < other.key

    def __le__(self, other: _HeapItem[V]) -> bool:
        return self.key <= other.key


class SchedulerPriorityQueue(Generic[V]):
    """Deterministic binary min-heap priority queue with lazy updates for scheduling."""

    def __init__(self) -> None:
        self._heap: List[_HeapItem[V]] = []
        # Maps flight_id -> latest valid version number
        self._latest_version: Dict[str, int] = {}

    def __len__(self) -> int:
        """Return the number of active, non-invalidated items in the queue."""
        return len(self._latest_version)

    def is_empty(self) -> bool:
        return len(self._latest_version) == 0

    def _parent(self, i: int) -> int:
        return (i - 1) // 2

    def _left_child(self, i: int) -> int:
        return 2 * i + 1

    def _right_child(self, i: int) -> int:
        return 2 * i + 2

    def _sift_up(self, idx: int) -> None:
        """Restore min-heap invariant by moving element at idx upward."""
        curr = idx
        while curr > 0:
            parent = self._parent(curr)
            if self._heap[curr] < self._heap[parent]:
                self._heap[curr], self._heap[parent] = self._heap[parent], self._heap[curr]
                curr = parent
            else:
                break

    def _sift_down(self, idx: int) -> None:
        """Restore min-heap invariant by moving element at idx downward."""
        curr = idx
        size = len(self._heap)
        while True:
            left = self._left_child(curr)
            right = self._right_child(curr)
            smallest = curr

            if left < size and self._heap[left] < self._heap[smallest]:
                smallest = left
            if right < size and self._heap[right] < self._heap[smallest]:
                smallest = right

            if smallest != curr:
                self._heap[curr], self._heap[smallest] = self._heap[smallest], self._heap[curr]
                curr = smallest
            else:
                break

    def push(
        self,
        flight_id: str,
        priority: Tuple[int, int, int, int, str] | PriorityKey | SchedulePriority,
        payload: Optional[V] = None,
    ) -> None:
        """Push an unassigned flight onto the scheduler priority queue."""
        self.push_or_update(flight_id, priority, payload)

    def push_or_update(
        self,
        flight_id: str,
        priority: Tuple[int, int, int, int, str] | PriorityKey | SchedulePriority,
        payload: Optional[V] = None,
    ) -> None:
        """Push or lazily update priority for a flight leg in O(log n) time."""
        key = PriorityKey.from_tuple(priority)
        if key.flight_id != flight_id:
            raise ValueError(f"Priority key flight_id '{key.flight_id}' does not match argument '{flight_id}'")

        # Increment version to invalidate previous entries for this flight_id
        new_version = self._latest_version.get(flight_id, 0) + 1
        self._latest_version[flight_id] = new_version

        item = _HeapItem(key=key, version=new_version, flight_id=flight_id, payload=payload)
        self._heap.append(item)
        self._sift_up(len(self._heap) - 1)

    def _clean_stale_top(self) -> None:
        """Discard stale/invalidated entries from the top of the heap."""
        while self._heap:
            top = self._heap[0]
            if top.flight_id in self._latest_version and top.version == self._latest_version[top.flight_id]:
                break
            # Stale entry at top: replace with last element and sift down
            last = self._heap.pop()
            if self._heap:
                self._heap[0] = last
                self._sift_down(0)

    def pop(self) -> Tuple[str, PriorityKey, Optional[V]]:
        """Pop and return the highest-urgency flight (flight_id, priority_key, payload).

        Raises:
            IndexError: If the priority queue is empty.
        """
        self._clean_stale_top()
        if not self._heap:
            raise IndexError("pop from an empty SchedulerPriorityQueue")

        # Top is guaranteed valid
        root = self._heap[0]
        last = self._heap.pop()
        if self._heap:
            self._heap[0] = last
            self._sift_down(0)

        # Remove from active tracking
        del self._latest_version[root.flight_id]
        return root.flight_id, root.key, root.payload

    def peek(self) -> Optional[Tuple[str, PriorityKey, Optional[V]]]:
        """Return the highest-urgency flight without removing it, or None if empty."""
        self._clean_stale_top()
        if not self._heap:
            return None
        top = self._heap[0]
        return top.flight_id, top.key, top.payload

    def clear(self) -> None:
        """Clear all items and reset queue."""
        self._heap.clear()
        self._latest_version.clear()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return queue capacity, stale count, and structural health metrics."""
        return {
            "size": len(self),
            "heap_capacity": len(self._heap),
            "stale_entries": len(self._heap) - len(self),
            "invariants_valid": self.verify_invariants(),
        }

    def verify_invariants(self) -> bool:
        """Verify the binary min-heap property and version tracking integrity."""
        # 1. Active count must not exceed heap length
        if len(self._latest_version) > len(self._heap):
            return False

        # 2. Binary min-heap invariant
        for i in range(1, len(self._heap)):
            parent = self._parent(i)
            if self._heap[i] < self._heap[parent]:
                return False

        return True
