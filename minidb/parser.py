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

from collections.abc import Callable, Iterable
from typing import NoReturn, TypeVar, cast

from minidb.errors import SqlError
from minidb.statements import Insert, Name, Select, Statement, Value, Where
from minidb.tokenizer import Token, TokenType, iter_tokens

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------


def parse_script(text: str) -> list[Statement]:
    """SQL 파일 내용 전체를 문장 목록으로 바꾼다. 빈 파일·주석만 있으면 [] (B2).

    SqlError를 던질 때 statement(몇 번째 문장인지)를 채운다.
    토크나이저 에러도 토큰을 하나씩 받으며 세므로 문장 번호가 붙는다.
    """
    return _parse_script_tokens(iter_tokens(text))


def parse(tokens: list[Token]) -> list[Statement]:
    """토큰 목록(마지막은 EOF)을 문장 목록으로 바꾼다."""
    return _parse_script_tokens(tokens)


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------

_SYMBOL_TEXT = {
    TokenType.STAR: "*",
    TokenType.COMMA: ",",
    TokenType.LPAREN: "(",
    TokenType.RPAREN: ")",
    TokenType.SEMICOLON: ";",
    TokenType.EQUALS: "=",
}

_Item = TypeVar("_Item")


def _parse_script_tokens(tokens: Iterable[Token]) -> list[Statement]:
    statements = []
    current = []
    try:
        for token in tokens:
            current.append(token)
            if _is_statement_end(token):
                statements.extend(_parse_collected(current))
                current = []
    except SqlError as error:
        error.statement = len(statements) + 1
        raise
    return statements


def _is_statement_end(token: Token) -> bool:
    return token.type in (TokenType.SEMICOLON, TokenType.EOF)


def _parse_collected(tokens: list[Token]) -> list[Statement]:
    # 끝 토큰 하나만 있으면 빈 문장(;;)이나 파일 끝이라 건너뛴다 (p6).
    if len(tokens) == 1:
        return []
    return [_StatementParser(tokens).parse()]


class _StatementParser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def parse(self) -> Statement:
        if self._take(TokenType.KEYWORD, "INSERT"):
            statement = self._insert()
        elif self._take(TokenType.KEYWORD, "SELECT"):
            statement = self._select()
        else:
            _raise_unexpected(self.current, "INSERT or SELECT")
        self._expect(TokenType.SEMICOLON, "';'")
        return statement

    def _take(self, kind: TokenType, value: str | None = None) -> Token | None:
        token = self.current
        if token.type == kind and (value is None or token.value == value):
            self.index += 1
            return token
        return None

    def _expect(
        self, kind: TokenType, label: str, value: str | None = None,
    ) -> Token:
        token = self._take(kind, value)
        if token is None:
            _raise_unexpected(self.current, label)
        return token

    def _insert(self) -> Insert:
        self._expect(TokenType.KEYWORD, "INTO", "INTO")
        table = self._name()
        columns = None
        if self._take(TokenType.LPAREN):
            columns = self._comma_list(self._name)
            self._expect(TokenType.RPAREN, "')'")
        self._expect(TokenType.KEYWORD, "VALUES", "VALUES")
        return Insert(table, columns, self._comma_list(self._row))

    def _name(self) -> Name:
        token = self._expect(TokenType.NAME, "table or column name")
        return Name(cast(str, token.value), token.position)

    def _comma_list(self, read_item: Callable[[], _Item]) -> list[_Item]:
        items = [read_item()]
        while self._take(TokenType.COMMA):
            items.append(read_item())
        return items

    def _row(self) -> list[Value]:
        self._expect(TokenType.LPAREN, "'('")
        values = self._comma_list(self._value)
        self._expect(TokenType.RPAREN, "')'")
        return values

    def _value(self) -> Value:
        token = self.current
        if token.type in (TokenType.INTEGER, TokenType.STRING):
            self.index += 1
            return Value(cast(int | str, token.value), token.position)
        if token.type == TokenType.KEYWORD and token.value == "NULL":
            raise SqlError("NULL is not supported", token.position)
        _raise_unexpected(token, "a value (integer or 'string')")

    def _select(self) -> Select:
        columns = None
        if not self._take(TokenType.STAR):
            columns = self._comma_list(self._name)
        self._expect(TokenType.KEYWORD, "FROM", "FROM")
        table = self._name()
        where = None
        if self._take(TokenType.KEYWORD, "WHERE"):
            column = self._name()
            self._expect(TokenType.EQUALS, "'='")
            where = Where(column, self._value())
        return Select(columns, table, where)


def _raise_unexpected(token: Token, expected: str) -> NoReturn:
    raise SqlError(
        f"expected {expected} but got {_describe(token)}", token.position,
    )


def _describe(token: Token) -> str:
    if token.type == TokenType.EOF:
        return "end of file"
    if token.type == TokenType.KEYWORD:
        return f"keyword {token.value}"
    if token.type == TokenType.NAME:
        return f"name {token.value}"
    if token.type == TokenType.STRING:
        return f"string '{token.value}'"
    if token.type == TokenType.INTEGER:
        return f"integer {token.value}"
    return f"'{_SYMBOL_TEXT[token.type]}'"
