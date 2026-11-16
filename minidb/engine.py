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
- Phase 2  WHERE id = 값은 테이블별 메모리 B+ 트리를 사용한다.

담당: (이름)
"""

from dataclasses import dataclass, field

from minidb.bptree import BPlusTree
from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.schema import Column, Schema
from minidb.statements import Insert, Name, Select, Statement, Value, Where
from minidb.storage import Row, Table, open_table

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
        self._indexes: dict[str, BPlusTree[Row]] = {}

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
                return self._insert(table, statement)
            return self._select(table, statement)
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
        self._indexes.clear()
        if first_error is not None:
            raise first_error

    def _get_table(self, name: str) -> Table:
        table = self.tables.get(name)
        if table is None:
            table = open_table(name)
            self.tables[name] = table
        return table

    def _insert(self, table: Table, statement: Insert) -> Result:
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

        stored_rows = [tuple(row) for row in rows]
        index = self._get_index(table, id_index)
        table.append_rows(stored_rows)
        for row_id, stored_row in enumerate(stored_rows, start=next_id):
            index.insert(row_id, stored_row)
        return Result(kind="insert", affected=len(stored_rows))

    def _select(self, table: Table, statement: Select) -> Result:
        schema = table.schema
        if statement.columns is None:
            indices = list(range(len(schema.columns)))
        else:
            indices = [_find_column(schema, name) for name in statement.columns]

        if statement.where is None:
            matching_rows = table.read_rows()
        else:
            matching_rows = self._find_matching_rows(table, statement.where)
        rows = [tuple(row[index] for index in indices) for row in matching_rows]
        return Result(
            kind="select", columns=[schema.columns[i].name for i in indices],
            rows=rows,
        )

    def _find_matching_rows(self, table: Table, where: Where) -> list[Row]:
        column_index = _find_column(table.schema, where.column)
        value = _check_value(table.schema.columns[column_index], where.value)
        if where.column.text == "id":
            assert isinstance(value, int)
            return self._get_index(table, column_index).find(value)
        return [row for row in table.read_rows() if row[column_index] == value]

    def _get_index(self, table: Table, id_index: int) -> BPlusTree[Row]:
        index = self._indexes.get(table.name)
        if index is not None:
            return index

        index = BPlusTree()
        for row in table.read_rows():
            row_id = row[id_index]
            assert isinstance(row_id, int)
            index.insert(row_id, row)
        self._indexes[table.name] = index
        return index


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------


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
