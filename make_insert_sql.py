"""대용량 INSERT SQL 파일 만들기 (Phase 2).

    python make_insert_sql.py 1000000 big.sql
    python sql_processor.py big.sql

users(id:int,name:str,age:int) 테이블에 넣을 행을 만든다. 행 n은
('user{n}', n % 100)이고, id는 처리기가 자동으로 매긴다 (B13).
데이터는 Phase 1 처리기로 그대로 넣는다. INSERT 문 하나에 --batch 행씩 담는다.
"""

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------

DEFAULT_BATCH = 10_000


def main(argv: list[str]) -> int:
    options = _parse_arguments(argv)
    path = Path(options.output)
    with path.open("w", encoding="utf-8") as file:
        file.writelines(
            generate_insert_statements(options.rows, options.batch)
        )
    size = path.stat().st_size / 1_000_000
    print(f"wrote {options.rows:,} rows to {path} ({size:.1f} MB)")
    return 0


def generate_insert_statements(rows: int, batch: int) -> Iterator[str]:
    """INSERT 문을 한 줄씩. 문장 하나에 batch 행까지 담는다."""
    for start in range(1, rows + 1, batch):
        stop = min(start + batch, rows + 1)
        values = ", ".join(
            f"('user{number}', {number % 100})"
            for number in range(start, stop)
        )
        yield f"INSERT INTO users (name, age) VALUES {values};\n"


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------


def _parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rows", type=_positive_int, help="넣을 행 수")
    parser.add_argument("output", help="만들 SQL 파일")
    parser.add_argument(
        "--batch", type=_positive_int, default=DEFAULT_BATCH,
        help=f"INSERT 문 하나에 넣을 행 수 (기본 {DEFAULT_BATCH:,})",
    )
    return parser.parse_args(argv)


def _positive_int(text: str) -> int:
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError(
            f"expected a positive integer but got {text}"
        )
    return number


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
