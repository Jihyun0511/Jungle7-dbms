"""테이블 파일(data/<이름>.csv) 읽기·쓰기. SQL은 모른다.

규칙 (노션 요구분석 번호):
- B3  테이블 파일은 실행한 폴더 기준 data/ 에 있다
- B12 CSV. 파일은 newline="" 으로 연다 (값 안의 줄바꿈 보존, s4). 읽은 값은 스키마 타입으로 바꾼다 (s3)
- B14 파일을 열어 둔 채로 쓰고, 읽기 직전에만 flush한다 (s6). close()에서 반드시 flush
- B13 다음 id = 마지막 행 id + 1 (행이 없으면 1). 처음 한 번만 읽고 기억한다.
      마지막 "줄"이 아니라 마지막 "CSV 행" 기준 (s5, s5b)
- B15 파일이 없으면 SqlError (만들지 않음)
- B19 인코딩은 보류. 지금은 utf-8

요구분석에 없어서 임시로 정한 것:
- 데이터 행의 컬럼 수가 헤더와 다르거나 int 칸이 정수가 아니면 SqlError
  (손으로 고친 파일 대비. 에러로 할지 건너뛸지는 팀이 나중에 정함)
- 파일 끝에 줄바꿈이 없으면 쓰기 전에 하나 붙인다. 안 그러면 새 행이
  마지막 행 뒤에 이어 붙는다

담당: (이름)
"""

import csv
from pathlib import Path
from typing import TextIO

from minidb.errors import SqlError
from minidb.schema import Schema, parse_header

DATA_DIR = Path("data")
ENCODING = "utf-8"

Row = tuple[int | str, ...]


class Table:
    """열린 테이블 하나. Engine이 테이블마다 하나씩 들고 있다."""

    def __init__(self, name: str, path: Path, schema: Schema) -> None:
        self.name = name
        self.path = path
        self.schema = schema
        self._file: TextIO | None = None   # 첫 append_rows 때 연다
        self._next_id: int | None = None   # 처음 find_next_id 때 읽는다

    def read_rows(self) -> list[Row]:
        """모든 행을 스키마 타입으로 바꿔 돌려준다. 읽기 전에 쓰기 버퍼를 flush한다."""
        self._flush()
        with open(self.path, newline="", encoding=ENCODING) as file:
            reader = csv.reader(file)
            next(reader, None)
            return [self._convert_row(fields, reader.line_num)
                    for fields in reader]

    def append_rows(self, rows: list[Row]) -> None:
        """검사가 끝난 행(id 포함, 스키마 순서)을 파일 끝에 쓴다. flush는 하지 않는다."""
        next_id = self.find_next_id()
        file = self._open_for_append()
        csv.writer(file).writerows(rows)
        self._next_id = next_id + len(rows)

    def find_next_id(self) -> int:
        """다음에 쓸 id. append_rows로 쓴 행만큼 늘어난다."""
        if self._next_id is None:
            self._next_id = self._read_last_id() + 1
        return self._next_id

    def close(self) -> None:
        """버퍼를 flush하고 파일을 닫는다. 여러 번 불러도 된다."""
        if self._file is not None:
            self._file.close()
            self._file = None

    def _flush(self) -> None:
        if self._file is not None:
            self._file.flush()

    def _convert_row(self, fields: list[str], line_number: int) -> Row:
        """CSV 문자열 칸들을 스키마 타입으로. line_number는 에러 메시지용."""
        where = f"{self.path.name} {line_number}줄"
        if len(fields) != len(self.schema.columns):
            raise SqlError(f"{where}: 컬럼 수가 헤더와 다름 "
                           f"({len(fields)}개, 헤더는 "
                           f"{len(self.schema.columns)}개)")
        return tuple(_convert_value(field, column.type, where)
                     for field, column in zip(fields, self.schema.columns))

    def _read_last_id(self) -> int:
        """마지막 CSV 행의 id. 행이 없으면 0."""
        rows = self.read_rows()
        if not rows:
            return 0
        return rows[-1][self.schema.find("id")]

    def _open_for_append(self) -> TextIO:
        if self._file is None:
            needs_newline = not _ends_with_newline(self.path)
            self._file = open(self.path, "a", newline="", encoding=ENCODING)
            if needs_newline:
                self._file.write("\r\n")
        return self._file


def open_table(name: str) -> Table:
    """data/<name>.csv를 열고 헤더를 검사한다.

    name: 이미 소문자. 파일이 없으면 SqlError(B15), 헤더가 잘못되면 SqlError(B20).
    """
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise SqlError(f"테이블 {name}가 없음")
    schema = _read_schema(path)
    return Table(name, path, schema)


def _read_schema(path: Path) -> Schema:
    with open(path, newline="", encoding=ENCODING) as file:
        fields = next(csv.reader(file), [])
    return parse_header(fields, path.name)


def _convert_value(field: str, value_type: type, where: str) -> int | str:
    if value_type is str:
        return field
    try:
        return int(field)
    except ValueError:
        raise SqlError(f"{where}: int 칸에 정수가 아닌 값 {field!r}") from None


def _ends_with_newline(path: Path) -> bool:
    """빈 파일이면 참으로 본다 (붙일 줄바꿈이 필요 없음)."""
    with open(path, "rb") as file:
        file.seek(0, 2)
        if file.tell() == 0:
            return True
        file.seek(-1, 2)
        return file.read(1) == b"\n"
