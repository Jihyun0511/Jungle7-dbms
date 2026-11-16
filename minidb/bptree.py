"""메모리 기반 B+ 트리: 정수 키(id) → 값 (Phase 2 인덱스).

- 노드 하나에 키가 max_keys개까지 들어간다. 넘치면(max_keys + 1개) 반으로 쪼갠다
- 데이터(값)는 리프에만 있다. 내부 노드의 키는 길 안내용 이정표다
- 리프는 오른쪽 리프와 next로 이어져 있어 범위 검색을 옆으로 따라간다
- 리프를 쪼갤 때는 오른쪽 첫 키를 부모에 "복사"하고,
  내부 노드를 쪼갤 때는 가운데 키를 부모로 "이동"한다
- 값에 무엇을 넣을지(행 번호, 파일 위치 등)는 부르는 쪽이 정한다

담당: (이름)
"""

from bisect import bisect_left, bisect_right
from collections.abc import Iterator

DEFAULT_MAX_KEYS = 128


class BPlusTree:
    """키는 서로 달라야 한다. 지우기는 없다 (DELETE는 비목표)."""

    def __init__(self, max_keys: int = DEFAULT_MAX_KEYS) -> None:
        """max_keys: 노드 하나의 최대 키 수 (차수). 2보다 작으면 ValueError."""
        if max_keys < 2:
            raise ValueError(f"max_keys는 2 이상이어야 함: {max_keys}")
        self.max_keys = max_keys
        self._root: _Leaf | _Internal = _Leaf()
        self._size = 0
        self._height = 1

    def __len__(self) -> int:
        return self._size

    @property
    def height(self) -> int:
        """루트에서 리프까지 노드 수. 비어 있으면 1 (빈 리프 하나)."""
        return self._height

    def insert(self, key: int, value: object) -> None:
        """이미 있는 키면 KeyError. 그때 원래 값은 그대로 남는다.

        value로 None은 넣지 않는다 (find가 None을 "없음"으로 쓴다).
        """
        parents, leaf = self._find_path(key)
        index = bisect_left(leaf.keys, key)
        if _has_key_at(leaf, index, key):
            raise KeyError(f"키 {key}가 이미 있음")
        leaf.keys.insert(index, key)
        leaf.values.insert(index, value)
        self._split_up(leaf, parents)
        self._size += 1

    def find(self, key: int) -> object | None:
        """키의 값. 없으면 None."""
        leaf = self._find_leaf(key)
        index = bisect_left(leaf.keys, key)
        if not _has_key_at(leaf, index, key):
            return None
        return leaf.values[index]

    def find_range(self, low: int, high: int) -> Iterator[tuple[int, object]]:
        """low 이상 high 이하인 (키, 값)을 키 순서대로.

        시작 리프 하나만 찾고, 그다음은 리프의 next를 따라 옆으로 간다.
        """
        leaf = self._find_leaf(low)
        index = bisect_left(leaf.keys, low)
        while leaf is not None:
            for key, value in zip(leaf.keys[index:], leaf.values[index:]):
                if key > high:
                    return
                yield key, value
            leaf, index = leaf.next, 0

    def has_valid_structure(self) -> bool:
        """테스트용: B+ 트리 규칙을 모두 지키면 참.

        노드 안 키 정렬, 키 개수 범위, 이정표와 자식 키 범위,
        모든 리프 깊이 같음, 리프 연결 순서와 전체 키 개수를 본다.
        """
        checker = _StructureChecker(self.max_keys)
        if not checker.is_valid_subtree(self._root, 1, None, None):
            return False
        if checker.key_count != self._size:
            return False
        if checker.leaf_depth != self._height:
            return False
        return _has_sorted_leaf_chain(self._root, self._size)

    def _find_path(self, key: int) -> tuple[list[tuple["_Internal", int]],
                                            "_Leaf"]:
        """루트부터 key가 들어갈 리프까지. parents는 (노드, 내려간 자식 번호)."""
        parents = []
        node = self._root
        while isinstance(node, _Internal):
            child_index = bisect_right(node.keys, key)
            parents.append((node, child_index))
            node = node.children[child_index]
        return parents, node

    def _find_leaf(self, key: int) -> "_Leaf":
        _, leaf = self._find_path(key)
        return leaf

    def _split_up(self, node: "_Leaf | _Internal",
                  parents: list[tuple["_Internal", int]]) -> None:
        """넘친 노드를 쪼개 부모에 넣는다. 부모가 넘치면 또 쪼갠다."""
        while len(node.keys) > self.max_keys:
            promoted, right = _split_node(node)
            if not parents:
                self._grow_root(node, promoted, right)
                return
            parent, child_index = parents.pop()
            parent.keys.insert(child_index, promoted)
            parent.children.insert(child_index + 1, right)
            node = parent

    def _grow_root(self, left: "_Leaf | _Internal", key: int,
                   right: "_Leaf | _Internal") -> None:
        """루트가 쪼개지면 그 위에 새 루트를 둔다. 트리는 이때만 높아진다."""
        self._root = _Internal([key], [left, right])
        self._height += 1


class _Leaf:
    # 노드가 수만 개라 __slots__로 객체마다 붙는 dict를 없앤다
    __slots__ = ("keys", "values", "next")

    def __init__(self, keys: list[int] | None = None,
                 values: list[object] | None = None,
                 next_leaf: "_Leaf | None" = None) -> None:
        self.keys = [] if keys is None else keys
        self.values = [] if values is None else values
        self.next = next_leaf


class _Internal:
    """자식은 키보다 하나 많다. children[i]의 키는 keys[i-1] 이상 keys[i] 미만."""

    __slots__ = ("keys", "children")

    def __init__(self, keys: list[int],
                 children: list["_Leaf | _Internal"]) -> None:
        self.keys = keys
        self.children = children


def _has_key_at(leaf: _Leaf, index: int, key: int) -> bool:
    return index < len(leaf.keys) and leaf.keys[index] == key


def _split_node(node: _Leaf | _Internal) -> tuple[int, _Leaf | _Internal]:
    """node의 뒤쪽 절반을 새 노드로 옮긴다. (부모에 올릴 키, 새 노드)."""
    if isinstance(node, _Leaf):
        return _split_leaf(node)
    return _split_internal(node)


def _split_leaf(leaf: _Leaf) -> tuple[int, _Leaf]:
    """올린 키가 오른쪽 리프에도 남는다 (복사). 데이터는 리프에만 있어야 해서."""
    keep = len(leaf.keys) // 2
    right = _Leaf(leaf.keys[keep:], leaf.values[keep:], leaf.next)
    del leaf.keys[keep:]
    del leaf.values[keep:]
    leaf.next = right
    return right.keys[0], right


def _split_internal(node: _Internal) -> tuple[int, _Internal]:
    """가운데 키는 양쪽 어디에도 남지 않는다 (이동). 이정표는 한 곳이면 돼서."""
    middle = len(node.keys) // 2
    promoted = node.keys[middle]
    right = _Internal(node.keys[middle + 1:], node.children[middle + 1:])
    del node.keys[middle:]
    del node.children[middle + 1:]
    return promoted, right


class _StructureChecker:
    """has_valid_structure용. 돌면서 리프 깊이와 키 개수를 모은다."""

    def __init__(self, max_keys: int) -> None:
        self.max_keys = max_keys
        self.leaf_depth: int | None = None
        self.key_count = 0

    def is_valid_subtree(self, node: _Leaf | _Internal, depth: int,
                         low: int | None, high: int | None) -> bool:
        """depth: 루트가 1. node의 키는 모두 low 이상 high 미만 (None은 끝 없음)."""
        if not self._has_valid_count(node, depth):
            return False
        if not _has_sorted_keys_in_range(node.keys, low, high):
            return False
        if isinstance(node, _Leaf):
            self.key_count += len(node.keys)
            return self._has_same_leaf_depth(depth)
        if len(node.children) != len(node.keys) + 1:
            return False
        bounds = [low, *node.keys, high]
        return all(
            self.is_valid_subtree(child, depth + 1, bounds[i], bounds[i + 1])
            for i, child in enumerate(node.children)
        )

    def _has_valid_count(self, node: _Leaf | _Internal, depth: int) -> bool:
        """루트가 아니면 최소 max_keys // 2개 (쪼갤 때 반씩 나누므로)."""
        count = len(node.keys)
        if count > self.max_keys:
            return False
        if depth == 1:
            return isinstance(node, _Leaf) or count >= 1
        return count >= max(1, self.max_keys // 2)

    def _has_same_leaf_depth(self, depth: int) -> bool:
        if self.leaf_depth is None:
            self.leaf_depth = depth
        return self.leaf_depth == depth


def _has_sorted_keys_in_range(keys: list[int], low: int | None,
                              high: int | None) -> bool:
    if any(keys[i - 1] >= keys[i] for i in range(1, len(keys))):
        return False
    if not keys:
        return True
    if low is not None and keys[0] < low:
        return False
    return high is None or keys[-1] < high


def _has_sorted_leaf_chain(root: _Leaf | _Internal, size: int) -> bool:
    """맨 왼쪽 리프부터 next를 따라가며 키가 계속 커지고 개수가 size인지."""
    leaf = root
    while isinstance(leaf, _Internal):
        leaf = leaf.children[0]
    keys = []
    while leaf is not None:
        keys.extend(leaf.keys)
        leaf = leaf.next
    is_sorted = all(keys[i - 1] < keys[i] for i in range(1, len(keys)))
    return is_sorted and len(keys) == size
