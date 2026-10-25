"""Custom Separate-Chaining Hash Table implementation for Nova Air (AirCrewOps).

Provides deterministic O(1) average lookup, insertion, and deletion for in-memory
domain entity indexing (airports, aircraft, crew, flights).
Does NOT use Python dict or set internally.
"""

from __future__ import annotations

from typing import Any, Generic, Iterator, List, Optional, Tuple, TypeVar

K = TypeVar("K")
V = TypeVar("V")

# List of prime capacities for dynamic resizing to minimize clustering
PRIME_CAPACITIES = [
    11, 23, 47, 97, 197, 397, 797, 1597, 3203, 6421, 12853, 25717, 51437,
    102877, 205759, 411527, 823117, 1646237, 3292489, 6584983, 13169977,
]


class HashNode(Generic[K, V]):
    """Singly-linked list node for separate chaining collision resolution."""

    __slots__ = ("key", "value", "next")

    def __init__(self, key: K, value: V, next_node: Optional[HashNode[K, V]] = None) -> None:
        self.key: K = key
        self.value: V = value
        self.next: Optional[HashNode[K, V]] = next_node

    def __repr__(self) -> str:
        return f"HashNode({self.key!r}: {self.value!r})"


class SeparateChainingHashTable(Generic[K, V]):
    """Custom Separate-Chaining Hash Table.

    Guarantees reproducible hashing across process restarts using 64-bit FNV-1a.
    Maintains buckets as a fixed-size list of HashNode head pointers.
    """

    FNV_OFFSET_BASIS = 14695981039346656037
    FNV_PRIME = 1099511628211
    FNV_MASK = 0xFFFFFFFFFFFFFFFF

    def __init__(self, initial_capacity: int = 11, max_load_factor: float = 0.75) -> None:
        if initial_capacity <= 0:
            raise ValueError(f"initial_capacity must be positive, got {initial_capacity}")
        if max_load_factor <= 0.0:
            raise ValueError(f"max_load_factor must be positive, got {max_load_factor}")

        self._capacity: int = self._find_next_prime(initial_capacity)
        self._max_load_factor: float = max_load_factor
        self._size: int = 0
        # Explicit bucket array of head pointers
        self._buckets: List[Optional[HashNode[K, V]]] = [None] * self._capacity

    @classmethod
    def _fnv1a_hash(cls, key: Any) -> int:
        """Deterministic 64-bit FNV-1a hash algorithm for arbitrary keys."""
        if isinstance(key, bytes):
            data = key
        elif isinstance(key, str):
            data = key.encode("utf-8")
        elif isinstance(key, int):
            data = str(key).encode("utf-8")
        else:
            data = repr(key).encode("utf-8")

        h = cls.FNV_OFFSET_BASIS
        for b in data:
            h ^= b
            h = (h * cls.FNV_PRIME) & cls.FNV_MASK
        return h

    def _hash(self, key: K) -> int:
        """Computes bucket index for the given key."""
        return self._fnv1a_hash(key) % self._capacity

    @staticmethod
    def _find_next_prime(min_val: int) -> int:
        for p in PRIME_CAPACITIES:
            if p >= min_val:
                return p
        # Fallback to odd number above min_val if exceeding prime table
        val = min_val | 1
        while True:
            # Simple prime check
            is_prime = True
            for d in range(3, int(val ** 0.5) + 1, 2):
                if val % d == 0:
                    is_prime = False
                    break
            if is_prime:
                return val
            val += 2

    def __len__(self) -> int:
        return self._size

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def load_factor(self) -> float:
        return self._size / self._capacity if self._capacity > 0 else 0.0

    def put(self, key: K, value: V) -> None:
        """Inserts or updates the key-value pair."""
        bucket_idx = self._hash(key)
        curr = self._buckets[bucket_idx]

        # Check if key already exists in this bucket chain
        while curr is not None:
            if curr.key == key:
                curr.value = value
                return
            curr = curr.next

        # Insert new node at head of bucket chain
        new_node = HashNode(key, value, self._buckets[bucket_idx])
        self._buckets[bucket_idx] = new_node
        self._size += 1

        # Check for dynamic resize
        if (self._size / self._capacity) > self._max_load_factor:
            self._resize()

    def insert(self, key: K, value: V) -> None:
        """Alias for put."""
        self.put(key, value)

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Retrieves value associated with key, or returns default."""
        bucket_idx = self._hash(key)
        curr = self._buckets[bucket_idx]
        while curr is not None:
            if curr.key == key:
                return curr.value
            curr = curr.next
        return default

    def contains(self, key: K) -> bool:
        """Returns True if key exists in hash table."""
        bucket_idx = self._hash(key)
        curr = self._buckets[bucket_idx]
        while curr is not None:
            if curr.key == key:
                return True
            curr = curr.next
        return False

    def remove(self, key: K) -> V:
        """Removes key and returns its value. Raises KeyError if not found."""
        bucket_idx = self._hash(key)
        curr = self._buckets[bucket_idx]
        prev: Optional[HashNode[K, V]] = None

        while curr is not None:
            if curr.key == key:
                if prev is None:
                    # Removing head of chain
                    self._buckets[bucket_idx] = curr.next
                else:
                    # Removing middle or tail
                    prev.next = curr.next
                self._size -= 1
                return curr.value
            prev = curr
            curr = curr.next

        raise KeyError(f"Key not found in hash table: {key!r}")

    def pop(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Removes key and returns its value, or returns default if not found."""
        try:
            return self.remove(key)
        except KeyError:
            return default

    def keys(self) -> List[K]:
        """Returns list of all keys."""
        res: List[K] = []
        for head in self._buckets:
            curr = head
            while curr is not None:
                res.append(curr.key)
                curr = curr.next
        return res

    def values(self) -> List[V]:
        """Returns list of all values."""
        res: List[V] = []
        for head in self._buckets:
            curr = head
            while curr is not None:
                res.append(curr.value)
                curr = curr.next
        return res

    def items(self) -> List[Tuple[K, V]]:
        """Returns list of (key, value) pairs."""
        res: List[Tuple[K, V]] = []
        for head in self._buckets:
            curr = head
            while curr is not None:
                res.append((curr.key, curr.value))
                curr = curr.next
        return res

    def clear(self) -> None:
        """Clears all elements from the table."""
        self._buckets = [None] * self._capacity
        self._size = 0

    def _resize(self, new_capacity: Optional[int] = None) -> None:
        """Resizes the bucket array to the next prime capacity and rehashes all nodes."""
        if new_capacity is None:
            target = self._capacity * 2 + 1
            new_capacity = self._find_next_prime(target)

        old_buckets = self._buckets
        self._capacity = new_capacity
        self._buckets = [None] * self._capacity

        # Rehash all nodes into new buckets without altering self._size
        for head in old_buckets:
            curr = head
            while curr is not None:
                next_node = curr.next
                # Compute new bucket index
                idx = self._fnv1a_hash(curr.key) % self._capacity
                # Insert at head of new bucket
                curr.next = self._buckets[idx]
                self._buckets[idx] = curr
                curr = next_node

    def get_diagnostics(self) -> dict[str, Any]:
        """Returns operational metrics and collision diagnostics."""
        occupied_buckets = 0
        max_chain_length = 0
        total_collisions = 0
        chain_lengths: List[int] = []

        for head in self._buckets:
            if head is not None:
                occupied_buckets += 1
                chain_len = 0
                curr = head
                while curr is not None:
                    chain_len += 1
                    curr = curr.next
                chain_lengths.append(chain_len)
                if chain_len > max_chain_length:
                    max_chain_length = chain_len
                if chain_len > 1:
                    total_collisions += (chain_len - 1)

        empty_buckets = self._capacity - occupied_buckets
        avg_chain = (sum(chain_lengths) / occupied_buckets) if occupied_buckets > 0 else 0.0

        return {
            "size": self._size,
            "capacity": self._capacity,
            "load_factor": round(self.load_factor, 4),
            "max_load_factor": self._max_load_factor,
            "occupied_buckets": occupied_buckets,
            "empty_buckets": empty_buckets,
            "max_chain_length": max_chain_length,
            "average_chain_length": round(avg_chain, 4),
            "total_collisions": total_collisions,
        }

    def verify_invariants(self) -> bool:
        """Validates internal consistency: node count match and key uniqueness."""
        counted_nodes = 0
        seen_keys: List[K] = []

        for head in self._buckets:
            curr = head
            while curr is not None:
                # Key uniqueness check without built-in set
                for k in seen_keys:
                    if k == curr.key:
                        raise AssertionError(f"Duplicate key found in hash table: {curr.key!r}")
                seen_keys.append(curr.key)
                counted_nodes += 1
                curr = curr.next

        if counted_nodes != self._size:
            raise AssertionError(f"Size invariant violated: recorded {self._size}, but counted {counted_nodes}")

        return True

    # Pythonic dunder methods
    def __getitem__(self, key: K) -> V:
        val = self.get(key)
        if val is None and not self.contains(key):
            raise KeyError(f"Key not found: {key!r}")
        return val  # type: ignore[return-value]

    def __setitem__(self, key: K, value: V) -> None:
        self.put(key, value)

    def __delitem__(self, key: K) -> None:
        self.remove(key)

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def __iter__(self) -> Iterator[K]:
        return iter(self.keys())

    def __repr__(self) -> str:
        diag = self.get_diagnostics()
        return f"SeparateChainingHashTable(size={diag['size']}, capacity={diag['capacity']}, load={diag['load_factor']})"
