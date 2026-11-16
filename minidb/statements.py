"""파서가 만들고 엔진이 실행하는 문장 구조.

파서 담당과 엔진 담당이 같이 쓰는 약속이라, 바꿀 때는 둘이 같이 정한다.
에러 메시지에 위치를 넣으려고(B4) 이름과 값마다 position을 들고 있다.
"""

from dataclasses import dataclass

from minidb.errors import Position


@dataclass(frozen=True)
class Name:
    """테이블·컬럼 이름. text는 이미 소문자 (B5)."""

    text: str
    position: Position


@dataclass(frozen=True)
class Value:
    """리터럴 값. int 또는 str (NULL 없음, B10)."""

    value: int | str
    position: Position


@dataclass(frozen=True)
class Insert:
    """INSERT INTO table [(columns)] VALUES (...), (...);

    columns: 컬럼 목록이 없으면 None (B6). 있으면 적힌 순서 그대로.
    rows: 행마다 값 목록. 개수·타입 검사는 엔진이 한다 (파서는 모양만 봄).
    """

    table: Name
    columns: list[Name] | None
    rows: list[list[Value]]


@dataclass(frozen=True)
class Where:
    """WHERE column = value 하나 (B8)."""

    column: Name
    value: Value


@dataclass(frozen=True)
class Select:
    """SELECT * | a, b FROM table [WHERE column = value];

    columns: SELECT * 이면 None (B7). 있으면 적힌 순서 그대로.
    """

    columns: list[Name] | None
    table: Name
    where: Where | None


Statement = Insert | Select
