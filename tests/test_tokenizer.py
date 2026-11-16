"""토크나이저 단위 테스트 (R-Q1). 노션 5절 u1~u12."""

import pytest

from minidb.errors import Position, SqlError
from minidb.tokenizer import TokenType, tokenize


def _values(text):
    return [(token.type, token.value) for token in tokenize(text)[:-1]]


def test_u1_keywords_ignore_case():
    """insert, InSeRt → 둘 다 KEYWORD 'INSERT' (B5)"""
    assert _values("insert InSeRt") == [
        (TokenType.KEYWORD, "INSERT"),
        (TokenType.KEYWORD, "INSERT"),
    ]


def test_u2_names_become_lowercase():
    """Users → NAME 'users' (B5)"""
    assert _values("Users") == [(TokenType.NAME, "users")]


def test_u3a_string_with_symbols_is_one_token():
    """'a, b; (c)' → STRING 'a, b; (c)' 하나 (B9)"""
    assert _values("'a, b; (c)'") == [(TokenType.STRING, "a, b; (c)")]


def test_u3b_string_with_newline_is_one_token():
    """'첫줄\\n둘째줄' → STRING 하나. 다음 토큰의 줄 번호가 하나 늘어남 (B9)"""
    tokens = tokenize("'첫줄\n둘째줄' x")
    assert (tokens[0].type, tokens[0].value) == (
        TokenType.STRING, "첫줄\n둘째줄",
    )
    assert tokens[1].position == Position(2, 6)


def test_u4_doubled_quote_is_one_quote():
    """'it''s' → it's (B9)"""
    assert _values("'it''s'") == [(TokenType.STRING, "it's")]


def test_u5_empty_string():
    """'' → STRING '' (B9)"""
    assert _values("''") == [(TokenType.STRING, "")]


def test_u6_unclosed_string_is_error():
    """'yena, 24); → SqlError, position은 문자열 시작 위치 (B9)"""
    with pytest.raises(SqlError) as caught:
        tokenize("VALUES ('yena, 24);")
    assert caught.value.position == Position(1, 9)


def test_u7_integers():
    """-5, +5, 007 → INTEGER -5, 5, 7 (B10)"""
    assert _values("-5, +5, 007") == [
        (TokenType.INTEGER, -5),
        (TokenType.COMMA, None),
        (TokenType.INTEGER, 5),
        (TokenType.COMMA, None),
        (TokenType.INTEGER, 7),
    ]


def test_u8_decimal_is_error():
    """3.14 → SqlError (B10)"""
    with pytest.raises(SqlError):
        tokenize("3.14")


def test_u9_comments_are_skipped():
    """-- 주석, /* 주석 */ 은 건너뛰고 'a -- b'는 STRING (B1)"""
    text = "-- 주석\n/* 여러\n줄 주석 */ 'a -- b' /* x */"
    assert _values(text) == [(TokenType.STRING, "a -- b")]


def test_u10_unclosed_block_comment_is_error():
    """/* 닫히지 않음 → SqlError (B1)"""
    with pytest.raises(SqlError) as caught:
        tokenize("SELECT /* 닫히지 않음")
    assert caught.value.position == Position(1, 8)


def test_u11_double_quoted_name_is_error():
    """"Users" → SqlError (B5)"""
    with pytest.raises(SqlError):
        tokenize('SELECT * FROM "Users";')


def test_u12_positions_over_lines():
    """여러 줄 입력에서 토큰마다 줄·칸 위치가 맞음 (B4)"""
    tokens = tokenize("SELECT *\n  FROM users;")
    assert [token.position for token in tokens] == [
        Position(1, 1),
        Position(1, 8),
        Position(2, 3),
        Position(2, 8),
        Position(2, 13),
        Position(2, 14),
    ]
    assert tokens[-1].type is TokenType.EOF
