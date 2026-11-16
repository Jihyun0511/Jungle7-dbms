"""저장(CSV)·스키마 단위 테스트 (R-Q1). 노션 5절 s1~s6, Phase 2 s7~s12."""

import pytest

import minidb.storage
from conftest import USERS_HEADER, read_table, write_table
from minidb.bptree import BPlusTree
from minidb.errors import SqlError
from minidb.schema import Column
from minidb.storage import open_table


def test_s1_read_header(workspace):
    write_table(workspace, "users", USERS_HEADER)
    schema = open_table("users").schema
    assert schema.columns == [
        Column("id", int), Column("name", str), Column("age", int)
    ]
    assert schema.names == ["id", "name", "age"]
    assert schema.find("age") == 2
    assert schema.find("unknown") is None
    assert schema.value_columns == [Column("name", str), Column("age", int)]


@pytest.mark.parametrize(
    ("header", "message"),
    [
        ("id:int,age:float\n", "column 2: unknown type float"),
        ("id:int,name\n", "column 2: missing type"),
        ("id:int,name:str,NAME:str\n", "column 3: duplicate name name"),
        ("name:str\n", "has no id column"),
        ("id:str\n", "id column must be int"),
        ("", "header is empty"),
    ],
)
def test_s2_header_errors(workspace, header, message):
    write_table(workspace, "users", header)
    with pytest.raises(SqlError, match=message):
        open_table("users")


def test_s2b_only_first_header_error(workspace):
    write_table(workspace, "users", "name,name:float\n")
    with pytest.raises(SqlError) as error:
        open_table("users")
    assert error.value.message == "users.csv header column 1: missing type"


def test_s3_values_get_schema_types(workspace):
    write_table(workspace, "users", USERS_HEADER + "1,yena,24\n2,024,-5\n")
    assert open_table("users").read_rows() == [(1, "yena", 24), (2, "024", -5)]


def test_s4_tricky_values_round_trip(workspace):
    write_table(workspace, "users", USERS_HEADER)
    rows = [(1, '이름,"별명"\r\n둘째 줄\r셋째 줄\n넷째 줄', 24)]
    table = open_table("users")
    try:
        table.append_rows(rows)
    finally:
        table.close()
    assert open_table("users").read_rows() == rows


def test_s5_next_id(workspace):
    write_table(workspace, "users", USERS_HEADER)
    assert open_table("users").find_next_id() == 1
    write_table(workspace, "users", "name:str,id:int\nyena,9\nkim,3\n")
    assert open_table("users").find_next_id() == 4


def test_s5b_next_id_when_last_row_has_newline(workspace):
    write_table(workspace, "users", USERS_HEADER + '3,"첫줄\n둘째줄",24')
    table = open_table("users")
    try:
        assert table.find_next_id() == 4
        table.append_rows([(4, "kim", 20)])
        assert table.read_rows() == [(3, "첫줄\n둘째줄", 24), (4, "kim", 20)]
    finally:
        table.close()


def test_s6_read_sees_unflushed_rows(workspace):
    write_table(workspace, "users", USERS_HEADER)
    table = open_table("users")
    try:
        table.append_rows([(1, "yena", 24)])
        assert read_table(workspace, "users") == USERS_HEADER
        assert table.find_next_id() == 2
        assert table.read_rows() == [(1, "yena", 24)]

        table.append_rows([(2, "kim", 20)])
        assert table.find_next_id() == 3
        assert read_table(workspace, "users") == USERS_HEADER + "1,yena,24\n"
    finally:
        table.close()
    table.close()
    assert open_table("users").read_rows() == [(1, "yena", 24), (2, "kim", 20)]


@pytest.fixture
def built_trees(monkeypatch):
    """storage가 만든 B+ 트리를 모은다. 트리를 언제 만드는지 확인용."""
    trees = []

    def make_tree():
        tree = BPlusTree(order=3)
        trees.append(tree)
        return tree

    monkeypatch.setattr(minidb.storage, "BPlusTree", make_tree)
    return trees


def test_s7_find_row_by_id_reads_one_row(workspace, built_trees):
    write_table(
        workspace, "users",
        USERS_HEADER + '1,yena,24\n2,"첫줄\n둘째줄",20\n3,kim,30\n'
        + "".join(f"{i},user{i},{i}\n" for i in range(4, 21)),
    )
    table = open_table("users")
    assert table.find_row_by_id(2) == (2, "첫줄\n둘째줄", 20)
    assert table.find_row_by_id(3) == (3, "kim", 30)
    assert table.find_row_by_id(20) == (20, "user20", 20)
    assert table.find_row_by_id(21) is None
    assert table.find_row_by_id(0) is None
    assert len(built_trees) == 1
    assert table.find_next_id() == 21


def test_s8_insert_does_not_build_tree(workspace, built_trees):
    write_table(workspace, "users", USERS_HEADER + "1,yena,24\n")
    table = open_table("users")
    try:
        table.append_rows([(2, "kim", 20)])
        assert built_trees == []

        # 트리를 처음 만들 때 아직 flush 안 된 행까지 읽는다 (B14)
        assert table.find_row_by_id(2) == (2, "kim", 20)
        assert len(built_trees) == 1
    finally:
        table.close()


def test_s9_insert_after_tree_is_registered(workspace, built_trees):
    write_table(workspace, "users", USERS_HEADER + "1,yena,24\n")
    table = open_table("users")
    try:
        assert table.find_row_by_id(1) == (1, "yena", 24)
        rows = [(i, f"user{i}", i) for i in range(2, 12)]
        table.append_rows(rows)
        table.append_rows([(12, '쉼표,와 "따옴표"', 12)])
        assert len(built_trees) == 1
        assert len(built_trees[0]) == 12
        for row in rows:
            assert table.find_row_by_id(row[0]) == row
        assert table.find_row_by_id(12) == (12, '쉼표,와 "따옴표"', 12)
    finally:
        table.close()


def test_s10_duplicate_ids(workspace):
    write_table(workspace, "users", USERS_HEADER + "1,a,1\n2,b,2\n1,c,3\n")
    with pytest.raises(SqlError) as error:
        open_table("users").find_row_by_id(2)
    assert error.value.message == "users.csv data row 3: duplicate id 1"

    # 마지막 행 id + 1 (B13)이 앞 행의 id와 겹치는 파일
    text = USERS_HEADER + "1,a,1\n5,b,2\n4,c,3\n"
    write_table(workspace, "users", text)
    table = open_table("users")
    try:
        assert table.find_row_by_id(5) == (5, "b", 2)
        with pytest.raises(SqlError, match="id 5 already exists in users"):
            table.append_rows([(5, "d", 4)])
        assert table.find_next_id() == 5
    finally:
        table.close()
    assert read_table(workspace, "users") == text


def test_s11_id_not_first_column(workspace):
    write_table(
        workspace, "staff",
        "name:str,id:int,age:int\nyena,4,24\n\"kim, jr\",9,20\npark,2,22\n",
    )
    table = open_table("staff")
    assert table.find_row_by_id(9) == ("kim, jr", 9, 20)
    assert table.find_row_by_id(2) == ("park", 2, 22)
    assert table.find_row_by_id(3) is None
    assert table.find_next_id() == 3


def test_s12_quick_split_matches_csv(workspace):
    """따옴표 없는 행은 쉼표로 바로 자른다. 섞인 파일에서도 결과가 같아야 한다."""
    write_table(
        workspace, "items",
        "name:str,note:str,id:int\n"
        "a,plain,1\r\n"
        '"b, c","say ""hi""",2\r\n'
        'd,"첫줄\n둘째줄",3\r\n'
        ",,4\r\n"
        "한글,값,5\r\n"
        '"",x,6',
    )
    table = open_table("items")
    rows = table.read_rows()
    assert [row[2] for row in rows] == [1, 2, 3, 4, 5, 6]
    assert [table.find_row_by_id(row[2]) for row in rows] == rows
    assert table.find_next_id() == 7


def test_s12_invalid_id_is_error_on_both_paths(workspace):
    for line in ("x,1,abc\n", '"x",1,abc\n', "x,1\n"):
        write_table(workspace, "items", "name:str,age:int,id:int\n" + line)
        with pytest.raises(SqlError, match="data row 1 has an invalid id"):
            open_table("items").find_row_by_id(1)
