"""토큰 목록을 문장 구조(statements.py)로 바꾼다.

규칙 (노션 요구분석 번호):
- B1  ; 로 문장을 나눈다. 마지막 문장에도 ; 필수 (없으면 SqlError, p5). 빈 문장 ;; 은 무시 (p6)
- B6  INSERT INTO t VALUES (...), (...);  /  INSERT INTO t (a, b) VALUES (...);
- B7  SELECT * FROM t;  /  SELECT a, b FROM t;
- B8  WHERE column = value 하나
- B10 NULL 키워드는 문법 에러 (p7)
- B4  문법 에러에는 위치를 넣는다 (p8)
- B17 파일 전체를 먼저 파싱한다. 문법 에러가 하나라도 있으면 한 문장도 실행하지 않음

파서는 "모양"만 본다. 테이블이 있는지, 값 개수·타입이 맞는지는 엔진이 본다.

담당: (이름)
"""

from minidb.errors import SqlError  # noqa: F401  (구현할 때 사용)
from minidb.statements import Statement
from minidb.tokenizer import Token, tokenize  # noqa: F401


def parse_script(text: str) -> list[Statement]:
    """SQL 파일 내용 전체를 문장 목록으로 바꾼다. 빈 파일·주석만 있으면 [] (B2).

    SqlError를 던질 때 statement(몇 번째 문장인지)를 채운다.
    """
    raise NotImplementedError


def parse(tokens: list[Token]) -> list[Statement]:
    """토큰 목록(마지막은 EOF)을 문장 목록으로 바꾼다."""
    raise NotImplementedError
