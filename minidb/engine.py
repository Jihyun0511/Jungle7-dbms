"""문장을 실행하고 결과를 돌려준다. print도 sys.argv도 쓰지 않는다 (B18).

규칙 (노션 요구분석 번호):
- B6  컬럼 목록 없는 INSERT: id를 뺀 컬럼을 스키마 순서대로.
      컬럼 목록 INSERT 에러: id가 있음, 없는 컬럼, 같은 컬럼 두 번, id 외 컬럼 누락, 개수 불일치
- B10 타입 검사 엄격: int 컬럼엔 int 값만, str 컬럼엔 str 값만
- B13 id는 자동. 사용자가 id를 넣으면 에러
- B17 여러 행 INSERT는 모든 행을 검사한 뒤에 쓴다. 실패하면 한 행도 안 쓰고 id도 안 씀 (e6)
- B7  없는 컬럼을 SELECT하면 에러
- B8  WHERE column = value. 없는 컬럼이면 에러. 값은 대소문자 구분 (B5)
- B21 WHERE 값 타입이 컬럼과 다르면 에러 (e12)
- Phase 2 WHERE id = ? 는 B+ 트리 인덱스로, 다른 컬럼은 선형 탐색으로 찾는다
      (e13~e15)
- Phase 3 여러 스레드가 Engine 하나를 같이 쓴다 (노션 6절 B23~B27, t1~t5)
      B25 테이블 찾기·열기는 엔진 락으로 짧게. 놓은 뒤에 테이블 락을 잡는다
          (두 락을 동시에 쥐지 않는다)
      B23 C insert: 파싱·값 검사는 락 밖, find_next_id → id 채우기 →
          append_rows만 테이블 락 안
          select: 락 안에서는 flush + 끝 위치 기억(또는 트리에서 offset 찾기)만,
          파일 읽기·디코딩·결과 만들기는 락 밖
      B24 prepare_tables(): 서버 시작 때 data/의 테이블을 모두 열고 트리·다음 id를
          미리 만든다
      B27 close()는 워커를 모두 멈춘 뒤에 부른다 (부르는 쪽 책임)

담당: (이름)
"""

import threading
from dataclasses import dataclass, field

from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.schema import Column, Schema
from minidb.statements import Insert, Name, Select, Statement, Value
from minidb.storage import DATA_DIR, Row, Table, open_table

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------


@dataclass
class Result:
    """문장 하나의 결과. 출력 모양(B16)은 CLI가 정한다.

    kind: "insert" 또는 "select"
    columns, rows: SELECT 결과 (INSERT면 빈 목록)
    affected: INSERT로 들어간 행 수 (SELECT면 0)
    """

    kind: str
    columns: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    affected: int = 0


class Engine:
    """문장을 실행하고 테이블을 보관한다. 다 쓰면 close()를 부른다 (B14)."""

    def __init__(self) -> None:
        self.tables: dict[str, Table] = {}
        self._engine_lock = threading.Lock()   # self.tables만 지킨다 (B25)

    def execute(self, sql: str) -> Result:
        """SQL 문장이 정확히 하나면 실행하고, 그 외에는 SqlError를 던진다."""
        statements = parse_script(sql)
        if len(statements) != 1:
            raise SqlError(
                f"expected exactly one statement but got {len(statements)}"
            )
        return self.run(statements[0])

    def run(self, statement: Statement) -> Result:
        """파싱된 문장 하나를 실행한다. CLI는 이걸 문장마다 부른다."""
        try:
            table = self._get_table(statement.table.text)
            if isinstance(statement, Insert):
                return _insert(table, statement)
            return _select(table, statement)
        except SqlError as error:
            if error.position is None and isinstance(
                error.__cause__, FileNotFoundError
            ):
                error.position = statement.table.position
            raise

    def prepare_tables(self) -> list[str]:
        """data/의 테이블을 모두 열고 트리·다음 id를 미리 만든다 (B24).

        서버 시작 때 워커를 띄우기 전에 부른다. 연 테이블 이름을 돌려준다.
        테이블 파일이 잘못돼 있으면 SqlError.
        """
        names = sorted(path.stem for path in DATA_DIR.glob("*.csv"))
        for name in names:
            table = self._get_table(name)
            with table.lock:
                table.prepare()
        return names

    def close(self) -> None:
        """열린 테이블을 모두 닫는다 (버퍼 flush 포함).

        여러 스레드에서 쓸 때는 워커를 모두 멈춘 뒤에 부른다 (B27).
        """
        with self._engine_lock:
            tables = list(self.tables.values())
            self.tables.clear()
        first_error = None
        for table in tables:
            try:
                table.close()
            except SqlError as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def _get_table(self, name: str) -> Table:
        # 두 워커가 동시에 "없네" 하면 Table이 두 개, 락도 두 개가 된다 (B25)
        with self._engine_lock:
            table = self.tables.get(name)
            if table is None:
                table = open_table(name)
                self.tables[name] = table
            return table


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------


def _insert(table: Table, statement: Insert) -> Result:
    schema = table.schema
    column_indices = _insert_column_indices(schema, statement)
    rows = [
        _check_insert_row(schema, column_indices, values, statement.table)
        for values in statement.rows
    ]

    id_index = schema.find("id")
    assert id_index is not None
    # 다음 id 읽기부터 쓰기까지 한 덩어리여야 id가 겹치지 않는다 (B23, t2)
    with table.lock:
        next_id = table.find_next_id()
        for row_id, row in enumerate(rows, start=next_id):
            row[id_index] = row_id
        table.append_rows([tuple(row) for row in rows])
    return Result(kind="insert", affected=len(rows))


def _insert_column_indices(schema: Schema, statement: Insert) -> list[int]:
    if statement.columns is None:
        return [
            index for index, column in enumerate(schema.columns)
            if column.name != "id"
        ]

    indices = []
    seen_names = set()
    for name in statement.columns:
        if name.text == "id":
            raise SqlError(
                "id is assigned automatically and cannot be inserted",
                name.position,
            )
        if name.text in seen_names:
            raise SqlError(
                f"column {name.text} appears twice", name.position,
            )
        indices.append(_find_column(schema, name))
        seen_names.add(name.text)

    missing = [
        column.name for column in schema.value_columns
        if column.name not in seen_names
    ]
    if missing:
        names = ", ".join(missing)
        raise SqlError(
            f"INSERT column list is missing {names}",
            statement.table.position,
        )
    return indices


def _check_insert_row(
    schema: Schema, indices: list[int], values: list[Value], table: Name,
) -> list[int | str]:
    if len(values) != len(indices):
        position = values[0].position if values else table.position
        raise SqlError(
            f"expected {len(indices)} values but got {len(values)}",
            position,
        )

    row: list[int | str] = [0] * len(schema.columns)
    for index, value in zip(indices, values):
        row[index] = _check_value(schema.columns[index], value)
    return row


def _select(table: Table, statement: Select) -> Result:
    schema = table.schema
    if statement.columns is None:
        indices = list(range(len(schema.columns)))
    else:
        indices = [_find_column(schema, name) for name in statement.columns]

    where_index = None
    where_value = None
    if statement.where is not None:
        where_index = _find_column(schema, statement.where.column)
        where_value = _check_value(
            schema.columns[where_index], statement.where.value,
        )

    rows = [
        tuple(row[index] for index in indices)
        for row in _find_rows(table, where_index, where_value)
    ]
    return Result(
        kind="select", columns=[schema.columns[i].name for i in indices],
        rows=rows,
    )


def _find_rows(
    table: Table, where_index: int | None, where_value: int | str | None,
) -> list[Row]:
    """락은 위치를 정하는 동안만 쥐고, 읽기·디코딩은 락 밖에서 한다 (B23 C)."""
    if where_index is not None and table.schema.columns[where_index].name == "id":
        assert isinstance(where_value, int)
        return _find_row_by_id(table, where_value)
    with table.lock:
        end = table.snapshot_end()
    rows = table.read_rows(end)
    if where_index is None:
        return rows
    return [row for row in rows if row[where_index] == where_value]


def _find_row_by_id(table: Table, row_id: int) -> list[Row]:
    with table.lock:
        offset = table.find_offset(row_id)
    if offset is None:
        return []
    return [table.read_row_at(offset, row_id)]


def _find_column(schema: Schema, name: Name) -> int:
    index = schema.find(name.text)
    if index is None:
        raise SqlError(f"column {name.text} does not exist", name.position)
    return index


def _check_value(column: Column, value: Value) -> int | str:
    if type(value.value) is not column.type:
        expected = column.type.__name__
        raise SqlError(
            f"{column.name} is {expected} but got {_describe(value)}",
            value.position,
        )
    return value.value


def _describe(value: Value) -> str:
    if isinstance(value.value, str):
        return f"string '{value.value}'"
    return f"integer {value.value}"
