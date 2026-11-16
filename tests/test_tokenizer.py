"""토크나이저 단위 테스트 (R-Q1). 노션 5절 u1~u12."""

import pytest

from minidb.errors import Position, SqlError
from minidb.tokenizer import Token, TokenType, tokenize


def test_u1_keywords_ignore_case():
    tokens = tokenize("insert InSeRt")
    assert [(token.type, token.value) for token in tokens] == [
        (TokenType.KEYWORD, "INSERT"),
        (TokenType.KEYWORD, "INSERT"),
        (TokenType.EOF, None),
    ]


def test_u2_names_become_lowercase():
    assert tokenize("Users")[0] == Token(TokenType.NAME, "users", Position(1, 1))


def test_u3a_string_with_symbols_is_one_token():
    assert tokenize("'a, b; (c)'") == [
        Token(TokenType.STRING, "a, b; (c)", Position(1, 1)),
        Token(TokenType.EOF, None, Position(1, 12)),
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_u3b_string_with_newline_is_one_token(newline):
    value = f"첫줄{newline}둘째줄"
    assert tokenize(f"'{value}';") == [
        Token(TokenType.STRING, value, Position(1, 1)),
        Token(TokenType.SEMICOLON, None, Position(2, 5)),
        Token(TokenType.EOF, None, Position(2, 6)),
    ]


def test_u4_doubled_quote_is_one_quote():
    assert tokenize("'it''s'")[0] == Token(TokenType.STRING, "it's", Position(1, 1))


def test_u5_empty_string():
    assert tokenize("''")[0] == Token(TokenType.STRING, "", Position(1, 1))


def test_u6_unclosed_string_is_error():
    with pytest.raises(SqlError) as error:
        tokenize("\n  'yena, 24);")
    assert error.value.position == Position(2, 3)
    assert error.value.statement is None


def test_u7_integers():
    assert [(token.type, token.value) for token in tokenize("-5, +5, 007")] == [
        (TokenType.INTEGER, -5),
        (TokenType.COMMA, None),
        (TokenType.INTEGER, 5),
        (TokenType.COMMA, None),
        (TokenType.INTEGER, 7),
        (TokenType.EOF, None),
    ]


def test_u8_decimal_is_error():
    with pytest.raises(SqlError) as error:
        tokenize("3.14")
    assert error.value.position == Position(1, 1)


def test_u9_comments_are_skipped():
    tokens = tokenize("-- 주석 ;\r\n/* 블록\r\n주석 */ 'a -- b /* c */'; -- 끝")
    assert tokens[:-1] == [
        Token(TokenType.STRING, "a -- b /* c */", Position(3, 7)),
        Token(TokenType.SEMICOLON, None, Position(3, 23)),
    ]
    assert tokens[-1].type == TokenType.EOF
    assert tokenize("-- 주석") == [Token(TokenType.EOF, None, Position(1, 6))]


def test_u10_unclosed_block_comment_is_error():
    with pytest.raises(SqlError) as error:
        tokenize("SELECT /* 닫히지 않음")
    assert error.value.position == Position(1, 8)


def test_u11_double_quoted_name_is_error():
    with pytest.raises(SqlError) as error:
        tokenize('FROM "Users"')
    assert error.value.position == Position(1, 6)


def test_u12_positions_over_lines():
    assert tokenize("SELECT *\nFROM Users\nWHERE (id = 7);\n") == [
        Token(TokenType.KEYWORD, "SELECT", Position(1, 1)),
        Token(TokenType.STAR, None, Position(1, 8)),
        Token(TokenType.KEYWORD, "FROM", Position(2, 1)),
        Token(TokenType.NAME, "users", Position(2, 6)),
        Token(TokenType.KEYWORD, "WHERE", Position(3, 1)),
        Token(TokenType.LPAREN, None, Position(3, 7)),
        Token(TokenType.NAME, "id", Position(3, 8)),
        Token(TokenType.EQUALS, None, Position(3, 11)),
        Token(TokenType.INTEGER, 7, Position(3, 13)),
        Token(TokenType.RPAREN, None, Position(3, 14)),
        Token(TokenType.SEMICOLON, None, Position(3, 15)),
        Token(TokenType.EOF, None, Position(4, 1)),
    ]
