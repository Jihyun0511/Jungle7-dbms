"""진입점: python server.py [--host 0.0.0.0] [--port 8000] [--workers 8]
[--queue-size 64]"""

import sys

from minidb.server import run_server

if __name__ == "__main__":
    # sql_processor.py와 같은 이유로 출력 인코딩을 utf-8로 고정한다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(run_server(sys.argv[1:]))
