"""B+ 트리 단위 테스트 (Phase 2).

테스트 ID(t1~t10)는 임시다. Phase 2 요구분석 테스트 계획이 정해지면 맞춘다.
차수(max_keys)를 작게 두어 키 몇 개만으로도 분할이 일어나게 한다.
"""

import random

import pytest

from minidb.bptree import BPlusTree


def test_t1_rejects_small_order():
    """max_keys가 2보다 작으면 ValueError, 2는 허용"""
    for max_keys in (0, 1):
        with pytest.raises(ValueError):
            BPlusTree(max_keys)
    assert len(BPlusTree(2)) == 0


def test_t2_empty_tree():
    """빈 트리: 못 찾음, 크기 0, 높이 1, 구조 정상"""
    tree = BPlusTree(4)
    assert tree.find(1) is None
    assert len(tree) == 0
    assert tree.height == 1
    assert tree.has_valid_structure()


def test_t3_insert_and_find_few():
    """몇 개 넣고 찾기, 없는 키는 None"""
    tree = BPlusTree(4)
    for key in (10, 30, 20):
        tree.insert(key, key * 10)
    assert tree.find(20) == 200
    assert tree.find(25) is None
    assert len(tree) == 3
    assert tree.has_valid_structure()


def test_t4_duplicate_key_keeps_old_value():
    """같은 키를 또 넣으면 KeyError, 원래 값과 크기는 그대로"""
    tree = BPlusTree(4)
    tree.insert(5, 50)
    with pytest.raises(KeyError):
        tree.insert(5, 999)
    assert tree.find(5) == 50
    assert len(tree) == 1


def test_t5_first_split_grows_height():
    """최대 4개인 리프에 5번째 키가 들어오면 쪼개져 높이 2"""
    tree = BPlusTree(4)
    for key in range(1, 5):
        tree.insert(key, key * 10)
    assert tree.height == 1
    tree.insert(5, 50)
    assert tree.height == 2
    assert tree.has_valid_structure()
    assert [tree.find(key) for key in range(1, 6)] == [10, 20, 30, 40, 50]


def test_t6_ascending_many():
    """id처럼 1부터 차례로 10만 개 (Phase 2의 실제 사용 모양)"""
    count = 100_000
    tree = BPlusTree(4)
    for key in range(1, count + 1):
        tree.insert(key, key - 1)
    assert len(tree) == count
    assert tree.has_valid_structure()
    assert all(tree.find(key) == key - 1 for key in range(1, count + 1))
    assert tree.find(0) is None
    assert tree.find(count + 1) is None


@pytest.mark.parametrize("max_keys", [2, 3, 4, 5, 16, 128])
def test_t7_shuffled_keys(max_keys):
    """섞인 순서로 넣어도 가운데 노드 분할이 맞는지, 차수 여러 개로"""
    keys = list(range(20_000))
    random.Random(max_keys).shuffle(keys)
    tree = BPlusTree(max_keys)
    for key in keys:
        tree.insert(key, key * 2)
    assert tree.has_valid_structure()
    assert all(tree.find(key) == key * 2 for key in range(20_000))


def test_t8_negative_and_huge_keys():
    """음수, 0, 64비트를 넘는 큰 정수도 키가 된다 (파이썬 int)"""
    tree = BPlusTree(3)
    keys = [2**70, -5, 0, -2**70, 7, -1]
    for value, key in enumerate(keys):
        tree.insert(key, value)
    assert tree.has_valid_structure()
    assert tree.find(-2**70) == 3
    assert tree.find(2**70) == 0
    assert tree.find(1) is None


def test_t9_find_range_follows_leaf_chain():
    """low 이상 high 이하를 키 순서대로. 리프 여러 개에 걸쳐도 이어진다"""
    tree = BPlusTree(3)
    for key in range(1, 31):
        tree.insert(key, f"row{key}")
    assert [key for key, _ in tree.find_range(5, 12)] == list(range(5, 13))
    assert list(tree.find_range(29, 100)) == [(29, "row29"), (30, "row30")]
    assert list(tree.find_range(40, 50)) == []


def test_t10_height_with_large_order():
    """차례로 100만 개, 차수 128 → 높이 4.

    쪼갠 왼쪽 노드가 반만 찬 채로 남아 노드당 키가 64개쯤이라
    100만 / 64 / 64 / 64 → 리프 위로 3층.
    """
    tree = BPlusTree(128)
    for key in range(1, 1_000_001):
        tree.insert(key, key)
    assert tree.height == 4
    assert tree.has_valid_structure()
