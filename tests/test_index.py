"""B+ 트리 인덱스를 엔진·저장에 연결한 것 테스트 (Phase 2).

테스트 ID(i1~i7)는 임시다. Phase 2 요구분석 테스트 계획이 정해지면 맞춘다.
"""

import pytest

from conftest import USERS_HEADER, read_table, write_table
from minidb.engine import Engine
from minidb.errors import SqlError
from minidb.storage import Table, open_table

THREE_USERS = USERS_HEADER + "1,yena,24\n2,kim,20\n3,Yena,24\n"


def test_i1_find_row_by_id(workspace):
    """id로 행을 찾고, 없는 id는 None"""
    write_table(workspace, "users", THREE_USERS)
    table = open_table("users")
    assert table.find_row_by_id(2) == (2, "kim", 20)
    assert table.find_row_by_id(4) is None


def test_i2_index_sees_appended_rows(workspace):
    """읽기 전에 쓴 행도, 읽은 뒤에 쓴 행도 인덱스로 찾아진다"""
    write_table(workspace, "users", USERS_HEADER)
    table = open_table("users")
    table.append_rows([(1, "yena", 24)])
    assert table.find_row_by_id(1) == (1, "yena", 24)
    table.append_rows([(2, "kim", 20)])
    assert table.find_row_by_id(2) == (2, "kim", 20)
    assert table.read_rows() == [(1, "yena", 24), (2, "kim", 20)]
    table.close()


def test_i3_duplicate_id_in_file_is_error(workspace):
    """파일에 같은 id가 두 번 있으면 SqlError"""
    write_table(workspace, "users", USERS_HEADER + "1,a,1\n1,b,2\n")
    with pytest.raises(SqlError) as error:
        open_table("users").read_rows()
    assert "duplicate id 1" in error.value.message


def test_i4_where_id_uses_index(workspace, monkeypatch):
    """WHERE id = ? 는 선형 탐색(read_rows)을 부르지 않는다"""
    write_table(workspace, "users", THREE_USERS)

    def fail_scan(self):
        raise AssertionError("WHERE id는 선형 탐색을 하면 안 됨")

    monkeypatch.setattr(Table, "read_rows", fail_scan)
    engine = Engine()
    assert engine.execute("SELECT * FROM users WHERE id = 2;").rows == [
        (2, "kim", 20),
    ]
    assert engine.execute("SELECT name FROM users WHERE id = 9;").rows == []
    engine.close()


def test_i5_other_column_uses_scan(workspace, monkeypatch):
    """id가 아닌 컬럼은 인덱스를 쓰지 않고 선형 탐색"""
    write_table(workspace, "users", THREE_USERS)

    def fail_index(self, row_id):
        raise AssertionError("id가 아닌 컬럼은 인덱스를 쓰면 안 됨")

    monkeypatch.setattr(Table, "find_row_by_id", fail_index)
    engine = Engine()
    result = engine.execute("SELECT id FROM users WHERE age = 24;")
    assert result.rows == [(1,), (3,)]
    engine.close()


def test_i6_insert_then_select_by_id(workspace):
    """같은 엔진에서 INSERT한 행을 바로 id로 찾는다 (인덱스에 등록됨)"""
    write_table(workspace, "users", THREE_USERS)
    engine = Engine()
    engine.execute("SELECT * FROM users WHERE id = 1;")
    engine.execute("INSERT INTO users VALUES ('park', 30), ('lee', 31);")
    assert engine.execute("SELECT name FROM users WHERE id = 5;").rows == [
        ("lee",),
    ]
    engine.close()


def test_i7_next_id_collision_writes_nothing(workspace):
    """손으로 고쳐 id가 차례대로가 아닌 파일: 마지막 id + 1이 겹치면 SqlError,
    파일은 그대로
    """
    original = USERS_HEADER + "5,a,1\n3,b,2\n"
    write_table(workspace, "users", original)
    engine = Engine()
    engine.execute("SELECT * FROM users WHERE id = 5;")
    engine.execute("INSERT INTO users VALUES ('c', 3);")   # id 4
    with pytest.raises(SqlError) as error:
        engine.execute("INSERT INTO users VALUES ('d', 4);")   # id 5
    assert "already has id 5" in error.value.message
    engine.close()
    assert read_table(workspace, "users") == original + "4,c,3\n"
