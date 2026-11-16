"""B+ 트리의 분할과 키 검색을 확인한다."""

from random import Random

from minidb.bptree import BPlusTree


def test_find_after_leaf_and_branch_splits():
    tree = BPlusTree[int](max_keys=3)
    keys = list(range(-100, 101))
    Random(0).shuffle(keys)
    for key in keys:
        tree.insert(key * 2, key)

    for key in keys:
        assert tree.find(key * 2) == [key]
        assert tree.find(key * 2 + 1) == []
    assert tree.find(-201) == []


def test_find_duplicate_keys_across_leaves_in_insert_order():
    tree = BPlusTree[str](max_keys=2)
    assert tree.find(7) == []

    for number in range(30):
        tree.insert(6, "left")
        tree.insert(7, str(number))
        tree.insert(8, "right")

    assert tree.find(7) == [str(number) for number in range(30)]
