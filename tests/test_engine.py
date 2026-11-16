"""엔진 단위 테스트 (R-Q1). 노션 5절 e1~e12.

Engine().execute(sql)의 Result와, 실행 뒤 파일 내용(read_table)을 같이 확인한다.
"""

import pytest

from conftest import USERS_HEADER, read_table, write_table
from minidb.engine import Engine
from minidb.errors import SqlError


@pytest.fixture
def users(workspace):
    write_table(workspace, "users", USERS_HEADER)
    return workspace


@pytest.fixture
def engine():
    engine = Engine()
    yield engine
    engine.close()


def _assert_error(engine, sql):
    with pytest.raises(SqlError) as caught:
        engine.execute(sql)
    return caught.value


def test_e1_ids_are_assigned(users, engine):
    """INSERT 두 번 → 파일에 1,yena,24 / 2,kim,20 (B13)"""
    first = engine.execute("INSERT INTO users VALUES ('yena', 24);")
    engine.execute("INSERT INTO users VALUES ('kim', 20);")
    engine.close()
    assert (first.kind, first.affected) == ("insert", 1)
    assert read_table(users, "users") == (
        USERS_HEADER + "1,yena,24\n2,kim,20\n"
    )


def test_e2_user_given_id_is_error(users, engine):
    """VALUES (5, 'yena', 24), (id, name, age) VALUES (...) → SqlError,
    파일은 헤더만 (B13)
    """
    error = _assert_error(engine, "INSERT INTO users VALUES (5, 'yena', 24);")
    assert "id" in error.message
    error = _assert_error(
        engine, "INSERT INTO users (id, name, age) VALUES (5, 'yena', 24);",
    )
    assert "id" in error.message
    engine.close()
    assert read_table(users, "users") == USERS_HEADER


@pytest.mark.parametrize("sql", [
    "INSERT INTO users VALUES ('yena');",
    "INSERT INTO users VALUES ('yena', 24, 'x');",
    "INSERT INTO users (name, age) VALUES ('yena');",
])
def test_e3_value_count_mismatch(users, engine, sql):
    """VALUES ('yena'), VALUES ('yena', 24, 'x'),
    (name, age) VALUES ('yena') → SqlError (B6)
    """
    error = _assert_error(engine, sql)
    assert error.position is not None


def test_e4_strict_types(users, engine):
    """('yena', '24'), (24, 24) → SqlError / ('yena', -5) → 성공 (B10)"""
    _assert_error(engine, "INSERT INTO users VALUES ('yena', '24');")
    _assert_error(engine, "INSERT INTO users VALUES (24, 24);")
    engine.execute("INSERT INTO users VALUES ('yena', -5);")
    engine.close()
    assert read_table(users, "users") == USERS_HEADER + "1,yena,-5\n"


@pytest.mark.parametrize("columns", [
    "(name, nope)", "(name, name)", "(name)",
])
def test_e5_column_list_errors(users, engine, columns):
    """없는 컬럼, 같은 컬럼 두 번, age 빠짐 → SqlError /
    (age, name) VALUES (24, 'yena') → 파일에 1,yena,24 (B6)
    """
    values = "('yena')" if columns == "(name)" else "('yena', 'x')"
    _assert_error(engine, f"INSERT INTO users {columns} VALUES {values};")
    engine.execute("INSERT INTO users (age, name) VALUES (24, 'yena');")
    engine.close()
    assert read_table(users, "users") == USERS_HEADER + "1,yena,24\n"


def test_e6_bad_row_writes_nothing(users, engine):
    """('a', 1), ('b', 'x'), ('c', 3) → SqlError, 파일은 헤더만,
    다음 INSERT의 id는 1 (B13, B17)
    """
    _assert_error(
        engine, "INSERT INTO users VALUES ('a', 1), ('b', 'x'), ('c', 3);",
    )
    assert read_table(users, "users") == USERS_HEADER
    engine.execute("INSERT INTO users VALUES ('d', 4);")
    engine.close()
    assert read_table(users, "users") == USERS_HEADER + "1,d,4\n"


def test_e7_select_columns(users, engine):
    """SELECT name, age → [name, age] / SELECT age, id → 적힌 순서 /
    SELECT nope → SqlError (B7)
    """
    engine.execute("INSERT INTO users VALUES ('yena', 24);")
    result = engine.execute("SELECT name, age FROM users;")
    assert (result.kind, result.columns) == ("select", ["name", "age"])
    assert result.rows == [("yena", 24)]
    result = engine.execute("SELECT age, id FROM users;")
    assert (result.columns, result.rows) == (["age", "id"], [(24, 1)])
    _assert_error(engine, "SELECT nope FROM users;")


def test_e8_where(workspace, engine):
    """id = 2 → kim / age = 24 → yena, Yena / name = 'yena' → yena만 /
    name = 'park' → 0건 (B8, B5)
    """
    write_table(
        workspace, "users",
        USERS_HEADER + "1,yena,24\n2,kim,20\n3,Yena,24\n",
    )

    def names(condition):
        result = engine.execute(f"SELECT name FROM users WHERE {condition};")
        return [row[0] for row in result.rows]

    assert names("id = 2") == ["kim"]
    assert names("age = 24") == ["yena", "Yena"]
    assert names("name = 'yena'") == ["yena"]
    assert names("name = 'park'") == []


def test_e9_where_unknown_column_is_error(users, engine):
    """WHERE nope = 1 → SqlError (0건 아님) (B8)"""
    error = _assert_error(engine, "SELECT * FROM users WHERE nope = 1;")
    assert "nope" in error.message


def test_e10_missing_table_is_error(workspace, engine):
    """orders 없음: INSERT, SELECT 모두 SqlError, 파일도 생기지 않음 (B15)"""
    error = _assert_error(engine, "INSERT INTO orders VALUES (1);")
    assert error.message == "테이블 orders가 없음"
    assert error.position is not None
    _assert_error(engine, "SELECT * FROM orders;")
    assert not (workspace / "data" / "orders.csv").exists()


def test_e11_table_name_ignores_case(users, engine):
    """INSERT INTO Users 후 SELECT * FROM USERS → data/users.csv 하나만 씀 (B5)"""
    engine.execute("INSERT INTO Users VALUES ('yena', 24);")
    result = engine.execute("SELECT * FROM USERS;")
    assert result.rows == [(1, "yena", 24)]
    assert [path.name for path in (users / "data").iterdir()] == [
        "users.csv",
    ]


@pytest.mark.parametrize("condition", ["age = '24'", "name = 24"])
def test_e12_where_type_mismatch_is_error(users, engine, condition):
    """WHERE age = '24', WHERE name = 24 → SqlError (0건 아님) (B21)"""
    _assert_error(engine, f"SELECT * FROM users WHERE {condition};")


def test_e13_execute_needs_exactly_one_statement(users, engine):
    """execute는 문장이 정확히 하나여야 함"""
    _assert_error(engine, "SELECT * FROM users; SELECT * FROM users;")
    _assert_error(engine, "-- 비어 있음")
