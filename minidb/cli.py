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

import sys  # noqa: F401  (구현할 때 사용)

from minidb.engine import Engine, Result  # noqa: F401
from minidb.errors import SqlError  # noqa: F401
from minidb.parser import parse_script  # noqa: F401

USAGE = "usage: python sql_processor.py <file.sql>"


def main(argv: list[str]) -> int:
    """argv: 프로그램 이름을 뺀 인자 목록. 종료 코드를 돌려준다."""
    raise NotImplementedError


def format_result(result: Result) -> str:
    """결과 하나를 출력할 문자열로 바꾼다. 끝에 줄바꿈 포함."""
    raise NotImplementedError
