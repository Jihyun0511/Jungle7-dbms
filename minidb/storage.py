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
- B17 insert 쓰기가 중간에 실패하면 파일을 그 문장 전 길이로 잘라 되돌린다.
      되돌리지 못하면 테이블을 고장으로 표시하고 이후 읽기·쓰기를 거절한다
- B23 락 방식 C: 테이블마다 lock 하나. insert 경로(find_next_id, append_rows)는
      호출자가 lock을 쥐고 부른다 (재진입 안 됨). select는 flush·끝 위치·
      offset 찾기만 락 안에서 하고, 파일 읽기와 _decode_row는 락 밖에서 한다.
      파일은 덧붙이기만 하므로 락 안에서 정한 끝 위치까지만 읽으면
      쓰는 중인 반쪽 행을 보지 않는다. close도 lock 안에서 해서 insert가
      버퍼에 쓰는 도중에 파일이 닫히지 않는다
- B24 load_index로 트리와 다음 id를 서버 시작 때 미리 만든다.
      Engine.open_all_tables가 부른다

담당: (이름)
"""

import csv
import os
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
    """열린 테이블 하나. Engine이 테이블마다 하나씩 들고 있다.

    lock: 이 테이블의 쓰기 상태(버퍼, 다음 id, 트리)를 지키는 락 (B23).
    재진입이 안 되므로 쥔 채로 read_rows·find_row_by_id를 부르면 멈춘다.
    """

    def __init__(self, name: str, path: Path, schema: Schema) -> None:
        self.name = name
        self.path = path
        self.schema = schema
        self.lock = threading.Lock()
        self._append_file: BufferedRandom | None = None
        self._end_offset = 0
        self._next_id: int | None = None
        self._index: BPlusTree | None = None
        self._is_broken = False

    def read_rows(self) -> list[Row]:
        """읽기 전에 쓰기 버퍼를 비우고, 행을 스키마 타입으로 바꾼다.

        안에서 lock을 잡으므로 lock을 쥔 채로 부르지 않는다. 락을 놓은 뒤에
        들어온 행은 보이지 않는다.
        """
        with self.lock:
            self._flush()
            end_offset = self._read_end_offset()
        records = _read_records(self.path, end_offset)
        return [
            self._decode_row(fields, f"data row {number}")
            for number, fields in enumerate(records[1:], start=1)
        ]

    def find_row_by_id(self, row_id: int) -> Row | None:
        """B+ 트리로 위치를 찾아 그 행 하나만 읽는다. 없으면 None.

        트리가 없으면 이때 파일을 한 번 훑어 만든다. 파일에 같은 id가
        두 번 있으면 SqlError. 안에서 lock을 잡으므로 lock을 쥔 채로
        부르지 않는다.
        """
        with self.lock:
            self._flush()
            offset = self._load_index().find(row_id)
        # offset의 행은 flush가 끝난 바이트라 락 밖에서 읽어도 바뀌지 않는다
        if offset is None:
            return None
        with _open_binary(self.path) as file:
            file.seek(offset)
            fields = _parse_record(_read_record(file), self.path)
        return self._decode_row(fields, f"row with id {row_id}")

    def append_rows(self, rows: list[Row]) -> None:
        """검사가 끝난 행(id 포함, 스키마 순서)을 버퍼에 쓴다.

        트리가 이미 있으면 쓴 행을 트리에도 등록한다. 그 id가 트리에
        이미 있으면 아무것도 쓰지 않고 SqlError.
        호출자가 table.lock을 쥐고 부른다 (find_next_id와 한 덩어리).
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

    def load_index(self) -> None:
        """트리와 다음 id를 지금 만든다 (B24). 이미 있으면 아무것도 안 한다.

        안에서 lock을 잡으므로 lock을 쥔 채로 부르지 않는다. 파일에 같은
        id가 두 번 있거나 id가 잘못된 행이 있으면 SqlError.
        """
        with self.lock:
            self._flush()
            self._load_index()

    def find_next_id(self) -> int:
        """다음에 쓸 id. append_rows로 쓴 행만큼 늘어난다.

        호출자가 table.lock을 쥐고 부른다. 놓았다가 append_rows를 부르면
        다른 워커가 같은 id를 받을 수 있다.
        """
        if self._next_id is None:
            self._next_id = self._read_next_id()
        return self._next_id

    def close(self) -> None:
        """버퍼를 flush하고 파일을 닫는다. 여러 번 불러도 된다.

        안에서 lock을 잡으므로 lock을 쥔 채로 부르지 않는다. 쓰는 중인
        insert가 있으면 그 문장이 끝난 뒤에 닫는다.
        """
        with self.lock:
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
        self._check_usable()
        if self._append_file is None:
            return
        try:
            self._append_file.flush()
        except OSError as error:
            raise SqlError(f"cannot write rows to {self.path.name}") from error

    def _read_end_offset(self) -> int:
        """지금까지 쓴 데이터가 끝나는 바이트 위치. lock 안에서 flush 뒤에 부른다."""
        # _end_offset은 _write가 append 파일을 처음 열 때 정해진다.
        # 그 전에는 0이지만 파일에는 행이 있으므로 파일 크기를 쓴다.
        if self._append_file is not None:
            return self._end_offset
        try:
            return self.path.stat().st_size
        except FileNotFoundError as error:
            raise SqlError(f"table {self.name} does not exist") from error
        except OSError as error:
            raise SqlError(f"cannot read {self.path.name}") from error

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
        records = _scan_records(self.path, self._read_end_offset())
        for number, (offset, record) in enumerate(records, start=1):
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

    def _check_usable(self) -> None:
        if self._is_broken:
            raise SqlError(
                f"table {self.name} is unusable after a failed write; "
                f"check {self.path.name} and restart"
            )

    def _write(self, data: bytes) -> int:
        """data를 파일 끝에 쓰고, data가 시작한 바이트 위치를 돌려준다.

        쓰다가 실패하면 파일을 쓰기 전 길이로 되돌리고 SqlError (B17).
        """
        self._check_usable()
        if self._append_file is None:
            self._open_append()
        assert self._append_file is not None
        start = self._end_offset
        try:
            self._append_file.write(data)
        except OSError as error:
            self._undo_write(start)
            raise SqlError(f"cannot write rows to {self.path.name}") from error
        self._end_offset += len(data)
        return start

    def _open_append(self) -> None:
        try:
            self._append_file = _open_append_file(self.path)
            self._end_offset = self._append_file.tell()
        except FileNotFoundError as error:
            raise SqlError(f"table {self.name} does not exist") from error
        except OSError as error:
            raise SqlError(f"cannot write rows to {self.path.name}") from error

    def _undo_write(self, start: int) -> None:
        """실패한 문장이 남긴 앞부분을 잘라 낸다. 못 하면 고장으로 표시한다.

        다음 쓰기 때 append 파일을 다시 열어 끝 위치를 새로 잡는다.
        """
        append_file = self._append_file
        self._append_file = None
        assert append_file is not None
        try:
            append_file.close()
        except OSError:
            # 버퍼를 내보내다 또 실패해도 파일 핸들은 닫힌다. 남은 바이트는
            # 아래에서 크기를 보고 판단하므로 여기서는 넘어간다.
            pass
        try:
            _truncate_file(self.path, start)
        except OSError as error:
            self._is_broken = True
            raise SqlError(
                f"cannot undo a failed write to {self.path.name}"
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


def _read_records(path: Path, end_offset: int) -> list[list[str]]:
    """헤더를 포함한 행들. end_offset 바이트까지만 읽는다 (B23).

    그 뒤는 다른 워커가 쓰는 중일 수 있어 반쪽 행이 섞인다.
    """
    with _open_binary(path) as file:
        data = file.read(end_offset)
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


def _scan_records(
    path: Path, end_offset: int,
) -> Iterator[tuple[int, bytes]]:
    """헤더를 뺀 행마다 (시작 바이트 위치, 행의 바이트).

    end_offset에서 멈춘다. 그 뒤는 끝 위치를 정한 뒤에 들어온 행이다 (B23).
    """
    with _open_binary(path) as file:
        _read_record(file)
        while file.tell() < end_offset:
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


def _truncate_file(path: Path, size: int) -> None:
    """파일을 size 바이트로 줄인다. 이미 size보다 짧으면 OSError.

    짧다는 것은 앞 문장들이 버퍼에만 있다가 함께 사라졌다는 뜻이라,
    잘라서 되돌릴 수 없다.
    """
    actual_size = path.stat().st_size
    if actual_size < size:
        raise OSError(
            f"{path.name} is {actual_size} bytes but expected at least {size}"
        )
    if actual_size > size:
        os.truncate(path, size)


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
