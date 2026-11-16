"""테이블 파일(data/<이름>.csv) 읽기·쓰기. SQL은 모른다.

규칙 (노션 요구분석 번호):
- B3  테이블 파일은 실행한 폴더 기준 data/ 에 있다
- B12 CSV. 파일은 newline="" 으로 연다 (값 안의 줄바꿈 보존, s4). 읽은 값은 스키마 타입으로 바꾼다 (s3)
- B14 파일을 열어 둔 채로 쓰고, 읽기 직전에만 flush한다 (s6). close()에서 반드시 flush
- B13 다음 id = 마지막 행 id + 1 (행이 없으면 1). 처음 한 번만 읽고 기억한다.
      마지막 "줄"이 아니라 마지막 "CSV 행" 기준 (s5, s5b)
- B15 파일이 없으면 SqlError (만들지 않음)
- B19 인코딩은 보류. 지금은 utf-8

담당: (이름)
"""

from pathlib import Path

from minidb.errors import SqlError  # noqa: F401  (구현할 때 사용)
from minidb.schema import Schema, parse_header  # noqa: F401

DATA_DIR = Path("data")
ENCODING = "utf-8"

Row = tuple[int | str, ...]


class Table:
    """열린 테이블 하나. Engine이 테이블마다 하나씩 들고 있다."""

    def __init__(self, name: str, path: Path, schema: Schema):
        self.name = name
        self.path = path
        self.schema = schema

    def read_rows(self) -> list[Row]:
        """모든 행을 스키마 타입으로 바꿔 돌려준다. 읽기 전에 쓰기 버퍼를 flush한다."""
        raise NotImplementedError

    def append_rows(self, rows: list[Row]) -> None:
        """검사가 끝난 행(id 포함, 스키마 순서)을 파일 끝에 쓴다. flush는 하지 않는다."""
        raise NotImplementedError

    def next_id(self) -> int:
        """다음에 쓸 id. append_rows로 쓴 행만큼 늘어난다."""
        raise NotImplementedError

    def close(self) -> None:
        """버퍼를 flush하고 파일을 닫는다. 여러 번 불러도 된다."""
        raise NotImplementedError


def open_table(name: str) -> Table:
    """data/<name>.csv를 열고 헤더를 검사한다.

    name: 이미 소문자. 파일이 없으면 SqlError(B15), 헤더가 잘못되면 SqlError(B20).
    """
    raise NotImplementedError
