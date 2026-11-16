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

SQL 파일이 utf-8이 아니면 '파일을 열 수 없음'과 같은 형식으로 알린다.

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
# csv.writer 기본값 '\r\n'을 윈도우 stdout으로 내보내면 '\r\r\n'이 되어
# 행마다 빈 줄이 생긴다 (c1, c3, c4). csv.writer(..., lineterminator=이 값)
OUTPUT_LINE_END = "\n"
# 메모장 등이 붙이는 BOM이 있으면 떼고 읽는다. 없으면 utf-8과 같다.
# newline은 기본값으로 두어 '\r\n'을 '\n'으로 바꿔 읽는다 (칸 번호, 값 안의 \r)
SQL_ENCODING = "utf-8-sig"


def main(argv: list[str]) -> int:
    """argv: 프로그램 이름을 뺀 인자 목록. 종료 코드를 돌려준다."""
    if len(argv) != 1:
        _print_error(USAGE)
        return 1
    try:
        statements = parse_script(_read_sql(argv[0]))
    except SqlError as error:
        _print_error(error.format())
        return 1
    return _run_statements(statements)


def format_result(result: Result) -> str:
    """결과 하나를 출력할 문자열로 바꾼다. 끝에 줄바꿈 포함."""
    if result.kind == "insert":
        noun = "row" if result.affected == 1 else "rows"
        return f"{result.affected} {noun} affected{OUTPUT_LINE_END}"
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=OUTPUT_LINE_END)
    writer.writerow(result.columns)
    writer.writerows(_flatten_newlines(row) for row in result.rows)
    if not result.rows:
        buffer.write(f"(0 rows){OUTPUT_LINE_END}")
    return buffer.getvalue()


def _print_error(message: str) -> None:
    print(message, file=sys.stderr)


def _read_sql(path: str) -> str:
    """SQL 파일 내용. 못 열거나 utf-8이 아니면 SqlError (B2)."""
    try:
        with open(path, encoding=SQL_ENCODING) as file:
            return file.read()
    except (OSError, UnicodeDecodeError):
        raise SqlError(f"{path} 파일을 열 수 없음") from None


def _run_statements(statements: list[Statement]) -> int:
    """문장을 차례로 실행하고 결과를 출력한다. 실행 에러면 그 자리에서 멈춘다 (B17)."""
    engine = Engine()
    try:
        for number, statement in enumerate(statements, start=1):
            result = _run_numbered(engine, statement, number)
            sys.stdout.write(format_result(result))
    except SqlError as error:
        _print_error(error.format())
        return 1
    finally:
        engine.close()
    return 0


def _run_numbered(engine: Engine, statement: Statement,
                  number: int) -> Result:
    """실행 에러에 몇 번째 문장인지 채워서 다시 던진다."""
    try:
        return engine.run(statement)
    except SqlError as error:
        error.statement = number
        raise


def _flatten_newlines(row: tuple) -> tuple:
    """값 안의 줄바꿈을 '\\n' 두 글자로 바꿔 한 행이 한 줄에 나오게 한다 (B16)."""
    return tuple(
        value.replace("\r\n", "\n").replace("\n", "\\n")
        if isinstance(value, str) else value
        for value in row
    )
