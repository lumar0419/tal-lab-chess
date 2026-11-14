# Tal Lab v0.9.3

전술 정확도를 높이는 **전술 탐색** 프로필을 추가했습니다. 선택적 탐색 위에서, 루트에서 기물을 내주는 수를 2반수 더 깊이 봅니다. 조정용 574문제에서 같은 시간 정답이 2초 260→318, 8초(절반 표본) 143→196으로 늘었습니다. 기본 탐색 경로는 그대로이며 옵션으로 켭니다. [측정 결과와 한계](VALIDATION_v093.md)

v0.9.2: 프로파일 기반 수 생성 최적화, 선택적 Cython 빌드, PyPy 비교, 가지치기 진단과 독립 방어 일관성 검증을 추가했습니다. [실제 측정 및 한계](VALIDATION_v092.md), [실행·재현 방법](PERFORMANCE_v092.md).

직접 개발한 Python 체스 엔진으로 여러 마스터의 희생수와 상대 방어를 연구하는 분석실입니다. Fischer, Kasparov, Anderssen의 실전 사례 6개와 기존 FEN 분석, 대국 화면, UCI 인터페이스를 제공합니다. 심층 연구 도구에는 9명의 마스터가 둔 23개 국면이 포함됩니다. [v0.8.8 검증 기록](VALIDATION_v088.md), [v0.8.7](VALIDATION_v087.md), [v0.8.6](VALIDATION_v086.md), [전술 분기 진단](VALIDATION_v085.md), [서버 검증 기록](VALIDATION_v084.md), [개발 기록](CHANGELOG.md)

## 실행

Python 3.12에서 검증했습니다. 웹 앱은 Python 표준 라이브러리만으로 실행됩니다.

```bash
python web_server.py --no-browser
```

브라우저에서 `http://127.0.0.1:8000/`을 엽니다. `/analysis`도 같은 분석 화면이며, `/play`에서 대국할 수 있습니다. GUI에 엔진을 연결할 때는 `python uci.py`를 사용합니다.

## 분석실 사용

- **MultiPV와 화살표**. 후보 수를 1·2·3·5개 중 고릅니다. 체스판에는 완료된 깊이의 상위 3개까지 표시됩니다. 두께와 색은 현재 둘 차례의 관점에서 최선수와의 평가 차이를 보여 줍니다. 숫자는 순위입니다. 후보 카드를 선택하면 그 수순이 표시됩니다. 기물 이동 소리는 체크박스로 켭니다.
- **CPU 선택**. 서버 CPU와 브라우저 로컬 CPU가 동일한 Tal Lab Python 엔진을 실행합니다. 브라우저 실행에는 WebAssembly와 Pyodide 0.27.7 다운로드가 필요합니다. `CPU 성능 비교`를 누르면 같은 2개 국면을 깊이 3, MultiPV 3으로 각각 3회 측정합니다. `자동`에서는 결과가 일치하고 로컬 중앙값이 서버보다 15% 넘게 짧을 때 로컬을 선택합니다. 측정 전이나 실패 시 서버를 사용합니다. 비교는 다운로드와 통신 시간을 제외합니다.
- **PGN**. UTF-8 기준 최대 128 KiB, 600반수의 표준 체스 기보 한 판을 불러올 수 있습니다. 주석과 변형 수순은 건너뛰고 본 수순을 검증합니다. 수 목록이나 탐색 버튼으로 원하는 시점으로 이동합니다. 평가 그래프는 실제로 분석한 국면만 표시합니다. 이전 국면에서 새로운 수를 두면 그 지점부터 새 수순으로 이어집니다.
- **희생 연구**. 분석을 중단한 뒤 `희생 찾기`를 누르면 상대가 즉시 수락할 수 있는 기물 희생을 검색합니다. `후보 검증`에서는 수락·거절 방어와 예상 수순을 최대 세 줄 표시합니다. 메이트 점수가 나오면 최대 7반수에서 합법 방어를 전부 확인합니다. 서버는 약 5초의 예산을 사용합니다. 검증 결과와 범위는 [v0.9.0 검증 기록](VALIDATION_v090.md)에 있습니다.
- **UCI MultiPV**. `setoption name MultiPV value 3`으로 바꾸면 완료한 깊이마다 추천수 세 줄을 보냅니다. 설정 범위는 1–5입니다.

최소 깊이는 목표입니다. 시간 상한에 도달하면 마지막으로 모든 후보를 계산한 깊이를 사용합니다. 메이트 점수는 폰 단위 점수와 별도로 읽으세요. 브라우저 모드는 분석 계산을 로컬에서 수행하며 기보와 국면 조작에는 사이트 API를 사용합니다.

## 심층 분석

분석 화면의 **심층 분석**을 열고 60·180·300·600초를 선택합니다. 전체 합법수는 MultiPV 1로 탐색하고, 즉시 수락 가능한 희생 후보와 이전에 앞섰던 수는 독립적으로 다시 계산합니다. 비교할 수에 UCI 수를 넣을 수도 있습니다. 후보 간 평가는 공통으로 완료한 깊이에서 읽으세요. 상대 차례에서도 별도로 탐색하므로 같은 후보의 방어 점수는 루트 점수와 다를 수 있습니다.

기본 방식은 v0.9.3부터 **전술 탐색**입니다(아래 절 참고). **보수적 LMR**은 비PV 노드의 늦은 조용한 수만 한 반수 줄여 보고, 알파를 넘을 때 본래 깊이로 재탐색합니다. 기본 탐색과 전체 선택적 탐색도 선택할 수 있습니다. 짧은 메이트를 확정할 때는 합법 방어 전수 검사와 무승부 청구를 적용합니다. 나머지 결과에는 깊이, 수순, 평가와 기물 손실이 기록됩니다. 후보와 실제 전체 탐색 1위는 화면에서 따로 표시합니다.

서버 CPU 심층 분석은 다른 사용자의 빠른 분석·대국이 들어오면 중단되고 이미 완료된 결과가 남습니다. 로컬 CPU는 웹 워커를 사용하고 **중단** 버튼으로 멈춥니다. **분석 JSON 저장**으로 재검토할 수 있습니다.

```bash
python -m deep_analysis --fen "b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24" --seconds 600 --candidate d1d4 --output rxd4.json
```

지정 수를 생략하면 후보를 자동으로 선정합니다. `--moves`로 시작 FEN에서 UCI 착수 이력을 재현할 수 있습니다. [심층 탐색 검증과 미해결 국면](VALIDATION_v091.md)

## 전술 탐색 (v0.9.3)

희생 수는 보상이 몇 수 뒤에야 드러나서, 같은 깊이로 보면 "기물만 잃는 수"로 평가되기 쉽습니다. 전술 탐색은 선택적 탐색으로 깊이를 벌고, 루트에서 그 칸의 교환으로 100cp 이상 손해인 수(SEE ≤ −100)를 2반수 더 깊이 탐색합니다. 가지를 더 버리지는 않습니다. 희생이 아닌 수는 같은 시간에 명목 깊이가 약 1 낮아집니다.

- **분석 화면**. `전술 탐색 (희생 수 연장)` 체크박스. 최대 깊이 상한에 3반수를 더해 시간 상한까지 계산합니다.
- **심층 분석**. 탐색 방식의 첫 항목 `전술 탐색`. 명령줄은 `--profile tactical`.
- **대국 화면**. `전술 탐색 (희생 수 연장)` 체크박스.
- **UCI**. `setoption name TacticalSearch value true`. 끄면 `SelectiveSearch` 설정으로 돌아갑니다.
- **코드**. `Searcher().set_tactical(True)`. 값은 `search.TACTICAL_PROFILE`.

```bash
python -m research.suite_runner run --suite evidence/v088/suite.json --output tactical.json --seconds 2 --profile tactical
python -m research.ladder_v093 --case kasparov_topalov_1999_ply47 --profile tactical --seconds 300 --output rxd4.json
```

선택적 가지치기의 알려진 위험(조용한 준비 수 누락)은 그대로 남습니다. 표시되는 깊이는 전폭 깊이가 아닙니다.

## 선택적 탐색 (SelectiveSearch)

선택적 탐색은 같은 시간에 더 깊이 도달할 수 있는 실험 설정입니다. 정적 탐색에서 체크하는 캡처와 킹 인접 캡처, 앙파상, 승격을 보존합니다. 루트 쪽이 기물을 내준 수순은 루트에서 3반수까지 일부 가지치기에서 보호합니다. 정답률과 완료 깊이 비교는 [v0.8.9 검증 기록](VALIDATION_v089.md)에 있습니다.

- **UCI**. 기본값은 꺼짐입니다. `setoption name SelectiveSearch value true`로 켤 수 있습니다.
- **분석 화면**. `SelectiveSearch (실험)` 체크박스로 켤 수 있습니다.
- **대국 화면**. `깊은 전술 탐색` 체크박스로 켜면 깊이 상한에 3반수를 더합니다.
- **코드**. `Searcher().selective = True`. `Searcher()`의 기본값은 전폭 탐색입니다.

전술 모음으로 두 설정을 비교하려면 다음을 실행합니다.

```bash
python -m research.suite_runner run --suite evidence/v088/suite.json --output full.json --seconds 1 --only wac
python -m research.suite_runner run --suite evidence/v088/suite.json --output selective.json --seconds 1 --only wac --profile selective
python -m research.suite_runner compare --suite evidence/v088/suite.json full.json selective.json
```

## 심층 희생 연구

임의 FEN에서 Tal Lab만 사용해 후보를 먼저 발견하고, 각 후보 뒤 모든 합법 방어를 대상으로 평가합니다.

```bash
python -m research.deep_sacrifice --fen "4kb1r/p2n1ppp/4q3/4p1B1/4P3/1Q6/PPP2PPP/2KR4 w k - 0 16" --seconds 5 --depth 8 --output opera.json
```

`--move b3b8`처럼 입력하면 일반 탐색을 먼저 완료한 뒤 지정 수도 비교합니다. `--seconds`는 각 탐색의 시간 상한입니다. 여러 후보와 비교 탐색을 실행하므로 전체 소요 시간은 더 길 수 있습니다. `--multipv 1`로 한 후보에 계산 시간을 집중할 수 있습니다. `--check-continuation`은 정적 탐색에서 연속 체크를 비교하는 실험 옵션입니다. `--profile selective`는 후보 발견과 지정 수 탐색에 선택적 탐색을 씁니다. 결과에는 완료 깊이, 평가 차이, 상대 방어 후보, 판정의 근거와 증명 범위가 기록됩니다.

## 기존 GitHub와 Render에 반영

GitHub `lumar0419/tal-lab-chess`의 기준 커밋은 `4b91b757a49b2b33ae1fdbebd00fd350bc905442`입니다. 패키지의 `tal-lab-chess/`는 최신 소스입니다. 기존 저장소에서는 현재 체크아웃에 맞는 패치를 골라 적용하세요.

| 현재 체크아웃 | 패치 |
|---|---|
| GitHub main의 기준 커밋 | `patches/github-main-to-v0.9.1.patch` |
| v0.9.0 개발판 `af02d34` | `patches/v0.9.0-to-v0.9.1.patch` |

```bash
git switch -c development/deep-tactical-v091
git apply --check --whitespace=nowarn /path/to/github-main-to-v0.9.1.patch
git apply --index --whitespace=nowarn /path/to/github-main-to-v0.9.1.patch
git commit -m "Integrate Tal Lab v0.9.1"
```

검사에서 충돌하면 현재 소스와 패치를 비교하세요. 기존 Render 서비스는 같은 `render.yaml`, `cloud_server.py` 시작 명령과 환경변수 이름을 사용합니다. 배포 후 로그인, `/analysis`, `/play`, `/healthz`를 확인하세요. 재시작하면 메모리에 있던 국면과 진행 중 분석이 초기화됩니다.

## 검사 재현

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -q
python test_engine.py --full
python test_uci.py
node test_visuals.js
node test_frontend.js
python perft.py
python -m research.measure_search --baseline /path/to/v081 --seconds 1 --repeats 2 --output one-second-ab.json
python -m research.deep_benchmark --baseline /path/to/v081 --stockfish /path/to/stockfish --reference-seconds 8 --output kasparov-timed.json
python -m research.diagnose_kasparov --stockfish /path/to/stockfish --output kasparov-diagnostic.json
python -m research.deep_sacrifice --baseline /path/to/v081 --stockfish /path/to/stockfish --seconds 1.5 --reference-seconds 2 --depth 8 --output historical-ab.json
```

`chess` 패키지와 Stockfish 실행 파일은 검증에 사용합니다. Stockfish 비교를 실행하려면 별도로 설치한 실행 파일 경로를 지정하세요.
