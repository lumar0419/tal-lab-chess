# v0.9.4 원시 결과와 재현

최종 해석은 [VALIDATION_v094.md](../../VALIDATION_v094.md). 완료된 측정과 미실행 항목을 구분한다. 기본 evaluator/search 정책은 v0.9.3과 같고, 검증 실패 후보는 연구 실행기에만 있다.

## 파일 지도

| 자료 | 내용 |
|---|---|
| `environment.json`, `external-sources.json`, `data-license.json` | 실행 환경, SF 바이너리 hash/URL, 외부 소스 고정 커밋, 데이터 CC0 고지 |
| `diagnostic-v093-60s.json` | 두 PGN 전체 재생 FEN, 12개 주요 국면의 실제 history·MultiPV 1/2·60초 기준선 |
| `diagnostic-v093-100kn.json`, `stockfish-100kn.json` | 같은 100,000노드 제한(서로 같은 계산량이라는 뜻은 아님) |
| `stockfish-3s.json` | 21개 국면 루트 MultiPV 3 + 실제 수 강제, 각각 3초 |
| `ablation-diagnostic-100kn.json` | 주요 12개 × 8설정, 이전 수순 복원, 동일 노드 |
| `ablation-tactics-2s.json` | 이전 holdout 32 × 8설정, 2초 |
| `positional-suite.json`, `ablation-positional-1s.json`, `reference-positional.json` | 새 quiet 48 × 8설정, 1초, SF 루트/서로 다른 후보 강제 각각 1초 |
| `texel-data.json.gz`, `texel-data-manifest.json`, `texel-fit.json` | 9,297개 데이터 행, 출처/필터/분리, 모든 학습 pass와 선택 결과 |
| `match-candidate.*`, `match-final.*` | 각각 20판, 색 교환 10오프닝, 5초+0.05초, PGN/CSV/JSON/log |
| `historical-v093-1mn.json`, `historical-v094-1mn.json` | 4개 역사 국면 100만노드, 수/점수/PV/노드 동일성 |
| `historical-v094-60s-pypy.json` | 최종 엔진 PyPy 60초, 역사적 수의 발견 과정 |
| `runtime-{python,pypy,native}.json`, `runtime-parity.json` | 고정 깊이 runtime 비교, 실제 Pyodide와 CPython JSON 일치 |
| `oracle-{python,native}.json` | 독립 규칙 oracle digest |
| `diagnostic-trace-v094.json` | 제공된 기보에서 생성한 FEN/history로 수집한 bounded trace; 국면별 최대 100건, 나머지 dropped 수 기록 |
| `profile-baseline.json/.prof`, `summary.json` | CPU 함수별 profile, 원시 자료에서 재계산한 집계 |
| `*-unittest.log`, `final-*.log`, `positional-tests.log` | 회귀 결과. `uci-concurrent-attempt.log`는 대국 잠금 충돌로 실패한 첫 시도, `final-uci.log`는 종료 뒤 71/71 통과 재실행 |

점수 방향은 파일 schema를 확인한다. diagnostics와 ablation 최종 `score_white`는 백 기준, 역사 기록의 `score`와 ablation iteration의 `score`는 둘 차례 기준이다. mate는 cp와 별개다. 여러 예산/설정의 raw row를 합쳐 하나의 정확도나 Elo라고 부르지 않는다.

## 준비

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pip install -r requirements-research-v094.txt
git worktree add --detach ../tal-v093 af201fb488e4ef74f35f519fb61f4081df9b184c
# 공식 sf_19 Linux universal 압축을 받아 푼 실행 파일의 경로
export TAL_SF=/absolute/path/to/stockfish-linux-x86-64-universal
```

SF 다운로드 URL와 실제 파일 hash는 `environment.json`에 있다. 실행 파일과 외부 엔진/모델은 저장소에 포함하지 않는다. 연구 의존성은 production에 필요하지 않다. 원래 실험은 CPU affinity 0/1/2로 다른 작업을 분리했고 동시 host 부하가 있었으며, 재실행 시간 결과는 달라질 수 있다.

## PGN과 Stockfish 진단

```bash
python -m research.diagnostics_v094 --replay-only --output replay.json
python -m research.diagnostics_v094 --engine ../tal-v093 --seconds 60 --output baseline-60s.json
python -m research.diagnostics_v094 --engine ../tal-v093 --nodes 100000 --output baseline-100kn.json
python -m research.diagnostics_v094 --stockfish "$TAL_SF" --reference-seconds 3 --output sf-3s.json
python -m research.diagnostics_v094 --stockfish "$TAL_SF" --nodes 100000 --output sf-100kn.json
python -m research.diagnostics_v094 --seconds 1 --trace-limit 100 --output trace.json
```

최초 baseline raw의 MultiPV 2 iteration에는 1순위 callback과 전체 group callback이 같은 깊이에 각각 남아 있을 수 있다. 최종 group/결과는 동일하다. 현재 harness는 전체 group만 기록하도록 정리했다. 탐색 정책/노드/최종 점수 변화는 없다.

## 데이터 준비와 튜닝

```bash
mkdir -p work
curl -L https://database.lichess.org/standard/lichess_db_standard_rated_2013-01.pgn.zst -o work/lichess-2013-01.pgn.zst
OPENBLAS_NUM_THREADS=1 python -m research.texel_v094 prepare \
  --input work/lichess-2013-01.pgn.zst --games 10000 --seed 9417 --output work/texel-data.json
OPENBLAS_NUM_THREADS=1 python -m research.texel_v094 fit \
  --input evidence/v094/texel-data.json.gz --output work/texel-fit.json
```

학습 데이터 제외 목록은 v090/v091/v092/v093의 JSON과 사용자 PGN에 고정한다. v094의 자기 출력물을 다음 준비 실행에서 제외하지 않아 재현 시 표본이 바뀌지 않는다. 원본 archive SHA-256은 manifest에 있다. 입력 JSON이 게임을 다른 split에 중복 배치하거나 동일 국면을 반복하면 fit이 거부한다. validation으로 계수를 선택한 뒤 test loss를 계산한다. 결과를 `evaluate.py`에 자동 적용하지 않는다.

48개 quiet suite의 선택은 test 행 순서를 유지해 `rows[::max(1,len(rows)//48)][:48]`이며, id는 `quiet_holdout_00`부터 붙인다. 원시 데이터의 FEN과 game hash를 그대로 사용했다. 이미 확정해 저장한 `positional-suite.json`으로 후속 실험을 재현할 수 있다.

## Ablation

```bash
python -m research.ablation_v094 --suite evidence/v092/holdout.json --seconds 2 --output tactics.json
python -m research.ablation_v094 --suite evidence/v094/user-suite.json --nodes 100000 --output diagnostics.json
python -m research.ablation_v094 --suite evidence/v094/positional-suite.json --seconds 1 --output positional.json
python -m research.reference_positional_v094 --suite evidence/v094/positional-suite.json \
  --ablation positional.json --stockfish "$TAL_SF" --seconds 1 --output reference.json
python -m research.summarize_v094
```

A/B/C/D/E/F/G/conservative의 정의는 최상위 validation 문서. 순서 효과를 줄이기 위해 국면마다 실행 순서를 회전했다. `summarize_v094`는 저장된 evidence 파일명을 입력으로 사용한다. 원시 파일을 덮어쓰지 않으려면 복사한 checkout에서 재측정한다.

## 대국

같은 컴퓨터에서 `match.py` 실험은 한 번에 하나만 실행한다. **`test_uci.py`도 내부에서 match.py fault 테스트를 실행하므로 실제 대국과 동시에 돌리지 않는다.**

```bash
python match.py \
  --engine1 "python -m research.candidate_uci_v094 --no-quiet-pruning" \
  --engine2 "python ../tal-v093/uci.py" \
  --opt1 TacticalSearch=true --opt2 TacticalSearch=true \
  --games 20 --tc 5+0.05 --seed 9417 --label v094-no-quiet-pruning-screen --pgn candidate.pgn
python match.py --engine1 "python uci.py" --engine2 "python ../tal-v093/uci.py" \
  --opt1 TacticalSearch=true --opt2 TacticalSearch=true \
  --games 20 --tc 5+0.05 --seed 9421 --label v094-final-v093-regression --pgn final.pgn
```

이것은 fixed-budget screening/회귀이며 SPRT나 수당 60초 대국이 아니다. 추후 SPRT는 fastchess의 검증된 paired 통계를 사용하고, 가설/시간/오프닝/판수 상한을 먼저 고정해야 한다. 이번에 승인된 Elo 개선치는 없다.

## 역사·런타임·회귀

```bash
pypy3 -m research.historical_v094 --source ../tal-v093 --nodes 1000000 --output old-history.json
pypy3 -m research.historical_v094 --nodes 1000000 --output new-history.json
pypy3 -m research.historical_v094 --seconds 60 --output history-60s.json
python -m research.profile_v092 --depth 5 --selective --output profile.json
python -m research.runtime_bench_v092 --depth 4 --warmups 1 --repeats 3 --output python.json
pypy3 -m research.runtime_bench_v092 --depth 4 --warmups 1 --repeats 3 --output pypy.json
pip install Cython==3.1.8 setuptools wheel
CC=gcc LDSHARED='gcc -shared' python tools/build_native.py build_ext --build-lib build/native
python native_engine.py research.runtime_bench_v092 --depth 4 --warmups 1 --repeats 3 --output native.json
python -m unittest discover -q
python native_engine.py unittest discover -q
pypy3 -m unittest discover -q  # PyPy에도 python-chess 개발 의존성 필요
python test_engine.py --quick
python test_uci.py
python perft.py
python -m research.validate_backend_v092 --output oracle-python.json
python native_engine.py research.validate_backend_v092 --output oracle-native.json
node --check web/analysis.js
node --check web/engine-worker.js
node test_frontend.js
node test_visuals.js
npm install --prefix work/pyodide pyodide@0.27.7
TAL_PYODIDE="$PWD/work/pyodide/node_modules/pyodide" TAL_PYTHON=python node research/runtime_parity_v094.cjs
```

Runtime parity 도구는 `evidence/v094/runtime-parity.json`을 기록한다. 실제 Pyodide와 CPython을 비교하지만 실제 Chrome UI 전체 자동화는 아니다. Render 배포, Windows native, NNUE 학습/추론은 이번에 실행하지 않았다.
