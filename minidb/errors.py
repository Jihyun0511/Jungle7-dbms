"""모든 모듈이 같이 쓰는 에러 타입과 위치."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """SQL 텍스트 안의 위치. 줄과 칸 모두 1부터 센다."""

    line: int
    column: int


class SqlError(Exception):
    """사용자에게 보여 줄 에러. CLI가 받아서 stderr로 출력하고 종료 코드 1로 끝낸다 (B17).

    position: SQL 안의 위치. 헤더 오류(B20)처럼 SQL과 상관없는 에러면 None.
    statement: 몇 번째 문장인지 (1부터). 아는 쪽(파서 또는 CLI)이 채운다.
    """

    def __init__(self, message: str, position: Position | None = None,
                 statement: int | None = None):
        super().__init__(message)
        self.message = message
        self.position = position
        self.statement = statement

    def format(self) -> str:
        """예: "error: statement 2 (line 2, column 33): age is int but got
        string 'abc'"
        """
        where = []
        if self.statement is not None:
            where.append(f"statement {self.statement}")
        if self.position is not None:
            line, column = self.position.line, self.position.column
            where.append(f"(line {line}, column {column})")
        if not where:
            return f"error: {self.message}"
        return f"error: {' '.join(where)}: {self.message}"
