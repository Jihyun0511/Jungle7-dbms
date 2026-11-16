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

담당: (이름)
"""

from dataclasses import dataclass, field

from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.schema import Column, Schema
from minidb.statements import Insert, Name, Select, Statement, Value
from minidb.storage import Row, Table, open_table


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

    def execute(self, sql: str) -> Result:
        """SQL 문장이 정확히 하나면 실행하고, 그 외에는 SqlError를 던진다."""
        statements = parse_script(sql)
        if len(statements) != 1:
            raise SqlError("SQL 문장이 정확히 하나 필요")
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

    def close(self) -> None:
        """열린 테이블을 모두 닫는다 (버퍼 flush 포함)."""
        first_error = None
        for table in self.tables.values():
            try:
                table.close()
            except SqlError as error:
                if first_error is None:
                    first_error = error
        self.tables.clear()
        if first_error is not None:
            raise first_error

    def _get_table(self, name: str) -> Table:
        table = self.tables.get(name)
        if table is None:
            table = open_table(name)
            self.tables[name] = table
        return table


def _insert(table: Table, statement: Insert) -> Result:
    schema = table.schema
    column_indices = _insert_column_indices(schema, statement)
    rows = [
        _check_insert_row(schema, column_indices, values, statement.table)
        for values in statement.rows
    ]

    id_index = schema.find("id")
    assert id_index is not None
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
            raise SqlError("id는 자동으로 부여하는 컬럼", name.position)
        if name.text in seen_names:
            raise SqlError(f"컬럼 {name.text} 중복", name.position)
        indices.append(_find_column(schema, name))
        seen_names.add(name.text)

    missing = [
        column.name for column in schema.value_columns
        if column.name not in seen_names
    ]
    if missing:
        names = ", ".join(missing)
        raise SqlError(f"INSERT 컬럼 누락 ({names})", statement.table.position)
    return indices


def _check_insert_row(
    schema: Schema, indices: list[int], values: list[Value], table: Name,
) -> list[int | str]:
    if len(values) != len(indices):
        position = values[0].position if values else table.position
        raise SqlError(
            f"INSERT 값 개수 불일치 (필요 {len(indices)}개, 입력 {len(values)}개)",
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
        for row in table.read_rows()
        if where_index is None or row[where_index] == where_value
    ]
    return Result(
        kind="select", columns=[schema.columns[i].name for i in indices],
        rows=rows,
    )


def _find_column(schema: Schema, name: Name) -> int:
    index = schema.find(name.text)
    if index is None:
        raise SqlError(f"컬럼 {name.text}가 없음", name.position)
    return index


def _check_value(column: Column, value: Value) -> int | str:
    if type(value.value) is not column.type:
        expected = column.type.__name__
        actual = type(value.value).__name__
        raise SqlError(
            f"컬럼 {column.name}은 {expected} 타입, 입력값은 {actual} 타입",
            value.position,
        )
    return value.value
