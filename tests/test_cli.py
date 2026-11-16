"""CLI 기능 테스트 (R-Q2). 노션 5절 c1~c9.

run_cli로 sql_processor.py를 진짜 프로세스로 실행하고 stdout, stderr, 종료 코드,
실행 뒤 파일 내용을 확인한다. 에러 메시지는 포함 여부로 확인한다 (B22).
"""

import pytest

from conftest import USERS_HEADER, read_table, run_cli, write_table


@pytest.fixture
def users(tmp_path):
    write_table(tmp_path, "users", USERS_HEADER)
    return tmp_path


def test_c1_insert_and_select(users):
    """INSERT 2행 + SELECT → stdout '2 rows affected' + CSV 결과,
    stderr 없음, 0 (B16)
    """
    done = run_cli(users, sql=(
        "INSERT INTO users VALUES ('yena', 24), ('kim, k', 20);\n"
        "SELECT * FROM users;\n"
    ))
    assert done.stdout == (
        "2 rows affected\n"
        "id,name,age\n"
        "1,yena,24\n"
        '2,"kim, k",20\n'
    )
    assert (done.stderr, done.returncode) == ("", 0)


def test_c2_one_row_affected(users):
    """INSERT 1행 → '1 row affected' (B16)"""
    done = run_cli(users, sql="INSERT INTO users VALUES ('yena', 24);")
    assert (done.stdout, done.stderr, done.returncode) == (
        "1 row affected\n", "", 0,
    )


def test_c3_empty_select(users):
    """빈 테이블 SELECT → 'id,name,age' 다음 줄 '(0 rows)' (B16)"""
    done = run_cli(users, sql="SELECT * FROM users;")
    assert (done.stdout, done.stderr, done.returncode) == (
        "id,name,age\n(0 rows)\n", "", 0,
    )


def test_c4_newline_value_on_one_line(users):
    """줄바꿈이 든 값 → '\\n' 두 글자로 한 줄 출력 (B16)"""
    done = run_cli(users, sql=(
        "INSERT INTO users VALUES ('첫줄\n둘째줄', 24);\n"
        "SELECT name FROM users;\n"
    ))
    assert done.stdout == "1 row affected\nname\n첫줄\\n둘째줄\n"
    assert done.returncode == 0


def test_c5_runtime_error_stops(users):
    """1 성공, 2 타입 에러, 3 SELECT → stdout은 1의 결과만, stderr에 2번째 문장 에러, 1.
    파일에 yena 한 행이 남음 (에러에도 close로 flush) (B17, B14)
    """
    done = run_cli(users, sql=(
        "INSERT INTO users VALUES ('yena', 24);\n"
        "INSERT INTO users VALUES ('kim', 'x');\n"
        "SELECT * FROM users;\n"
    ))
    assert done.stdout == "1 row affected\n"
    assert "error: (2줄 34칸)" in done.stderr
    assert done.returncode == 1
    assert read_table(users, "users") == USERS_HEADER + "1,yena,24\n"


def test_c6_syntax_error_runs_nothing(users):
    """3번째 문장 문법 에러 → stdout 없음, 1·2도 실행 안 됨 (파일은 헤더만), 1 (B17)"""
    done = run_cli(users, sql=(
        "INSERT INTO users VALUES ('yena', 24);\n"
        "SELECT * FROM users;\n"
        "SELECT * users;\n"
    ))
    assert done.stdout == ""
    assert "error: (3줄 10칸)" in done.stderr
    assert done.returncode == 1
    assert read_table(users, "users") == USERS_HEADER


@pytest.mark.parametrize("args", [[], ["a.sql", "b.sql"]])
def test_c7_wrong_argument_count(tmp_path, args):
    """인자 없음, 인자 2개 → stderr에 usage, 1 (B2)"""
    done = run_cli(tmp_path, args=args)
    assert done.stdout == ""
    assert "usage: python sql_processor.py <file.sql>" in done.stderr
    assert done.returncode == 1


def test_c8_missing_file(tmp_path):
    """없는 파일 → stderr에 파일 에러, 1 (B2)"""
    done = run_cli(tmp_path, args=["nope.sql"])
    assert done.stdout == ""
    assert "error: nope.sql 파일을 열 수 없음" in done.stderr
    assert done.returncode == 1


@pytest.mark.parametrize("sql", ["", "-- 주석만\n/* 블록\n주석 */\n"])
def test_c9_empty_or_comment_only_file(tmp_path, sql):
    """빈 파일, 주석만 있는 파일 → stdout·stderr 없음, 0 (B2)"""
    done = run_cli(tmp_path, sql=sql)
    assert (done.stdout, done.stderr, done.returncode) == ("", "", 0)
