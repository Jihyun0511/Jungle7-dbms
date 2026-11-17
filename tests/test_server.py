"""Phase 3 서버 테스트 (노션 "dbms 구현" B29~B37, 테스트 ID v1~v14).

대부분은 SqlServer를 같은 프로세스의 스레드로 띄워 진짜 HTTP로 부른다.
v12, v13만 server.py를 진짜 프로세스로 실행한다.

v1  여러 문장 한 요청 → 200, 결과가 문장 순서대로
v2  문법 에러 → 400, 결과 없음, 한 문장도 실행 안 함 (B31)
v3  실행 에러 → 400, 앞 문장 결과 + 에러, 앞 문장은 써진 채로 남음 (B31)
v4  빈 본문 → 200, 결과 없음
v5  없는 경로 404, 틀린 메서드 405 + Allow 헤더
v6  Content-Type을 보지 않는다 (B30)
v7  BOM·한글 본문은 그대로, UTF-8이 아니면 400
v8  서버 버그 → 500 "internal error"만 (B32)
v9  워커 + 큐가 다 차면 503 "server busy" (B34)
v10 종료 때 큐에 남은 요청은 503 "server shutting down" (B36)
v11 /shutdown은 localhost에서만, 밖이면 403 (B36)
v12 server.py 실행 → /shutdown → 종료 코드 0, 버퍼가 파일에 남음 (B27)
v13 헤더가 잘못된 테이블이 있으면 서버가 시작하지 않음 (B24)
v14 여러 클라이언트가 동시에 INSERT해도 id가 겹치지 않음 (B23)
"""

import http.client
import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from conftest import ROOT, USERS_HEADER, read_table, write_table
from minidb.engine import Engine, Result
from minidb.server import SqlServer

TIMEOUT = 10  # 초. 넘으면 멈춘 것으로 본다


@pytest.fixture
def start_server(workspace):
    """SqlServer를 스레드로 띄우는 함수를 준다. 테스트가 끝나면 닫는다."""
    running = []

    def start(engine=None, server_class=SqlServer, **options):
        engine = engine or Engine()
        server = server_class(("127.0.0.1", 0), engine, **options)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        running.append((server, thread, engine))
        return server

    yield start
    for server, thread, engine in running:
        server.request_stop()
        thread.join(TIMEOUT)
        server.close_workers()
        if isinstance(engine, Engine):
            engine.close()


def request(server, body="", path="/query", method="POST", headers=None):
    """(상태 코드, JSON 본문, 응답 헤더)를 돌려준다."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    address = urlsplit(server.url)
    connection = http.client.HTTPConnection(
        address.hostname, address.port, timeout=TIMEOUT,
    )
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload, response.headers
    finally:
        connection.close()


def test_v1_runs_statements_in_order(start_server):
    server = _start_with_users(start_server)
    status, payload, headers = request(
        server,
        "INSERT INTO users VALUES ('yena', 24), ('jihyun', 25);\n"
        "SELECT name, age FROM users WHERE id = 2;",
    )
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert payload == {"results": [
        {"affected": 2},
        {"columns": ["name", "age"], "rows": [["jihyun", 25]]},
    ]}


def test_v2_syntax_error_runs_nothing(start_server, workspace):
    server = _start_with_users(start_server)
    status, payload, _ = request(
        server, "INSERT INTO users VALUES ('yena', 24);\nSELECT * FROM;",
    )
    assert status == 400
    assert payload["results"] == []
    assert "statement 2" in payload["error"]
    _, after, _ = request(server, "SELECT * FROM users;")
    assert after["results"][0]["rows"] == []


def test_v3_execution_error_keeps_earlier_statements(start_server,
                                                     workspace):
    server = _start_with_users(start_server)
    status, payload, _ = request(
        server,
        "INSERT INTO users VALUES ('yena', 24);\n"
        "INSERT INTO users VALUES ('bad', 'x');\n"
        "INSERT INTO users VALUES ('never', 1);",
    )
    assert status == 400
    assert payload["results"] == [{"affected": 1}]
    assert payload["error"].startswith("error: statement 2 (line 2")
    _, after, _ = request(server, "SELECT name FROM users;")
    assert after["results"][0]["rows"] == [["yena"]]


def test_v4_empty_body_returns_no_results(start_server):
    server = _start_with_users(start_server)
    assert request(server, "")[:2] == (200, {"results": []})
    assert request(server, "-- 주석만\n")[:2] == (200, {"results": []})


def test_v5_unknown_path_and_method(start_server):
    server = _start_with_users(start_server)
    status, payload, _ = request(server, path="/nope")
    assert status == 404
    assert payload == {"error": "not found: /nope"}

    status, payload, headers = request(server, method="GET")
    assert status == 405
    assert payload == {"error": "method GET not allowed"}
    assert headers["Allow"] == "POST"


def test_v6_ignores_content_type(start_server):
    server = _start_with_users(start_server)
    for content_type in ("application/x-www-form-urlencoded",
                         "application/json", "text/plain"):
        status, _, _ = request(server, "SELECT * FROM users;",
                               headers={"Content-Type": content_type})
        assert status == 200


def test_v7_reads_utf8_with_bom(start_server):
    server = _start_with_users(start_server)
    body = "\ufeffINSERT INTO users VALUES ('예나', 24);".encode("utf-8")
    assert request(server, body)[:2] == (200, {"results": [{"affected": 1}]})
    _, payload, _ = request(server, "SELECT name FROM users;")
    assert payload["results"][0]["rows"] == [["예나"]]

    status, payload, _ = request(server, "SELECT '예나';".encode("cp949"))
    assert status == 400
    assert payload == {"error": "expected UTF-8 request body"}


def test_v8_server_bug_hides_details(start_server, capfd):
    server = start_server(engine=_BrokenEngine())
    status, payload, _ = request(server, "SELECT * FROM users;")
    assert status == 500
    assert payload == {"error": "internal error"}
    assert "secret path" in capfd.readouterr().err


def test_v9_rejects_when_full(start_server):
    engine = _BlockingEngine()
    server = start_server(engine=engine, workers=1, queue_size=0)
    first = _request_in_background(server)
    assert engine.started.wait(TIMEOUT)

    status, payload, _ = request(server, "SELECT * FROM users;")
    assert status == 503
    assert payload == {"error": "server busy"}

    engine.release.set()
    first.join(TIMEOUT)
    assert first.result[:2] == (200, {"results": [{"affected": 1}]})


def test_v10_queued_requests_get_503_on_stop(start_server):
    engine = _BlockingEngine()
    server = start_server(engine=engine, workers=1, queue_size=1)
    running = _request_in_background(server)
    assert engine.started.wait(TIMEOUT)
    queued = _request_in_background(server)
    # 자리 두 개가 다 찼다는 것은 queued가 큐에 들어갔다는 뜻이다
    _wait_until_busy(server)

    server.request_stop()
    engine.release.set()
    running.join(TIMEOUT)
    queued.join(TIMEOUT)
    assert running.result[0] == 200
    assert queued.result[:2] == (503, {"error": "server shutting down"})


def test_v11_shutdown_only_from_localhost(start_server):
    server = start_server(server_class=_RemoteClientServer)
    status, payload, _ = request(server, path="/shutdown")
    assert status == 403
    assert payload == {"error": "shutdown is allowed only from localhost"}
    assert request(server, "")[0] == 200  # 서버는 그대로 돈다


def test_v12_shutdown_flushes_and_exits(workspace):
    write_table(workspace, "users", USERS_HEADER)
    process = _run_server_process(workspace)
    try:
        server = _ProcessAddress(process.stdout.readline())
        assert request(server, "INSERT INTO users VALUES ('yena', 24);")[0] \
            == 200
        status, payload, _ = request(server, path="/shutdown")
        assert (status, payload) == (200, {"message": "shutting down"})
        assert process.wait(TIMEOUT) == 0
    finally:
        process.kill()
        process.communicate()
    assert read_table(workspace, "users") == USERS_HEADER + "1,yena,24\n"


def test_v13_bad_table_stops_startup(workspace):
    write_table(workspace, "users", "id:int,age:float\n")
    process = _run_server_process(workspace)
    _, error = process.communicate(timeout=TIMEOUT)
    assert process.returncode == 1
    assert "float" in error


def test_v14_concurrent_inserts_get_unique_ids(start_server):
    server = _start_with_users(start_server)
    clients, per_client = 8, 20

    def insert_many():
        for _ in range(per_client):
            assert request(server, "INSERT INTO users VALUES ('a', 1);")[0] \
                == 200

    threads = [threading.Thread(target=insert_many) for _ in range(clients)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)

    _, payload, _ = request(server, "SELECT id FROM users;")
    ids = sorted(row[0] for row in payload["results"][0]["rows"])
    assert ids == list(range(1, clients * per_client + 1))


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------


def _start_with_users(start_server):
    # start_server가 workspace로 실행 위치를 옮겨 두었다
    write_table(Path.cwd(), "users", USERS_HEADER)
    engine = Engine()
    engine.open_all_tables()
    return start_server(engine=engine)


class _BrokenEngine:
    def run(self, statement):
        raise RuntimeError("secret path C:/internal")


class _BlockingEngine:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, statement):
        self.started.set()
        self.release.wait(TIMEOUT)
        return Result("insert", affected=1)


class _RemoteClientServer(SqlServer):
    def finish_request(self, request, client_address):
        self.RequestHandlerClass(request, ("10.0.0.5", 50000), self)


class _BackgroundRequest(threading.Thread):
    def __init__(self, server):
        super().__init__(daemon=True)
        self.server = server
        self.result = None

    def run(self):
        self.result = request(self.server, "INSERT INTO users VALUES (1);")


def _request_in_background(server):
    thread = _BackgroundRequest(server)
    thread.start()
    return thread


def _wait_until_busy(server):
    # 요청을 보내 503인지 보면, 그 요청이 남은 자리를 먼저 차지할 수 있다.
    # 그래서 SqlServer._slots 이름에 기댄다. 이름을 바꾸면 같이 고친다
    for _ in range(200):
        if server._slots._value == 0:
            return
        threading.Event().wait(0.05)
    raise AssertionError("server never became busy")


def _run_server_process(folder):
    return subprocess.Popen(
        [sys.executable, str(ROOT / "server.py"), "--port", "0"],
        cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8",
    )


class _ProcessAddress:
    """'listening on http://...' 한 줄에서 url만 꺼낸다."""

    def __init__(self, line):
        self.url = line.strip().removeprefix("listening on ")
