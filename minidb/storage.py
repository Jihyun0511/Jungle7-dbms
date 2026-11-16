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

import csv
from pathlib import Path
from typing import TextIO

from minidb.errors import SqlError
from minidb.schema import ID_COLUMN, Column, Schema, parse_header

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
ENCODING = "utf-8"

Row = tuple[int | str, ...]


class Table:
    """열린 테이블 하나. Engine이 테이블마다 하나씩 들고 있다."""

    def __init__(self, name: str, path: Path, schema: Schema):
        self.name = name
        self.path = path
        self.schema = schema
        self._file: TextIO | None = None
        self._writer = None
        self._next_id: int | None = None

    def read_rows(self) -> list[Row]:
        """모든 행을 스키마 타입으로 바꿔 돌려준다. 읽기 전에 쓰기 버퍼를 flush한다.

        파일의 행이 헤더와 맞지 않으면 SqlError.
        """
        self._flush()
        with open(self.path, encoding=ENCODING, newline="") as file:
            reader = csv.reader(file)
            next(reader, None)
            return [
                self._convert_record(record, reader.line_num)
                for record in reader
                if record
            ]

    def append_rows(self, rows: list[Row]) -> None:
        """검사가 끝난 행(id 포함, 스키마 순서)을 파일 끝에 쓴다. flush는 하지 않는다."""
        if not rows:
            return
        # 쓰기 전에 구해야 한다. 쓴 뒤에 처음 읽으면 방금 쓴 행이 두 번 세진다.
        next_id = self.find_next_id()
        self._open_writer().writerows(rows)
        self._next_id = next_id + len(rows)

    def find_next_id(self) -> int:
        """다음에 쓸 id. append_rows로 쓴 행만큼 늘어난다."""
        if self._next_id is None:
            self._next_id = self._read_next_id()
        return self._next_id

    def close(self) -> None:
        """버퍼를 flush하고 파일을 닫는다. 여러 번 불러도 된다."""
        if self._file is None:
            return
        self._file.close()
        self._file = None
        self._writer = None

    def _flush(self) -> None:
        if self._file is not None:
            self._file.flush()

    def _convert_record(self, record: list[str], line: int) -> Row:
        where = f"{self.path.name} {line}줄"
        columns = self.schema.columns
        if len(record) != len(columns):
            raise SqlError(
                f"{where}: 값이 {len(columns)}개여야 하는데 {len(record)}개"
            )
        return tuple(
            _convert_field(field, column, where)
            for field, column in zip(record, columns)
        )

    def _read_next_id(self) -> int:
        rows = self.read_rows()
        if not rows:
            return 1
        id_index = self.schema.find(ID_COLUMN)
        return rows[-1][id_index] + 1

    def _open_writer(self):
        if self._writer is None:
            _add_missing_line_end(self.path)
            self._file = open(
                self.path, "a", encoding=ENCODING, newline="",
            )
            self._writer = csv.writer(self._file, lineterminator=_LINE_END)
        return self._writer


def open_table(name: str) -> Table:
    """data/<name>.csv를 열고 헤더를 검사한다.

    name: 이미 소문자. 파일이 없으면 SqlError(B15), 헤더가 잘못되면 SqlError(B20).
    """
    path = DATA_DIR / f"{name}.csv"
    if not path.is_file():
        raise SqlError(f"테이블 {name}가 없음")
    schema = _read_schema(path)
    return Table(name, path, schema)


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------

# 헤더를 손으로 쓴 파일과 같은 줄바꿈을 쓰려고 csv 기본값(\r\n) 대신 \n을 쓴다.
_LINE_END = "\n"


def _convert_field(field: str, column: Column, where: str) -> int | str:
    if column.type is str:
        return field
    try:
        return int(field)
    except ValueError as error:
        raise SqlError(
            f"{where}: {column.name}는 int인데 '{field}'가 들어 있음"
        ) from error


def _add_missing_line_end(path: Path) -> None:
    """마지막 줄이 줄바꿈 없이 끝나면 붙인다. 안 그러면 새 행이 그 줄에 이어진다."""
    with open(path, "rb") as file:
        file.seek(0, 2)
        if file.tell() == 0:
            return
        file.seek(-1, 2)
        last_byte = file.read(1)
    if last_byte != b"\n":
        with open(path, "a", encoding=ENCODING, newline="") as file:
            file.write(_LINE_END)


def _read_schema(path: Path) -> Schema:
    with open(path, encoding=ENCODING, newline="") as file:
        fields = next(csv.reader(file), [])
    return parse_header(fields, path.name)
