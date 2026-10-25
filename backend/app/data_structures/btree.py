"""Custom B-Tree implementation for Nova Air flight schedule indexing.

Indexes composite keys (effective_departure_utc, flight_id) with configurable minimum
degree t >= 2 (default t=3) for O(log n + k) chronological window queries.
Does NOT use Python dict or set on the critical path.
"""

from __future__ import annotations

from typing import Any, Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")


class BTreeNode(Generic[T]):
    """B-Tree node storing sorted composite keys, associated values, and child pointers."""

    __slots__ = ("leaf", "keys", "values", "children")

    def __init__(self, leaf: bool = True) -> None:
        self.leaf: bool = leaf
        self.keys: List[Tuple[int, str]] = []
        self.values: List[T] = []
        self.children: List[BTreeNode[T]] = []

    def __repr__(self) -> str:
        keys_summary = [f"{k[0]}:{k[1]}" for k in self.keys]
        return f"BTreeNode(leaf={self.leaf}, keys={keys_summary})"


class FlightScheduleBTree(Generic[T]):
    """Multi-way B-Tree schedule index for chronological flight departure queries.

    Key: (effective_departure_utc: int, flight_id: str)
    Value: Any (typically FlightLeg or schedule record)
    """

    def __init__(self, t: int = 3) -> None:
        if t < 2:
            raise ValueError(f"Minimum degree t must be >= 2, got {t}")
        self._t: int = t
        self._root: BTreeNode[T] = BTreeNode[T](leaf=True)
        self._size: int = 0

    @property
    def t(self) -> int:
        return self._t

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    def clear(self) -> None:
        """Removes all keys and values from the B-Tree."""
        self._root = BTreeNode[T](leaf=True)
        self._size = 0

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------
    def search(self, key: Tuple[int, str]) -> Optional[T]:
        """Searches for key (departure_utc, flight_id) and returns value or None."""
        return self._search_node(self._root, key)

    def _search_node(self, node: BTreeNode[T], key: Tuple[int, str]) -> Optional[T]:
        i = 0
        n = len(node.keys)
        while i < n and key > node.keys[i]:
            i += 1

        if i < n and key == node.keys[i]:
            return node.values[i]

        if node.leaf:
            return None

        return self._search_node(node.children[i], key)

    def contains(self, key: Tuple[int, str]) -> bool:
        return self.search(key) is not None

    def __contains__(self, key: Tuple[int, str]) -> bool:
        return self.contains(key)

    # -------------------------------------------------------------------------
    # Insertion
    # -------------------------------------------------------------------------
    def insert(self, key: Tuple[int, str], value: T) -> None:
        """Inserts key-value pair, or updates existing key."""
        root = self._root
        # First check if key already exists to perform in-place update
        if self._update_existing(root, key, value):
            return

        # If root is full, tree grows in height
        if len(root.keys) == (2 * self._t - 1):
            new_root = BTreeNode[T](leaf=False)
            new_root.children.append(self._root)
            self._split_child(new_root, 0)
            self._root = new_root
            self._insert_non_full(self._root, key, value)
        else:
            self._insert_non_full(root, key, value)

        self._size += 1

    def _update_existing(self, node: BTreeNode[T], key: Tuple[int, str], value: T) -> bool:
        i = 0
        n = len(node.keys)
        while i < n and key > node.keys[i]:
            i += 1

        if i < n and key == node.keys[i]:
            node.values[i] = value
            return True

        if node.leaf:
            return False

        return self._update_existing(node.children[i], key, value)

    def _insert_non_full(self, node: BTreeNode[T], key: Tuple[int, str], value: T) -> None:
        i = len(node.keys) - 1

        if node.leaf:
            # Insert into sorted position
            node.keys.append(key)
            node.values.append(value)
            while i >= 0 and key < node.keys[i]:
                node.keys[i + 1] = node.keys[i]
                node.values[i + 1] = node.values[i]
                i -= 1
            node.keys[i + 1] = key
            node.values[i + 1] = value
        else:
            # Find child which is to receive the new key
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1

            # If child is full, split it
            if len(node.children[i].keys) == (2 * self._t - 1):
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1
                elif key == node.keys[i]:
                    node.values[i] = value
                    return

            self._insert_non_full(node.children[i], key, value)

    def _split_child(self, parent: BTreeNode[T], index: int) -> None:
        """Splits full child parent.children[index] around median key."""
        t = self._t
        child = parent.children[index]
        new_sibling = BTreeNode[T](leaf=child.leaf)

        # Median index is t - 1
        median_key = child.keys[t - 1]
        median_val = child.values[t - 1]

        # Sibling gets keys and values from t to 2t-2
        new_sibling.keys = child.keys[t:]
        new_sibling.values = child.values[t:]
        if not child.leaf:
            new_sibling.children = child.children[t:]

        # Child keeps keys from 0 to t-2
        child.keys = child.keys[: t - 1]
        child.values = child.values[: t - 1]
        if not child.leaf:
            child.children = child.children[:t]

        # Insert sibling into parent's children
        parent.children.insert(index + 1, new_sibling)
        # Pull median key up into parent
        parent.keys.insert(index, median_key)
        parent.values.insert(index, median_val)

    # -------------------------------------------------------------------------
    # Deletion
    # -------------------------------------------------------------------------
    def delete(self, key: Tuple[int, str]) -> bool:
        """Deletes key from B-Tree with full underflow rebalancing.

        Returns True if deleted, False if key was not present.
        """
        if not self.contains(key):
            return False

        self._delete_from_node(self._root, key)
        self._size -= 1

        # If root is empty after deletion and is not leaf, shrink height
        if len(self._root.keys) == 0:
            if not self._root.leaf:
                self._root = self._root.children[0]
            else:
                self._root = BTreeNode[T](leaf=True)

        return True

    def _delete_from_node(self, node: BTreeNode[T], key: Tuple[int, str]) -> None:
        t = self._t
        i = 0
        n = len(node.keys)
        while i < n and key > node.keys[i]:
            i += 1

        # Case 1 & 2: Key found in this node
        if i < n and key == node.keys[i]:
            if node.leaf:
                # Case 1: Key in leaf -> simply remove
                node.keys.pop(i)
                node.values.pop(i)
            else:
                # Case 2: Key in internal node
                left_child = node.children[i]
                right_child = node.children[i + 1]

                if len(left_child.keys) >= t:
                    # Case 2a: Left child has at least t keys -> borrow predecessor
                    pred_key, pred_val = self._get_predecessor(left_child)
                    node.keys[i] = pred_key
                    node.values[i] = pred_val
                    self._delete_from_node(left_child, pred_key)
                elif len(right_child.keys) >= t:
                    # Case 2b: Right child has at least t keys -> borrow successor
                    succ_key, succ_val = self._get_successor(right_child)
                    node.keys[i] = succ_key
                    node.values[i] = succ_val
                    self._delete_from_node(right_child, succ_key)
                else:
                    # Case 2c: Both children have t-1 keys -> merge key & right into left
                    self._merge_children(node, i)
                    self._delete_from_node(left_child, key)
            return

        # Case 3: Key is not in this internal node
        if node.leaf:
            return  # Key not in tree

        # Ensure the child node.children[i] has at least t keys
        child = node.children[i]
        if len(child.keys) < t:
            # Check left sibling
            left_sibling = node.children[i - 1] if i > 0 else None
            # Check right sibling
            right_sibling = node.children[i + 1] if i < len(node.children) - 1 else None

            if left_sibling is not None and len(left_sibling.keys) >= t:
                self._borrow_from_left(node, i, child, left_sibling)
            elif right_sibling is not None and len(right_sibling.keys) >= t:
                self._borrow_from_right(node, i, child, right_sibling)
            else:
                # Merge with sibling
                if left_sibling is not None:
                    self._merge_children(node, i - 1)
                    child = left_sibling
                else:
                    self._merge_children(node, i)

        self._delete_from_node(child, key)

    def _get_predecessor(self, node: BTreeNode[T]) -> Tuple[Tuple[int, str], T]:
        curr = node
        while not curr.leaf:
            curr = curr.children[-1]
        return curr.keys[-1], curr.values[-1]

    def _get_successor(self, node: BTreeNode[T]) -> Tuple[Tuple[int, str], T]:
        curr = node
        while not curr.leaf:
            curr = curr.children[0]
        return curr.keys[0], curr.values[0]

    def _borrow_from_left(
        self, parent: BTreeNode[T], child_idx: int, child: BTreeNode[T], left_sibling: BTreeNode[T]
    ) -> None:
        # Move key from parent down to child's head
        child.keys.insert(0, parent.keys[child_idx - 1])
        child.values.insert(0, parent.values[child_idx - 1])

        # If not leaf, move sibling's last child to child's first child
        if not child.leaf:
            child.children.insert(0, left_sibling.children.pop())

        # Move last key from left sibling up to parent
        parent.keys[child_idx - 1] = left_sibling.keys.pop()
        parent.values[child_idx - 1] = left_sibling.values.pop()

    def _borrow_from_right(
        self, parent: BTreeNode[T], child_idx: int, child: BTreeNode[T], right_sibling: BTreeNode[T]
    ) -> None:
        # Move key from parent down to child's tail
        child.keys.append(parent.keys[child_idx])
        child.values.append(parent.values[child_idx])

        # If not leaf, move sibling's first child to child's last child
        if not child.leaf:
            child.children.append(right_sibling.children.pop(0))

        # Move first key from right sibling up to parent
        parent.keys[child_idx] = right_sibling.keys.pop(0)
        parent.values[child_idx] = right_sibling.values.pop(0)

    def _merge_children(self, parent: BTreeNode[T], left_idx: int) -> None:
        """Merges parent.children[left_idx] and parent.children[left_idx + 1] with parent.keys[left_idx]."""
        left = parent.children[left_idx]
        right = parent.children.pop(left_idx + 1)
        k = parent.keys.pop(left_idx)
        v = parent.values.pop(left_idx)

        # Pull parent key down into left child
        left.keys.append(k)
        left.values.append(v)

        # Append right child's keys and values to left
        left.keys.extend(right.keys)
        left.values.extend(right.values)

        if not left.leaf:
            left.children.extend(right.children)

    # -------------------------------------------------------------------------
    # Atomic Key Update
    # -------------------------------------------------------------------------
    def update_key(
        self, old_key: Tuple[int, str], new_key: Tuple[int, str], value: Optional[T] = None
    ) -> None:
        """Atomically updates a flight's key when rescheduled or delayed."""
        old_val = self.search(old_key)
        if old_val is None:
            raise KeyError(f"Cannot update non-existent key: {old_key}")

        val_to_use = value if value is not None else old_val
        self.delete(old_key)
        self.insert(new_key, val_to_use)

    # -------------------------------------------------------------------------
    # Range Query
    # -------------------------------------------------------------------------
    def range_query(
        self,
        min_time_utc: int,
        max_time_utc: int,
        include_min: bool = True,
        include_max: bool = True,
    ) -> List[Tuple[Tuple[int, str], T]]:
        """Queries time window [min_time_utc, max_time_utc] in O(log n + k).

        Returns sorted list of (key, value) pairs.
        """
        results: List[Tuple[Tuple[int, str], T]] = []
        if self._size == 0 or min_time_utc > max_time_utc:
            return results

        self._range_query_node(
            self._root, min_time_utc, max_time_utc, include_min, include_max, results
        )
        return results

    def _range_query_node(
        self,
        node: BTreeNode[T],
        min_time: int,
        max_time: int,
        include_min: bool,
        include_max: bool,
        results: List[Tuple[Tuple[int, str], T]],
    ) -> None:
        n = len(node.keys)

        for i in range(n):
            k_time = node.keys[i][0]

            # If child i could contain keys >= min_time, explore child i
            if not node.leaf:
                if k_time >= min_time:
                    self._range_query_node(
                        node.children[i], min_time, max_time, include_min, include_max, results
                    )

            # Check if node.keys[i] is in range
            in_range = True
            if include_min:
                if k_time < min_time:
                    in_range = False
            else:
                if k_time <= min_time:
                    in_range = False

            if include_max:
                if k_time > max_time:
                    in_range = False
            else:
                if k_time >= max_time:
                    in_range = False

            if in_range:
                results.append((node.keys[i], node.values[i]))

            # If node.keys[i] exceeds max_time, no need to explore further in this node
            if k_time > max_time:
                return

        # Explore the rightmost child if it could contain keys <= max_time
        if not node.leaf:
            if n > 0 and node.keys[-1][0] <= max_time:
                self._range_query_node(
                    node.children[n], min_time, max_time, include_min, include_max, results
                )

    # -------------------------------------------------------------------------
    # In-Order Traversal & Iteration
    # -------------------------------------------------------------------------
    def inorder_traversal(self) -> List[Tuple[Tuple[int, str], T]]:
        """Returns in-order list of all (key, value) pairs sorted by key."""
        results: List[Tuple[Tuple[int, str], T]] = []
        self._inorder_node(self._root, results)
        return results

    def _inorder_node(self, node: BTreeNode[T], results: List[Tuple[Tuple[int, str], T]]) -> None:
        for i in range(len(node.keys)):
            if not node.leaf:
                self._inorder_node(node.children[i], results)
            results.append((node.keys[i], node.values[i]))
        if not node.leaf:
            self._inorder_node(node.children[-1], results)

    def keys(self) -> List[Tuple[int, str]]:
        return [k for k, _ in self.inorder_traversal()]

    def values(self) -> List[T]:
        return [v for _, v in self.inorder_traversal()]

    def items(self) -> List[Tuple[Tuple[int, str], T]]:
        return self.inorder_traversal()

    def __iter__(self):
        return iter(self.keys())

    # -------------------------------------------------------------------------
    # Diagnostics & Invariant Verification
    # -------------------------------------------------------------------------
    def get_diagnostics(self) -> dict[str, Any]:
        """Calculates structural metrics and distribution statistics."""
        if self._size == 0:
            return {
                "size": 0,
                "degree_t": self._t,
                "height": 0,
                "total_nodes": 1,
                "leaf_nodes": 1,
                "internal_nodes": 0,
                "min_keys_per_node": 0,
                "max_keys_per_node": 0,
                "average_keys_per_node": 0.0,
            }

        total_nodes = 0
        leaf_nodes = 0
        internal_nodes = 0
        all_key_counts: List[int] = []
        height = self._get_height(self._root)

        nodes_to_visit = [self._root]
        while nodes_to_visit:
            curr = nodes_to_visit.pop(0)
            total_nodes += 1
            all_key_counts.append(len(curr.keys))
            if curr.leaf:
                leaf_nodes += 1
            else:
                internal_nodes += 1
                nodes_to_visit.extend(curr.children)

        non_root_counts = all_key_counts[1:] if len(all_key_counts) > 1 else all_key_counts
        min_k = min(non_root_counts) if non_root_counts else len(self._root.keys)
        max_k = max(all_key_counts) if all_key_counts else 0
        avg_k = sum(all_key_counts) / total_nodes if total_nodes > 0 else 0.0

        return {
            "size": self._size,
            "degree_t": self._t,
            "height": height,
            "total_nodes": total_nodes,
            "leaf_nodes": leaf_nodes,
            "internal_nodes": internal_nodes,
            "min_keys_per_node": min_k,
            "max_keys_per_node": max_k,
            "average_keys_per_node": round(avg_k, 2),
        }

    def _get_height(self, node: BTreeNode[T]) -> int:
        h = 0
        curr = node
        while not curr.leaf:
            curr = curr.children[0]
            h += 1
        return h

    def verify_invariants(self) -> bool:
        """Validates all formal B-Tree invariants:

        1. All leaves are at the exact same depth.
        2. Non-root nodes have between t-1 and 2t-1 keys.
        3. Root has between 0 and 2t-1 keys.
        4. Keys in every node are sorted in strictly ascending order.
        5. Internal node keys strictly separate child subtree intervals.
        6. Total keys match self._size.
        """
        if self._size == 0:
            if len(self._root.keys) != 0:
                raise AssertionError("Empty tree must have 0 root keys")
            return True

        leaf_depths: List[int] = []
        counted_keys = self._verify_node(self._root, depth=0, leaf_depths=leaf_depths, is_root=True)

        # 1. Uniform leaf depth check
        if len(set(leaf_depths)) > 1:
            raise AssertionError(f"Leaves at non-uniform depths: {set(leaf_depths)}")

        # 6. Total key count check
        if counted_keys != self._size:
            raise AssertionError(f"Total counted keys ({counted_keys}) does not match recorded size ({self._size})")

        return True

    def _verify_node(
        self,
        node: BTreeNode[T],
        depth: int,
        leaf_depths: List[int],
        is_root: bool,
    ) -> int:
        n = len(node.keys)
        t = self._t

        # Check key count bounds
        if is_root:
            if n > (2 * t - 1):
                raise AssertionError(f"Root exceeds max keys: {n} > {2 * t - 1}")
        else:
            if n < (t - 1) or n > (2 * t - 1):
                raise AssertionError(f"Node violates key bounds [{t-1}, {2*t-1}]: count={n}")

        # Check sorted order of keys within node
        for i in range(len(node.keys) - 1):
            if node.keys[i] >= node.keys[i + 1]:
                raise AssertionError(f"Keys out of order in node: {node.keys[i]} >= {node.keys[i + 1]}")

        # Check child count consistency
        if not node.leaf:
            if len(node.children) != n + 1:
                raise AssertionError(f"Internal node must have len(keys)+1 children: keys={n}, children={len(node.children)}")

        if node.leaf:
            leaf_depths.append(depth)
            return n

        # Recursive validation of children and separation check
        total_keys = n
        for i in range(len(node.children)):
            child = node.children[i]
            total_keys += self._verify_node(child, depth + 1, leaf_depths, is_root=False)

            # Check that child's keys are strictly less than node.keys[i] (if i < n)
            if i < n:
                sep_key = node.keys[i]
                for ck in child.keys:
                    if ck >= sep_key:
                        raise AssertionError(f"Child key {ck} violates upper separator {sep_key}")

            # Check that child's keys are strictly greater than node.keys[i-1] (if i > 0)
            if i > 0:
                sep_key = node.keys[i - 1]
                for ck in child.keys:
                    if ck <= sep_key:
                        raise AssertionError(f"Child key {ck} violates lower separator {sep_key}")

        return total_keys
