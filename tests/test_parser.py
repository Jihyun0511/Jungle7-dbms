"""파서 단위 테스트 (R-Q1). 노션 5절 p1~p8."""

import pytest

from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.statements import Insert, Select


def _texts(names):
    return [name.text for name in names]


def _row_values(row):
    return [value.value for value in row]


def test_p1_insert_multiple_rows():
    """INSERT INTO users VALUES ('a', 1), ('b', 2);
    → Insert, columns None, 행 2개 (B6)
    """
    [statement] = parse_script(
        "INSERT INTO users VALUES ('a', 1), ('b', 2);"
    )
    assert isinstance(statement, Insert)
    assert statement.table.text == "users"
    assert statement.columns is None
    assert [_row_values(row) for row in statement.rows] == [
        ["a", 1], ["b", 2],
    ]


def test_p2_insert_with_column_list():
    """INSERT INTO users (age, name) VALUES (1, 'a');
    → columns [age, name] (B6)
    """
    [statement] = parse_script(
        "INSERT INTO users (age, name) VALUES (1, 'a');"
    )
    assert _texts(statement.columns) == ["age", "name"]
    assert [_row_values(row) for row in statement.rows] == [[1, "a"]]


def test_p3_select_star_and_columns():
    """SELECT * → columns None / SELECT name, age → [name, age] (B7)"""
    star, listed = parse_script(
        "SELECT * FROM users; SELECT name, age FROM users;"
    )
    assert isinstance(star, Select)
    assert star.columns is None
    assert _texts(listed.columns) == ["name", "age"]
    assert listed.where is None


def test_p4_select_where():
    """SELECT * FROM users WHERE id = 5; → Where(id, 5) (B8)"""
    [statement] = parse_script("SELECT * FROM users WHERE id = 5;")
    assert statement.where.column.text == "id"
    assert statement.where.value.value == 5


def test_p5_missing_last_semicolon_is_error():
    """마지막 ; 없음 → SqlError (B1)"""
    with pytest.raises(SqlError) as caught:
        parse_script("SELECT * FROM users; SELECT * FROM users")
    assert caught.value.statement == 2


def test_p6_empty_statements_are_ignored():
    """;; → 빈 문장은 무시 (B1)"""
    statements = parse_script(";; SELECT * FROM users;;; ;")
    assert len(statements) == 1
    assert parse_script(";;") == []
    assert parse_script("") == []


def test_p7_null_is_error():
    """VALUES ('a', NULL) → SqlError (B10)"""
    with pytest.raises(SqlError) as caught:
        parse_script("INSERT INTO users VALUES ('a', NULL);")
    assert "NULL" in caught.value.message


@pytest.mark.parametrize("sql", [
    "INSERT INTO users ('a', 1);",
    "INSERT INTO users VALUES ('a', 1;",
    "UPDATE users SET age = 1;",
    "SELECT FROM users;",
    "SELECT * FROM users WHERE age 24;",
])
def test_p8_syntax_errors_have_position(sql):
    """VALUES 빠짐, ) 빠짐, UPDATE ... → SqlError, position 있음 (B4)"""
    with pytest.raises(SqlError) as caught:
        parse_script(sql)
    assert caught.value.position is not None
    assert caught.value.statement == 1
