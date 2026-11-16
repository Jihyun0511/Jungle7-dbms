"""모든 테스트가 같이 쓰는 도우미.

- workspace: 실행 위치를 빈 임시 폴더로 옮긴다. 진짜 data/를 건드리지 않는다 (B3)
- write_table: workspace 안에 data/<이름>.csv를 만든다
- run_cli: sql_processor.py를 진짜 프로세스로 실행한다 (B22)
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
USERS_HEADER = "id:int,name:str,age:int\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """data/ 폴더가 있는 빈 임시 폴더로 실행 위치를 옮긴다."""
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_table(folder: Path, name: str, text: str) -> Path:
    """folder/data/<name>.csv에 text를 그대로 쓴다. text에 헤더도 넣어야 한다."""
    path = folder / "data" / f"{name}.csv"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def read_table(folder: Path, name: str) -> str:
    return (folder / "data" / f"{name}.csv").read_text(encoding="utf-8")


def run_cli(folder: Path, sql: str | None = None,
            args: list[str] | None = None) -> subprocess.CompletedProcess:
    """folder를 실행 위치로 두고 sql_processor.py를 실행한다.

    sql을 주면 folder/input.sql에 쓰고 그 파일을 인자로 넘긴다.
    args를 주면 그대로 넘긴다 (인자 없음·여러 개·없는 파일 사례용).
    """
    if sql is not None:
        (folder / "input.sql").write_text(sql, encoding="utf-8")
        args = ["input.sql"]
    return subprocess.run(
        [sys.executable, str(ROOT / "sql_processor.py"), *(args or [])],
        cwd=folder, capture_output=True, text=True, encoding="utf-8",
    )
