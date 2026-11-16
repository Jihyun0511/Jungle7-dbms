"""토크나이저 단위 테스트 (R-Q1). 노션 5절 u1~u12.

작성한 테스트는 @TODO를 지운다.
"""

import pytest

from minidb.tokenizer import TokenType, tokenize  # noqa: F401

TODO = pytest.mark.skip(reason="아직 작성하지 않음")


@TODO
def test_u1_keywords_ignore_case():
    """insert, InSeRt → 둘 다 KEYWORD 'INSERT' (B5)"""


@TODO
def test_u2_names_become_lowercase():
    """Users → NAME 'users' (B5)"""


@TODO
def test_u3a_string_with_symbols_is_one_token():
    """'a, b; (c)' → STRING 'a, b; (c)' 하나 (B9)"""


@TODO
def test_u3b_string_with_newline_is_one_token():
    """'첫줄\\n둘째줄' → STRING 하나. 다음 토큰의 줄 번호가 하나 늘어남 (B9)"""


@TODO
def test_u4_doubled_quote_is_one_quote():
    """'it''s' → it's (B9)"""


@TODO
def test_u5_empty_string():
    """'' → STRING '' (B9)"""


@TODO
def test_u6_unclosed_string_is_error():
    """'yena, 24); → SqlError, position은 문자열 시작 위치 (B9)"""


@TODO
def test_u7_integers():
    """-5, +5, 007 → INTEGER -5, 5, 7 (B10)"""


@TODO
def test_u8_decimal_is_error():
    """3.14 → SqlError (B10)"""


@TODO
def test_u9_comments_are_skipped():
    """-- 주석, /* 주석 */ 은 건너뛰고 'a -- b'는 STRING (B1)"""


@TODO
def test_u10_unclosed_block_comment_is_error():
    """/* 닫히지 않음 → SqlError (B1)"""


@TODO
def test_u11_double_quoted_name_is_error():
    """"Users" → SqlError (B5)"""


@TODO
def test_u12_positions_over_lines():
    """여러 줄 입력에서 토큰마다 줄·칸 위치가 맞음 (B4)"""
