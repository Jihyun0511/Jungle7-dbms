"""대용량 SQL 생성기 기능 테스트 (Phase 2). g1."""

from conftest import USERS_HEADER, read_table, run_cli, write_table
from make_insert_sql import generate_insert_statements


def test_g1_generated_sql_runs_through_cli(tmp_path):
    write_table(tmp_path, "users", USERS_HEADER)
    statements = list(generate_insert_statements(25, batch=10))
    assert len(statements) == 3

    result = run_cli(
        tmp_path, "".join(statements) + "SELECT * FROM users WHERE id = 25;",
    )
    assert result.returncode == 0
    assert result.stdout == (
        "10 rows affected\n10 rows affected\n5 rows affected\n"
        "id,name,age\n25,user25,25\n"
    )
    lines = read_table(tmp_path, "users").splitlines()
    assert lines[1] == "1,user1,1"
    assert len(lines) == 26
