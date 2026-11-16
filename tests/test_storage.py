"""저장(CSV)·스키마 단위 테스트 (R-Q1). 노션 5절 s1~s6.

workspace 픽스처로 실행 위치를 임시 폴더로 옮긴 뒤 write_table로 파일을 만든다.
작성한 테스트는 @TODO를 지운다.
"""

import pytest

from conftest import USERS_HEADER, write_table  # noqa: F401
from minidb.schema import parse_header  # noqa: F401
from minidb.storage import open_table  # noqa: F401

TODO = pytest.mark.skip(reason="아직 작성하지 않음")


@TODO
def test_s1_read_header(workspace):
    """id:int,name:str,age:int
    → 컬럼 3개 [(id, int), (name, str), (age, int)] (B11)
    """


@TODO
def test_s2_header_errors(workspace):
    """모르는 타입, 타입 빠짐, 이름 중복, id 없음, 빈 파일 → 각각 SqlError.
    처음 만난 에러 하나만. 순서: 빈 파일 → 왼쪽 컬럼부터 (타입 없음 → 모르는 타입 → 이름 중복) → id 없음 (B20)
    """


@TODO
def test_s2b_only_first_header_error(workspace):
    """name,name:float → '1번째 컬럼: 타입 없음' 하나만 (B20)"""


@TODO
def test_s3_values_get_schema_types(workspace):
    """1,yena,24 → (1, 'yena', 24). 1과 24는 int (B12)"""


@TODO
def test_s4_tricky_values_round_trip(workspace):
    """쉼표·큰따옴표·줄바꿈이 든 값을 쓰고 다시 읽으면 그대로 (B9, B12)"""


@TODO
def test_s5_next_id(workspace):
    """헤더만 → 1 / id 1, 2, 3 → 4 (B13)"""


@TODO
def test_s5b_next_id_when_last_row_has_newline(workspace):
    """마지막 행 name에 줄바꿈 → 그 행 id + 1. 파일의 마지막 줄이 아니라 CSV 행 기준 (B13, B9)"""


@TODO
def test_s6_read_sees_unflushed_rows(workspace):
    """닫지 않은 Table에 append_rows 후 read_rows → 방금 쓴 행이 보임 (B14)"""
