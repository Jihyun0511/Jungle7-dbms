"""저장(CSV)·스키마 단위 테스트 (R-Q1). 노션 5절 s1~s6.

workspace 픽스처로 실행 위치를 임시 폴더로 옮긴 뒤 write_table로 파일을 만든다.
"""

import pytest

from conftest import USERS_HEADER, write_table
from minidb.errors import SqlError
from minidb.schema import parse_header
from minidb.storage import open_table


def test_s1_read_header(workspace):
    """id:int,name:str,age:int
    → 컬럼 3개 [(id, int), (name, str), (age, int)] (B11)
    """
    schema = parse_header(["id:int", "Name:str", "age:int"], "users.csv")
    assert [(column.name, column.type) for column in schema.columns] == [
        ("id", int), ("name", str), ("age", int),
    ]
    assert schema.names == ["id", "name", "age"]
    assert [column.name for column in schema.value_columns] == [
        "name", "age",
    ]
    assert schema.find("age") == 2
    assert schema.find("nope") is None


@pytest.mark.parametrize("header, expected", [
    ("id:int,age:float\n", "2번째 컬럼: 모르는 타입 float"),
    ("id:int,name\n", "2번째 컬럼: 타입 없음"),
    ("id:int,name:str,name:int\n", "3번째 컬럼: 이름 중복 name"),
    ("name:str,age:int\n", "id 컬럼이 없음"),
    ("", "헤더가 비어 있음"),
])
def test_s2_header_errors(workspace, header, expected):
    """모르는 타입, 타입 빠짐, 이름 중복, id 없음, 빈 파일 → 각각 SqlError.
    처음 만난 에러 하나만. 순서: 빈 파일 → 왼쪽 컬럼부터 (타입 없음 → 모르는 타입 → 이름 중복) → id 없음 (B20)
    """
    write_table(workspace, "users", header)
    with pytest.raises(SqlError) as caught:
        open_table("users")
    assert expected in caught.value.message
    assert "users.csv" in caught.value.message


def test_s2b_only_first_header_error(workspace):
    """name,name:float → '1번째 컬럼: 타입 없음' 하나만 (B20)"""
    write_table(workspace, "users", "name,name:float\n")
    with pytest.raises(SqlError) as caught:
        open_table("users")
    assert caught.value.message == "users.csv 헤더 1번째 컬럼: 타입 없음"


def test_s3_values_get_schema_types(workspace):
    """1,yena,24 → (1, 'yena', 24). 1과 24는 int (B12)"""
    write_table(workspace, "users", USERS_HEADER + "1,yena,24\n")
    table = open_table("users")
    assert table.read_rows() == [(1, "yena", 24)]
    table.close()


def test_s4_tricky_values_round_trip(workspace):
    """쉼표·큰따옴표·줄바꿈이 든 값을 쓰고 다시 읽으면 그대로 (B9, B12)"""
    write_table(workspace, "users", USERS_HEADER)
    tricky = 'a, "b"\n둘째줄; (c)'
    table = open_table("users")
    table.append_rows([(1, tricky, 24), (2, "", 0)])
    table.close()
    reopened = open_table("users")
    assert reopened.read_rows() == [(1, tricky, 24), (2, "", 0)]
    reopened.close()


def test_s5_next_id(workspace):
    """헤더만 → 1 / id 1, 2, 3 → 4 (B13)"""
    write_table(workspace, "empty", USERS_HEADER)
    write_table(
        workspace, "users", USERS_HEADER + "1,a,1\n2,b,2\n3,c,3\n",
    )
    empty = open_table("empty")
    users = open_table("users")
    assert empty.find_next_id() == 1
    assert users.find_next_id() == 4
    users.append_rows([(4, "d", 4), (5, "e", 5)])
    assert users.find_next_id() == 6
    empty.close()
    users.close()


def test_s5b_next_id_when_last_row_has_newline(workspace):
    """마지막 행 name에 줄바꿈 → 그 행 id + 1. 파일의 마지막 줄이 아니라 CSV 행 기준 (B13, B9)"""
    write_table(
        workspace, "users", USERS_HEADER + '1,a,1\n7,"첫줄\n둘째줄",20\n',
    )
    table = open_table("users")
    assert table.find_next_id() == 8
    table.close()


def test_s6_read_sees_unflushed_rows(workspace):
    """닫지 않은 Table에 append_rows 후 read_rows → 방금 쓴 행이 보임 (B14)"""
    write_table(workspace, "users", USERS_HEADER)
    table = open_table("users")
    table.append_rows([(1, "yena", 24)])
    assert table.read_rows() == [(1, "yena", 24)]
    table.close()
    table.close()


def test_s7_missing_line_end_is_added(workspace):
    """마지막 줄에 줄바꿈이 없어도 새 행이 그 줄에 붙지 않음 (R-Q3)"""
    write_table(workspace, "users", USERS_HEADER + "1,a,1")
    table = open_table("users")
    table.append_rows([(2, "b", 2)])
    assert table.read_rows() == [(1, "a", 1), (2, "b", 2)]
    table.close()
