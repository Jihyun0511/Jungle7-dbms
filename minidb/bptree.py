"""정수 키로 메모리의 값을 찾는 B+ 트리 (Phase 2)."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Generic, TypeAlias, TypeVar

_Value = TypeVar("_Value")


@dataclass(slots=True)
class _Leaf(Generic[_Value]):
    keys: list[int] = field(default_factory=list)
    values: list[_Value] = field(default_factory=list)
    next_leaf: _Leaf[_Value] | None = None


@dataclass(slots=True)
class _Branch(Generic[_Value]):
    keys: list[int]
    children: list[_Node[_Value]]


_Node: TypeAlias = _Leaf[_Value] | _Branch[_Value]


class BPlusTree(Generic[_Value]):
    """리프에 값을 저장하고, 내부 노드에는 오른쪽 자식의 시작 키를 둔다."""

    def __init__(self, max_keys: int = 64) -> None:
        if max_keys < 2:
            raise ValueError("max_keys must be at least 2")
        self._max_keys = max_keys
        self._root: _Node[_Value] = _Leaf()

    def insert(self, key: int, value: _Value) -> None:
        """같은 키가 있으면 기존 값 뒤에 추가한다."""
        split = self._insert(self._root, key, value)
        if split is not None:
            separator, right = split
            self._root = _Branch([separator], [self._root, right])

    def find(self, key: int) -> list[_Value]:
        """키와 일치하는 값을 삽입 순서대로 반환한다."""
        node = self._root
        while isinstance(node, _Branch):
            node = node.children[bisect_left(node.keys, key)]

        matches = []
        leaf: _Leaf[_Value] | None = node
        while leaf is not None:
            start = bisect_left(leaf.keys, key)
            end = bisect_right(leaf.keys, key, lo=start)
            matches.extend(leaf.values[start:end])
            if end < len(leaf.keys):
                break
            # 같은 키가 리프 분할 경계를 넘어 이어질 수 있다.
            leaf = leaf.next_leaf
        return matches

    def _insert(
        self, node: _Node[_Value], key: int, value: _Value,
    ) -> tuple[int, _Node[_Value]] | None:
        index = bisect_right(node.keys, key)
        if isinstance(node, _Leaf):
            node.keys.insert(index, key)
            node.values.insert(index, value)
            if len(node.keys) > self._max_keys:
                return _split_leaf(node)
            return None

        split = self._insert(node.children[index], key, value)
        if split is None:
            return None
        separator, right = split
        node.keys.insert(index, separator)
        node.children.insert(index + 1, right)
        if len(node.keys) > self._max_keys:
            return _split_branch(node)
        return None


def _split_leaf(leaf: _Leaf[_Value]) -> tuple[int, _Leaf[_Value]]:
    middle = len(leaf.keys) // 2
    right = _Leaf(leaf.keys[middle:], leaf.values[middle:], leaf.next_leaf)
    del leaf.keys[middle:]
    del leaf.values[middle:]
    leaf.next_leaf = right
    return right.keys[0], right


def _split_branch(branch: _Branch[_Value]) -> tuple[int, _Branch[_Value]]:
    middle = len(branch.keys) // 2
    separator = branch.keys[middle]
    right = _Branch(branch.keys[middle + 1:], branch.children[middle + 1:])
    del branch.keys[middle:]
    del branch.children[middle + 1:]
    return separator, right
