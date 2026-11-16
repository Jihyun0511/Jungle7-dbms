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

이름 규칙은 요구분석에 아직 없다. 임시로 영문자·_로 시작하고 영문자·숫자·_가
이어지는 것만 이름으로 본다 (이름이 곧 파일 이름이라 경로 문자를 막으려고).

담당: (이름)
"""

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

SYMBOLS = {
    "*": TokenType.STAR,
    ",": TokenType.COMMA,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ";": TokenType.SEMICOLON,
    "=": TokenType.EQUALS,
}

# str.isdigit()은 '²' 같은 유니코드 숫자도 참이라 int()에서 터진다
DIGITS = frozenset("0123456789")
NAME_START = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
)
NAME_PART = NAME_START | DIGITS


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str | int | None   # 기호와 EOF는 None
    position: Position


def tokenize(text: str) -> list[Token]:
    """text 전체를 토큰으로 바꾼다. 마지막 토큰은 항상 EOF.

    잘못된 입력이면 SqlError (statement는 채우지 않음. 파서가 채운다).
    """
    scanner = _Scanner(text)
    tokens = []
    while True:
        _skip_spaces_and_comments(scanner)
        token = _read_token(scanner)
        tokens.append(token)
        if token.type is TokenType.EOF:
            return tokens


class _Scanner:
    """text를 한 글자씩 읽으면서 지금 위치(줄, 칸)를 센다."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.line = 1
        self.column = 1

    @property
    def position(self) -> Position:
        return Position(self.line, self.column)

    def is_at_end(self) -> bool:
        return self.index >= len(self.text)

    def peek(self) -> str:
        """지금 글자. 끝이면 ''."""
        if self.is_at_end():
            return ""
        return self.text[self.index]

    def starts_with(self, prefix: str) -> bool:
        return self.text.startswith(prefix, self.index)

    def advance(self) -> str:
        """지금 글자를 돌려주고 한 칸 나아간다. 줄바꿈이면 다음 줄 1칸으로."""
        char = self.text[self.index]
        self.index += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char


def _skip_spaces_and_comments(scanner: _Scanner) -> None:
    while True:
        if scanner.peek().isspace():
            scanner.advance()
        elif scanner.starts_with("--"):
            _skip_line_comment(scanner)
        elif scanner.starts_with("/*"):
            _skip_block_comment(scanner)
        else:
            return


def _skip_line_comment(scanner: _Scanner) -> None:
    while not scanner.is_at_end() and scanner.peek() != "\n":
        scanner.advance()


def _skip_block_comment(scanner: _Scanner) -> None:
    """닫히지 않으면 주석이 시작한 위치로 SqlError."""
    start = scanner.position
    scanner.advance()
    scanner.advance()
    while not scanner.starts_with("*/"):
        if scanner.is_at_end():
            raise SqlError("블록 주석 /* 가 닫히지 않음", start)
        scanner.advance()
    scanner.advance()
    scanner.advance()


def _read_token(scanner: _Scanner) -> Token:
    position = scanner.position
    char = scanner.peek()
    if scanner.is_at_end():
        return Token(TokenType.EOF, None, position)
    if char in SYMBOLS:
        scanner.advance()
        return Token(SYMBOLS[char], None, position)
    if char == "'":
        return _read_string(scanner)
    if char in DIGITS or char in ("+", "-"):
        return _read_integer(scanner)
    if char in NAME_START:
        return _read_word(scanner)
    if char == '"':
        raise SqlError("큰따옴표 이름은 지원하지 않음", position)
    raise SqlError(f"모르는 글자 {char!r}", position)


def _read_string(scanner: _Scanner) -> Token:
    """'' 는 따옴표 하나로 읽는다. 닫히지 않으면 시작 위치로 SqlError."""
    start = scanner.position
    scanner.advance()
    characters = []
    while True:
        if scanner.is_at_end():
            raise SqlError("문자열이 닫히지 않음", start)
        char = scanner.advance()
        if char != "'":
            characters.append(char)
        elif scanner.peek() == "'":
            characters.append(scanner.advance())
        else:
            return Token(TokenType.STRING, "".join(characters), start)


def _read_integer(scanner: _Scanner) -> Token:
    """부호(+, -)는 하나까지. 소수점이나 글자가 바로 붙으면 SqlError."""
    start = scanner.position
    text = ""
    if scanner.peek() in ("+", "-"):
        text += scanner.advance()
    while scanner.peek() in DIGITS:
        text += scanner.advance()
    _check_integer_end(scanner, text, start)
    return Token(TokenType.INTEGER, int(text), start)


def _check_integer_end(scanner: _Scanner, text: str, start: Position) -> None:
    if text in ("", "+", "-"):
        raise SqlError(f"{text} 다음에 숫자가 와야 함", start)
    if scanner.peek() == ".":
        raise SqlError("소수는 지원하지 않음 (int만 가능)", start)
    if scanner.peek() in NAME_PART:
        raise SqlError(f"숫자 {text} 바로 뒤에 글자가 붙음", start)


def _read_word(scanner: _Scanner) -> Token:
    """키워드면 대문자로, 아니면 이름으로 보고 소문자로 바꾼다 (B5)."""
    start = scanner.position
    word = ""
    while scanner.peek() in NAME_PART:
        word += scanner.advance()
    if word.upper() in KEYWORDS:
        return Token(TokenType.KEYWORD, word.upper(), start)
    return Token(TokenType.NAME, word.lower(), start)
