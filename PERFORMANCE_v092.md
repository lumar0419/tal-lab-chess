# Tal Lab v0.9.2 실행과 재현

기본 실행은 기존 Python 엔진입니다. Stockfish 코드를 엔진에 넣지 않았습니다.
`evaluate.py`의 평가 공식과 점수는 유지하며, 희생 보너스를 추가하지 않았습니다.
실제 측정 결과와 미해결 문제는 `VALIDATION_v092.md`, 원시 자료는 `evidence/v092/`를 참고하세요.

## 개발 기준과 변경 검토

GitHub에서 확인한 `main`은 `4b91b757a49b2b33ae1fdbebd00fd350bc905442`이며 README 기준 v0.5.5입니다.
원격 브랜치는 main 하나였습니다. 제공 ZIP에는 `.git`이 없었으므로 ZIP의 기존 커밋 이력을 복원했다고 주장하지 않습니다.
원격 이력 위에 ZIP 전체를 보존한 기준 커밋은 `4fa222e`입니다.
기존 v0.9.0 보고서가 가리키는 `af02d346...`는 원격에서도 가져올 수 없어 재측정하지 않았습니다.
작업 브랜치는 `development/performance-accuracy-v092`입니다. main과 Render는 변경하거나 배포하지 않았습니다.

GitHub 개발 브랜치와 보고서에 기록한 v0.9.1 기준 커밋을 비교해 변경을 검토할 수 있습니다.
로컬 작업의 커밋 ID와 GitHub API로 옮긴 커밋 ID는 다를 수 있으며, 각 단계의 tree SHA 일치를 검증합니다.
원격 커밋 매핑은 `evidence/v092/remote-provenance.json`에 기록합니다.

```sh
git fetch origin development/performance-accuracy-v092
git switch --track origin/development/performance-accuracy-v092
```

제공하는 비교 패치는 **ZIP v0.9.1과 동일한 트리의 기준 커밋** 이후 변경입니다.
현재 GitHub main에 직접 적용하는 패치가 아닙니다. 전체 소스 ZIP에는 기존 소스와 테스트,
기존 검증 자료도 포함합니다. 컴파일 산출물과 외부 실행 파일은 포함하지 않습니다.
기준 벤치마크를 다시 실행하려면 다음 v0.9.1 원격 커밋으로 별도 worktree를 만드세요.

```sh
git worktree add --detach ../baseline-v091 2d5f6ced5a74fee37ba531d55d64e4e1b9882cb0
```

## 실행 방식

| 환경 | 명령 | 구현 |
|---|---|---|
| 기본 UCI | `python uci.py` | Tal Lab Python |
| 기본 로컬 웹 | `python web_server.py --no-browser` | Tal Lab Python |
| PyPy UCI | `pypy3 uci.py` | 같은 Python 소스 / PyPy JIT |
| PyPy 서버 | `pypy3 cloud_server.py` | 같은 Python 소스 / PyPy JIT |
| Cython UCI | `python native_engine.py uci` | 동일 board/evaluate/search 소스의 컴파일 결과 |
| Cython 웹 | `python native_engine.py web_server --no-browser` | Cython 엔진과 기존 Python 웹 서버 |
| Cython 서버 | `python native_engine.py cloud_server` | Cython 엔진과 기존 Python 서버 |
| 브라우저 로컬 CPU | 기존 로컬 CPU 선택 | Python / Pyodide 0.27.7 |

분석 화면과 API의 `engine_implementation`은 실제로 불러온 엔진 구현을 표시합니다.
서버/브라우저의 알고리즘과 평가는 같아도 런타임과 시간제한에 따라 완료 깊이는 다를 수 있습니다.
PyPy는 JIT 준비 시간과 높은 메모리 사용량을 함께 고려해야 합니다. 서버 시작 명령과 Render 설정은 자동 변경하지 않았습니다.

## 선택적 Cython 빌드

```sh
python -m pip install Cython==3.1.8 setuptools wheel
python tools/build_native.py build_ext --build-lib build/native
python native_engine.py uci
```

Linux에서 Python의 기본 빌드 설정이 설치되지 않은 clang을 가리킨다면:

```sh
CC=gcc LDSHARED='gcc -shared' python tools/build_native.py build_ext --build-lib build/native
```

Windows는 CPython 및 Visual Studio C++ Build Tools가 필요합니다. 빌드 명령은 같습니다.
이번 환경에서 Windows 빌드/실행을 직접 확인하지는 못했습니다. 수동 실행용 Windows/Linux CI를
`.github/workflows/native.yml`에 추가했지만, 아직 실행된 결과로 취급하지 않습니다.

`build/native/manifest.json`의 소스 해시와 Python ABI를 확인하고, 파일이 바뀌거나 모듈이 누락되면 실행을 거절합니다.
소스 수정 후에는 다시 빌드해야 합니다. `.so`/`.pyd`를 원본 옆에 설치하지 않으므로 기존 Python 경로와
브라우저 소스를 그대로 유지합니다. Pyodide에서는 이 네이티브 확장을 사용하지 않습니다.

C++/Rust 별도 재구현은 검토만 했습니다. 현재 10×12 mailbox와 Python 객체 API를 유지할 때 경계 변환과
두 구현의 유지 비용이 커서, 같은 소스를 컴파일하는 Cython을 먼저 시험했습니다. 별도 C++/Rust 엔진은 구현하지 않았습니다.
증분 평가나 비트보드 전체 재작성도 하지 않았습니다. 측정된 이득과 정확성 검증이 있는 변경만 포함합니다.

## 프로파일과 비교

검증용 의존성은 엔진 실행에는 필요하지 않습니다.

```sh
python -m pip install chess==1.11.2
python -m research.profile_v092 --output evidence/v092/reprofile.json
python -m research.profile_v092 --selective --output evidence/v092/reprofile-selective.json
python -m research.compare_v092 --baseline ../baseline-v091 --repeats 3 --output evidence/v092/refixed-python.json
python -m research.compare_v092 --baseline ../baseline-v091 --native --repeats 3 --output evidence/v092/refixed-native.json
python -m research.runtime_bench_v092 --output evidence/v092/reruntime-python.json
pypy3 -m research.runtime_bench_v092 --output evidence/v092/reruntime-pypy.json
python native_engine.py research.runtime_bench_v092 --output evidence/v092/reruntime-native.json
```

같은 CPU 코어에서 순차 실행하세요. 본 측정은 Linux의 서로 다른 코어에 장시간 분석과 비교 배치를
각각 고정했으며 총 CPU 사용량은 환경의 두 코어 예산 안에서 유지했습니다. 작은 시간 차이는
공유 호스트 부하를 포함할 수 있습니다. NPS만으로 기력을 판단하지 않습니다.
프로파일러 시간은 호출 경로와 비용 분포를 분석하는 자료이며, 속도 향상률은 프로파일러 없는 반복 측정에서 계산합니다.

## 정확성 및 전술 측정

```sh
python -m unittest discover -q
python native_engine.py unittest discover -q
python -m research.uci_backend_v092
python test_engine.py --quick
python test_uci.py
python perft.py
node test_frontend.js
node test_visuals.js
python -m research.validate_backend_v092 --output oracle-python.json
python native_engine.py research.validate_backend_v092 --output oracle-native.json
python -m research.suite_v092 --source ../baseline-v091 --suite evidence/v092/holdout.json --output reholdout-v091.json
python -m research.suite_v092 --suite evidence/v092/holdout.json --output reholdout-python.json
pypy3 -m research.suite_v092 --suite evidence/v092/holdout.json --output reholdout-pypy.json
python -m research.suite_v092 --native --suite evidence/v092/holdout.json --output reholdout-native.json
```

`evidence/v091/holdout.json`도 이제는 기존 회귀 자료입니다. 새 v0.9.2 holdout과 섞지 않습니다.
새 표본은 Lichess CC0 퍼즐에서 기존 JSON의 게임/FEN을 제외하고 엔진 결과를 보기 전에 고정했습니다.
선정 원본과 제외 수, 해시는 `holdout.source.json`, `holdout.provenance.json`에 보존했습니다.
연속 희생은 원본 풀이에서 두 번 이상의 손해 교환을 독립적으로 검사했습니다.
포지셔널 범주는 조용한 비강제 장기 희생의 대리 지표로, 엄밀한 포지셔널 희생 정답 자료가 아닙니다.
한 유형당 4개라는 작은 표본으로 일반적인 정확도나 Elo 개선을 확정하지 않습니다.

## 장시간 분석과 방어 검증

```sh
python -m research.ladder_v092 --source ../baseline-v091 --seconds 600 --output ladder-old.json
pypy3 -m research.ladder_v092 --seconds 600 --output ladder-pypy.json
python -m deep_analysis --fen "b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24" --seconds 600 --output deep-600.json
pypy3 -m research.workflow_v092 --case rotlewi_rubinstein_1907_ply44 --seconds 180 --output rubinstein.json
```

`ladder`의 60/180/300/600초는 한 600초 실행의 체크포인트입니다. 별도 시간제한 반복 실험으로 표현하지 않습니다.
후보 지정은 이후 진단 비교에만 영향을 주며, 최초 전체 합법수 탐색 결과를 덮어쓰지 않습니다.
일반 루트에 64% 예산을 먼저 보장하고 후보끼리는 동일 시간·동일 TT 시작 상태를 유지합니다.
그 뒤 남은 예산의 더 큰 부분을 독립 방어에 남겨두며, 모든 후보에게 균등 몫을 보장한 후 평가 변동·응수 변동·근접 점수에 추가 시간을 배정합니다.
희생 여부는 추가 시간 가중치에 들어가지 않습니다. `adaptive=False`로 기존 분할과 비교할 수 있습니다.

`consistency`는 같은 명목 깊이에서의 응수와 백 점수를 비교합니다. 루트 체크 연장과 메이트 거리도 보정합니다.
`deepest_defense_verified`는 후보의 가장 깊은 결과까지 일치하는 경우에만 참입니다.
독립 탐색은 TT/탐색 순서와 루트 위치가 달라지므로, 선택적 탐색의 일치를 수학적 전술 증명으로 해석하지 않습니다.
강제 메이트 전수 증명은 기존 7반수/25,000노드 상한을 유지합니다.

## 선택적 가지치기 진단

```sh
python -m research.pruning_trace --fen FEN --seconds 5 --output trace.json
python -m research.pruning_trace --replay trace.json --index 0 --seconds 10 --output replay.json
```

기본 탐색에서 진단은 꺼져 있습니다. 켜면 이유, FEN, 수, 깊이, ply, alpha/beta, 정적 평가,
축소량, null 시험 점수, 이력과 노드를 기록합니다. 저장 상한을 넘은 기록은 개수만 셉니다.
기존 5인자 `selective_trace` 콜백도 유지합니다. replay는 새 TT/전체 창에서 해당 분기를 강제로
계산하는 반사실 비교이며, 과거 TT/창/탐색 순서를 완전히 재현하는 기능은 아닙니다.

전체 선택적 모드의 RFP/Null/LMR/Futility/LMP/IIR/QS 컷에는 여전히 전술 누락 위험이 있습니다.
기본 빠른 분석과 보수적 심층 프로필에 새 공격적 가지치기를 추가하지 않았습니다.
반복에 관한 탐색 내부의 2회 근사도 유지합니다. TT의 검색 간 무승부 이력 오염은 차단했지만,
모든 경로의 그래프 이력 의존성까지 완전히 제거한 증명은 아닙니다.

명시적 Kasparov 수락 후 Re7+ 분기는 다음 입력으로 재현할 수 있습니다.

```sh
pypy3 -m research.probe_search < evidence/v092/kasparov-re7-task.json
```
