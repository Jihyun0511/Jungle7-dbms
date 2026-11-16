"""토크나이저 단위 테스트 (R-Q1). 노션 5절 u1~u12.

작성한 테스트는 @TODO를 지운다.
"""

import pytest

from minidb.errors import Position, SqlError
from minidb.tokenizer import TokenType, tokenize


def test_u1_keywords_ignore_case():
    """insert, InSeRt → 둘 다 KEYWORD 'INSERT' (B5)"""
    for text in ("insert", "InSeRt"):
        token = tokenize(text)[0]
        assert token.type is TokenType.KEYWORD
        assert token.value == "INSERT"


def test_u2_names_become_lowercase():
    """Users → NAME 'users' (B5)"""
    token = tokenize("Users")[0]
    assert token.type is TokenType.NAME
    assert token.value == "users"


def test_u3a_string_with_symbols_is_one_token():
    """'a, b; (c)' → STRING 'a, b; (c)' 하나 (B9)"""
    tokens = tokenize("'a, b; (c)'")
    assert [token.type for token in tokens] == [
        TokenType.STRING, TokenType.EOF,
    ]
    assert tokens[0].value == "a, b; (c)"


def test_u3b_string_with_newline_is_one_token():
    """'첫줄\\n둘째줄' → STRING 하나. 다음 토큰의 줄 번호가 하나 늘어남 (B9)"""
    tokens = tokenize("'첫줄\n둘째줄' x")
    assert tokens[0].type is TokenType.STRING
    assert tokens[0].value == "첫줄\n둘째줄"
    assert tokens[1].position == Position(2, 6)


def test_u4_doubled_quote_is_one_quote():
    """'it''s' → it's (B9)"""
    assert tokenize("'it''s'")[0].value == "it's"


def test_u5_empty_string():
    """'' → STRING '' (B9)"""
    token = tokenize("''")[0]
    assert token.type is TokenType.STRING
    assert token.value == ""


def test_u6_unclosed_string_is_error():
    """'yena, 24); → SqlError, position은 문자열 시작 위치 (B9)"""
    with pytest.raises(SqlError) as error:
        tokenize("VALUES ('yena, 24);")
    assert error.value.position == Position(1, 9)


def test_u7_integers():
    """-5, +5, 007 → INTEGER -5, 5, 7 (B10)"""
    tokens = tokenize("-5 +5 007")[:-1]
    assert [token.type for token in tokens] == [TokenType.INTEGER] * 3
    assert [token.value for token in tokens] == [-5, 5, 7]


def test_u8_decimal_is_error():
    """3.14 → SqlError (B10)"""
    with pytest.raises(SqlError):
        tokenize("3.14")


def test_u9_comments_are_skipped():
    """-- 주석, /* 주석 */ 은 건너뛰고 'a -- b'는 STRING (B1)"""
    tokens = tokenize("-- 주석\n/* 여러\n줄 주석 */ 'a -- b'")
    assert [token.type for token in tokens] == [
        TokenType.STRING, TokenType.EOF,
    ]
    assert tokens[0].value == "a -- b"
    assert tokens[0].position == Position(3, 9)


def test_u10_unclosed_block_comment_is_error():
    """/* 닫히지 않음 → SqlError (B1)"""
    with pytest.raises(SqlError) as error:
        tokenize("SELECT /* 닫히지 않음")
    assert error.value.position == Position(1, 8)


def test_u11_double_quoted_name_is_error():
    """"Users" → SqlError (B5)"""
    with pytest.raises(SqlError):
        tokenize('"Users"')


def test_u12_positions_over_lines():
    """여러 줄 입력에서 토큰마다 줄·칸 위치가 맞음 (B4)"""
    tokens = tokenize("SELECT name\n  FROM users;")
    assert [token.position for token in tokens] == [
        Position(1, 1),   # SELECT
        Position(1, 8),   # name
        Position(2, 3),   # FROM
        Position(2, 8),   # users
        Position(2, 13),  # ;
        Position(2, 14),  # EOF
    ]
