# 성능과 실행 환경 — v0.9.4-dev

기존 엔진 코어의 기본 평가·탐색 정책을 변경하지 않았다. 이번 측정은 사용 가능한 실행 환경과 후보 기능의 비용을 확인하는 것이며, v0.9.3 대비 새 속도 개선을 주장하지 않는다.

## 환경과 CPU profile

CPython 3.12.14, PyPy Python 3.11.17 / PyPy 8.0.1, Cython 3.1.8, Pyodide 0.27.7을 사용했다. OS/CPU/Stockfish 바이너리 출처·SHA-256은 `evidence/v094/environment.json`, 외부 엔진 커밋은 `external-sources.json`이다. 세 CPU에 작업을 고정하여 동시에 다른 실험이 실행된 구간이 있다. 서로 다른 코어라도 공유 host 부하와 cache 영향을 완전히 제거하지 못하므로 작은 시간 차이를 채택 근거로 쓰지 않았다. 중단 후에도 완료된 원시 결과를 재사용하고 미완료 검사만 이어갔다.

`research.profile_v092 --selective --depth 5`의 Kasparov 국면에서 self time 상위는 pseudo-legal movegen(0.366s), 공격 판정(0.320s), unmake(0.286s), QS(0.248s), make(0.226s), negamax(0.218s)였다. evaluate_white는 self 0.187s / cumulative 0.289s다. 계측된 시간이므로 일반 NPS와 직접 비교하지 않는다. 평가만 native로 바꿔 모든 병목을 해결할 수 없다는 근거다. 전체 함수별 자료는 `profile-baseline.json`.

## 같은 코드·같은 고정 깊이

역사 국면 4개 × 깊이 4, warmup 1회 뒤 3회 측정. 각 반복은 새 Searcher, 보수적 LMR, pawn cache 초기화이며 TT 300,000이다. NPS는 전체 측정 노드 합 / 전체 시간 합이다. 매우 짧고 얕은 표본이며 PyPy JIT 상태, 장기 검색, 실제 게임 NPS에 일반화하지 않는다.

| 실행 | 측정 12회 합계 초 | aggregate NPS | CPython 대비 |
|---|---:|---:|---:|
| python | 9.258 | 49,838 | 1.00× |
| pypy | 3.394 | 135,957 | 2.73× |
| native | 4.939 | 93,425 | 1.87× |

모든 반복의 **최선수·점수·PV·노드 수가 세 런타임에서 일치**했다. PyPy가 빠르다는 사실만으로 평가 정확도 개선이나 Elo 향상을 주장하지 않는다.

Cython은 기존 `tools/build_native.py`로 동일 소스만 별도 컴파일했다. 기본 compiler 설정의 clang이 없어 첫 빌드 시도는 실패했으며, 설치된 gcc로 `CC=gcc LDSHARED='gcc -shared'`를 지정해 성공했다. 런타임 loader의 소스 해시/ABI 검사는 유지한다. 바이너리는 커밋하지 않는다. native package 버전은 `version.py`와 일치하게 했다.

## 후보 평가 비용

기존 전술 표본 32개·2초와 새 quiet 표본 48개·1초에서 B/C/D 후보의 NPS는 기준의 대략 절반이었다. 현재 연구 구현은 항목 추출과 안전 mobility의 ray scan을 매 평가마다 수행한다. 값의 효과와 비용을 분리하기 위해 실전 진단 12개에서는 고정 100,000노드 비교도 했다. 고정 노드에서 좋은 판단이 나와도 동일 시간에 완료 깊이가 낮아지면 실제 사용에서는 손해일 수 있다.

F(quiet futility/LMP 끔)의 NPS는 오히려 높았지만 이것은 더 단순한 노드를 많이 탐색하는 효과와 노드 구성이 섞여 있다. 노드 감소, 완료 깊이, 전술 정확도, 실제 대국 개선과 동일한 지표가 아니다. F를 속도 최적화로 채택하지 않았다.

## 호환성 확인 범위

- CPython/Cython 전체 unittest, 빠른 엔진 회귀, UCI, perft/hash, frontend 계약 검사 결과는 `VALIDATION_v094.md`에 기록.
- 독립 python-chess oracle: 1,996국면, 61,907 make/unmake 간선, 255,488 공격 판정. CPython/Cython digest가 동일하다.
- PyPy 전체 unittest를 별도 실행. 개발용 python-chess는 순수 Python 의존성으로 별도 경로에 설치했다.
- Node에서 **실제 Pyodide 0.27.7**을 로드하고 worker의 allowlist 소스를 사용했다. MultiPV, 옵션 전환, 심층 분석의 메이트 증명, 새 평가 상세/착수 전후 JSON이 CPython과 일치했다. 이것은 WASM 런타임 검증이며 실제 Chrome 화면 렌더링/상호작용 전체를 검사했다는 뜻은 아니다.
- 로컬 HTTP/클라우드 세션·인증·취소 테스트를 유지했다. Render에 배포하지 않았고 두 기존 사이트의 설정도 수정하지 않았다. Windows native 빌드는 이번에 실행하지 않았다.
- production은 표준 라이브러리만 필요하다. NumPy/Zstandard/python-chess는 연구 및 검증용이다.

## 실행 예

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python web_server.py --no-browser
python uci.py

# 선택적 native 실행 (gcc가 설치된 Linux 예)
pip install Cython==3.1.8 setuptools wheel
CC=gcc LDSHARED='gcc -shared' python tools/build_native.py build_ext --build-lib build/native
python native_engine.py uci

# 연구 도구 의존성만 추가
pip install -r requirements-research-v094.txt
python -m research.texel_v094 fit --input evidence/v094/texel-data.json.gz --output fit.json
```

재현 명령 전체와 각 파일의 의미는 `evidence/v094/README.md`에 있다. 평가 설명은 요청 시에만 계산하고 검색 hot path에 추가하지 않았다. 정적 evaluator fast path는 기존 그대로이며 trace 추가 필드도 trace가 켜질 때만 할당한다.
