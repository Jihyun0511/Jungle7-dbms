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

from collections.abc import Callable
from typing import TypeVar

from minidb.errors import SqlError
from minidb.statements import Insert, Name, Select, Statement, Value, Where
from minidb.tokenizer import Token, TokenType, tokenize

_SYMBOL_TEXT = {
    TokenType.STAR: "*",
    TokenType.COMMA: ",",
    TokenType.LPAREN: "(",
    TokenType.RPAREN: ")",
    TokenType.SEMICOLON: ";",
    TokenType.EQUALS: "=",
}

_Item = TypeVar("_Item")


def parse_script(text: str) -> list[Statement]:
    """SQL 파일 내용 전체를 문장 목록으로 바꾼다. 빈 파일·주석만 있으면 [] (B2).

    SqlError를 던질 때 statement(몇 번째 문장인지)를 채운다.
    토크나이저 에러는 아직 문장을 나누기 전이라 statement가 None이다.
    """
    return parse(tokenize(text))


def parse(tokens: list[Token]) -> list[Statement]:
    """토큰 목록(마지막은 EOF)을 문장 목록으로 바꾼다.

    빈 문장(;;)은 번호를 세지 않는다. 그래야 CLI의 문장 번호와 맞는다.
    """
    parser = _Parser(tokens)
    statements = []
    while True:
        parser.skip_semicolons()
        if parser.is_at_end():
            return statements
        number = len(statements) + 1
        statements.append(_parse_numbered_statement(parser, number))


class _Parser:
    """토큰 목록과 지금 보고 있는 자리."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def peek(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.tokens[self.index]
        if token.type is not TokenType.EOF:
            self.index += 1
        return token

    def is_at_end(self) -> bool:
        return self.peek().type is TokenType.EOF

    def is_type(self, token_type: TokenType) -> bool:
        return self.peek().type is token_type

    def is_keyword(self, word: str) -> bool:
        token = self.peek()
        return token.type is TokenType.KEYWORD and token.value == word

    def skip_semicolons(self) -> None:
        while self.is_type(TokenType.SEMICOLON):
            self.advance()

    def expect(self, token_type: TokenType, label: str) -> Token:
        if not self.is_type(token_type):
            raise _create_unexpected_error(self.peek(), label)
        return self.advance()

    def expect_keyword(self, word: str) -> Token:
        if not self.is_keyword(word):
            raise _create_unexpected_error(self.peek(), word)
        return self.advance()


def _create_unexpected_error(token: Token, label: str) -> SqlError:
    return SqlError(
        f"{label}가 와야 하는 자리에 {_describe(token)}가 있음",
        token.position,
    )


def _describe(token: Token) -> str:
    if token.type is TokenType.EOF:
        return "파일 끝"
    if token.type is TokenType.STRING:
        return f"문자열 '{token.value}'"
    if token.type is TokenType.INTEGER:
        return f"정수 {token.value}"
    if token.type is TokenType.KEYWORD:
        return f"키워드 {token.value}"
    if token.type is TokenType.NAME:
        return f"이름 {token.value}"
    return f"'{_SYMBOL_TEXT[token.type]}'"


def _parse_numbered_statement(parser: _Parser, number: int) -> Statement:
    try:
        statement = _parse_statement(parser)
        parser.expect(TokenType.SEMICOLON, ";")
    except SqlError as error:
        error.statement = number
        raise
    return statement


def _parse_statement(parser: _Parser) -> Statement:
    if parser.is_keyword("INSERT"):
        return _parse_insert(parser)
    if parser.is_keyword("SELECT"):
        return _parse_select(parser)
    token = parser.peek()
    raise SqlError(
        f"INSERT나 SELECT로 시작해야 하는데 {_describe(token)}가 있음",
        token.position,
    )


def _parse_insert(parser: _Parser) -> Insert:
    parser.expect_keyword("INSERT")
    parser.expect_keyword("INTO")
    table = _parse_name(parser)
    columns = None
    if parser.is_type(TokenType.LPAREN):
        columns = _parse_name_list(parser)
    parser.expect_keyword("VALUES")
    rows = _parse_comma_list(parser, _parse_row)
    return Insert(table, columns, rows)


def _parse_name(parser: _Parser) -> Name:
    token = parser.expect(TokenType.NAME, "이름")
    return Name(token.value, token.position)


def _parse_name_list(parser: _Parser) -> list[Name]:
    parser.expect(TokenType.LPAREN, "(")
    names = _parse_comma_list(parser, _parse_name)
    parser.expect(TokenType.RPAREN, ")")
    return names


def _parse_comma_list(
    parser: _Parser, parse_item: Callable[[_Parser], _Item],
) -> list[_Item]:
    items = [parse_item(parser)]
    while parser.is_type(TokenType.COMMA):
        parser.advance()
        items.append(parse_item(parser))
    return items


def _parse_row(parser: _Parser) -> list[Value]:
    parser.expect(TokenType.LPAREN, "(")
    values = _parse_comma_list(parser, _parse_value)
    parser.expect(TokenType.RPAREN, ")")
    return values


def _parse_value(parser: _Parser) -> Value:
    token = parser.peek()
    if parser.is_keyword("NULL"):
        raise SqlError("NULL은 지원하지 않음", token.position)
    if token.type not in (TokenType.STRING, TokenType.INTEGER):
        raise _create_unexpected_error(token, "값")
    parser.advance()
    return Value(token.value, token.position)


def _parse_select(parser: _Parser) -> Select:
    parser.expect_keyword("SELECT")
    columns = _parse_select_columns(parser)
    parser.expect_keyword("FROM")
    table = _parse_name(parser)
    where = None
    if parser.is_keyword("WHERE"):
        where = _parse_where(parser)
    return Select(columns, table, where)


def _parse_select_columns(parser: _Parser) -> list[Name] | None:
    """SELECT * 이면 None."""
    if parser.is_type(TokenType.STAR):
        parser.advance()
        return None
    return _parse_comma_list(parser, _parse_name)


def _parse_where(parser: _Parser) -> Where:
    parser.expect_keyword("WHERE")
    column = _parse_name(parser)
    parser.expect(TokenType.EQUALS, "=")
    value = _parse_value(parser)
    return Where(column, value)
