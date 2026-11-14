# MyEngine v0.4.7 — 실제 미하일 탈 기보 기반 공격 스타일 진단

이 프로젝트는 **기존 단 하나의 체스 엔진** v0.4.6을 이어서 개발한 버전입니다. 이번 업데이트에서는 객관적으로 입증되지 않은 희생 보너스나 무조건적인 공격 선호를 엔진에 넣지 않고, **탈의 실제 수 선택이 이루어진 국면을 재현하고 평가하는 도구**를 추가했습니다.

## 1. 새로 추가된 기능

- `tal_games.json`: 공개 기보에서 확보한 탈의 실제 **4개 대국**, 전체 수순을 UCI 수 형식으로 기록. 탈이 백 또는 흑으로 둔 게임 모두 포함.
- `tal_positions.json`: 그 대국들에서 추출한 **22개 역사적 판단 국면(FEN)**, 탈이 실제로 선택한 수, 주제, 출처를 기록.
- `tal_style_benchmark.py`: `Board`의 전체 합법수 생성으로 **모든 수순을 처음부터 재생**해 FEN·역사적 수의 일치를 확인하고, **현재 하나의 엔진**에서 평가 옵션만 바꿔 동일 깊이 탐색 비교. 기존 설정에 변경을 남기지 않음.
- `test_tal_style.py`: 기보 재생 및 데이터 손상 탐지, 22개 수의 합법성, 색상·메타데이터, 전역 옵션 복원, 제한 탐색 및 출력 등을 검증하는 **7개 신규 테스트**.
- `tal_benchmark_depth3.json`: 전체 22개 국면에 대한 baseline/combined 깊이 3 실측 결과.
- `tal_benchmark_featured_depth4.json`: 대표 희생 국면 4개에 대한 baseline/combined 깊이 4 실측 결과.

이번 버전은 **탐색이나 평가의 수식을 바꾸지 않았습니다**. `search.py`와 `uci.py`에 표시된 버전만 0.4.7로 올렸으며, 나머지 엔진 코드는 v0.4.6과 동일합니다. 해당 검사 도구의 목적은 **탈의 스타일을 목표로 앞으로 무엇을 고칠지 측정하는 기준선**을 만드는 것입니다.

## 2. 자료 출처 및 대표 역사적 선택

| 역사적 대국 | 탈이 둔 측 | 대표 순간 | 이 데이터에서 사용하는 기준 수 |
|---|---|---|---|
| Botvinnik–Tal, World Championship Game 6 (1960) | 흑 | **21...Nf4** 나이트 희생 | `h5f4` |
| Tal–Larsen, Candidates Semifinal Game 10 (1965) | 백 | **16.Nd5** 포지셔널 나이트 희생 | `c3d5` |
| Tal–Benko, Candidates Round 14 (1959) | 백 | **23.Bf8** 비숍 제안 | `h6f8` |
| Tal–Smyslov, Candidates Round 8 (1959) | 백 | **14.Qh4** 공격을 위한 퀸 이동 | `d4h4` |

공개 기보 출처:

1. Botvinnik–Tal 1960: https://en.wikipedia.org/wiki/World_Chess_Championship_1960
2. Tal–Larsen 1965: https://github.com/tonymorris/immortalgames/blob/master/immortal_games.pgn
3. Tal–Benko 1959: https://www.chessbox.in/chessgame/tal-mihail-benko-pal-c-2/
4. Tal–Smyslov 1959: https://chessmotion.com/explore/famous-chess-games/tal-smyslov-1959

PGN 전체 원문이나 외부 사이트의 주석을 그대로 복제하지 않습니다. 선택한 역사적 수순을 UCI 형식으로 재생하고, 기보에서 얻은 FEN 및 역사적 선택만 데이터셋으로 저장했습니다. 개별 수순에 붙인 `theme`/`note`는 진단 용도의 개략적 분류이며 외부 엔진의 객관적 최선 수 인증이 아닙니다.

## 3. 사용법

### 4개의 대표 국면 빠르게 보기

```bash
python tal_style_benchmark.py --quick --depth 3 --profiles baseline,tactical,activity,initiative,combined
```

### 전체 22개 국면을 동일 깊이에서 비교

```bash
python tal_style_benchmark.py --depth 3 --profiles baseline,combined --json-output tal_report.json
```

### 한 국면만 깊게 보기

```bash
python tal_style_benchmark.py --case botvinnik_tal_1960_g6_ply42 --depth 5 --profiles baseline,combined
```

`baseline`은 추가 공격 옵션 OFF. `tactical`은 TacticalChecks만 ON, `activity`는 AttackActivity만 ON, `initiative`는 Initiative만 ON, `combined`는 세 기능을 모두 ON으로 실행합니다. KingSafety는 이번 실험에서 일관되게 OFF이며, 기존 엔진의 기본값도 변경하지 않습니다.

출력의 `MATCH`는 **역사적 탈의 수와 정확히 일치했다**는 뜻일 뿐, 엔진이 객관적인 최선수를 찾았다거나 인간다운 수를 두었다는 뜻이 아닙니다. 탈의 희생 중에는 정밀한 컴퓨터 분석에서 최선이 아닐 수 있는 것도 있습니다.

프로그램은 각 국면마다 일반 탐색과 Tal의 수만 허용한 **별도의 루트 제한 탐색**을 수행합니다. 둘의 점수 차이는 **제한된 깊이에서 얻은 근사치**이며, 수 정렬·탐색 특성상 완전한 객관적 손실값이 아닙니다. 메이트 점수를 센티폰 차이로 오인하지 않도록 구분합니다.

`selected_checks`, `selected_captures`, `selected_exposed_piece_proxy` 지표는 **설명용 수순 특성**입니다. 상대에게 공격받는 칸에 기물을 둔다고 반드시 훌륭한 희생이 되는 것이 아닙니다. 위협의 지속성과 희생의 건전성은 독립적인 깊은 분석과 실제 대국으로 확인해야 합니다.

외부 Stockfish로 특정 후보의 깊은 분석을 진행하려면, 기존 `analyze_sacrifices.py`를 사용하세요:

```bash
pip install chess
python analyze_sacrifices.py --fen "2r3k1/pp4bp/3p2p1/3Ppb1n/1qr5/2N1B1PP/PP2QPBK/R1R5 b - - 1 21" --depth 4 --moves h5f4 --stockfish stockfish --sf-depth 18
```

Stockfish는 별도의 **검증 도구**이며 자체 엔진에 통합되지 않습니다. 이 환경에서는 Stockfish 실행 파일이 없어 이 교차 검증을 수행하지 못했습니다.

## 4. 이번 환경의 실제 실험 결과

각 국면을 독립적인 `Board(FEN)`에서 탐색했습니다. 실제 수순이 알려진 위치라도 FEN만으로 과거 반복 이력을 복구하지 않으므로, 역사적 대국 전체의 규칙 이력은 탐색에 들어가지 않습니다.

| 실험 | baseline | combined | 판단 |
|---|---:|---:|---|
| 전체 22개, 깊이 3 | **8/22 역사적 수 일치** | **9/22 일치** | 표본이 매우 작고, 정답률이나 Elo가 아님 |
| 4개 대표 공격 결정, 깊이 3 | **0/4** | **0/4** | 현재 옵션만으로 핵심 탈 희생을 재현하지 못함 |
| 4개 대표 공격 결정, 깊이 4 | **0/4** | **0/4** | 깊이를 올려도 네 역사적 희생은 선택하지 않음 |
| 깊이 3, 전체 22개 탐색 노드 | 235,559 | 269,038 | 서로 다른 평가/탐색 옵션으로 노드 수 비교에 한계 |
| 깊이 3, 전체 22개 탐색 시간 | 약 3.14초 | 약 7.60초 | 동일 기기에서의 일회성 관찰 |

이는 현재 엔진이 역사적 탈의 희생을 **쉽게 포착하지 못한다는 유용한 진단 결과**입니다. 그러나 원인이 얕은 탐색인지, 정적 평가에 공격의 보상이 부족한지, 실제로 그 희생이 객관적으로 부정확한지는 **이 결과만으로 판단할 수 없습니다**. 성능 향상이나 Elo 변화는 이번에 주장하지 않습니다.

## 5. 회귀 테스트

```bash
python test_tal_style.py
python test_v046.py
python test_v045.py
python test_v044.py
python test_tactics.py
python test_engine.py --quick
python test_uci.py
python perft.py
```

이 환경에서 직접 확인한 결과:

- 신규 `test_tal_style.py`: **7/7 통과**.
- 기존 `test_v046.py`: **8/8**, `test_v045.py`: **11/11**, `test_v044.py`: **11/11**, `test_tactics.py`: **10/10** 통과.
- `test_engine.py --quick`: **158/158 통과**, 외부 python-chess 교차 검증 1개 건너뜀.
- UCI 핵심 테스트 54개 항목: **54/54 통과**.
- 일반 `perft.py` 6개 포지션 기본 깊이 및 Zobrist 271,312 노드 검증 **통과**.
- 전체 장시간 테스트와 모든 포지션의 `perft.py --deep`는 **이번 실행에서 완료하지 못함**.
- 이 환경에서 `python-chess` 및 Stockfish 실행 파일은 없으므로 외부 엔진의 객관적 수 평가 및 자동 대국은 **미실시**.

## 6. 앞으로의 실제 알고리즘 개발

이번 데이터셋으로 확인한 4가지 핵심 공격 판단이 왜 선택되지 않는지 **독립적 깊은 분석과 더 깊은 자체 탐색**으로 확인한 뒤, 중요한 원인이 드러나면 최소한의 탐색 또는 평가 변경을 실험합니다. 기물 희생에 임의로 가산점을 부여하거나 Tal 수를 강제로 두게 만들지 않습니다.

다음 후보는 `quiet-check`의 선별 조건과 성능 대조, **강제 수순 탐색의 깊이**, 근거 있는 mobility/initiative 정밀화, 공격 보상이 실제로 이어지는 수순을 찾는 분석 기능입니다. **강함(대국 결과), 정확성(전술 건전성), 스타일 유사성(역사적 선택)**을 서로 구분하여 측정합니다.
