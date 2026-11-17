"""HTTP API 서버: 엔진을 감싸 POST /query로 SQL을 받는다.

규칙 (노션 요구분석 번호):
- B29 HTTP, 표준 http.server. 연결 하나에 요청 하나 (HTTP/1.0)
- B30 POST /query 본문에 SQL 그대로. Content-Type은 보지 않고 UTF-8로 읽는다
      (B19처럼 BOM은 무시)
- B31 CLI와 같다: 전부 파싱 → 문법 에러면 아무것도 실행 안 함.
      실행 에러면 그 자리에서 멈추고, 앞 문장은 이미 써진 채로 둔다
- B32 SQL 실행 결과는 {"results": [...]}. SELECT는 {"columns", "rows"},
      INSERT는 {"affected"}. 에러는 "error"에 SqlError.format() 문자열.
      400 SqlError(앞 결과도 같이) / 500 "internal error"만 / 503 바쁨·종료 중
      / 404 없는 경로 / 405 틀린 메서드 / 403 밖에서 온 /shutdown
- B33 요청은 ThreadPoolExecutor의 워커가 처리한다
- B34 워커 + 큐가 다 차면 받는 스레드가 바로 503
- B35 python server.py [--host] [--port] [--workers] [--queue-size]
- B36 Ctrl+C 또는 POST /shutdown(127.0.0.1에서만). 큐에 남은 요청은 503,
      처리 중인 요청은 기다린 뒤 Engine.close() (B27)
- B24 워커를 띄우기 전에 engine.open_all_tables()

담당: (이름)
"""

import argparse
import json
import socket
import sys
import threading
import traceback
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer

from minidb.engine import Engine, Result
from minidb.errors import SqlError
from minidb.parser import parse_script
from minidb.statements import Statement

# ---------------------------------------------------------------------------
# 공개: 다른 모듈이 가져다 쓴다. 모양을 바꾸려면 팀과 먼저 정한다.
# ---------------------------------------------------------------------------

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_WORKERS = 8
DEFAULT_QUEUE_SIZE = 64


class SqlServer(HTTPServer):
    """요청을 워커 풀에 넘기는 HTTP 서버. engine은 만든 쪽이 닫는다.

    workers + queue_size개까지 받아 두고, 넘치면 받는 스레드가 503을 보낸다.
    """

    def __init__(self, address: tuple[str, int], engine: Engine,
                 workers: int = DEFAULT_WORKERS,
                 queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        if workers < 1:
            raise ValueError("expected at least one worker")
        if queue_size < 0:
            raise ValueError("expected a non-negative queue size")
        self.engine = engine
        self._slots = threading.BoundedSemaphore(workers + queue_size)
        self._stopping = threading.Event()
        self._stop_lock = threading.Lock()
        super().__init__(address, _Handler)
        self._executor = ThreadPoolExecutor(max_workers=workers)

    @property
    def is_stopping(self) -> bool:
        return self._stopping.is_set()

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def process_request(self, request: socket.socket,
                        client_address: tuple) -> None:
        if self.is_stopping:
            _reject_connection(self, request, client_address, _StoppingHandler)
            return
        if not self._slots.acquire(blocking=False):
            _reject_connection(self, request, client_address, _BusyHandler)
            return
        try:
            self._executor.submit(
                self._process_in_worker, request, client_address,
            )
        except RuntimeError:
            self._slots.release()
            if not self.is_stopping:
                raise
            _reject_connection(self, request, client_address, _StoppingHandler)

    def request_stop(self) -> None:
        """serve_forever를 멈추게 한다. 이미 큐에 있는 요청은 503을 받는다.

        serve_forever를 도는 스레드에서 부르면 멈추므로 다른 스레드에서
        shutdown을 부른다.
        """
        with self._stop_lock:
            if self.is_stopping:
                return
            self._stopping.set()
        threading.Thread(target=self.shutdown, daemon=True).start()

    def close_workers(self) -> None:
        """접수 소켓을 닫고 워커의 실행과 큐의 503 응답을 기다린다 (B27)."""
        self._stopping.set()
        try:
            self.server_close()
        finally:
            self._executor.shutdown(wait=True)

    def _process_in_worker(self, request: socket.socket,
                           client_address: tuple) -> None:
        try:
            if self.is_stopping:
                _StoppingHandler(request, client_address, self)
            else:
                self.finish_request(request, client_address)
        except Exception:
            # socketserver 기본 process_request와 같다. 워커 안에서 난 예외는
            # future에 묻혀 사라지므로 handle_error로 traceback을 찍는다
            self.handle_error(request, client_address)
        finally:
            try:
                self.shutdown_request(request)
            finally:
                self._slots.release()


def run_server(argv: list[str]) -> int:
    """argv: 프로그램 이름을 뺀 인자 목록. 종료 코드를 돌려준다."""
    options = _parse_options(argv)
    engine = Engine()
    try:
        return _serve(engine, options)
    except SqlError as error:
        print(error.format(), file=sys.stderr)
        return 1
    finally:
        engine.close()


# ---------------------------------------------------------------------------
# 도우미: 이 파일 안에서만 쓴다. 이름 앞에 _를 붙인다.
# ---------------------------------------------------------------------------

_LOCAL_HOSTS = ("127.0.0.1", "::1")
_ROUTES = {"/query": "_query", "/shutdown": "_shutdown"}
# 느린 클라이언트가 워커를 붙잡아 두지 않게 한다
_REQUEST_TIMEOUT = 30
# 503은 받는 스레드가 보내므로 오래 기다리지 않는다
_BUSY_TIMEOUT = 1
_DRAIN_CHUNK_SIZE = 64 * 1024


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    timeout = _REQUEST_TIMEOUT
    server: SqlServer

    def do_POST(self) -> None:
        self._handle()

    def send_error(self, code: int, message: str | None = None,
                   explain: str | None = None) -> None:
        # 기본 핸들러가 do_*를 찾지 못한 요청도 B32의 404·405로 처리한다.
        if code == HTTPStatus.NOT_IMPLEMENTED:
            self._handle()
            return
        super().send_error(code, message, explain)

    def _handle(self) -> None:
        # 본문을 다 읽지 않고 닫으면 윈도우는 RST를 보내 응답이 사라질 수 있다
        try:
            body = self._read_body()
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._route(body)

    def _read_body(self) -> bytes:
        path = self.path.partition("?")[0]
        length = self._content_length()
        if self.command != "POST" or path != "/query":
            self._discard_body(length)
            return b""
        return b"".join(self._read_body_chunks(length))

    def _content_length(self) -> int:
        if "Transfer-Encoding" in self.headers:
            raise ValueError("Transfer-Encoding is not supported")
        lengths = self.headers.get_all("Content-Length", ["0"])
        if len(lengths) != 1:
            raise ValueError("expected one Content-Length header")
        text = lengths[0]
        if not text.isascii() or not text.isdigit():
            raise ValueError(
                f"expected a number for Content-Length but got {text!r}"
            )
        significant_digits = text.lstrip("0") or "0"
        if len(significant_digits) > len(str(sys.maxsize)):
            raise ValueError("Content-Length is too large")
        length = int(significant_digits)
        if length > sys.maxsize:
            raise ValueError("Content-Length is too large")
        return length

    def _discard_body(self, length: int) -> None:
        for _ in self._read_body_chunks(length):
            pass

    def _read_body_chunks(self, length: int) -> Iterator[bytes]:
        while length:
            chunk = self.rfile.read1(min(length, _DRAIN_CHUNK_SIZE))
            if not chunk:
                raise ValueError("incomplete request body")
            length -= len(chunk)
            yield chunk

    def _route(self, body: bytes) -> None:
        path = self.path.partition("?")[0]
        if path not in _ROUTES:
            self._send_json(HTTPStatus.NOT_FOUND,
                            {"error": f"not found: {self.path}"})
            return
        if self.command != "POST":
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED,
                            {"error": f"method {self.command} not allowed"},
                            headers={"Allow": "POST"})
            return
        getattr(self, _ROUTES[path])(body)

    def _query(self, body: bytes) -> None:
        try:
            sql = body.decode("utf-8-sig")
        except UnicodeDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST,
                            {"error": "expected UTF-8 request body"})
            return
        status, payload = _execute_sql(self.server.engine, sql)
        self._send_json(status, payload)

    def _shutdown(self, body: bytes) -> None:
        if self.client_address[0] not in _LOCAL_HOSTS:
            self._send_json(HTTPStatus.FORBIDDEN, {
                "error": "shutdown is allowed only from localhost",
            })
            return
        self._send_json(HTTPStatus.OK, {"message": "shutting down"})
        self.server.request_stop()

    def _send_json(self, status: HTTPStatus, payload: dict,
                   headers: dict[str, str] | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


class _UnavailableHandler(_Handler):
    message: str

    def _read_body(self) -> bytes:
        self._discard_body(self._content_length())
        return b""

    def _route(self, body: bytes) -> None:
        self._send_json(HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": self.message})


class _BusyHandler(_UnavailableHandler):
    timeout = _BUSY_TIMEOUT
    message = "server busy"


class _StoppingHandler(_UnavailableHandler):
    message = "server shutting down"


def _reject_connection(
    server: SqlServer, request: socket.socket, client_address: tuple,
    handler: type[_UnavailableHandler],
) -> None:
    try:
        handler(request, client_address, server)
    except OSError:
        server.handle_error(request, client_address)
    finally:
        server.shutdown_request(request)


def _execute_sql(engine: Engine, sql: str) -> tuple[HTTPStatus, dict]:
    try:
        return _execute_statements(engine, sql)
    except Exception:
        # 서버 버그는 클라이언트에 내부 사정을 보이지 않고 콘솔에만 남긴다
        # (B32). 삼키지 않고 traceback을 찍는다
        traceback.print_exc()
        return HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"}


def _execute_statements(engine: Engine,
                        sql: str) -> tuple[HTTPStatus, dict]:
    try:
        statements = parse_script(sql)
    except SqlError as error:
        return HTTPStatus.BAD_REQUEST, {"results": [], "error": error.format()}
    results, failure = _run_statements(engine, statements)
    if failure is not None:
        return HTTPStatus.BAD_REQUEST, {
            "results": results, "error": failure.format(),
        }
    return HTTPStatus.OK, {"results": results}


def _run_statements(
    engine: Engine, statements: list[Statement],
) -> tuple[list[dict], SqlError | None]:
    """실패하면 그때까지의 결과와 에러를 돌려준다. 앞 문장은 되돌리지 않는다."""
    results = []
    for number, statement in enumerate(statements, start=1):
        try:
            results.append(_format_result(engine.run(statement)))
        except SqlError as error:
            error.statement = number
            return results, error
    return results, None


def _format_result(result: Result) -> dict:
    if result.kind == "insert":
        return {"affected": result.affected}
    return {
        "columns": result.columns,
        "rows": [list(row) for row in result.rows],
    }


def _parse_options(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python server.py")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="0.0.0.0이면 다른 컴퓨터에서도 접속할 수 있다")
    parser.add_argument("--port", type=_port_number, default=DEFAULT_PORT)
    parser.add_argument("--workers", type=_positive, default=DEFAULT_WORKERS)
    parser.add_argument("--queue-size", type=_not_negative,
                        default=DEFAULT_QUEUE_SIZE)
    return parser.parse_args(argv)


def _port_number(text: str) -> int:
    number = int(text)
    if not 0 <= number <= 65535:
        raise argparse.ArgumentTypeError(f"expected a TCP port but got {text}")
    return number


def _positive(text: str) -> int:
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError(f"expected 1 or more but got {text}")
    return number


def _not_negative(text: str) -> int:
    number = int(text)
    if number < 0:
        raise argparse.ArgumentTypeError(f"expected 0 or more but got {text}")
    return number


def _serve(engine: Engine, options: argparse.Namespace) -> int:
    engine.open_all_tables()
    try:
        server = SqlServer((options.host, options.port), engine,
                           options.workers, options.queue_size)
    except OSError as error:
        print(f"error: cannot listen on {options.host}:{options.port}: "
              f"{error.strerror}", file=sys.stderr)
        return 1
    print(f"listening on {server.url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close_workers()
    return 0
