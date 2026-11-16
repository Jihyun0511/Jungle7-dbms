"""CLI 기능 테스트 (R-Q2). 노션 5절 c1~c9.

run_cli로 sql_processor.py를 진짜 프로세스로 실행하고 stdout, stderr, 종료 코드,
실행 뒤 파일 내용을 확인한다. 에러 메시지는 포함 여부로 확인한다 (B22).
작성한 테스트는 @TODO를 지운다.
"""

import pytest

from conftest import USERS_HEADER, read_table, run_cli, write_table


def test_c1_insert_and_select(tmp_path):
    """INSERT 2행 + SELECT → stdout '2 rows affected' + CSV 결과,
    stderr 없음, 0 (B16)
    """
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, sql=(
        "INSERT INTO users VALUES ('yena', 24), ('kim', 20);\n"
        "SELECT * FROM users;\n"
    ))
    assert result.stdout == (
        "2 rows affected\n"
        "id,name,age\n"
        "1,yena,24\n"
        "2,kim,20\n"
    )
    assert result.stderr == ""
    assert result.returncode == 0


def test_c2_one_row_affected(tmp_path):
    """INSERT 1행 → '1 row affected' (B16)"""
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, sql="INSERT INTO users VALUES ('yena', 24);")
    assert result.stdout == "1 row affected\n"
    assert result.returncode == 0


def test_c3_empty_select(tmp_path):
    """빈 테이블 SELECT → 'id,name,age' 다음 줄 '(0 rows)' (B16)"""
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, sql="SELECT * FROM users;")
    assert result.stdout == "id,name,age\n(0 rows)\n"
    assert result.returncode == 0


def test_c4_newline_value_on_one_line(tmp_path):
    """줄바꿈이 든 값 → '\\n' 두 글자로 한 줄 출력 (B16)"""
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, sql=(
        "INSERT INTO users VALUES ('첫줄\n둘째줄', 20);\n"
        "SELECT name FROM users;\n"
    ))
    assert result.stdout == "1 row affected\nname\n첫줄\\n둘째줄\n"
    assert result.returncode == 0


def test_c5_runtime_error_stops(tmp_path):
    """1 성공, 2 타입 에러, 3 SELECT → stdout은 1의 결과만, stderr에 2번째 문장 에러, 1.
    파일에 yena 한 행이 남음 (에러에도 close로 flush) (B17, B14)
    """
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, sql=(
        "INSERT INTO users VALUES ('yena', 24);\n"
        "INSERT INTO users VALUES ('kim', 'x');\n"
        "SELECT * FROM users;\n"
    ))
    assert result.stdout == "1 row affected\n"
    assert "2번째 문장" in result.stderr
    assert result.returncode == 1
    assert read_table(tmp_path, "users") == USERS_HEADER + "1,yena,24\n"


def test_c6_syntax_error_runs_nothing(tmp_path):
    """3번째 문장 문법 에러 → stdout 없음, 1·2도 실행 안 됨 (파일은 헤더만), 1 (B17)"""
    write_table(tmp_path, "users", USERS_HEADER)
    result = run_cli(tmp_path, sql=(
        "INSERT INTO users VALUES ('yena', 24);\n"
        "SELECT * FROM users;\n"
        "SELECT FROM users;\n"
    ))
    assert result.stdout == ""
    assert "3번째 문장 (3줄 8칸)" in result.stderr
    assert result.returncode == 1
    assert read_table(tmp_path, "users") == USERS_HEADER


@pytest.mark.parametrize("args", [[], ["a.sql", "b.sql"]])
def test_c7_wrong_argument_count(tmp_path, args):
    """인자 없음, 인자 2개 → stderr에 usage, 1 (B2)"""
    result = run_cli(tmp_path, args=args)
    assert result.stdout == ""
    assert "usage: python sql_processor.py <file.sql>" in result.stderr
    assert result.returncode == 1


def test_c8_missing_file(tmp_path):
    """없는 파일 → stderr에 파일 에러, 1 (B2)"""
    result = run_cli(tmp_path, args=["nope.sql"])
    assert "error: nope.sql 파일을 열 수 없음" in result.stderr
    assert result.returncode == 1


@pytest.mark.parametrize("sql", ["", "-- 주석만\n/* 블록\n주석 */\n"])
def test_c9_empty_or_comment_only_file(tmp_path, sql):
    """빈 파일, 주석만 있는 파일 → stdout·stderr 없음, 0 (B2)"""
    result = run_cli(tmp_path, sql=sql)
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.returncode == 0
