"""B+ 트리 단위 테스트 (Phase 2). b1~b10.

분할을 많이 일으키려고 작은 order(3~4)를 쓴다. 기본 order 255는 b6과
100만 건 실행으로 확인한다. 넣은 뒤에는 has_valid_structure로 트리 모양
(정렬, 키 개수, 구분 키 범위, 잎 깊이, 잎 연결)까지 본다.
"""

import random

import pytest

from minidb.bptree import DEFAULT_ORDER, BPlusTree


def test_b1_empty_tree_finds_nothing():
    tree = BPlusTree()
    assert tree.find(1) is None
    assert not tree.has_key(1)
    assert len(tree) == 0
    assert tree.height == 1
    assert list(tree.items()) == []
    assert tree.has_valid_structure()


def test_b2_find_after_many_splits():
    tree = BPlusTree(order=4)
    keys = list(range(1, 501))
    random.Random(7).shuffle(keys)
    for key in keys:
        tree.insert(key, key * 10)
    assert len(tree) == 500
    assert tree.has_valid_structure()
    assert all(tree.find(key) == key * 10 for key in range(1, 501))
    assert tree.find(0) is None
    assert tree.find(501) is None


def test_b3_separator_keys_are_found():
    # order 3이면 키 3개에서 잎이 [1] [2, 3]으로 나뉘고 2가 구분 키가 된다.
    # 구분 키와 같은 키는 오른쪽 잎에 있어야 한다 (bisect_right).
    tree = BPlusTree(order=3)
    for key in range(1, 3):
        tree.insert(key, key)
    assert tree.height == 1
    tree.insert(3, 3)
    assert tree.height == 2
    assert tree.has_valid_structure()
    assert [tree.find(key) for key in range(1, 4)] == [1, 2, 3]

    for key in range(4, 30):
        tree.insert(key, key)
    assert tree.height >= 3
    assert tree.has_valid_structure()
    assert [tree.find(key) for key in range(1, 30)] == list(range(1, 30))


def test_b4_leaves_are_linked_in_key_order():
    tree = BPlusTree(order=3)
    for key in [5, 1, 9, 3, 7, 2, 8, 4, 6]:
        tree.insert(key, -key)
    assert list(tree.items()) == [(key, -key) for key in range(1, 10)]
    assert tree.has_valid_structure()


def test_b5_duplicate_key_is_error_and_tree_unchanged():
    tree = BPlusTree(order=3)
    for key in range(1, 6):
        tree.insert(key, key)
    with pytest.raises(ValueError, match="key 3 already exists"):
        tree.insert(3, 99)
    assert tree.find(3) == 3
    assert len(tree) == 5
    assert tree.has_valid_structure()


def test_b6_default_order_is_one_page():
    tree = BPlusTree()
    assert tree.order == DEFAULT_ORDER == 255
    for key in range(1, 100_001):
        tree.insert(key, key)
    # 순서대로 넣으면 노드가 반쯤 차서 한 층에 약 127배씩 늘어난다.
    assert tree.height == 3
    assert tree.has_valid_structure()
    assert tree.find(100_000) == 100_000


def test_b7_order_too_small_is_error():
    with pytest.raises(ValueError):
        BPlusTree(order=2)


@pytest.mark.parametrize("order", [3, 4, 5, 16])
def test_b8_shuffled_keys_with_many_orders(order):
    tree = BPlusTree(order=order)
    keys = list(range(300))
    random.Random(order).shuffle(keys)
    for key in keys:
        tree.insert(key, -key)
    assert tree.has_valid_structure()
    assert [key for key, _ in tree.items()] == list(range(300))
    assert all(tree.find(key) == -key for key in keys)


def test_b9_negative_and_huge_keys():
    tree = BPlusTree(order=3)
    keys = [-(10**30), -5, 0, 7, 2**63, 10**30]
    for key in reversed(keys):
        tree.insert(key, key)
    assert tree.has_valid_structure()
    assert all(tree.find(key) == key for key in keys)
    assert tree.find(1) is None


def test_b10_structure_check_catches_broken_tree():
    tree = BPlusTree(order=3)
    for key in range(1, 10):
        tree.insert(key, key)
    assert tree.has_valid_structure()
    tree._root.keys[0] = 100  # 구분 키를 일부러 망가뜨린다
    assert not tree.has_valid_structure()
