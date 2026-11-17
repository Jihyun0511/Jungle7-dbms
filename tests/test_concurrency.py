"""여러 스레드가 Engine 하나를 같이 쓸 때 (노션 9절 t1~t5, B23~B25).

GIL 빌드에서는 switchinterval을 아주 짧게 해서 스레드가 몇 줄마다 바뀌게
한다. 그래야 경쟁 상태가 실제로 드러난다. t3는 minidb.engine.open_table,
t5는 Table._decode_row 이름에 기댄다 (구현에서 이름을 바꾸면 같이 고친다).
"""

import sys
import threading

import pytest

import minidb.engine
from conftest import USERS_HEADER, write_table
from minidb.engine import Engine
from minidb.storage import Table

THREADS = 8


@pytest.fixture(autouse=True)
def frequent_switches():
    original = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(original)


@pytest.fixture
def engine(workspace):
    write_table(workspace, "users", USERS_HEADER)
    opened = Engine()
    yield opened
    opened.close()


def _run_together(target, count: int = THREADS) -> list[BaseException]:
    """target(번호)를 스레드 count개로 동시에 시작하고, 난 예외를 모은다."""
    barrier = threading.Barrier(count)
    errors = []

    def worker(number: int) -> None:
        barrier.wait()
        try:
            target(number)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def test_t1_insert_then_find_by_id_in_other_thread(engine):
    """스레드1 insert가 끝난 뒤 신호 → 스레드2 WHERE id = 1에서 그 행이 보임"""
    inserted = threading.Event()
    found = []

    def writer() -> None:
        engine.execute("INSERT INTO users VALUES ('yena', 24);")
        inserted.set()

    def reader() -> None:
        inserted.wait(timeout=5)
        found.append(
            engine.execute("SELECT * FROM users WHERE id = 1;").rows
        )

    threads = [threading.Thread(target=reader), threading.Thread(target=writer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert found == [[(1, "yena", 24)]]


def test_t2_parallel_inserts_get_each_id_once(engine):
    """8스레드 × 200 insert → id 1~1600 정확히 한 번씩, 트리 조회 결과도 같음"""
    per_thread = 200

    def insert_many(number: int) -> None:
        for i in range(per_thread):
            engine.execute(f"INSERT INTO users VALUES ('t{number}-{i}', {i});")

    assert _run_together(insert_many) == []
    total = THREADS * per_thread
    rows = engine.execute("SELECT id, name FROM users;").rows
    assert sorted(row[0] for row in rows) == list(range(1, total + 1))
    names = dict(rows)
    for row_id in range(1, total + 1):
        found = engine.execute(
            f"SELECT id, name FROM users WHERE id = {row_id};"
        ).rows
        assert found == [(row_id, names[row_id])]


@pytest.fixture
def opened_tables(monkeypatch):
    """Engine이 open_table을 부른 횟수를 센다."""
    names = []
    real_open_table = minidb.engine.open_table

    def counting_open(name: str) -> Table:
        names.append(name)
        return real_open_table(name)

    monkeypatch.setattr(minidb.engine, "open_table", counting_open)
    return names


def test_t3_first_requests_open_table_once(engine, opened_tables):
    """서버 직후 같은 테이블 첫 요청 8개 동시에 → 테이블을 한 번만 엶"""
    errors = _run_together(
        lambda number: engine.execute("SELECT * FROM users WHERE id = 1;")
    )
    assert errors == []
    assert opened_tables == ["users"]


def test_t3b_prepared_tables_are_not_opened_again(engine, opened_tables):
    """B24: prepare_tables로 미리 열면 요청 중에는 0번 엶"""
    assert engine.prepare_tables() == ["users"]
    opened_tables.clear()
    errors = _run_together(
        lambda number: engine.execute(
            f"INSERT INTO users VALUES ('t{number}', {number});"
        )
    )
    assert errors == []
    assert opened_tables == []
    assert len(engine.execute("SELECT * FROM users;").rows) == THREADS


def test_t4_big_insert_is_seen_whole(engine):
    """큰 multi-row insert와 select 동시에 → 반쪽 행이 없고 행 수는 늘 500의 배수"""
    batch, statements = 500, 10
    values = ", ".join(f"('n{i}', {i})" for i in range(batch))
    done = threading.Event()
    counts = []

    def work(number: int) -> None:
        if number == 0:
            for _ in range(statements):
                engine.execute(f"INSERT INTO users VALUES {values};")
            done.set()
            return
        while not done.is_set():
            counts.append(len(engine.execute("SELECT * FROM users;").rows))

    assert _run_together(work, count=4) == []
    assert counts, "select가 한 번도 안 돌았음"
    assert all(count % batch == 0 for count in counts)
    assert len(engine.execute("SELECT * FROM users;").rows) == batch * statements


def test_t5_insert_is_not_blocked_by_slow_read(engine, monkeypatch):
    """select가 파일을 읽는 도중(디코딩에서 멈춤) insert → insert가 2초 안에 끝남"""
    engine.execute("INSERT INTO users VALUES ('yena', 24);")
    reading = threading.Event()
    release = threading.Event()
    original_decode = Table._decode_row

    def slow_decode(self, fields, where):
        reading.set()
        release.wait(timeout=10)
        return original_decode(self, fields, where)

    monkeypatch.setattr(Table, "_decode_row", slow_decode)
    reader = threading.Thread(
        target=lambda: engine.execute("SELECT * FROM users;")
    )
    reader.start()
    assert reading.wait(timeout=5)

    writer = threading.Thread(
        target=lambda: engine.execute("INSERT INTO users VALUES ('kim', 20);")
    )
    writer.start()
    writer.join(timeout=2)
    finished_in_time = not writer.is_alive()
    release.set()
    reader.join()
    writer.join()
    assert finished_in_time
