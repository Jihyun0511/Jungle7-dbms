"""CLI 기능 테스트 (R-Q2). 노션 5절 c1~c10, Phase 2 c11.

run_cli로 sql_processor.py를 진짜 프로세스로 실행하고 stdout, stderr, 종료 코드,
실행 뒤 파일 내용을 확인한다. 에러 메시지는 포함 여부로 확인한다 (B22).
"""

import pytest

from conftest import USERS_HEADER, read_table, run_cli, write_table


def test_c1_insert_and_select(tmp_path):
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(
        tmp_path,
        "INSERT INTO users VALUES ('yena', 24), ('kim', 20);\n"
        "SELECT * FROM users;",
    )
    rows = "1,yena,24\n2,kim,20\n"
    assert result.returncode == 0
    assert result.stdout == "2 rows affected\nid,name,age\n" + rows
    assert result.stderr == ""
    assert read_table(tmp_path, "users") == USERS_HEADER + rows


def test_c2_one_row_affected(tmp_path):
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, "INSERT INTO users VALUES ('yena', 24);")
    assert result.returncode == 0
    assert result.stdout == "1 row affected\n"
    assert result.stderr == ""
    assert read_table(tmp_path, "users") == USERS_HEADER + "1,yena,24\n"


def test_c3_empty_select(tmp_path):
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, "SELECT * FROM users;")
    assert result.returncode == 0
    assert result.stdout == "id,name,age\n(0 rows)\n"
    assert result.stderr == ""


def test_c4_newline_value_on_one_line(tmp_path):
    table = write_table(tmp_path, "users", USERS_HEADER)
    name = '첫줄\r\n둘째줄, "별명"'
    sql = f"INSERT INTO users VALUES ('{name}', 24);\nSELECT name FROM users;"
    (tmp_path / "input.sql").write_text(sql, encoding="utf-8", newline="")
    result = run_cli(tmp_path, args=["input.sql"])
    assert result.returncode == 0
    assert result.stdout == '1 row affected\nname\n"첫줄\\n둘째줄, ""별명"""\n'
    assert result.stderr == ""
    assert "첫줄\r\n둘째줄".encode() in table.read_bytes()


@pytest.mark.parametrize(
    ("bad_statement", "location", "message"),
    [
        (
            "INSERT INTO users VALUES ('kim', '20');",
            "line 2, column 34",
            "age is int but got string '20'",
        ),
        (
            "INSERT INTO orders VALUES ('kim', 20);",
            "line 2, column 13",
            "table orders does not exist",
        ),
    ],
)
def test_c5_runtime_error_stops(tmp_path, bad_statement, location, message):
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(
        tmp_path,
        "INSERT INTO users VALUES ('yena', 24);\n"
        f"{bad_statement}\n"
        "SELECT * FROM users;",
    )
    assert result.returncode == 1
    assert result.stdout == "1 row affected\n"
    assert result.stderr.startswith(f"error: statement 2 ({location}): ")
    assert message in result.stderr
    assert read_table(tmp_path, "users") == USERS_HEADER + "1,yena,24\n"
    assert not (tmp_path / "data/orders.csv").exists()


@pytest.mark.parametrize(
    "bad_statement",
    ["SELECT * FROM users", "INSERT INTO users VALUES ('닫히지 않음"],
)
def test_c6_syntax_error_runs_nothing(tmp_path, bad_statement):
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(
        tmp_path,
        "INSERT INTO users VALUES ('yena', 24);\n"
        "INSERT INTO users VALUES ('kim', 20);\n"
        f"{bad_statement}",
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: statement 3 (line 3, ")
    assert read_table(tmp_path, "users") == USERS_HEADER


@pytest.mark.parametrize("args", [[], ["a.sql", "b.sql"]])
def test_c7_wrong_argument_count(tmp_path, args):
    result = run_cli(tmp_path, args=args)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "usage: python sql_processor.py <file.sql>\n"


def test_c8_missing_file(tmp_path):
    result = run_cli(tmp_path, args=["a.sql"])
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "error: cannot open a.sql\n"


@pytest.mark.parametrize("sql", ["", "-- 주석 ;\n/* 블록 주석 ; */"])
def test_c9_empty_or_comment_only_file(tmp_path, sql):
    result = run_cli(tmp_path, sql)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


def test_c10_utf8_bom_is_ignored(tmp_path):
    """메모장이 붙이는 BOM이 있어도 첫 키워드를 읽는다 (B19)."""
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, "﻿INSERT INTO users VALUES ('yena', 24);")
    assert result.returncode == 0
    assert result.stdout == "1 row affected\n"
    assert result.stderr == ""


def test_c11_where_id(tmp_path):
    """Phase 2: 파일에 있던 행, 트리 전에 넣은 행, 트리 뒤에 넣은 행."""
    write_table(tmp_path, "users", USERS_HEADER + '1,"a\nb",24\n')
    result = run_cli(
        tmp_path,
        "INSERT INTO users VALUES ('kim', 20);\n"
        "SELECT * FROM users WHERE id = 1;\n"
        "SELECT name FROM users WHERE id = 2;\n"
        "INSERT INTO users VALUES ('park', 22);\n"
        "SELECT name FROM users WHERE id = 3;\n"
        "SELECT name FROM users WHERE id = 4;",
    )
    assert result.returncode == 0
    assert result.stdout == (
        "1 row affected\n"
        "id,name,age\n1,a\\nb,24\n"
        "name\nkim\n"
        "1 row affected\n"
        "name\npark\n"
        "name\n(0 rows)\n"
    )
    assert result.stderr == ""
