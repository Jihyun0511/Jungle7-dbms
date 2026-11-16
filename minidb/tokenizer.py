"""SQL 텍스트를 토큰 목록으로 바꾼다.

규칙 (노션 요구분석 번호):
- B5  키워드는 대소문자 무시 → value를 대문자로. 이름은 소문자로 바꾼다 (Users → users).
      큰따옴표 이름("Users")은 지원하지 않음 → SqlError (u11)
- B9  문자열은 작은따옴표만. '' 는 따옴표 하나. 안에 , ; ( ) 줄바꿈 허용. '' 는 빈 문자열.
      닫히지 않은 문자열은 SqlError, position은 문자열이 시작한 위치 (u6)
- B10 정수는 -5, +5, 007(→7) 허용. 3.14 는 SqlError (u7, u8)
- B1  주석: -- 줄 주석, /* */ 블록 주석은 건너뛴다. 따옴표 안은 주석이 아님.
      닫히지 않은 블록 주석은 SqlError (u9, u10)
- B4  모든 토큰에 줄·칸 위치를 넣는다. 문자열 안 줄바꿈도 줄 번호에 반영 (u3b, u12)

담당: (이름)
"""

from dataclasses import dataclass
from enum import Enum, auto

from minidb.errors import Position, SqlError  # noqa: F401  (구현할 때 사용)


class TokenType(Enum):
    KEYWORD = auto()    # value: 대문자 문자열 ("INSERT")
    NAME = auto()       # value: 소문자 문자열 ("users")
    STRING = auto()     # value: 따옴표를 벗긴 문자열 ("it's")
    INTEGER = auto()    # value: int (-5)
    STAR = auto()       # *
    COMMA = auto()      # ,
    LPAREN = auto()     # (
    RPAREN = auto()     # )
    SEMICOLON = auto()  # ;
    EQUALS = auto()     # =
    EOF = auto()        # 입력 끝. 목록의 마지막에 항상 하나


KEYWORDS = frozenset({
    "INSERT", "INTO", "VALUES", "SELECT", "FROM", "WHERE", "NULL",
})


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str | int | None   # 기호와 EOF는 None
    position: Position


def tokenize(text: str) -> list[Token]:
    """text 전체를 토큰으로 바꾼다. 마지막 토큰은 항상 EOF.

    잘못된 입력이면 SqlError (statement는 채우지 않음. 파서가 채운다).
    """
    raise NotImplementedError
