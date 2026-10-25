"""Augmented Red-Black Interval Tree for Nova Air Resource Reservations.

This module implements an in-memory Augmented Red-Black Tree (RBIntervalTree)
indexing half-open time intervals [start_utc, end_utc) for aircraft rotations,
crew duty periods, turnaround times (TAT), and maintenance downtime blocks.

Key Design Principles:
1. Half-Open UTC Intervals: [start_utc, end_utc) with start_utc < end_utc.
   Endpoints touching at boundary (e.g. [1000, 2000) and [2000, 3000)) DO NOT overlap.
2. Composite BST Ordering: Keyed by (start_utc, end_utc, interval_id) to ensure
   strict deterministic ordering and support multiple intervals sharing start times.
3. Subtree Augmentation: Every node maintains max_end = max(end_utc, left.max_end, right.max_end)
   enabling O(log n) find_first_overlap and O(log n + k) find_all_overlaps pruned subtree search.
4. Red-Black Balancing: Strict color, black-height, and rotation fixups with explicit
   black NIL sentinel node.
5. Zero Built-In Replacements: No Python dict, bisect, or database queries on the critical path.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, Iterator, Optional, TypeVar


class NodeColor(Enum):
    """Red-Black Tree node colors."""
    RED = 0
    BLACK = 1


V = TypeVar("V")


class IntervalNode(Generic[V]):
    """Augmented Red-Black Tree node storing an interval [start_utc, end_utc)."""

    __slots__ = (
        "start_utc",
        "end_utc",
        "interval_id",
        "data",
        "color",
        "max_end",
        "left",
        "right",
        "parent",
    )

    def __init__(
        self,
        start_utc: int = 0,
        end_utc: int = 0,
        interval_id: str = "",
        data: Optional[V] = None,
        color: NodeColor = NodeColor.BLACK,
    ) -> None:
        self.start_utc: int = start_utc
        self.end_utc: int = end_utc
        self.interval_id: str = interval_id
        self.data: Optional[V] = data
        self.color: NodeColor = color
        self.max_end: int = end_utc
        self.left: IntervalNode[V] = self
        self.right: IntervalNode[V] = self
        self.parent: IntervalNode[V] = self

    @property
    def key(self) -> tuple[int, int, str]:
        """Composite search key for deterministic BST ordering."""
        return (self.start_utc, self.end_utc, self.interval_id)

    @property
    def interval(self) -> tuple[int, int]:
        """Half-open interval bounds [start_utc, end_utc)."""
        return (self.start_utc, self.end_utc)

    def __repr__(self) -> str:
        color_str = "R" if self.color == NodeColor.RED else "B"
        return (
            f"IntervalNode([{self.start_utc}, {self.end_utc}), id='{self.interval_id}', "
            f"max_end={self.max_end}, {color_str})"
        )


class RBIntervalTree(Generic[V]):
    """Augmented Red-Black Tree for half-open interval indexing and overlap queries.

    Maintains:
    - Root pointer and size tally.
    - Explicit black NIL sentinel node with max_end = -1.
    - Subtree max_end augmentation at all non-NIL nodes.
    """

    def __init__(self) -> None:
        # Create unique black NIL sentinel for this tree instance
        self.nil: IntervalNode[V] = IntervalNode(
            start_utc=-1,
            end_utc=-1,
            interval_id="__NIL__",
            data=None,
            color=NodeColor.BLACK,
        )
        self.nil.max_end = -1
        self.nil.left = self.nil
        self.nil.right = self.nil
        self.nil.parent = self.nil

        self.root: IntervalNode[V] = self.nil
        self._size: int = 0

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    @staticmethod
    def intervals_overlap(s1: int, e1: int, s2: int, e2: int) -> bool:
        """Half-open [s1, e1) and [s2, e2) overlap iff s1 < e2 and s2 < e1.

        Touching boundaries (e.g. e1 == s2) do NOT overlap.
        """
        return s1 < e2 and s2 < e1

    def _update_max_end(self, node: IntervalNode[V]) -> None:
        """Recompute node.max_end from its end_utc and both children."""
        if node != self.nil:
            left_max = node.left.max_end if node.left != self.nil else -1
            right_max = node.right.max_end if node.right != self.nil else -1
            node.max_end = max(node.end_utc, left_max, right_max)

    def _update_max_end_upward(self, node: IntervalNode[V]) -> None:
        """Propagate max_end changes upward along the parent chain."""
        curr = node
        while curr != self.nil:
            self._update_max_end(curr)
            curr = curr.parent

    def _left_rotate(self, x: IntervalNode[V]) -> None:
        """Perform standard Red-Black left rotation at x."""
        y = x.right
        x.right = y.left
        if y.left != self.nil:
            y.left.parent = x

        y.parent = x.parent
        if x.parent == self.nil:
            self.root = y
        elif x == x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y

        y.left = x
        x.parent = y

        # Recompute max_end: x is now child of y, so x first, then upward from y
        self._update_max_end(x)
        self._update_max_end_upward(y)

    def _right_rotate(self, y: IntervalNode[V]) -> None:
        """Perform standard Red-Black right rotation at y."""
        x = y.left
        y.left = x.right
        if x.right != self.nil:
            x.right.parent = y

        x.parent = y.parent
        if y.parent == self.nil:
            self.root = x
        elif y == y.parent.right:
            y.parent.right = x
        else:
            y.parent.left = x

        x.right = y
        y.parent = x

        # Recompute max_end: y is now child of x, so y first, then upward from x
        self._update_max_end(y)
        self._update_max_end_upward(x)

    def insert(
        self,
        start_utc: int,
        end_utc: int,
        interval_id: str,
        data: Optional[V] = None,
    ) -> IntervalNode[V]:
        """Insert a half-open interval [start_utc, end_utc) into the tree.

        Args:
            start_utc: UTC epoch start timestamp (inclusive).
            end_utc: UTC epoch end timestamp (exclusive).
            interval_id: Unique identifier for tie-breaking and tracking.
            data: Optional payload (e.g. FlightLeg, DutyPeriod, MaintenanceBlock).

        Returns:
            The newly inserted IntervalNode.

        Raises:
            ValueError: If start_utc >= end_utc or if exact composite key already exists.
        """
        if start_utc >= end_utc:
            raise ValueError(
                f"Invalid half-open interval: start_utc ({start_utc}) must be strictly < end_utc ({end_utc})"
            )

        key = (start_utc, end_utc, interval_id)
        z = IntervalNode(
            start_utc=start_utc,
            end_utc=end_utc,
            interval_id=interval_id,
            data=data,
            color=NodeColor.RED,
        )
        z.left = self.nil
        z.right = self.nil
        z.max_end = end_utc

        y = self.nil
        x = self.root
        while x != self.nil:
            y = x
            if key == x.key:
                raise ValueError(f"Duplicate interval key already exists in tree: {key}")
            elif key < x.key:
                x = x.left
            else:
                x = x.right

        z.parent = y
        if y == self.nil:
            self.root = z
        elif key < y.key:
            y.left = z
        else:
            y.right = z

        self._size += 1
        self._update_max_end_upward(z)
        self._insert_fixup(z)
        self._update_max_end_upward(z)
        return z

    def _insert_fixup(self, z: IntervalNode[V]) -> None:
        """Restore Red-Black invariants after insertion."""
        while z.parent.color == NodeColor.RED:
            if z.parent == z.parent.parent.left:
                y = z.parent.parent.right  # uncle
                if y.color == NodeColor.RED:
                    # Case 1: uncle is RED -> recolor
                    z.parent.color = NodeColor.BLACK
                    y.color = NodeColor.BLACK
                    z.parent.parent.color = NodeColor.RED
                    z = z.parent.parent
                else:
                    if z == z.parent.right:
                        # Case 2: uncle is BLACK and z is right child -> rotate left
                        z = z.parent
                        self._left_rotate(z)
                    # Case 3: uncle is BLACK and z is left child -> rotate right
                    z.parent.color = NodeColor.BLACK
                    z.parent.parent.color = NodeColor.RED
                    self._right_rotate(z.parent.parent)
            else:
                y = z.parent.parent.left  # uncle
                if y.color == NodeColor.RED:
                    # Case 1: uncle is RED -> recolor
                    z.parent.color = NodeColor.BLACK
                    y.color = NodeColor.BLACK
                    z.parent.parent.color = NodeColor.RED
                    z = z.parent.parent
                else:
                    if z == z.parent.left:
                        # Case 2: uncle is BLACK and z is left child -> rotate right
                        z = z.parent
                        self._right_rotate(z)
                    # Case 3: uncle is BLACK and z is right child -> rotate left
                    z.parent.color = NodeColor.BLACK
                    z.parent.parent.color = NodeColor.RED
                    self._left_rotate(z.parent.parent)

        self.root.color = NodeColor.BLACK
        # Ensure sentinel is untouched
        self.nil.color = NodeColor.BLACK
        self.nil.max_end = -1

    def _transplant(self, u: IntervalNode[V], v: IntervalNode[V]) -> None:
        """Replace subtree rooted at u with subtree rooted at v."""
        if u.parent == self.nil:
            self.root = v
        elif u == u.parent.left:
            u.parent.left = v
        else:
            u.parent.right = v
        v.parent = u.parent

    def _minimum(self, node: IntervalNode[V]) -> IntervalNode[V]:
        """Find node with minimum key in subtree rooted at node."""
        curr = node
        while curr.left != self.nil:
            curr = curr.left
        return curr

    def _maximum(self, node: IntervalNode[V]) -> IntervalNode[V]:
        """Find node with maximum key in subtree rooted at node."""
        curr = node
        while curr.right != self.nil:
            curr = curr.right
        return curr

    def search(
        self,
        start_utc: int,
        end_utc: int,
        interval_id: str,
    ) -> Optional[IntervalNode[V]]:
        """Exact match search for an interval by its composite key."""
        key = (start_utc, end_utc, interval_id)
        curr = self.root
        while curr != self.nil:
            if key == curr.key:
                return curr
            elif key < curr.key:
                curr = curr.left
            else:
                curr = curr.right
        return None

    def delete(
        self,
        start_utc: int,
        end_utc: int,
        interval_id: str,
    ) -> bool:
        """Delete an interval by its composite key.

        Returns:
            True if found and deleted, False otherwise.
        """
        z = self.search(start_utc, end_utc, interval_id)
        if z is None or z == self.nil:
            return False

        y = z
        y_original_color = y.color

        if z.left == self.nil:
            x = z.right
            fixup_start = z.parent
            self._transplant(z, z.right)
        elif z.right == self.nil:
            x = z.left
            fixup_start = z.parent
            self._transplant(z, z.left)
        else:
            y = self._minimum(z.right)
            y_original_color = y.color
            x = y.right
            if y.parent == z:
                x.parent = y
                fixup_start = y
            else:
                fixup_start = y.parent
                self._transplant(y, y.right)
                y.right = z.right
                y.right.parent = y

            self._transplant(z, y)
            y.left = z.left
            y.left.parent = y
            y.color = z.color
            self._update_max_end(y)

        self._size -= 1
        self._update_max_end_upward(fixup_start)

        if y_original_color == NodeColor.BLACK:
            self._delete_fixup(x)

        # Restore sentinel invariants
        self.nil.parent = self.nil
        self.nil.left = self.nil
        self.nil.right = self.nil
        self.nil.color = NodeColor.BLACK
        self.nil.max_end = -1

        # Post-deletion upward propagation to ensure exact max_end
        if fixup_start != self.nil:
            self._update_max_end_upward(fixup_start)
        else:
            self._update_max_end_upward(self.root)
        if x != self.nil:
            self._update_max_end_upward(x)
        return True

    def _delete_fixup(self, x: IntervalNode[V]) -> None:
        """Restore Red-Black invariants after deletion."""
        while x != self.root and x.color == NodeColor.BLACK:
            if x == x.parent.left:
                w = x.parent.right  # sibling
                if w.color == NodeColor.RED:
                    # Case 1
                    w.color = NodeColor.BLACK
                    x.parent.color = NodeColor.RED
                    self._left_rotate(x.parent)
                    w = x.parent.right
                if w.left.color == NodeColor.BLACK and w.right.color == NodeColor.BLACK:
                    # Case 2
                    w.color = NodeColor.RED
                    x = x.parent
                else:
                    if w.right.color == NodeColor.BLACK:
                        # Case 3
                        w.left.color = NodeColor.BLACK
                        w.color = NodeColor.RED
                        self._right_rotate(w)
                        w = x.parent.right
                    # Case 4
                    w.color = x.parent.color
                    x.parent.color = NodeColor.BLACK
                    w.right.color = NodeColor.BLACK
                    self._left_rotate(x.parent)
                    x = self.root
            else:
                w = x.parent.left  # sibling
                if w.color == NodeColor.RED:
                    # Case 1
                    w.color = NodeColor.BLACK
                    x.parent.color = NodeColor.RED
                    self._right_rotate(x.parent)
                    w = x.parent.left
                if w.right.color == NodeColor.BLACK and w.left.color == NodeColor.BLACK:
                    # Case 2
                    w.color = NodeColor.RED
                    x = x.parent
                else:
                    if w.left.color == NodeColor.BLACK:
                        # Case 3
                        w.right.color = NodeColor.BLACK
                        w.color = NodeColor.RED
                        self._left_rotate(w)
                        w = x.parent.left
                    # Case 4
                    w.color = x.parent.color
                    x.parent.color = NodeColor.BLACK
                    w.left.color = NodeColor.BLACK
                    self._right_rotate(x.parent)
                    x = self.root

        x.color = NodeColor.BLACK

    def find_first_overlap(
        self,
        start_utc: int,
        end_utc: int,
    ) -> Optional[IntervalNode[V]]:
        """Find any single interval in the tree that overlaps [start_utc, end_utc).

        Runs in strict O(log n) time by pruning branches using subtree max_end.
        """
        if start_utc >= end_utc:
            return None

        x = self.root
        while x != self.nil and not self.intervals_overlap(x.start_utc, x.end_utc, start_utc, end_utc):
            if x.left != self.nil and x.left.max_end > start_utc:
                x = x.left
            else:
                x = x.right

        return x if x != self.nil else None

    def find_all_overlaps(
        self,
        start_utc: int,
        end_utc: int,
    ) -> list[IntervalNode[V]]:
        """Find all intervals in the tree that overlap [start_utc, end_utc).

        Traverses in in-order (chronological start time order) with subtree pruning:
        - Prunes subtree if node.max_end <= start_utc.
        - Skips left subtree if node.left.max_end <= start_utc.
        - Skips right subtree if node.start_utc >= end_utc.

        Complexity: O(min(n, k log n)) worst-case, O(log n + k) expected.
        """
        if start_utc >= end_utc:
            return []

        results: list[IntervalNode[V]] = []

        def _traverse(node: IntervalNode[V]) -> None:
            if node == self.nil:
                return

            # If subtree max_end cannot exceed start_utc, no interval can overlap
            if node.max_end <= start_utc:
                return

            # Explore left subtree if it has any interval ending after query start
            if node.left != self.nil and node.left.max_end > start_utc:
                _traverse(node.left)

            # Check current node
            if self.intervals_overlap(node.start_utc, node.end_utc, start_utc, end_utc):
                results.append(node)

            # Explore right subtree only if node.start_utc < end_utc
            # (all right-descendant intervals start at or after node.start_utc)
            if node.start_utc < end_utc and node.right != self.nil:
                _traverse(node.right)

        _traverse(self.root)
        return results

    def find_predecessor(self, start_utc: int) -> Optional[IntervalNode[V]]:
        """Find the latest interval ending at or before start_utc (end_utc <= start_utc).

        Used in aviation scheduling to find the preceding duty for rest-gap calculation.
        Maximizes end_utc; ties broken by start_utc, then interval_id.
        """
        best: Optional[IntervalNode[V]] = None

        def _search(node: IntervalNode[V]) -> None:
            nonlocal best
            if node == self.nil:
                return

            if node.start_utc >= start_utc:
                # All right descendants have start_utc >= node.start_utc >= start_utc,
                # meaning end_utc > start_utc for all of them. Search left only.
                _search(node.left)
                return

            # Search right subtree first (contains intervals with larger start_utc)
            _search(node.right)

            # Check current node
            if node.end_utc <= start_utc:
                if (
                    best is None
                    or node.end_utc > best.end_utc
                    or (node.end_utc == best.end_utc and node.start_utc > best.start_utc)
                ):
                    best = node

            # Search left subtree only if its max_end can exceed our best candidate's end_utc
            if node.left != self.nil:
                if best is None or node.left.max_end >= (best.end_utc if best else -1):
                    _search(node.left)

        _search(self.root)
        return best

    def find_successor(self, end_utc: int) -> Optional[IntervalNode[V]]:
        """Find the earliest interval starting at or after end_utc (start_utc >= end_utc).

        Used in aviation scheduling to find the succeeding duty for rest-gap calculation.
        Minimizes start_utc; ties broken by end_utc, then interval_id in O(log n) time.
        """
        candidate: Optional[IntervalNode[V]] = None
        curr = self.root
        while curr != self.nil:
            if curr.start_utc >= end_utc:
                candidate = curr
                curr = curr.left  # Look for an even smaller start_utc >= end_utc
            else:
                curr = curr.right

        return candidate

    def inorder_traversal(self) -> list[IntervalNode[V]]:
        """Return all nodes in ascending composite key order."""
        result: list[IntervalNode[V]] = []

        def _inorder(node: IntervalNode[V]) -> None:
            if node != self.nil:
                _inorder(node.left)
                result.append(node)
                _inorder(node.right)

        _inorder(self.root)
        return result

    def clear(self) -> None:
        """Remove all intervals and reset tree."""
        self.root = self.nil
        self._size = 0

    def height(self) -> int:
        """Compute the maximum depth of the tree from root to leaf."""
        def _h(node: IntervalNode[V]) -> int:
            if node == self.nil:
                return 0
            return 1 + max(_h(node.left), _h(node.right))
        return _h(self.root)

    def black_height(self) -> int:
        """Compute the black height of the root node."""
        def _bh(node: IntervalNode[V]) -> int:
            if node == self.nil:
                return 1
            left_bh = _bh(node.left)
            right_bh = _bh(node.right)
            if left_bh != right_bh:
                return -1
            return left_bh + (1 if node.color == NodeColor.BLACK else 0)

        return _bh(self.root)

    def get_diagnostics(self) -> dict[str, Any]:
        """Compute comprehensive health and structural metrics."""
        red_count = 0
        black_count = 0
        for node in self.inorder_traversal():
            if node.color == NodeColor.RED:
                red_count += 1
            else:
                black_count += 1

        return {
            "size": self._size,
            "height": self.height(),
            "black_height": self.black_height(),
            "max_end": self.root.max_end if self.root != self.nil else -1,
            "red_nodes": red_count,
            "black_nodes": black_count,
            "invariants_valid": self.verify_invariants(),
        }

    def verify_invariants(self) -> bool:
        """Verify all Red-Black and Interval Tree invariants.

        Checks:
        1. Sentinel invariants (NIL is black, max_end == -1, self-referential pointers).
        2. Root color is BLACK (or NIL if empty).
        3. Root's parent is NIL.
        4. Red node property: no red node has a red child.
        5. Black-height property: uniform black height along all paths from root to NIL.
        6. BST ordering property: strictly increasing keys in in-order traversal.
        7. Max-end augmentation: node.max_end == max(node.end_utc, left.max_end, right.max_end).
        8. Size matches in-order traversal count.
        """
        # 1. Sentinel checks
        if self.nil.color != NodeColor.BLACK or self.nil.max_end != -1:
            return False

        if self._size == 0:
            return self.root == self.nil

        # 2. Root color
        if self.root.color != NodeColor.BLACK:
            return False

        # 3. Root parent
        if self.root.parent != self.nil:
            return False

        # 4 & 7. Child pointers, Red-Red violations, and Max-End maintenance
        def _check_node(node: IntervalNode[V]) -> bool:
            if node == self.nil:
                return True

            # Pointer consistency
            if node.left != self.nil and node.left.parent != node:
                return False
            if node.right != self.nil and node.right.parent != node:
                return False

            # Red-Red violation
            if node.color == NodeColor.RED:
                if node.left.color == NodeColor.RED or node.right.color == NodeColor.RED:
                    return False

            # Subtree max_end exactness
            expected_max = max(
                node.end_utc,
                node.left.max_end if node.left != self.nil else -1,
                node.right.max_end if node.right != self.nil else -1,
            )
            if node.max_end != expected_max:
                return False

            return _check_node(node.left) and _check_node(node.right)

        if not _check_node(self.root):
            return False

        # 5. Uniform black height
        def _check_black_height(node: IntervalNode[V]) -> tuple[bool, int]:
            if node == self.nil:
                return True, 1

            left_valid, left_bh = _check_black_height(node.left)
            right_valid, right_bh = _check_black_height(node.right)

            if not left_valid or not right_valid or left_bh != right_bh:
                return False, 0

            return True, left_bh + (1 if node.color == NodeColor.BLACK else 0)

        bh_valid, _ = _check_black_height(self.root)
        if not bh_valid:
            return False

        # 6 & 8. BST ordering and size check
        nodes = self.inorder_traversal()
        if len(nodes) != self._size:
            return False

        for i in range(len(nodes) - 1):
            if nodes[i].key >= nodes[i + 1].key:
                return False

        return True
