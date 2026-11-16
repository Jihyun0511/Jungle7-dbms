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
from collections.abc import Iterator
from contextlib import contextmanager
from io import SEEK_END, TextIOWrapper
from pathlib import Path

from minidb.errors import SqlError
from minidb.schema import Schema, parse_header

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")

Row = tuple[int | str, ...]


class Table:
    """열린 테이블 하나. Engine이 테이블마다 하나씩 들고 있다."""

    def __init__(self, name: str, path: Path, schema: Schema) -> None:
        self.name = name
        self.path = path
        self.schema = schema
        self._append_file: TextIOWrapper | None = None
        self._next_id: int | None = None

    def read_rows(self) -> list[Row]:
        """읽기 전에 쓰기 버퍼를 비우고, 행을 스키마 타입으로 바꾼다."""
        with _open_records(self.path) as records:
            if self._append_file is not None:
                self._append_file.flush()
            next(records, None)
            return [
                self._decode_row(fields, number)
                for number, fields in enumerate(records, start=1)
            ]

    def append_rows(self, rows: list[Row]) -> None:
        """검사가 끝난 행(id 포함, 스키마 순서)을 버퍼에 쓴다."""
        if not rows:
            return
        next_id = self.find_next_id()
        try:
            if self._append_file is None:
                self._append_file = _open_append_file(self.path)
            csv.writer(self._append_file).writerows(rows)
        except FileNotFoundError as error:
            raise SqlError(f"table {self.name} does not exist") from error
        except (OSError, UnicodeError, csv.Error) as error:
            raise SqlError(f"cannot write rows to {self.path.name}") from error
        self._next_id = next_id + len(rows)

    def find_next_id(self) -> int:
        """다음에 쓸 id. append_rows로 쓴 행만큼 늘어난다."""
        if self._next_id is None:
            self._next_id = self._read_next_id()
        return self._next_id

    def close(self) -> None:
        """버퍼를 flush하고 파일을 닫는다. 여러 번 불러도 된다."""
        if self._append_file is None:
            return
        append_file = self._append_file
        self._append_file = None
        try:
            append_file.close()
        except OSError as error:
            raise SqlError(f"cannot close {self.path.name}") from error

    def _decode_row(self, fields: list[str], number: int) -> Row:
        location = f"{self.path.name} data row {number}"
        if len(fields) != len(self.schema.columns):
            raise SqlError(
                f"{location}: expected {len(self.schema.columns)} values "
                f"like the header but got {len(fields)}"
            )
        try:
            return tuple(
                column.type(value)
                for column, value in zip(self.schema.columns, fields)
            )
        except ValueError as error:
            raise SqlError(
                f"{location}: value does not match header type"
            ) from error

    def _read_next_id(self) -> int:
        last_fields = None
        with _open_records(self.path) as records:
            next(records, None)
            for fields in records:
                last_fields = fields
        if last_fields is None:
            return 1

        id_index = self.schema.find("id")
        assert id_index is not None
        try:
            return int(last_fields[id_index]) + 1
        except (IndexError, ValueError) as error:
            raise SqlError(
                f"{self.path.name} last row has an invalid id"
            ) from error


def open_table(name: str) -> Table:
    """data/<name>.csv를 열고 헤더를 검사한다.

    name: 이미 소문자. 파일이나 헤더가 잘못되면 SqlError (B15, B20).
    """
    path = DATA_DIR / f"{name}.csv"
    with _open_records(path) as records:
        fields = next(records, [])
    return Table(name, path, parse_header(fields, path.name))


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------

_ENCODING = "utf-8"


@contextmanager
def _open_records(path: Path) -> Iterator[Iterator[list[str]]]:
    try:
        with path.open(encoding=_ENCODING, newline="") as file:
            yield csv.reader(file, strict=True)
    except FileNotFoundError as error:
        raise SqlError(f"table {path.stem} does not exist") from error
    except (OSError, UnicodeError, csv.Error) as error:
        raise SqlError(f"cannot read {path.name}") from error


def _open_append_file(path: Path) -> TextIOWrapper:
    file = path.open("r+b")
    try:
        if file.seek(0, SEEK_END):
            file.seek(-1, SEEK_END)
        # 마지막 레코드에 줄바꿈이 빠져 있으면 새 행과 구분한다.
        if file.read(1) not in (b"", b"\n", b"\r"):
            file.write(b"\n")
        return TextIOWrapper(file, encoding=_ENCODING, newline="")
    except OSError:
        file.close()
        raise
