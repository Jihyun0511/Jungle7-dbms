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
from minidb.schema import ID_COLUMN, Column, Schema
from minidb.statements import Insert, Name, Select, Statement, Value, Where
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
    """열린 테이블을 들고 있다가 문장을 실행한다. 다 쓰면 close()를 꼭 부른다 (B14)."""

    def __init__(self):
        self.tables: dict[str, Table] = {}

    def execute(self, sql: str) -> Result:
        """SQL 한 문장을 실행한다. 문장이 정확히 하나가 아니면 SqlError. (단위 테스트용)"""
        statements = parse_script(sql)
        if len(statements) != 1:
            raise SqlError(f"문장이 하나여야 하는데 {len(statements)}개")
        return self.run(statements[0])

    def run(self, statement: Statement) -> Result:
        """파싱된 문장 하나를 실행한다. CLI는 이걸 문장마다 부른다."""
        if isinstance(statement, Insert):
            return self._run_insert(statement)
        return self._run_select(statement)

    def close(self) -> None:
        """열린 테이블을 모두 닫는다 (버퍼 flush 포함)."""
        for table in self.tables.values():
            table.close()
        self.tables.clear()

    def _run_insert(self, statement: Insert) -> Result:
        table = self._find_table(statement.table)
        targets = _find_insert_targets(statement, table.schema)
        first_id = table.find_next_id()
        rows = [
            _build_row(values, targets, table.schema, first_id + i)
            for i, values in enumerate(statement.rows)
        ]
        table.append_rows(rows)
        return Result("insert", affected=len(rows))

    def _run_select(self, statement: Select) -> Result:
        table = self._find_table(statement.table)
        schema = table.schema
        indexes = _find_select_indexes(statement.columns, schema)
        match = _create_where_match(statement.where, schema)
        rows = [
            tuple(row[index] for index in indexes)
            for row in table.read_rows()
            if match(row)
        ]
        names = [schema.columns[index].name for index in indexes]
        return Result("select", columns=names, rows=rows)

    def _find_table(self, name: Name) -> Table:
        """처음 쓰는 테이블이면 연다. 여는 데 실패하면 SQL의 테이블 이름 위치를 붙인다."""
        if name.text not in self.tables:
            self.tables[name.text] = _open_table_at(name)
        return self.tables[name.text]


def _open_table_at(name: Name) -> Table:
    try:
        return open_table(name.text)
    except SqlError as error:
        raise SqlError(error.message, name.position) from error


def _find_insert_targets(statement: Insert, schema: Schema) -> list[int]:
    """값이 들어갈 스키마 위치를 값 순서대로 돌려준다."""
    if statement.columns is None:
        return [schema.find(column.name) for column in schema.value_columns]
    targets = [
        _find_insert_column(name, schema, statement.columns[:i])
        for i, name in enumerate(statement.columns)
    ]
    _check_missing_columns(statement, schema)
    return targets


def _find_insert_column(
    name: Name, schema: Schema, earlier: list[Name],
) -> int:
    if name.text == ID_COLUMN:
        raise SqlError("id는 자동으로 매기므로 넣을 수 없음", name.position)
    index = schema.find(name.text)
    if index is None:
        raise SqlError(f"컬럼 {name.text}가 없음", name.position)
    if any(seen.text == name.text for seen in earlier):
        raise SqlError(f"컬럼 {name.text}가 두 번 나옴", name.position)
    return index


def _check_missing_columns(statement: Insert, schema: Schema) -> None:
    given = {name.text for name in statement.columns}
    for column in schema.value_columns:
        if column.name not in given:
            raise SqlError(
                f"컬럼 {column.name}의 값이 빠짐", statement.columns[0].position,
            )


def _build_row(
    values: list[Value], targets: list[int], schema: Schema, row_id: int,
) -> Row:
    _check_value_count(values, targets, schema)
    fields: list[int | str] = [row_id] * len(schema.columns)
    for value, index in zip(values, targets):
        _check_value_type(value, schema.columns[index])
        fields[index] = value.value
    return tuple(fields)


def _check_value_count(
    values: list[Value], targets: list[int], schema: Schema,
) -> None:
    if len(values) == len(targets):
        return
    position = values[0].position
    if len(targets) == len(schema.value_columns) == len(values) - 1:
        raise SqlError("id는 자동으로 매기므로 값에 넣지 않음", position)
    raise SqlError(
        f"값이 {len(targets)}개여야 하는데 {len(values)}개", position,
    )


def _check_value_type(value: Value, column: Column) -> None:
    if type(value.value) is column.type:
        return
    raise SqlError(
        f"{column.name}는 {column.type.__name__}인데 "
        f"{_describe_value(value)}가 들어옴",
        value.position,
    )


def _describe_value(value: Value) -> str:
    if isinstance(value.value, str):
        return f"문자열 '{value.value}'"
    return f"정수 {value.value}"


def _find_select_indexes(
    columns: list[Name] | None, schema: Schema,
) -> list[int]:
    if columns is None:
        return list(range(len(schema.columns)))
    return [_find_column(name, schema) for name in columns]


def _find_column(name: Name, schema: Schema) -> int:
    index = schema.find(name.text)
    if index is None:
        raise SqlError(f"컬럼 {name.text}가 없음", name.position)
    return index


def _create_where_match(where: Where | None, schema: Schema):
    """행을 받아 조건에 맞는지 돌려주는 함수. 검사는 행을 읽기 전에 끝낸다."""
    if where is None:
        return lambda row: True
    index = _find_column(where.column, schema)
    _check_value_type(where.value, schema.columns[index])
    expected = where.value.value
    return lambda row: row[index] == expected
