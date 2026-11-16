"""커맨드 라인: SQL 파일을 읽고, 엔진을 돌리고, 결과를 출력한다.

규칙 (노션 요구분석 번호):
- B2  인자가 없거나 2개 이상이면 USAGE를 stderr로, 종료 코드 1.
      파일을 못 열면 'error: cannot open a.sql', 종료 코드 1. 빈 파일은 종료 코드 0
- B17 파일 전체를 먼저 파싱 → 문법 에러면 아무것도 실행하지 않고 1.
      실행 에러가 나면 그 자리에서 멈추고 1. 에러는 stderr로 SqlError.format()
- B14 에러로 멈춰도 try/finally로 engine.close()를 부른다 (c5)
- B16 SELECT: CSV 그대로(헤더 포함). 0건이면 헤더 다음 줄에 '(0 rows)'.
      값 안의 줄바꿈은 '\\n' 두 글자로 바꿔 한 줄로.
      INSERT: 'N rows affected', 1건이면 '1 row affected'
- B19 SQL 파일은 utf-8-sig로 읽는다 (메모장 BOM 무시)

담당: (이름)
"""

import csv
import sys
from io import StringIO
from pathlib import Path

from minidb.engine import Engine, Result
from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.statements import Statement

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------

USAGE = "usage: python sql_processor.py <file.sql>"


def main(argv: list[str]) -> int:
    """argv: 프로그램 이름을 뺀 인자 목록. 종료 코드를 돌려준다."""
    if len(argv) != 1:
        print(USAGE, file=sys.stderr)
        return 1

    try:
        with Path(argv[0]).open(encoding=_SQL_ENCODING, newline="") as file:
            text = file.read()
    except (OSError, ValueError):
        print(f"error: cannot open {argv[0]}", file=sys.stderr)
        return 1

    try:
        statements = parse_script(text)
        _execute_statements(statements)
    except SqlError as error:
        print(error.format(), file=sys.stderr)
        return 1
    return 0


def format_result(result: Result) -> str:
    """결과 하나를 출력할 문자열로 바꾼다. 끝에 줄바꿈 포함."""
    if result.kind == "insert":
        unit = "row" if result.affected == 1 else "rows"
        return f"{result.affected} {unit} affected\n"

    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(result.columns)
    writer.writerows(
        [_format_value(value) for value in row] for row in result.rows
    )
    if not result.rows:
        output.write("(0 rows)\n")
    return output.getvalue()


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------

# 윈도우 메모장이 붙이는 BOM을 SQL로 읽지 않게 utf-8-sig로 연다.
_SQL_ENCODING = "utf-8-sig"


def _execute_statements(statements: list[Statement]) -> None:
    engine = Engine()
    failure = None
    try:
        for number, statement in enumerate(statements, start=1):
            result = engine.run(statement)
            sys.stdout.write(format_result(result))
    except SqlError as error:
        error.statement = number
        failure = error
    finally:
        try:
            engine.close()
        except SqlError:
            if failure is None:
                raise
    if failure is not None:
        raise failure


def _format_value(value: int | str) -> int | str:
    if isinstance(value, str):
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.replace("\n", r"\n")
    return value
