"""Phase 3 동시성 테스트 초안 (R-동시성, R-ID는 Phase 3 요구분석에서 확정).

결정 기록: 노션 "dbms 구현" 6절 B23~B27 (락 방식 C).
서버 없이 Engine 하나를 여러 스레드가 같이 쓰는 상황으로 확인한다.

t1 insert가 끝난 뒤 시작한 select는 그 행을 본다
t2 동시에 insert해도 id가 겹치거나 빠지지 않는다
t3 같은 테이블에 동시에 온 첫 요청들도 테이블을 한 번만 연다 (C8, 엔진 락)
t4 select는 반쪽 행이나 반쪽 문장을 보지 않는다 (문장 단위로 통째로 보이거나 안 보임)
t5 select가 파일을 읽는 동안에도 insert는 막히지 않는다 (C: 읽기는 락 밖)

GIL 빌드에서는 경쟁이 드물게 나서 sys.setswitchinterval을 아주 작게 줄여
스레드가 자주 바뀌게 한다. 3.14t(free-threaded)에서는 그대로 진짜 병렬로 돈다.

t3, t5는 구현 이름(minidb.engine.open_table, Table._decode_row)에 기대고 있다.
구현에서 이름을 바꾸면 테스트도 사람이 같이 고친다.
"""

import sys
import threading

import pytest

import minidb.engine
import minidb.storage
from conftest import USERS_HEADER, write_table
from minidb.engine import Engine

THREADS = 8
TIMEOUT = 10  # 초. 넘으면 멈춘 것으로 본다


@pytest.fixture(autouse=True)
def frequent_switches():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


@pytest.fixture
def engine(workspace):
    write_table(workspace, "users", USERS_HEADER)
    instance = Engine()
    try:
        yield instance
    finally:
        instance.close()


def run_threads(targets):
    """targets를 동시에 출발시키고, 스레드 안에서 난 예외를 모아 돌려준다."""
    barrier = threading.Barrier(len(targets))
    errors = []

    def wrap(target):
        def body():
            try:
                barrier.wait()
                target()
            except BaseException as error:  # noqa: BLE001 - 테스트로 넘김
                errors.append(error)
        return body

    threads = [threading.Thread(target=wrap(target)) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)
        assert not thread.is_alive(), "스레드가 끝나지 않음 (락이 안 풀렸을 수 있음)"
    return errors


def test_t1_finished_insert_is_visible_to_other_thread(engine):
    inserted = threading.Event()
    seen = []

    def writer():
        engine.execute("INSERT INTO users VALUES ('yena', 24);")
        inserted.set()

    def reader():
        assert inserted.wait(TIMEOUT)
        seen.extend(engine.execute("SELECT * FROM users WHERE id = 1;").rows)

    assert run_threads([writer, reader]) == []
    assert seen == [(1, "yena", 24)]


def test_t2_concurrent_inserts_get_unique_ids(engine):
    per_thread = 200

    def writer(number):
        def body():
            for i in range(per_thread):
                engine.execute(f"INSERT INTO users VALUES ('w{number}', {i});")
        return body

    assert run_threads([writer(number) for number in range(THREADS)]) == []

    rows = engine.execute("SELECT * FROM users;").rows
    ids = [row[0] for row in rows]
    assert sorted(ids) == list(range(1, THREADS * per_thread + 1))
    # 트리로 찾아도 같은 행이 나온다 (파일과 트리가 어긋나지 않음)
    for row in rows[:: per_thread // 4]:
        assert engine.execute(
            f"SELECT * FROM users WHERE id = {row[0]};"
        ).rows == [row]


def test_t3_first_requests_open_table_once(engine, monkeypatch):
    opened = []
    real_open = minidb.engine.open_table

    def slow_open(name):
        opened.append(name)
        threading.Event().wait(0.05)  # 찾기와 넣기 사이에 끼어들 틈을 만든다
        return real_open(name)

    monkeypatch.setattr(minidb.engine, "open_table", slow_open)

    def request():
        engine.execute("SELECT * FROM users;")

    assert run_threads([request] * THREADS) == []
    assert opened.count("users") <= 1  # 서버 시작 때 미리 열었으면 0


def test_t3b_prepared_tables_are_not_opened_again(engine, monkeypatch):
    """B24: open_all_tables로 미리 열면 요청 중에는 0번 연다 (지현 #13)"""
    engine.open_all_tables()
    opened = []
    real_open = minidb.engine.open_table

    def counting_open(name):
        opened.append(name)
        return real_open(name)

    monkeypatch.setattr(minidb.engine, "open_table", counting_open)

    def request(number):
        def body():
            engine.execute(f"INSERT INTO users VALUES ('t{number}', {number});")
        return body

    assert run_threads([request(number) for number in range(THREADS)]) == []
    assert opened == []
    assert len(engine.execute("SELECT * FROM users;").rows) == THREADS


def test_t4_select_sees_whole_statements_only(engine):
    batch = 50
    statements = 40
    name = "x" * 200  # 버퍼(8KB)를 넘겨 쓰는 도중 일부가 파일로 나가게 한다
    values = ", ".join(f"('{name}', {i})" for i in range(batch))
    done = threading.Event()
    counts = []

    def writer():
        try:
            for _ in range(statements):
                engine.execute(f"INSERT INTO users VALUES {values};")
        finally:
            done.set()

    def reader():
        while not done.is_set():
            rows = engine.execute("SELECT * FROM users;").rows
            for row in rows:
                assert row[1] == name and 0 <= row[2] < batch
            counts.append(len(rows))
            # 다른 필드 선형 탐색도 같은 규칙
            engine.execute("SELECT * FROM users WHERE age = 3;")

    assert run_threads([writer] + [reader] * (THREADS - 1)) == []
    assert all(count % batch == 0 for count in counts), counts
    final_rows = engine.execute("SELECT * FROM users;").rows
    assert len(final_rows) == batch * statements


def test_t5_insert_is_not_blocked_while_select_reads(engine, monkeypatch):
    values = ", ".join(f"('n{i}', {i})" for i in range(100))
    engine.execute(f"INSERT INTO users VALUES {values};")

    reading = threading.Event()
    release = threading.Event()
    real_decode = minidb.storage.Table._decode_row

    def paused_decode(self, fields, where):
        if threading.current_thread().name == "slow-select":
            reading.set()
            release.wait(TIMEOUT)  # 읽는 도중에 멈춰 둔다
        return real_decode(self, fields, where)

    monkeypatch.setattr(minidb.storage.Table, "_decode_row", paused_decode)

    select = threading.Thread(
        name="slow-select",
        target=engine.execute,
        args=("SELECT * FROM users WHERE age = 7;",),
    )
    select.start()
    try:
        assert reading.wait(TIMEOUT)
        insert = threading.Thread(
            target=engine.execute,
            args=("INSERT INTO users VALUES ('late', 1);",),
        )
        insert.start()
        insert.join(2)
        assert not insert.is_alive(), "select가 읽는 동안 insert가 막힘"
    finally:
        release.set()
        select.join(TIMEOUT)
