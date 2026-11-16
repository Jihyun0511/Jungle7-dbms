"""커맨드 라인: SQL 파일을 읽고, 엔진을 돌리고, 결과를 출력한다.

규칙 (노션 요구분석 번호):
- B2  인자가 없거나 2개 이상이면 USAGE를 stderr로, 종료 코드 1.
      파일을 못 열면 'error: a.sql 파일을 열 수 없음', 종료 코드 1. 빈 파일은 종료 코드 0
- B17 파일 전체를 먼저 파싱 → 문법 에러면 아무것도 실행하지 않고 1.
      실행 에러가 나면 그 자리에서 멈추고 1. 에러는 stderr로 SqlError.format()
- B14 에러로 멈춰도 try/finally로 engine.close()를 부른다 (c5)
- B16 SELECT: CSV 그대로(헤더 포함). 0건이면 헤더 다음 줄에 '(0 rows)'.
      값 안의 줄바꿈은 '\\n' 두 글자로 바꿔 한 줄로.
      INSERT: 'N rows affected', 1건이면 '1 row affected'

담당: (이름)
"""

import csv
import io
import sys

from minidb.engine import Engine, Result
from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.statements import Statement

USAGE = "usage: python sql_processor.py <file.sql>"
# 윈도우 메모장이 붙이는 BOM을 SQL로 읽지 않게 utf-8-sig로 연다.
SQL_ENCODING = "utf-8-sig"


def main(argv: list[str]) -> int:
    """argv: 프로그램 이름을 뺀 인자 목록. 종료 코드를 돌려준다."""
    if len(argv) != 1:
        print(USAGE, file=sys.stderr)
        return 1
    try:
        text = _read_sql_file(argv[0])
        statements = parse_script(text)
        _run_statements(statements)
    except SqlError as error:
        print(error.format(), file=sys.stderr)
        return 1
    return 0


def format_result(result: Result) -> str:
    """결과 하나를 출력할 문자열로 바꾼다. 끝에 줄바꿈 포함."""
    if result.kind == "insert":
        return _format_affected(result.affected)
    return _format_rows(result)


def _read_sql_file(path: str) -> str:
    try:
        with open(path, encoding=SQL_ENCODING) as file:
            return file.read()
    except OSError as error:
        raise SqlError(f"{path} 파일을 열 수 없음") from error
    except UnicodeDecodeError as error:
        raise SqlError(f"{path} 파일을 utf-8로 읽을 수 없음") from error


def _run_statements(statements: list[Statement]) -> None:
    engine = Engine()
    try:
        for number, statement in enumerate(statements, start=1):
            result = _run_numbered(engine, statement, number)
            sys.stdout.write(format_result(result))
    finally:
        engine.close()


def _run_numbered(engine: Engine, statement: Statement, number: int) -> Result:
    try:
        return engine.run(statement)
    except SqlError as error:
        error.statement = number
        raise


def _format_affected(count: int) -> str:
    if count == 1:
        return "1 row affected\n"
    return f"{count} rows affected\n"


def _format_rows(result: Result) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(result.columns)
    for row in result.rows:
        writer.writerow([_flatten_value(value) for value in row])
    if not result.rows:
        buffer.write("(0 rows)\n")
    return buffer.getvalue()


def _flatten_value(value: int | str) -> int | str:
    if isinstance(value, int):
        return value
    return value.replace("\r\n", "\\n").replace("\n", "\\n")
