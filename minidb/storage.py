"""테이블 파일(data/<이름>.csv) 읽기·쓰기. SQL은 모른다.

규칙 (노션 요구분석 번호):
- B3  테이블 파일은 실행한 폴더 기준 data/ 에 있다
- B12 CSV. 파일은 newline="" 으로 연다 (값 안의 줄바꿈 보존, s4). 읽은 값은 스키마 타입으로 바꾼다 (s3)
- B14 파일을 열어 둔 채로 쓰고, 읽기 직전에만 flush한다 (s6). close()에서 반드시 flush
- B13 다음 id = 마지막 행 id + 1 (행이 없으면 1). 처음 한 번만 읽고 기억한다.
      마지막 "줄"이 아니라 마지막 "CSV 행" 기준 (s5, s5b)
- B15 파일이 없으면 SqlError (만들지 않음)
- B19 인코딩은 보류. 지금은 utf-8
- Phase 2 id 인덱스: 메모리 B+ 트리에 id → 행이 시작하는 바이트 위치.
      id로 처음 찾을 때만 파일을 한 번 훑어 만든다. INSERT는 트리를 만들지 않고,
      트리가 이미 있을 때만 쓴 행을 바로 등록한다 (s7).
      id로 찾을 때는 그 위치로 가서 행 하나만 읽는다
- Phase 3 B23 C: Table.lock은 Engine이 잡는다. Table 메서드는 락을 잡지 않는다.
      락 안에서 부를 것: find_next_id, append_rows, snapshot_end, find_offset, prepare
      락 밖에서 불러도 되는 것: read_rows(end), read_row_at (파일은 덧붙이기만 하므로
      락 안에서 받은 끝 위치·offset까지의 바이트는 바뀌지 않는다)
- Phase 3 B24 prepare(): 서버 시작 때 트리와 다음 id를 미리 만든다

담당: (이름)
"""

import csv
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from io import SEEK_END, BufferedRandom, BufferedReader, StringIO
from pathlib import Path

from minidb.bptree import BPlusTree
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
        self._append_file: BufferedRandom | None = None
        self._end_offset = 0
        self._next_id: int | None = None
        self._index: BPlusTree | None = None
        # 다음 id, 트리, 쓰기 파일을 지킨다. 잡는 쪽은 Engine (B23)
        self.lock = threading.Lock()

    def read_rows(self, end: int | None = None) -> list[Row]:
        """행을 스키마 타입으로 바꾼다. end 바이트 위치까지만 읽는다 (B23).

        end가 None이면 쓰기 버퍼를 비우고 파일 끝까지 읽는다 (스레드 하나일
        때). 여러 스레드에서는 락 안에서 snapshot_end()로 받은 값을 넘긴다.
        """
        if end is None:
            end = self.snapshot_end()
        records = _parse_records(self._read_bytes(end), self.path)
        return [
            self._decode_row(fields, f"data row {number}")
            for number, fields in enumerate(records[1:], start=1)
        ]

    def snapshot_end(self) -> int:
        """쓰기 버퍼를 비운 뒤의 파일 끝 바이트 위치. 락 안에서 부른다."""
        self._flush()
        try:
            return self.path.stat().st_size
        except FileNotFoundError as error:
            raise SqlError(f"table {self.name} does not exist") from error
        except OSError as error:
            raise SqlError(f"cannot read {self.path.name}") from error

    def find_row_by_id(self, row_id: int) -> Row | None:
        """B+ 트리로 위치를 찾아 그 행 하나만 읽는다. 없으면 None.

        스레드 하나일 때 쓰는 줄임. 여러 스레드에서는 find_offset(락 안)과
        read_row_at(락 밖)으로 나눠 부른다 (B23).
        """
        offset = self.find_offset(row_id)
        if offset is None:
            return None
        return self.read_row_at(offset, row_id)

    def find_offset(self, row_id: int) -> int | None:
        """id인 행이 시작하는 바이트 위치. 없으면 None. 락 안에서 부른다.

        트리가 없으면 이때 파일을 한 번 훑어 만든다 (B24로 미리 만들 수 있음).
        파일에 같은 id가 두 번 있으면 SqlError.
        """
        self._flush()
        return self._load_index().find(row_id)

    def read_row_at(self, offset: int, row_id: int) -> Row:
        """offset에서 시작하는 행 하나. 락 밖에서 불러도 된다."""
        with _open_binary(self.path) as file:
            file.seek(offset)
            fields = _parse_record(_read_record(file), self.path)
        return self._decode_row(fields, f"row with id {row_id}")

    def prepare(self) -> None:
        """트리와 다음 id를 미리 만든다 (B24). 락 안에서 부른다.

        안 하면 첫 WHERE id가 테이블 락을 쥔 채 파일 전체를 훑는다.
        """
        self._flush()
        self._load_index()

    def append_rows(self, rows: list[Row]) -> None:
        """검사가 끝난 행(id 포함, 스키마 순서)을 버퍼에 쓴다.

        트리가 이미 있으면 쓴 행을 트리에도 등록한다. 그 id가 트리에
        이미 있으면 아무것도 쓰지 않고 SqlError.
        """
        if not rows:
            return
        next_id = self.find_next_id()
        row_ids = [row[self._id_index] for row in rows]
        self._check_new_ids(row_ids)
        encoded_rows = [_encode_row(row, self.path) for row in rows]

        offset = self._write(b"".join(encoded_rows))
        self._next_id = next_id + len(rows)
        if self._index is None:
            return
        for row_id, encoded in zip(row_ids, encoded_rows):
            self._index.insert(row_id, offset)
            offset += len(encoded)

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

    @property
    def _id_index(self) -> int:
        id_index = self.schema.find("id")
        assert id_index is not None
        return id_index

    def _flush(self) -> None:
        if self._append_file is None:
            return
        try:
            self._append_file.flush()
        except OSError as error:
            raise SqlError(f"cannot write rows to {self.path.name}") from error

    def _read_bytes(self, end: int) -> bytes:
        """파일 처음부터 end 바이트까지. 그 뒤에 덧붙는 행은 보지 않는다."""
        with _open_binary(self.path) as file:
            return file.read(end)

    def _decode_row(self, fields: list[str], where: str) -> Row:
        location = f"{self.path.name} {where}"
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

        try:
            return int(last_fields[self._id_index]) + 1
        except (IndexError, ValueError) as error:
            raise SqlError(
                f"{self.path.name} last row has an invalid id"
            ) from error

    def _load_index(self) -> BPlusTree:
        """처음 한 번 파일을 훑어 id → 바이트 위치 트리를 만든다."""
        if self._index is not None:
            return self._index
        index = BPlusTree()
        last_id = None
        for number, (offset, record) in enumerate(
            _scan_records(self.path), start=1,
        ):
            last_id = self._read_row_id(record, number)
            self._register_id(index, last_id, offset, number)
        self._index = index
        # 다음 id(B13)를 아직 몰랐다면 같은 훑기에서 얻은 값을 쓴다.
        if self._next_id is None:
            self._next_id = 1 if last_id is None else last_id + 1
        return index

    def _read_row_id(self, record: bytes, number: int) -> int:
        fields = _split_record(record, self.path)
        try:
            return int(fields[self._id_index])
        except (IndexError, ValueError) as error:
            raise SqlError(
                f"{self.path.name} data row {number} has an invalid id"
            ) from error

    def _register_id(self, index: BPlusTree, row_id: int, offset: int,
                     number: int) -> None:
        try:
            index.insert(row_id, offset)
        except ValueError as error:
            raise SqlError(
                f"{self.path.name} data row {number}: duplicate id {row_id}"
            ) from error

    def _check_new_ids(self, row_ids: list[int]) -> None:
        # 트리가 없으면 확인할 방법이 없다. 그때는 B13대로 믿고 쓴다.
        if self._index is None:
            return
        for row_id in row_ids:
            if self._index.has_key(row_id):
                raise SqlError(f"id {row_id} already exists in {self.name}")

    def _write(self, data: bytes) -> int:
        """data를 파일 끝에 쓰고, data가 시작한 바이트 위치를 돌려준다."""
        try:
            if self._append_file is None:
                self._append_file = _open_append_file(self.path)
                self._end_offset = self._append_file.tell()
            self._append_file.write(data)
        except FileNotFoundError as error:
            raise SqlError(f"table {self.name} does not exist") from error
        except OSError as error:
            raise SqlError(f"cannot write rows to {self.path.name}") from error
        start = self._end_offset
        self._end_offset += len(data)
        return start


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
_QUOTE = ord('"')


@contextmanager
def _open_records(path: Path) -> Iterator[Iterator[list[str]]]:
    try:
        with path.open(encoding=_ENCODING, newline="") as file:
            yield csv.reader(file, strict=True)
    except FileNotFoundError as error:
        raise SqlError(f"table {path.stem} does not exist") from error
    except (OSError, UnicodeError, csv.Error) as error:
        raise SqlError(f"cannot read {path.name}") from error


@contextmanager
def _open_binary(path: Path) -> Iterator[BufferedReader]:
    # 바이트 위치(seek/tell)를 쓰려고 바이너리로 연다. 글자 변환은 직접 한다.
    try:
        with path.open("rb") as file:
            yield file
    except FileNotFoundError as error:
        raise SqlError(f"table {path.stem} does not exist") from error
    except OSError as error:
        raise SqlError(f"cannot read {path.name}") from error


def _parse_records(data: bytes, path: Path) -> list[list[str]]:
    """바이트 덩어리를 CSV 행들로 (헤더 포함). 깨진 내용이면 SqlError."""
    try:
        text = data.decode(_ENCODING)
        return list(csv.reader(StringIO(text, newline=""), strict=True))
    except (UnicodeError, csv.Error) as error:
        raise SqlError(f"cannot read {path.name}") from error


def _parse_record(record: bytes, path: Path) -> list[str]:
    try:
        text = record.decode(_ENCODING)
        return next(csv.reader(StringIO(text, newline=""), strict=True), [])
    except (UnicodeError, csv.Error) as error:
        raise SqlError(f"cannot read {path.name}") from error


def _read_record(file: BufferedReader) -> bytes:
    """CSV 행 하나의 바이트. 따옴표 안의 줄바꿈이면 다음 줄까지 붙인다."""
    record = file.readline()
    quotes = record.count(_QUOTE)
    while quotes % 2 == 1:
        line = file.readline()
        if not line:
            break
        record += line
        quotes += line.count(_QUOTE)
    return record


def _scan_records(path: Path) -> Iterator[tuple[int, bytes]]:
    """헤더를 뺀 행마다 (시작 바이트 위치, 행의 바이트)."""
    with _open_binary(path) as file:
        _read_record(file)
        while True:
            offset = file.tell()
            record = _read_record(file)
            if not record:
                return
            yield offset, record


def _split_record(record: bytes, path: Path) -> list[bytes] | list[str]:
    """트리를 만들 때 id 칸만 꺼내려고 행을 칸으로 나눈다.

    따옴표가 없는 행은 csv 해석 없이 쉼표로 자른다. csv.writer는 쉼표·따옴표·
    줄바꿈이 든 값을 꼭 따옴표로 감싸므로, 따옴표가 없으면 쉼표가 곧 칸
    구분이고 결과가 csv 해석과 같다 (s12). 행마다 csv 해석기를 만드는
    비용을 줄이려는 것이다. 이 길에서는 id 칸 말고는 utf-8 검사를 하지
    않으므로, 다른 칸의 깨진 글자는 그 행을 읽을 때 에러가 난다.
    """
    if _QUOTE not in record:
        return record.rstrip(b"\r\n").split(b",")
    return _parse_record(record, path)


def _encode_row(row: Row, path: Path) -> bytes:
    text = StringIO(newline="")
    csv.writer(text).writerow(row)
    try:
        return text.getvalue().encode(_ENCODING)
    except UnicodeError as error:
        raise SqlError(f"cannot write rows to {path.name}") from error


def _open_append_file(path: Path) -> BufferedRandom:
    file = path.open("r+b")
    try:
        if file.seek(0, SEEK_END):
            file.seek(-1, SEEK_END)
        # 마지막 레코드에 줄바꿈이 빠져 있으면 새 행과 구분한다.
        if file.read(1) not in (b"", b"\n", b"\r"):
            file.write(b"\n")
        return file
    except OSError:
        file.close()
        raise
