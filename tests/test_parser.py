"""파서 단위 테스트 (R-Q1). 노션 5절 p1~p8.

작성한 테스트는 @TODO를 지운다.
"""

import pytest

from minidb.parser import parse_script  # noqa: F401
from minidb.statements import Insert, Select  # noqa: F401

TODO = pytest.mark.skip(reason="아직 작성하지 않음")


@TODO
def test_p1_insert_multiple_rows():
    """INSERT INTO users VALUES ('a', 1), ('b', 2);
    → Insert, columns None, 행 2개 (B6)
    """


@TODO
def test_p2_insert_with_column_list():
    """INSERT INTO users (age, name) VALUES (1, 'a');
    → columns [age, name] (B6)
    """


@TODO
def test_p3_select_star_and_columns():
    """SELECT * → columns None / SELECT name, age → [name, age] (B7)"""


@TODO
def test_p4_select_where():
    """SELECT * FROM users WHERE id = 5; → Where(id, 5) (B8)"""


@TODO
def test_p5_missing_last_semicolon_is_error():
    """마지막 ; 없음 → SqlError (B1)"""


@TODO
def test_p6_empty_statements_are_ignored():
    """;; → 빈 문장은 무시 (B1)"""


@TODO
def test_p7_null_is_error():
    """VALUES ('a', NULL) → SqlError (B10)"""


@TODO
def test_p8_syntax_errors_have_position():
    """VALUES 빠짐, ) 빠짐, UPDATE ... → SqlError, position 있음 (B4)"""
