"""엔진 단위 테스트 (R-Q1). 노션 5절 e1~e12, Phase 2 e13~e18."""

import pytest

import minidb.storage
from conftest import USERS_HEADER, read_table, write_table
from minidb.engine import Engine, Result
from minidb.errors import Position, SqlError
from minidb.parser import parse_script


@pytest.fixture
def engine(workspace):
    write_table(workspace, "users", USERS_HEADER)
    instance = Engine()
    try:
        yield instance
    finally:
        instance.close()


def test_e1_ids_are_assigned(engine, workspace):
    write_table(workspace, "staff", "name:str,id:int\njin,5\n")
    assert engine.execute("INSERT INTO users VALUES ('yena', 24);") == Result(
        kind="insert", affected=1,
    )
    assert engine.execute("INSERT INTO users VALUES ('kim', 20);").affected == 1
    engine.execute("INSERT INTO staff VALUES ('park');")
    engine.close()
    assert read_table(workspace, "users") == (
        USERS_HEADER + "1,yena,24\n2,kim,20\n"
    )
    assert read_table(workspace, "staff") == "name:str,id:int\njin,5\npark,6\n"


@pytest.mark.parametrize(
    "clause",
    ["VALUES (5, 'yena', 24)", "(id, name, age) VALUES (5, 'yena', 24)"],
)
def test_e2_user_given_id_is_error(engine, workspace, clause):
    with pytest.raises(SqlError):
        engine.execute(f"INSERT INTO users {clause};")
    engine.close()
    assert read_table(workspace, "users") == USERS_HEADER


@pytest.mark.parametrize(
    "clause",
    [
        "VALUES ('yena')",
        "VALUES ('yena', 24, 'x')",
        "(name, age) VALUES ('yena')",
    ],
)
def test_e3_value_count_mismatch(engine, clause):
    with pytest.raises(SqlError, match="expected 2 values but got"):
        engine.execute(f"INSERT INTO users {clause};")


def test_e4_strict_types(engine):
    for row in ("('yena', '24')", "(24, 24)"):
        with pytest.raises(SqlError, match="but got"):
            engine.execute(f"INSERT INTO users VALUES {row};")
    engine.execute("INSERT INTO users VALUES ('yena', -5);")
    assert engine.execute("SELECT * FROM users;").rows == [(1, "yena", -5)]


def test_e5_column_list_errors(engine, workspace):
    for columns, message in (
        ("name, nope", "column nope does not exist"),
        ("name, NAME", "column name appears twice"),
        ("name", "INSERT column list is missing age"),
    ):
        with pytest.raises(SqlError, match=message):
            engine.execute(f"INSERT INTO users ({columns}) VALUES ('yena');")
    engine.execute("INSERT INTO users (age, name) VALUES (24, 'yena');")
    engine.close()
    assert read_table(workspace, "users") == USERS_HEADER + "1,yena,24\n"


def test_e6_bad_row_writes_nothing(engine, workspace):
    with pytest.raises(SqlError, match="but got"):
        engine.execute(
            "INSERT INTO users VALUES ('a', 1), ('b', 'x'), ('c', 3);"
        )
    assert engine.execute("SELECT * FROM users;").rows == []
    assert read_table(workspace, "users") == USERS_HEADER
    engine.execute("INSERT INTO users VALUES ('d', 4);")
    assert engine.execute("SELECT * FROM users;").rows == [(1, "d", 4)]


def test_e6_execute_rejects_multiple_statements_before_writing(engine):
    with pytest.raises(SqlError, match="expected exactly one statement"):
        engine.execute(
            "INSERT INTO users VALUES ('a', 1); SELECT * FROM users;"
        )
    assert engine.execute("SELECT * FROM users;").rows == []
    with pytest.raises(SqlError, match="expected exactly one statement"):
        engine.execute("-- comment only")


def test_e7_select_columns(engine):
    engine.execute("INSERT INTO users VALUES ('yena', 24);")
    assert engine.execute("SELECT name, age FROM users;") == Result(
        kind="select", columns=["name", "age"], rows=[("yena", 24)],
    )
    assert engine.execute("SELECT age, id FROM users;") == Result(
        kind="select", columns=["age", "id"], rows=[(24, 1)],
    )
    with pytest.raises(SqlError, match="column nope does not exist") as error:
        engine.execute("SELECT nope FROM users;")
    assert error.value.position == Position(1, 8)


def test_e8_where(engine, capsys):
    insert, select = parse_script(
        "INSERT INTO users VALUES ('yena', 24), ('kim', 20), ('Yena', 24);"
        "SELECT name FROM users WHERE id = 2;"
    )
    assert engine.run(insert).affected == 3
    assert engine.run(select).rows == [("kim",)]
    assert engine.execute("SELECT name FROM users WHERE age = 24;").rows == [
        ("yena",), ("Yena",),
    ]
    matching = engine.execute("SELECT id FROM users WHERE name = 'yena';")
    assert matching.rows == [(1,)]
    empty = engine.execute("SELECT id FROM users WHERE name = 'park';")
    assert empty == Result(kind="select", columns=["id"])
    assert capsys.readouterr() == ("", "")


def test_e9_where_unknown_column_is_error(engine):
    with pytest.raises(SqlError, match="column nope does not exist"):
        engine.execute("SELECT * FROM users WHERE nope = 1;")


@pytest.mark.parametrize(
    ("sql", "position"),
    [
        ("INSERT INTO orders VALUES ('a', 1);", Position(1, 13)),
        ("SELECT * FROM orders;", Position(1, 15)),
    ],
)
def test_e10_missing_table_is_error(engine, workspace, sql, position):
    with pytest.raises(SqlError, match="table orders does not exist") as error:
        engine.execute(sql)
    assert error.value.position == position
    assert not (workspace / "data/orders.csv").exists()


def test_e11_table_name_ignores_case(engine, workspace):
    engine.execute("INSERT INTO Users VALUES ('Yena', 24);")
    assert engine.execute("SELECT NAME FROM USERS;").rows == [("Yena",)]
    files = (workspace / "data").iterdir()
    assert [path.name for path in files] == ["users.csv"]


@pytest.mark.parametrize("condition", ["age = '24'", "name = 24"])
def test_e12_where_type_mismatch_is_error(engine, condition):
    with pytest.raises(SqlError, match="but got"):
        engine.execute(f"SELECT * FROM users WHERE {condition};")


def _fail_scan():
    raise AssertionError("WHERE id must not scan the table")


def test_e13_where_id_uses_index_not_scan(engine, monkeypatch):
    engine.execute("INSERT INTO users VALUES ('yena', 24), ('kim', 20);")
    monkeypatch.setattr(engine.tables["users"], "read_rows", _fail_scan)
    assert engine.execute("SELECT name FROM users WHERE id = 2;").rows == [
        ("kim",),
    ]


def test_e14_where_id_without_match_is_empty(engine):
    engine.execute("INSERT INTO users VALUES ('yena', 24);")
    for row_id in (0, 2, -1):
        result = engine.execute(f"SELECT * FROM users WHERE id = {row_id};")
        assert result == Result(kind="select", columns=["id", "name", "age"])


def test_e15_other_column_still_scans(engine, monkeypatch):
    engine.execute("INSERT INTO users VALUES ('yena', 24), ('kim', 24);")
    table = engine.tables["users"]
    scans = []
    original = table.read_rows

    def count_scan():
        scans.append(1)
        return original()

    monkeypatch.setattr(table, "read_rows", count_scan)
    assert engine.execute("SELECT id FROM users WHERE age = 24;").rows == [
        (1,), (2,),
    ]
    assert scans == [1]


def test_e16_where_id_sees_rows_inserted_after_tree(engine, monkeypatch):
    engine.execute("INSERT INTO users VALUES ('yena', 24);")
    assert engine.execute("SELECT name FROM users WHERE id = 1;").rows == [
        ("yena",),
    ]
    engine.execute("INSERT INTO users VALUES ('kim', 20), ('park', 22);")
    monkeypatch.setattr(engine.tables["users"], "read_rows", _fail_scan)
    assert engine.execute("SELECT name FROM users WHERE id = 3;").rows == [
        ("park",),
    ]


def test_e17_failed_write_keeps_row_out_of_tree(engine, monkeypatch):
    assert engine.execute("SELECT * FROM users WHERE id = 1;").rows == []

    def reject_open(path):
        raise PermissionError(path)

    with monkeypatch.context() as patch:
        patch.setattr(minidb.storage, "_open_append_file", reject_open)
        with pytest.raises(SqlError, match="cannot write rows"):
            engine.execute("INSERT INTO users VALUES ('kim', 20);")
    assert engine.execute("SELECT * FROM users WHERE id = 1;").rows == []

    engine.execute("INSERT INTO users VALUES ('park', 26);")
    assert engine.execute("SELECT name FROM users WHERE id = 1;").rows == [
        ("park",),
    ]


def test_e18_where_id_after_close_rebuilds_tree(engine):
    engine.execute("INSERT INTO users VALUES ('yena', 24), ('kim', 20);")
    assert engine.execute("SELECT name FROM users WHERE id = 2;").rows == [
        ("kim",),
    ]
    engine.close()
    assert engine.tables == {}
    assert engine.execute("SELECT name FROM users WHERE id = 2;").rows == [
        ("kim",),
    ]
    engine.execute("INSERT INTO users VALUES ('park', 22);")
    assert engine.execute("SELECT name FROM users WHERE id = 3;").rows == [
        ("park",),
    ]
