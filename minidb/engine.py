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

없는 테이블 에러에는 위치를 붙이지 않는다 (팀 결정, B15 예시와 다름).
컬럼 목록 검사는 왼쪽 이름부터 (id → 없는 컬럼 → 중복) 다음에 빠진 컬럼을 본다.
SELECT에 같은 컬럼을 두 번 적는 것(SELECT name, name)은 막지 않는다.

담당: (이름)
"""

from dataclasses import dataclass, field

from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.schema import Column, Schema
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

    def __init__(self) -> None:
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
        """검사를 전부 끝낸 뒤에 한 번에 쓴다 (B17, e6)."""
        table = self._find_table(statement.table)
        columns = _find_insert_columns(statement, table.schema)
        for values in statement.rows:
            _check_row(values, columns)
        rows = _build_rows(statement.rows, columns, table)
        table.append_rows(rows)
        return Result("insert", affected=len(rows))

    def _find_table(self, name: Name) -> Table:
        """처음 쓰는 테이블이면 열어서 기억한다. 없으면 SqlError (B15)."""
        if name.text not in self.tables:
            self.tables[name.text] = open_table(name.text)
        return self.tables[name.text]

    def _run_select(self, statement: Select) -> Result:
        """검사(컬럼, WHERE)를 먼저 끝내고 나서 파일을 읽는다."""
        table = self._find_table(statement.table)
        schema = table.schema
        names = _find_select_names(statement.columns, schema)
        where = statement.where
        if where is not None:
            where_index = _find_where_index(where, schema)
        rows = table.read_rows()
        if where is not None:
            rows = [row for row in rows
                    if row[where_index] == where.value.value]
        indexes = [schema.find(name) for name in names]
        picked = [tuple(row[index] for index in indexes) for row in rows]
        return Result("select", columns=names, rows=picked)


def _find_insert_columns(statement: Insert, schema: Schema) -> list[Column]:
    """값이 들어갈 컬럼을 값 순서대로. 컬럼 목록이 없으면 id를 뺀 스키마 순서 (B6)."""
    if statement.columns is None:
        return schema.value_columns
    columns = []
    for name in statement.columns:
        column = _find_listed_column(name, schema)
        if column in columns:
            raise SqlError(f"컬럼 {name.text}가 두 번 나옴", name.position)
        columns.append(column)
    _check_no_missing_columns(columns, schema, statement.table)
    return columns


def _find_listed_column(name: Name, schema: Schema) -> Column:
    if name.text == "id":
        raise SqlError("id는 자동으로 매겨지므로 넣을 수 없음", name.position)
    return _find_column(name, schema)


def _find_column(name: Name, schema: Schema) -> Column:
    index = schema.find(name.text)
    if index is None:
        raise SqlError(f"컬럼 {name.text}가 없음", name.position)
    return schema.columns[index]


def _check_no_missing_columns(columns: list[Column], schema: Schema,
                              table: Name) -> None:
    for column in schema.value_columns:
        if column not in columns:
            raise SqlError(f"컬럼 {column.name}의 값이 빠짐", table.position)


def _check_row(values: list[Value], columns: list[Column]) -> None:
    """값 개수와 타입을 본다 (B6, B10)."""
    if len(values) != len(columns):
        raise SqlError(f"값이 {len(columns)}개 필요한데 {len(values)}개",
                       values[0].position)
    for value, column in zip(values, columns):
        _check_value_type(value, column)


def _check_value_type(value: Value, column: Column) -> None:
    """int 컬럼엔 따옴표 없는 정수, str 컬럼엔 '문자열'만 (B10, B21)."""
    if isinstance(value.value, column.type):
        return
    if isinstance(value.value, str):
        found = f"문자열 '{value.value}'"
    else:
        found = f"정수 {value.value}"
    raise SqlError(f"{column.name}는 {column.type.__name__}인데 {found}가 옴",
                   value.position)


def _build_rows(rows: list[list[Value]], columns: list[Column],
                table: Table) -> list[Row]:
    """검사가 끝난 값을 스키마 순서의 행으로. id는 다음 id부터 차례로 (B13)."""
    next_id = table.find_next_id()
    built = []
    for offset, values in enumerate(rows):
        by_name = {column.name: value.value
                   for column, value in zip(columns, values)}
        by_name["id"] = next_id + offset
        built.append(tuple(by_name[name] for name in table.schema.names))
    return built


def _find_select_names(columns: list[Name] | None,
                       schema: Schema) -> list[str]:
    """SELECT * 이면 스키마 순서, 아니면 적힌 순서 (B7)."""
    if columns is None:
        return schema.names
    return [_find_column(name, schema).name for name in columns]


def _find_where_index(where: Where, schema: Schema) -> int:
    """WHERE 컬럼의 위치. 없는 컬럼이거나 값 타입이 다르면 SqlError (B8, B21).

    비교는 대소문자를 구분해 값 그대로 한다 (B5).
    """
    column = _find_column(where.column, schema)
    _check_value_type(where.value, column)
    return schema.find(column.name)
