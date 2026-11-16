"""테이블 스키마: CSV 첫 줄 헤더 'id:int,name:str,age:int' (B11).

규칙 (노션 요구분석 번호):
- B10 타입은 int, str 두 개
- B13 id 컬럼(int)이 반드시 있다. 처리기가 자동으로 매긴다
- B20 헤더가 잘못되면 SqlError. 처음 만난 에러 하나만 알린다.
      검사 순서: 빈 헤더 → 왼쪽 컬럼부터 (타입 없음 → 모르는 타입 → 이름 중복) → id 없음 (s2, s2b)

요구분석에 없어서 임시로 정한 것:
- 이름과 타입 앞뒤 공백은 무시한다 ('id:int, name:str' 허용)
- 이름은 소문자로 바꿔 비교한다 (name과 Name은 중복)
- id가 int가 아니면 에러 (B13 '마지막 id + 1'이 정수를 가정하므로). id 없음 다음에 검사

담당: storage 담당과 같은 사람 추천
"""

from dataclasses import dataclass

from minidb.errors import SqlError

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
        return [column.name for column in self.columns]

    def find(self, name: str) -> int | None:
        """컬럼 위치(0부터). 없으면 None."""
        if name not in self.names:
            return None
        return self.names.index(name)

    @property
    def value_columns(self) -> list[Column]:
        """id를 뺀 컬럼. 컬럼 목록 없는 INSERT가 값을 받는 순서 (B6)."""
        return [column for column in self.columns if column.name != "id"]


def parse_header(fields: list[str], file_name: str) -> Schema:
    """csv로 읽은 첫 줄(['id:int', 'name:str', ...])을 Schema로 바꾼다.

    file_name: 에러 메시지용 ('users.csv 헤더 3번째 컬럼: 모르는 타입 float')
    fields가 빈 목록이면 빈 파일로 본다.
    """
    if not fields:
        raise SqlError(f"{file_name} 헤더가 비어 있음")
    columns = []
    for number, field in enumerate(fields, start=1):
        column = _parse_column(field, f"{file_name} 헤더 {number}번째 컬럼")
        if column.name in [seen.name for seen in columns]:
            raise SqlError(f"{file_name} 헤더 {number}번째 컬럼: "
                           f"이름 중복 {column.name}")
        columns.append(column)
    schema = Schema(columns)
    _check_id_column(schema, file_name)
    return schema


def _parse_column(field: str, where: str) -> Column:
    """'name:str' 하나를 Column으로. where는 에러 메시지 앞부분."""
    name, _, type_name = field.partition(":")
    name = name.strip().lower()
    type_name = type_name.strip()
    if not type_name:
        raise SqlError(f"{where}: 타입 없음")
    if type_name not in TYPES:
        raise SqlError(f"{where}: 모르는 타입 {type_name}")
    return Column(name, TYPES[type_name])


def _check_id_column(schema: Schema, file_name: str) -> None:
    index = schema.find("id")
    if index is None:
        raise SqlError(f"{file_name} 헤더: id 컬럼이 없음")
    if schema.columns[index].type is not int:
        raise SqlError(f"{file_name} 헤더: id 컬럼은 int여야 함")
