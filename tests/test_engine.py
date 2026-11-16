"""엔진 단위 테스트 (R-Q1). 노션 5절 e1~e12.

Engine().execute(sql)의 Result와, 실행 뒤 파일 내용(read_table)을 같이 확인한다.
작성한 테스트는 @TODO를 지운다.
"""

import pytest

from conftest import USERS_HEADER, read_table, write_table
from minidb.engine import Engine
from minidb.errors import SqlError

THREE_USERS = USERS_HEADER + "1,yena,24\n2,kim,20\n3,Yena,24\n"


@pytest.fixture
def engine(workspace):
    """테스트가 끝나면 닫는다. 파일 내용을 보기 전에는 테스트 안에서 직접 close()."""
    opened = Engine()
    yield opened
    opened.close()


def _assert_error(engine: Engine, sql: str) -> SqlError:
    with pytest.raises(SqlError) as error:
        engine.execute(sql)
    return error.value


def test_e1_ids_are_assigned(workspace, engine):
    """INSERT 두 번 → 파일에 1,yena,24 / 2,kim,20 (B13)"""
    write_table(workspace, "users", USERS_HEADER)
    first = engine.execute("INSERT INTO users VALUES ('yena', 24);")
    engine.execute("INSERT INTO users VALUES ('kim', 20);")
    engine.close()
    assert first.kind == "insert"
    assert first.affected == 1
    assert read_table(workspace, "users") == (
        USERS_HEADER + "1,yena,24\n2,kim,20\n"
    )


def test_e2_user_given_id_is_error(workspace, engine):
    """VALUES (5, 'yena', 24), (id, name, age) VALUES (...) → SqlError,
    파일은 헤더만 (B13)
    """
    write_table(workspace, "users", USERS_HEADER)
    # 컬럼 목록이 없으면 id를 뺀 2개를 받으므로 '개수 불일치'로 걸린다
    _assert_error(engine, "INSERT INTO users VALUES (5, 'yena', 24);")
    error = _assert_error(
        engine, "INSERT INTO users (id, name, age) VALUES (5, 'yena', 24);"
    )
    assert "id" in error.message
    engine.close()
    assert read_table(workspace, "users") == USERS_HEADER


@pytest.mark.parametrize("sql", [
    "INSERT INTO users VALUES ('yena');",
    "INSERT INTO users VALUES ('yena', 24, 'x');",
    "INSERT INTO users (name, age) VALUES ('yena');",
])
def test_e3_value_count_mismatch(workspace, engine, sql):
    """VALUES ('yena'), VALUES ('yena', 24, 'x'),
    (name, age) VALUES ('yena') → SqlError (B6)
    """
    write_table(workspace, "users", USERS_HEADER)
    _assert_error(engine, sql)


def test_e4_strict_types(workspace, engine):
    """('yena', '24'), (24, 24) → SqlError / ('yena', -5) → 성공 (B10)"""
    write_table(workspace, "users", USERS_HEADER)
    _assert_error(engine, "INSERT INTO users VALUES ('yena', '24');")
    _assert_error(engine, "INSERT INTO users VALUES (24, 24);")
    engine.execute("INSERT INTO users VALUES ('yena', -5);")
    engine.close()
    assert read_table(workspace, "users") == USERS_HEADER + "1,yena,-5\n"


@pytest.mark.parametrize("sql", [
    "INSERT INTO users (nope, age) VALUES ('yena', 24);",
    "INSERT INTO users (name, name) VALUES ('yena', 'kim');",
    "INSERT INTO users (name) VALUES ('yena');",
])
def test_e5_column_list_errors(workspace, engine, sql):
    """없는 컬럼, 같은 컬럼 두 번, age 빠짐 → SqlError /
    (age, name) VALUES (24, 'yena') → 파일에 1,yena,24 (B6)
    """
    write_table(workspace, "users", USERS_HEADER)
    _assert_error(engine, sql)
    engine.execute("INSERT INTO users (age, name) VALUES (24, 'yena');")
    engine.close()
    assert read_table(workspace, "users") == USERS_HEADER + "1,yena,24\n"


def test_e6_bad_row_writes_nothing(workspace, engine):
    """('a', 1), ('b', 'x'), ('c', 3) → SqlError, 파일은 헤더만,
    다음 INSERT의 id는 1 (B13, B17)
    """
    write_table(workspace, "users", USERS_HEADER)
    _assert_error(
        engine, "INSERT INTO users VALUES ('a', 1), ('b', 'x'), ('c', 3);"
    )
    engine.close()
    assert read_table(workspace, "users") == USERS_HEADER
    engine.execute("INSERT INTO users VALUES ('d', 4);")
    engine.close()
    assert read_table(workspace, "users") == USERS_HEADER + "1,d,4\n"


def test_e7_select_columns(workspace, engine):
    """SELECT name, age → [name, age] / SELECT age, id → 적힌 순서 /
    SELECT nope → SqlError (B7)
    """
    write_table(workspace, "users", THREE_USERS)
    result = engine.execute("SELECT name, age FROM users;")
    assert result.kind == "select"
    assert result.columns == ["name", "age"]
    assert result.rows[0] == ("yena", 24)
    reordered = engine.execute("SELECT age, id FROM users;")
    assert reordered.columns == ["age", "id"]
    assert reordered.rows[1] == (20, 2)
    everything = engine.execute("SELECT * FROM users;")
    assert everything.columns == ["id", "name", "age"]
    assert len(everything.rows) == 3
    _assert_error(engine, "SELECT nope FROM users;")


def test_e8_where(workspace, engine):
    """id = 2 → kim / age = 24 → yena, Yena / name = 'yena' → yena만 /
    name = 'park' → 0건 (B8, B5)
    """
    write_table(workspace, "users", THREE_USERS)

    def select(where: str) -> list:
        return engine.execute(f"SELECT * FROM users WHERE {where};").rows

    assert select("id = 2") == [(2, "kim", 20)]
    assert select("age = 24") == [(1, "yena", 24), (3, "Yena", 24)]
    assert select("name = 'yena'") == [(1, "yena", 24)]
    assert select("name = 'park'") == []


def test_e9_where_unknown_column_is_error(workspace, engine):
    """WHERE nope = 1 → SqlError (0건 아님) (B8)"""
    write_table(workspace, "users", THREE_USERS)
    _assert_error(engine, "SELECT * FROM users WHERE nope = 1;")


def test_e10_missing_table_is_error(workspace, engine):
    """orders 없음: INSERT, SELECT 모두 SqlError, 파일도 생기지 않음 (B15)"""
    _assert_error(engine, "INSERT INTO orders VALUES ('a', 1);")
    _assert_error(engine, "SELECT * FROM orders;")
    assert not (workspace / "data" / "orders.csv").exists()


def test_e11_table_name_ignores_case(workspace, engine):
    """INSERT INTO Users 후 SELECT * FROM USERS → data/users.csv 하나만 씀 (B5)"""
    write_table(workspace, "users", USERS_HEADER)
    engine.execute("INSERT INTO Users VALUES ('yena', 24);")
    result = engine.execute("SELECT * FROM USERS;")
    assert result.rows == [(1, "yena", 24)]
    files = sorted(path.name for path in (workspace / "data").iterdir())
    assert files == ["users.csv"]


@pytest.mark.parametrize("sql", [
    "SELECT * FROM users WHERE age = '24';",
    "SELECT * FROM users WHERE name = 24;",
])
def test_e12_where_type_mismatch_is_error(workspace, engine, sql):
    """WHERE age = '24', WHERE name = 24 → SqlError (0건 아님) (B21)"""
    write_table(workspace, "users", THREE_USERS)
    _assert_error(engine, sql)
