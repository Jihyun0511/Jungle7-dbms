"""메모리 기반 B+ 트리. 키(id) → 값(행이 CSV 파일에서 시작하는 바이트 위치).

규칙 (Phase 2 요구분석):
- 디스크 기반 B+ 트리를 단순화해 노드를 메모리에 둔다. 테이블 파일은 CSV 그대로
- 노드 하나 = 페이지 하나. 기본 order 255 (4KB ÷ (키 8B + 포인터 8B)).
  테스트는 같은 코드에 작은 order(3~4)를 넘겨 분할을 많이 일으킨다
- 노드 안은 bisect(C로 된 이진 탐색)로 찾는다.
  내부 노드는 bisect_right: 구분 키와 같은 키는 오른쪽 자식으로 간다.
  잎은 bisect_left로 자리를 찾고 그 키가 맞는지 확인한다
- 값은 잎에만 둔다. 잎끼리는 next로 이어져 있다
- 같은 키를 두 번 넣으면 ValueError. 사용자에게 보여 줄 에러로 바꾸는 건 storage가 한다
"""

from bisect import bisect_left, bisect_right
from collections.abc import Iterator

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------

DEFAULT_ORDER = 255


class BPlusTree:
    """정수 키 → 정수 값. 키는 겹치지 않는다.

    order: 노드 하나에 들어갈 수 있는 자식 수. 키는 최대 order - 1개이고,
    order개가 되면 노드를 반으로 나눈다.
    """

    def __init__(self, order: int = DEFAULT_ORDER) -> None:
        if order < 3:
            raise ValueError(f"order must be at least 3 but got {order}")
        self.order = order
        self._root: _Leaf | _Internal = _Leaf()
        self._size = 0

    def __len__(self) -> int:
        return self._size

    @property
    def height(self) -> int:
        """뿌리부터 잎까지 노드 수. 잎 하나뿐이면 1."""
        height = 1
        node = self._root
        while isinstance(node, _Internal):
            node = node.children[0]
            height += 1
        return height

    def find(self, key: int) -> int | None:
        """키의 값. 없으면 None."""
        leaf = self._find_leaf(key)
        index = bisect_left(leaf.keys, key)
        if index < len(leaf.keys) and leaf.keys[index] == key:
            return leaf.values[index]
        return None

    def has_key(self, key: int) -> bool:
        return self.find(key) is not None

    def insert(self, key: int, value: int) -> None:
        """키가 이미 있으면 ValueError (트리는 그대로)."""
        split = _insert_into(self._root, key, value, self.order)
        self._size += 1
        if split is None:
            return
        separator, right = split
        self._root = _Internal([separator], [self._root, right])

    def items(self) -> Iterator[tuple[int, int]]:
        """키 순서대로 (키, 값). 가장 왼쪽 잎부터 next를 따라간다."""
        node = self._root
        while isinstance(node, _Internal):
            node = node.children[0]
        leaf: _Leaf | None = node
        while leaf is not None:
            yield from zip(leaf.keys, leaf.values)
            leaf = leaf.next

    def has_valid_structure(self) -> bool:
        """테스트용: B+ 트리 규칙을 모두 지키면 참.

        노드 안 키 정렬, 노드마다 키 개수 범위, 구분 키와 자식 키의 범위,
        모든 잎의 깊이가 같음, 잎 연결 순서와 전체 키 개수를 본다.
        """
        checker = _StructureChecker(self.order)
        if not checker.is_valid(self._root, None, None, 1, is_root=True):
            return False
        if len(checker.leaf_depths) != 1:
            return False
        keys = [key for key, _ in self.items()]
        is_increasing = all(left < right for left, right in zip(keys, keys[1:]))
        return is_increasing and len(keys) == self._size

    def _find_leaf(self, key: int) -> "_Leaf":
        node = self._root
        while isinstance(node, _Internal):
            node = node.children[bisect_right(node.keys, key)]
        return node


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------


class _Leaf:
    __slots__ = ("keys", "values", "next")

    def __init__(self, keys: list[int] | None = None,
                 values: list[int] | None = None) -> None:
        self.keys = keys if keys is not None else []
        self.values = values if values is not None else []
        self.next: _Leaf | None = None


class _Internal:
    """children[i]에는 keys[i - 1] 이상, keys[i] 미만인 키가 있다."""

    __slots__ = ("keys", "children")

    def __init__(self, keys: list[int],
                 children: list["_Leaf | _Internal"]) -> None:
        self.keys = keys
        self.children = children


_Split = tuple[int, "_Leaf | _Internal"]


def _insert_into(node: "_Leaf | _Internal", key: int, value: int,
                 order: int) -> _Split | None:
    """node 아래에 넣는다. node가 나뉘면 (구분 키, 오른쪽 새 노드)."""
    if isinstance(node, _Leaf):
        return _insert_into_leaf(node, key, value, order)

    child_index = bisect_right(node.keys, key)
    split = _insert_into(node.children[child_index], key, value, order)
    if split is None:
        return None
    separator, right = split
    node.keys.insert(child_index, separator)
    node.children.insert(child_index + 1, right)
    if len(node.keys) < order:
        return None
    return _split_internal(node)


def _insert_into_leaf(leaf: _Leaf, key: int, value: int,
                      order: int) -> _Split | None:
    index = bisect_left(leaf.keys, key)
    if index < len(leaf.keys) and leaf.keys[index] == key:
        raise ValueError(f"key {key} already exists")
    leaf.keys.insert(index, key)
    leaf.values.insert(index, value)
    if len(leaf.keys) < order:
        return None
    return _split_leaf(leaf)


def _split_leaf(leaf: _Leaf) -> _Split:
    # 잎은 구분 키를 오른쪽 잎에도 남긴다. 값은 잎에만 있기 때문이다.
    middle = len(leaf.keys) // 2
    right = _Leaf(leaf.keys[middle:], leaf.values[middle:])
    del leaf.keys[middle:]
    del leaf.values[middle:]
    right.next = leaf.next
    leaf.next = right
    return right.keys[0], right


def _split_internal(node: _Internal) -> _Split:
    # 내부 노드는 가운데 키를 위로 올리고 양쪽에서 뺀다.
    middle = len(node.keys) // 2
    separator = node.keys[middle]
    right = _Internal(node.keys[middle + 1:], node.children[middle + 1:])
    del node.keys[middle:]
    del node.children[middle + 1:]
    return separator, right


class _StructureChecker:
    """has_valid_structure용. 노드를 내려가며 잎의 깊이를 모은다."""

    def __init__(self, order: int) -> None:
        self.max_keys = order - 1
        # 뿌리가 아닌 노드는 나뉜 뒤에도 키가 ceil(order / 2) - 1개 이상이다.
        self.min_keys = (order + 1) // 2 - 1
        self.leaf_depths: set[int] = set()

    def is_valid(self, node: "_Leaf | _Internal", low: int | None,
                 high: int | None, depth: int, is_root: bool) -> bool:
        """node의 키가 모두 low 이상, high 미만인지까지 본다."""
        if not self._has_valid_keys(node.keys, low, high, is_root):
            return False
        if isinstance(node, _Leaf):
            self.leaf_depths.add(depth)
            return len(node.values) == len(node.keys)
        return self._has_valid_children(node, low, high, depth)

    def _has_valid_keys(self, keys: list[int], low: int | None,
                        high: int | None, is_root: bool) -> bool:
        if any(left >= right for left, right in zip(keys, keys[1:])):
            return False
        if len(keys) > self.max_keys:
            return False
        if not is_root and len(keys) < self.min_keys:
            return False
        if keys and low is not None and keys[0] < low:
            return False
        return not (keys and high is not None and keys[-1] >= high)

    def _has_valid_children(self, node: _Internal, low: int | None,
                            high: int | None, depth: int) -> bool:
        if not node.keys or len(node.children) != len(node.keys) + 1:
            return False
        bounds = [low, *node.keys, high]
        return all(
            self.is_valid(child, bounds[i], bounds[i + 1], depth + 1, False)
            for i, child in enumerate(node.children)
        )
