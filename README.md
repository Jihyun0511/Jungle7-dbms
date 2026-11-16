# Jungle7-dbms
크래프톤 정글 SW AI Lab Week 11-12 Mini DBMS

## Phase 1: SQL 처리기

```bash
python sql_processor.py input.sql
```

SQL 파일의 INSERT·SELECT를 실행한다. 테이블은 실행한 폴더의 `data/<이름>.csv`이고, 첫 줄은 스키마 헤더다.

```
id:int,name:str,age:int
1,yena,24
```

규칙의 근거(B1~B22)는 노션의 Phase 1 요구분석 문서에 있다. 각 파일 맨 위 주석에 그 파일이 지켜야 할 번호를 적어 두었다.

## 구조와 담당

```
sql_processor.py         진입점 (고치지 않음)
minidb/
  errors.py              SqlError, Position          (공용, 완성)
  statements.py          Insert, Select, Where, ...  (공용 약속, 완성)
  tokenizer.py           SQL 텍스트 → 토큰
  parser.py              토큰 → 문장 구조
  schema.py              CSV 헤더 → 스키마
  storage.py             CSV 파일 읽기·쓰기
  engine.py              문장 실행 → Result
  cli.py                 파일 읽기, 출력, 종료 코드
tests/
  conftest.py            workspace, write_table, run_cli (공용, 완성)
  test_tokenizer.py      u1~u12
  test_parser.py         p1~p8
  test_storage.py        s1~s6
  test_engine.py         e1~e12
  test_cli.py            c1~c9
data/users.csv           예시 테이블 (헤더만)
```

| 담당 | 파일 | 테스트 |
| --- | --- | --- |
|  | `tokenizer.py` | `test_tokenizer.py` |
|  | `parser.py` | `test_parser.py` |
|  | `schema.py`, `storage.py` | `test_storage.py` |
|  | `engine.py` | `test_engine.py` |
|  | `cli.py` | `test_cli.py` |

## 흐름

```
cli.main(["input.sql"])
  ├─ parse_script(text)        → [Insert, Select, ...]   문법 에러면 아무것도 실행하지 않음
  ├─ engine.run(statement)     → Result                  문장마다. 에러면 그 자리에서 멈춤
  │    └─ open_table(name)     → Table (schema, read_rows, append_rows, find_next_id)
  ├─ format_result(result)     → stdout
  └─ finally: engine.close()   에러가 나도 버퍼를 비움
```

## 모듈 사이의 약속

이름·에러 처리·배치·커밋 메시지 규칙은 [CLAUDE.md](CLAUDE.md)에 있다.

- 모듈끼리는 `statements.py`의 자료형과 각 함수의 시그니처로만 주고받는다. 바꿀 때는 관련 담당이 같이 정한다.
- 사용자에게 보여 줄 에러는 전부 `SqlError`로 던진다. 출력은 CLI만 한다 (`engine`·`storage`는 print하지 않음).
- 이름(테이블·컬럼)은 토크나이저에서 이미 소문자다. 값은 대소문자를 그대로 둔다.
- 엔진은 항상 `data/`를 쓴다. 테스트는 `workspace` 픽스처로 실행 위치를 임시 폴더로 옮겨서 진짜 `data/`를 건드리지 않는다.
- 출력(stdout·stderr)은 `sql_processor.py`에서 utf-8로 고정한다. 윈도우에서 파이프로 넘길 때 한글이 깨지지 않게 하려는 것이다.

## 테스트

```bash
python -m pytest
```

모든 테스트는 `@TODO`(skip)로 시작한다. 테스트를 작성하면 `@TODO`를 지운다. 테스트 이름의 번호(u1, e6 등)는 노션 5절 테스트 계획과 같다.

Python 3.10 이상, pytest가 필요하다 (`pip install -r requirements-dev.txt`).
