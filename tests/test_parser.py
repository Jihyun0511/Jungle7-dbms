"""파서 단위 테스트 (R-Q1). 노션 5절 p1~p8."""

import pytest

from minidb.errors import Position, SqlError
from minidb.parser import parse, parse_script
from minidb.statements import Insert, Name, Select, Value, Where
from minidb.tokenizer import tokenize


def test_p1_insert_multiple_rows():
    sql = "INSERT INTO users VALUES ('a,;()\nIt''s', -5), ('', +007);"
    statement, = parse(tokenize(sql))
    assert isinstance(statement, Insert)
    assert statement.table == Name("users", Position(1, 13))
    assert statement.columns is None
    assert [[value.value for value in row] for row in statement.rows] == [
        ["a,;()\nIt's", -5], ["", 7],
    ]


def test_p2_insert_with_column_list():
    statement, = parse_script("InSeRt INTO Users (Age, Name)\nVALUES (1, 'A'), (2, '24');")
    assert isinstance(statement, Insert)
    assert statement.table.text == "users"
    assert statement.columns == [Name("age", Position(1, 20)), Name("name", Position(1, 25))]
    assert [[value.value for value in row] for row in statement.rows] == [[1, "A"], [2, "24"]]


def test_p3_select_star_and_columns():
    wildcard, projection = parse_script("SELECT * FROM users; SELECT name, age FROM users;")
    assert isinstance(wildcard, Select)
    assert wildcard.columns is None
    assert wildcard.where is None
    assert isinstance(projection, Select)
    assert [column.text for column in projection.columns] == ["name", "age"]


def test_p4_select_where():
    statement, = parse_script("SELECT * FROM users\nWHERE id = 5;")
    assert isinstance(statement, Select)
    assert statement.where == Where(Name("id", Position(2, 7)), Value(5, Position(2, 12)))


def test_p5_missing_last_semicolon_is_error():
    with pytest.raises(SqlError) as error:
        parse_script("SELECT * FROM users;\nSELECT * FROM users")
    assert error.value.message == "expected ';' but got end of file"
    assert error.value.position == Position(2, 20)
    assert error.value.statement == 2


def test_p6_empty_statements_are_ignored():
    assert parse_script(";; -- ;\n /* ; */ ;") == []
    assert parse_script(";SELECT * FROM users;;;SELECT * FROM users;;") == parse_script(
        " SELECT * FROM users;  SELECT * FROM users; "
    )


@pytest.mark.parametrize(
    ("sql", "position"),
    [
        ("INSERT INTO users VALUES ('a', NULL);", Position(1, 32)),
        ("SELECT * FROM users WHERE name = null;", Position(1, 34)),
    ],
)
def test_p7_null_is_error(sql, position):
    with pytest.raises(SqlError) as error:
        parse_script(sql)
    assert error.value.message == "NULL is not supported"
    assert error.value.position == position


@pytest.mark.parametrize(
    ("sql", "position"),
    [
        ("INSERT INTO users;", Position(1, 18)),
        ("INSERT INTO users VALUES ('a', 1;", Position(1, 33)),
        ("UPDATE users;", Position(1, 1)),
        ("SELECT * FROM users WHERE id > 1;", Position(1, 30)),
        ("SELECT * FROM users WHERE id = 1 AND age = 2;", Position(1, 34)),
    ],
)
def test_p8_syntax_errors_have_position(sql, position):
    with pytest.raises(SqlError) as error:
        parse_script(sql)
    assert error.value.position == position
    assert error.value.statement == 1


def test_lexical_error_has_statement_number():
    sql = "SELECT * FROM users WHERE name = ';';;; -- ;\nINSERT INTO users VALUES ('open"
    with pytest.raises(SqlError) as error:
        parse_script(sql)
    assert error.value.position == Position(2, 27)
    assert error.value.statement == 2
