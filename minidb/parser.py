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
빈 문장(;;)은 문장 번호를 세지 않는다.
토크나이저 에러에는 문장 번호를 채우지 않는다 (몇 번째 문장인지 알 수 없음, 팀 결정).

담당: (이름)
"""

from typing import NoReturn

from minidb.errors import SqlError
from minidb.statements import Insert, Name, Select, Statement, Value, Where
from minidb.tokenizer import Token, TokenType, tokenize

SYMBOL_TEXT = {
    TokenType.STAR: "*",
    TokenType.COMMA: ",",
    TokenType.LPAREN: "(",
    TokenType.RPAREN: ")",
    TokenType.SEMICOLON: ";",
    TokenType.EQUALS: "=",
}


def parse_script(text: str) -> list[Statement]:
    """SQL 파일 내용 전체를 문장 목록으로 바꾼다. 빈 파일·주석만 있으면 [] (B2).

    SqlError를 던질 때 statement(몇 번째 문장인지)를 채운다.
    """
    tokens = tokenize(text)
    return parse(tokens)


def parse(tokens: list[Token]) -> list[Statement]:
    """토큰 목록(마지막은 EOF)을 문장 목록으로 바꾼다."""
    stream = _TokenStream(tokens)
    statements = []
    while not stream.is_type(TokenType.EOF):
        if stream.is_type(TokenType.SEMICOLON):
            stream.advance()
        else:
            number = len(statements) + 1
            statements.append(_parse_numbered_statement(stream, number))
    return statements


class _TokenStream:
    """토큰을 앞에서부터 하나씩 꺼낸다. 마지막 EOF에서는 더 나아가지 않는다."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def peek(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.tokens[self.index]
        if token.type is not TokenType.EOF:
            self.index += 1
        return token

    def is_type(self, token_type: TokenType) -> bool:
        return self.peek().type is token_type

    def is_keyword(self, word: str) -> bool:
        token = self.peek()
        return token.type is TokenType.KEYWORD and token.value == word

    def expect(self, token_type: TokenType, expected: str) -> Token:
        """다음 토큰이 token_type이면 꺼내고, 아니면 그 토큰 위치로 SqlError."""
        if not self.is_type(token_type):
            _raise_unexpected(self.peek(), expected)
        return self.advance()

    def expect_keyword(self, word: str) -> Token:
        if not self.is_keyword(word):
            _raise_unexpected(self.peek(), word)
        return self.advance()


def _raise_unexpected(token: Token, expected: str) -> NoReturn:
    found = _describe(token)
    raise SqlError(f"{expected}이(가) 와야 하는데 {found}이(가) 옴",
                   token.position)


def _describe(token: Token) -> str:
    """에러 메시지에 보여 줄 토큰 모양."""
    if token.type is TokenType.EOF:
        return "파일 끝"
    if token.type is TokenType.STRING:
        return f"문자열 '{token.value}'"
    if token.type in SYMBOL_TEXT:
        return SYMBOL_TEXT[token.type]
    return str(token.value)


def _parse_numbered_statement(stream: _TokenStream, number: int) -> Statement:
    """문장 하나를 읽고, 에러가 나면 몇 번째 문장인지 채워서 다시 던진다."""
    try:
        return _parse_statement(stream)
    except SqlError as error:
        error.statement = number
        raise


def _parse_statement(stream: _TokenStream) -> Statement:
    if stream.is_keyword("INSERT"):
        statement = _parse_insert(stream)
    elif stream.is_keyword("SELECT"):
        statement = _parse_select(stream)
    else:
        _raise_unexpected(stream.peek(), "INSERT 또는 SELECT")
    stream.expect(TokenType.SEMICOLON, "문장 끝 ;")
    return statement


def _parse_insert(stream: _TokenStream) -> Insert:
    """INSERT INTO table [(columns)] VALUES (...), (...)"""
    stream.expect_keyword("INSERT")
    stream.expect_keyword("INTO")
    table = _parse_name(stream, "테이블 이름")
    columns = None
    if stream.is_type(TokenType.LPAREN):
        columns = _parse_column_list(stream)
    stream.expect_keyword("VALUES")
    rows = [_parse_row(stream)]
    while stream.is_type(TokenType.COMMA):
        stream.advance()
        rows.append(_parse_row(stream))
    return Insert(table, columns, rows)


def _parse_name(stream: _TokenStream, expected: str) -> Name:
    token = stream.expect(TokenType.NAME, expected)
    return Name(token.value, token.position)


def _parse_column_list(stream: _TokenStream) -> list[Name]:
    """(a, b, c)"""
    stream.expect(TokenType.LPAREN, "(")
    columns = _parse_names(stream)
    stream.expect(TokenType.RPAREN, ")")
    return columns


def _parse_names(stream: _TokenStream) -> list[Name]:
    """a, b, c (쉼표로 이어진 이름 하나 이상)"""
    names = [_parse_name(stream, "컬럼 이름")]
    while stream.is_type(TokenType.COMMA):
        stream.advance()
        names.append(_parse_name(stream, "컬럼 이름"))
    return names


def _parse_row(stream: _TokenStream) -> list[Value]:
    """('a', 1, ...)"""
    stream.expect(TokenType.LPAREN, "(")
    values = [_parse_value(stream)]
    while stream.is_type(TokenType.COMMA):
        stream.advance()
        values.append(_parse_value(stream))
    stream.expect(TokenType.RPAREN, ")")
    return values


def _parse_value(stream: _TokenStream) -> Value:
    """정수 또는 문자열. NULL은 지원하지 않는다 (B10)."""
    token = stream.peek()
    if stream.is_keyword("NULL"):
        raise SqlError("NULL은 지원하지 않음", token.position)
    if token.type not in (TokenType.INTEGER, TokenType.STRING):
        _raise_unexpected(token, "값(정수 또는 '문자열')")
    stream.advance()
    return Value(token.value, token.position)


def _parse_select(stream: _TokenStream) -> Select:
    """SELECT * | a, b FROM table [WHERE column = value]"""
    stream.expect_keyword("SELECT")
    columns = None
    if stream.is_type(TokenType.STAR):
        stream.advance()
    else:
        columns = _parse_names(stream)
    stream.expect_keyword("FROM")
    table = _parse_name(stream, "테이블 이름")
    where = None
    if stream.is_keyword("WHERE"):
        where = _parse_where(stream)
    return Select(columns, table, where)


def _parse_where(stream: _TokenStream) -> Where:
    stream.expect_keyword("WHERE")
    column = _parse_name(stream, "컬럼 이름")
    stream.expect(TokenType.EQUALS, "=")
    value = _parse_value(stream)
    return Where(column, value)
