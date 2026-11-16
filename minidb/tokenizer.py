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

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from minidb.errors import Position, SqlError


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

_SYMBOLS = {
    "*": TokenType.STAR,
    ",": TokenType.COMMA,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ";": TokenType.SEMICOLON,
    "=": TokenType.EQUALS,
}
_WHITESPACE = re.compile(r"\s+")
_LINE_COMMENT = re.compile(r"--[^\r\n]*")
_INTEGER = re.compile(r"[+-]?[0-9]+")


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str | int | None   # 기호와 EOF는 None
    position: Position


def _read_string(text: str, start: int, position: Position) -> tuple[str, int]:
    parts = []
    offset = start + 1
    while (quote := text.find("'", offset)) != -1:
        parts.append(text[offset:quote])
        if not text.startswith("''", quote):
            return "".join(parts), quote + 1
        parts.append("'")
        offset = quote + 2
    raise SqlError("문자열이 닫히지 않음", position)


def tokenize(text: str) -> list[Token]:
    """text 전체를 토큰으로 바꾼다. 마지막 토큰은 항상 EOF.

    잘못된 입력이면 SqlError (statement는 채우지 않음. 파서가 채운다).
    """
    return list(iter_tokens(text))


def iter_tokens(text: str) -> Iterator[Token]:
    """토큰을 순서대로 넘겨 파서가 어휘 오류의 문장 번호를 알 수 있게 한다."""
    offset = 0
    line = column = 1

    def advance(end: int) -> None:
        nonlocal offset, line, column
        consumed = text[offset:end].replace("\r\n", "\n").replace("\r", "\n")
        newlines = consumed.count("\n")
        if newlines:
            line += newlines
            column = len(consumed) - consumed.rfind("\n")
        else:
            column += len(consumed)
        offset = end

    while offset < len(text):
        if whitespace := _WHITESPACE.match(text, offset):
            advance(whitespace.end())
            continue
        if comment := _LINE_COMMENT.match(text, offset):
            advance(comment.end())
            continue

        position = Position(line, column)
        if text.startswith("/*", offset):
            closing = text.find("*/", offset + 2)
            if closing == -1:
                raise SqlError("블록 주석이 닫히지 않음", position)
            advance(closing + 2)
            continue

        char = text[offset]
        if char in _SYMBOLS:
            token_type, value, end = _SYMBOLS[char], None, offset + 1
        elif char == "'":
            value, end = _read_string(text, offset, position)
            token_type = TokenType.STRING
        elif char == '"':
            raise SqlError("큰따옴표로 감싼 이름은 지원하지 않음", position)
        elif char.isalpha() or char == "_":
            end = offset + 1
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            name = text[offset:end]
            keyword = name.upper()
            if keyword in KEYWORDS:
                token_type, value = TokenType.KEYWORD, keyword
            else:
                token_type, value = TokenType.NAME, name.lower()
        elif integer := _INTEGER.match(text, offset):
            end = integer.end()
            if text.startswith(".", end):
                raise SqlError("숫자 리터럴은 정수만 지원함", position)
            try:
                value = int(integer[0])
            except ValueError as error:
                raise SqlError("정수 리터럴을 읽을 수 없음", position) from error
            token_type = TokenType.INTEGER
        else:
            raise SqlError(f"알 수 없는 문자 {char!r}", position)

        yield Token(token_type, value, position)
        advance(end)

    yield Token(TokenType.EOF, None, Position(line, column))
