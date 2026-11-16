"""문장을 실행하고 결과를 돌려준다. print도 sys.argv도 쓰지 않는다 (B18).

규칙 (노션 요구분석 번호):
- B6  컬럼 목록 없는 INSERT: id를 뺀 컬럼을 스키마 순서대로.
      컬럼 목록 INSERT 에러: id가 있음, 없는 컬럼, 같은 컬럼 두 번, id 외 컬럼 누락, 개수 불일치
- B10 타입 검사 엄격: int 컬럼엔 int 값만, str 컬럼엔 str 값만
- B13 id는 자동. 사용자가 id를 넣으면 에러
- B17 여러 행 INSERT는 모든 행을 검사한 뒤에 쓴다. 실패하면 한 행도 안 쓰고 id도 안 씀 (e6)
- B7  없는 컬럼을 SELECT하면 에러
- B8  WHERE column = value. 없는 컬럼이면 에러. 값은 대소문자 구분 (B5)
- B21 WHERE 값 타입이 컬럼과 다르면 에러 (e12)

담당: (이름)
"""

from dataclasses import dataclass, field

from minidb.errors import SqlError  # noqa: F401  (구현할 때 사용)
from minidb.parser import parse_script  # noqa: F401
from minidb.statements import Insert, Select, Statement  # noqa: F401
from minidb.storage import Row, Table, open_table  # noqa: F401


@dataclass
class Result:
    """문장 하나의 결과. 출력 모양(B16)은 CLI가 정한다.

    kind: "insert" 또는 "select"
    columns, rows: SELECT 결과 (INSERT면 빈 목록)
    affected: INSERT로 들어간 행 수 (SELECT면 0)
    """

    kind: str
    columns: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    affected: int = 0


class Engine:
    """열린 테이블을 들고 있다가 문장을 실행한다. 다 쓰면 close()를 꼭 부른다 (B14)."""

    def __init__(self):
        self.tables: dict[str, Table] = {}

    def execute(self, sql: str) -> Result:
        """SQL 한 문장을 실행한다. 문장이 정확히 하나가 아니면 SqlError. (단위 테스트용)"""
        raise NotImplementedError

    def run(self, statement: Statement) -> Result:
        """파싱된 문장 하나를 실행한다. CLI는 이걸 문장마다 부른다."""
        raise NotImplementedError

    def close(self) -> None:
        """열린 테이블을 모두 닫는다 (버퍼 flush 포함)."""
        raise NotImplementedError
