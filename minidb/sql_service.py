"""HTTP 요청의 SQL 여러 문장을 파싱하고 순서대로 실행한다 (B17, B18)."""

from minidb.engine import Engine, Result
from minidb.errors import SqlError
from minidb.parser import parse_script

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------


def execute_script(
    engine: Engine, sql: str,
) -> tuple[list[dict[str, object]], SqlError | None]:
    """실행에 실패해도 앞서 성공한 문장의 결과를 돌려준다."""
    try:
        statements = parse_script(sql)
    except SqlError as error:
        return [], error

    results = []
    for number, statement in enumerate(statements, start=1):
        try:
            result = engine.run(statement)
        except SqlError as error:
            error.statement = number
            return results, error
        results.append(_format_result(number, result))
    return results, None


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------


def _format_result(number: int, result: Result) -> dict[str, object]:
    if result.kind == "insert":
        return {
            "statement": number, "kind": "insert", "affected": result.affected,
        }
    return {
        "statement": number, "kind": "select",
        "columns": result.columns, "rows": result.rows,
    }
