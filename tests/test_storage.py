"""저장(CSV)·스키마 단위 테스트 (R-Q1). 노션 5절 s1~s6."""

import pytest

from conftest import USERS_HEADER, read_table, write_table
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
        ("id:int,age:float\n", "2번째 컬럼: 모르는 타입 float"),
        ("id:int,name\n", "2번째 컬럼: 타입 없음"),
        ("id:int,name:str,NAME:str\n", "3번째 컬럼: 이름 중복 name"),
        ("name:str\n", "id 컬럼 없음"),
        ("id:str\n", "id 컬럼은 int여야 함"),
        ("", "헤더가 비어 있음"),
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
    assert error.value.message == "users.csv 헤더 1번째 컬럼: 타입 없음"


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
