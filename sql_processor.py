"""진입점: python sql_processor.py <file.sql>"""

import sys

from minidb.cli import main

if __name__ == "__main__":
    # 윈도우에서 출력을 파이프로 넘기면 기본 인코딩이 cp949라 한글이 깨진다.
    # 테스트(run_cli)도 utf-8로 읽으므로 출력은 항상 utf-8로 고정한다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
