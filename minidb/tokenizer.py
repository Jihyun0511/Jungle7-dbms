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
        _skip_blanks_and_comments(scanner)
        token = _read_token(scanner)
        tokens.append(token)
        if token.type is TokenType.EOF:
            return tokens


class _Scanner:
    """읽는 자리와 그 자리의 줄·칸을 함께 들고 다닌다."""

    def __init__(self, text: str):
        self.text = text
        self.index = 0
        self.line = 1
        self.column = 1

    @property
    def position(self) -> Position:
        return Position(self.line, self.column)

    def is_at_end(self) -> bool:
        return self.index >= len(self.text)

    def has_prefix(self, prefix: str) -> bool:
        return self.text.startswith(prefix, self.index)

    def peek(self, offset: int = 0) -> str:
        """offset 뒤의 글자. 입력 끝을 넘으면 빈 문자열."""
        index = self.index + offset
        if index >= len(self.text):
            return ""
        return self.text[index]

    def advance(self) -> str:
        char = self.text[self.index]
        self.index += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char


def _skip_blanks_and_comments(scanner: _Scanner) -> None:
    while True:
        if scanner.peek().isspace():
            scanner.advance()
        elif scanner.has_prefix("--"):
            _skip_line_comment(scanner)
        elif scanner.has_prefix("/*"):
            _skip_block_comment(scanner)
        else:
            return


def _skip_line_comment(scanner: _Scanner) -> None:
    while not scanner.is_at_end() and scanner.peek() != "\n":
        scanner.advance()


def _skip_block_comment(scanner: _Scanner) -> None:
    start = scanner.position
    scanner.advance()
    scanner.advance()
    while not scanner.has_prefix("*/"):
        if scanner.is_at_end():
            raise SqlError("블록 주석 /* 가 닫히지 않음", start)
        scanner.advance()
    scanner.advance()
    scanner.advance()


def _read_token(scanner: _Scanner) -> Token:
    position = scanner.position
    if scanner.is_at_end():
        return Token(TokenType.EOF, None, position)
    char = scanner.peek()
    if char in _SYMBOLS:
        scanner.advance()
        return Token(_SYMBOLS[char], None, position)
    if char == "'":
        return _read_string(scanner)
    if char == '"':
        raise SqlError('큰따옴표 이름("...")은 지원하지 않음', position)
    if _is_number_start(scanner):
        return _read_integer(scanner)
    if _is_word_start(char):
        return _read_word(scanner)
    raise SqlError(f"알 수 없는 글자 {char}", position)


def _read_string(scanner: _Scanner) -> Token:
    """여는 따옴표에서 시작한다. 에러 위치는 여는 따옴표 자리 (u6)."""
    start = scanner.position
    scanner.advance()
    chars = []
    while True:
        if scanner.is_at_end():
            raise SqlError("작은따옴표 문자열이 닫히지 않음", start)
        char = scanner.advance()
        if char != "'":
            chars.append(char)
        elif scanner.peek() == "'":
            chars.append(scanner.advance())
        else:
            return Token(TokenType.STRING, "".join(chars), start)


def _is_number_start(scanner: _Scanner) -> bool:
    char = scanner.peek()
    if char in ("+", "-"):
        return _is_digit(scanner.peek(1))
    return _is_digit(char)


def _is_digit(char: str) -> bool:
    # str.isdigit()은 '²' 같은 글자도 참이라 int()가 실패하므로 ASCII만 본다.
    return char != "" and "0" <= char <= "9"


def _read_integer(scanner: _Scanner) -> Token:
    start = scanner.position
    chars = [scanner.advance()]
    while _is_digit(scanner.peek()):
        chars.append(scanner.advance())
    if scanner.peek() == ".":
        raise SqlError("소수는 지원하지 않음 (정수만 가능)", start)
    if _is_word_char(scanner.peek()):
        raise SqlError("숫자 뒤에 글자가 붙어 있음", start)
    return Token(TokenType.INTEGER, _convert_integer(chars, start), start)


def _convert_integer(chars: list[str], start: Position) -> int:
    try:
        return int("".join(chars))
    except ValueError as error:
        # 파이썬은 4300자리가 넘는 정수 변환을 막는다.
        raise SqlError("정수가 너무 김", start) from error


def _is_word_start(char: str) -> bool:
    return char.isalpha() or char == "_"


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def _read_word(scanner: _Scanner) -> Token:
    start = scanner.position
    chars = []
    while _is_word_char(scanner.peek()):
        chars.append(scanner.advance())
    word = "".join(chars)
    if word.upper() in KEYWORDS:
        return Token(TokenType.KEYWORD, word.upper(), start)
    return Token(TokenType.NAME, word.lower(), start)
