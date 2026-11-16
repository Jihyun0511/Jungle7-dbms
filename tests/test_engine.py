"""엔진 단위 테스트 (R-Q1). 노션 5절 e1~e12.

Engine().execute(sql)의 Result와, 실행 뒤 파일 내용(read_table)을 같이 확인한다.
작성한 테스트는 @TODO를 지운다.
"""

import pytest

from conftest import USERS_HEADER, read_table, write_table  # noqa: F401
from minidb.engine import Engine  # noqa: F401
from minidb.errors import SqlError  # noqa: F401

TODO = pytest.mark.skip(reason="아직 작성하지 않음")


@TODO
def test_e1_ids_are_assigned(workspace):
    """INSERT 두 번 → 파일에 1,yena,24 / 2,kim,20 (B13)"""


@TODO
def test_e2_user_given_id_is_error(workspace):
    """VALUES (5, 'yena', 24), (id, name, age) VALUES (...) → SqlError,
    파일은 헤더만 (B13)
    """


@TODO
def test_e3_value_count_mismatch(workspace):
    """VALUES ('yena'), VALUES ('yena', 24, 'x'),
    (name, age) VALUES ('yena') → SqlError (B6)
    """


@TODO
def test_e4_strict_types(workspace):
    """('yena', '24'), (24, 24) → SqlError / ('yena', -5) → 성공 (B10)"""


@TODO
def test_e5_column_list_errors(workspace):
    """없는 컬럼, 같은 컬럼 두 번, age 빠짐 → SqlError /
    (age, name) VALUES (24, 'yena') → 파일에 1,yena,24 (B6)
    """


@TODO
def test_e6_bad_row_writes_nothing(workspace):
    """('a', 1), ('b', 'x'), ('c', 3) → SqlError, 파일은 헤더만,
    다음 INSERT의 id는 1 (B13, B17)
    """


@TODO
def test_e7_select_columns(workspace):
    """SELECT name, age → [name, age] / SELECT age, id → 적힌 순서 /
    SELECT nope → SqlError (B7)
    """


@TODO
def test_e8_where(workspace):
    """id = 2 → kim / age = 24 → yena, Yena / name = 'yena' → yena만 /
    name = 'park' → 0건 (B8, B5)
    """


@TODO
def test_e9_where_unknown_column_is_error(workspace):
    """WHERE nope = 1 → SqlError (0건 아님) (B8)"""


@TODO
def test_e10_missing_table_is_error(workspace):
    """orders 없음: INSERT, SELECT 모두 SqlError, 파일도 생기지 않음 (B15)"""


@TODO
def test_e11_table_name_ignores_case(workspace):
    """INSERT INTO Users 후 SELECT * FROM USERS → data/users.csv 하나만 씀 (B5)"""


@TODO
def test_e12_where_type_mismatch_is_error(workspace):
    """WHERE age = '24', WHERE name = 24 → SqlError (0건 아님) (B21)"""
