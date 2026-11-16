"""테이블 스키마: CSV 첫 줄 헤더 'id:int,name:str,age:int' (B11).

규칙 (노션 요구분석 번호):
- B10 타입은 int, str 두 개
- B13 id 컬럼(int)이 반드시 있다. 처리기가 자동으로 매긴다
- B20 헤더가 잘못되면 SqlError. 처음 만난 에러 하나만 알린다.
      검사 순서: 빈 헤더 → 왼쪽 컬럼부터 (타입 없음 → 모르는 타입 → 이름 중복) → id 없음 (s2, s2b)

담당: storage 담당과 같은 사람 추천
"""

from dataclasses import dataclass

from minidb.errors import SqlError  # noqa: F401  (구현할 때 사용)

TYPES = {"int": int, "str": str}


@dataclass(frozen=True)
class Column:
    name: str      # 소문자
    type: type     # int 또는 str


@dataclass(frozen=True)
class Schema:
    columns: list[Column]   # 헤더에 적힌 순서

    @property
    def names(self) -> list[str]:
        """헤더 순서대로 컬럼 이름."""
        raise NotImplementedError

    def find(self, name: str) -> int | None:
        """컬럼 위치(0부터). 없으면 None."""
        raise NotImplementedError

    @property
    def value_columns(self) -> list[Column]:
        """id를 뺀 컬럼. 컬럼 목록 없는 INSERT가 값을 받는 순서 (B6)."""
        raise NotImplementedError


def parse_header(fields: list[str], file_name: str) -> Schema:
    """csv로 읽은 첫 줄(['id:int', 'name:str', ...])을 Schema로 바꾼다.

    file_name: 에러 메시지용 ('users.csv 헤더 3번째 컬럼: 모르는 타입 float')
    """
    raise NotImplementedError
