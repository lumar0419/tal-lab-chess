# MyEngine v0.4.11 — 공격적인 수 정렬과 제한된 연속 체크 탐색

**기존 하나의 체스 엔진** v0.4.10에서 계속 개발한 버전입니다. 미하일 탈의 역사적 수를 억지로 정답 처리하거나, 기물 희생에 임의의 평가 보너스를 주지 않았습니다. 이번 변경은 **유망한 공격수를 먼저 읽는 수 정렬**과 **강제 체크 수순의 선택적 연장**을 실험하는 것입니다.

## 변경 사항

- `search.py`: `Searcher.tactical_ordering` (기본 **False**) 도입. 탐색 트리 상단(`ply<=2`)의 얕은 탐색(`depth<=4`), 체크가 아닌 노드에서만 조용한 체크 가능성을 사전 선별해 MVV-LVA/승격 아래, killer 위에 정렬합니다. 일반 조용한 기물 수에는 상대 킹 쪽으로 다가가는 정도에 **작은 정렬 점수**를 부여합니다. 모든 후보 수는 여전히 탐색 대상이며, 합법수 판정이나 정적 평가 점수는 전혀 변경하지 않습니다. 예상 체크 후보는 *거짓 양성*이 있을 수 있어 강제 수는 탐색 단계에서만 확정합니다.
- `search.py`: `Searcher.check_continuation` (기본 **False**) 도입. `TacticalChecks=True`일 때 qsearch 첫 조용한 체크→강제 응수→다음 조용한 체크의 **최대 두 번**까지 검토할 수 있습니다. 캡처 가지에는 기존처럼 예산을 넘겨주지 않으며 `MAX_PLY` 제한이 적용됩니다. 이는 수 선택을 바꿀 수 있는 실험적 탐색 옵션입니다.
- `uci.py`: `TacticalOrdering`, `CheckContinuation` UCI 체크 옵션 추가, 두 옵션의 변경 시 TT 비움.
- `test_tactical_ordering.py`: 신규 단위/프로세스 테스트 **11개**. 수 생성 및 상태 보존, Tal 수 정렬 순위, 고정 깊이 점수, 언더프로모션/메이트/스테일메이트, node limit, 체크 연속성, UCI 테스트를 포함합니다.
- `bench_tal_forcing.py`: 하나의 엔진에서 옵션별 **새 TT/동일 깊이**로 실행해 JSON 비교. `tal_forcing_depth4_v0411.json`에 최초 비교 결과 포함.
- `test_aspiration.py`, `test_tal_depth.py`: 기존 버전 확인값만 현재 v0.4.11로 업데이트 (테스트 조건 완화 없음).

## 초기 Tal 국면에서 역사적 수의 **최초 정렬 순위**

TT 및 history가 비어 있는 최초 루트 순위이며, **역사적 수의 품질·체스 실력·엔진 실제 선택률을 의미하지 않습니다.**

| Tal 국면/수 | 기존 순위 | TacticalOrdering ON |
|---|---:|---:|
| Botvinnik–Tal 1960 `...Nf4` | 30/51 | **13/51** |
| Tal–Larsen 1965 `Nd5` | 17/45 | **3/45** |
| Tal–Benko 1959 `Bf8` | 42/45 | **23/45** |
| Tal–Smyslov 1959 `Qh4` | 53/59 | 55/59 |

네 사례 중 세 사례에서 앞당겨지고 한 사례에서는 뒤로 밀렸습니다. **깊이 4에서는 네 역사적 수 중 어느 것도 최선수로 선택되지 않았습니다.** 수를 일찍 검색하는 것만으로 그 수의 객관적 평가값이 증가하는 것은 아닙니다.

## 깊이 4 고정 깊이 성능 (단일 실행 샘플)

`python bench_tal_forcing.py --depth 4 --output tal_forcing_depth4_v0411.json`

| 국면 | baseline 노드 | ordering 노드 | baseline 시간 | ordering 시간 |
|---|---:|---:|---:|---:|
| 시작 | 3,629 | 3,531 | 0.049s | 0.042s |
| Kiwipete | 66,500 | 66,498 | 1.194s | 1.042s |
| Botvinnik–Tal | 100,200 | **116,021** | 1.489s | **1.716s** |
| Tal–Larsen | 19,923 | 21,372 | 0.286s | 0.297s |
| Tal–Benko | 31,614 | 31,956 | 0.400s | 0.397s |
| Tal–Smyslov | 53,327 | 52,003 | 0.717s | 0.590s |

위 6개 국면에서 **기본 설정과 TacticalOrdering ON의 깊이 4 평가값·최선수가 모두 일치**했습니다. 소요 시간의 ON/OFF 비율 중앙값은 약 **0.93**이지만 단일 실행에 의한 CPU 잡음이 커서 속도 향상을 확정할 수 없습니다. Botvinnik에서는 계산량과 시간이 증가했습니다.

`CheckContinuation`을 켜면 일부 국면에서 탐색 노드가 증가하고 평가가 바뀔 수도 있습니다. Tal–Smyslov 깊이 4 예시에서 TacticalChecks 기본 1회는 76,746노드 / +45cp, CheckContinuation 2회는 85,715노드 / +45cp였습니다. 같은 점수라도 노드가 늘어 **실전 승률 향상을 의미하지 않습니다.**

## 검증 결과

- `python -m unittest -v test_tactical_ordering.py`: **11/11 통과**.
- `python test_engine.py --quick`: **158/158 통과**, python-chess 1개 건너뜀.
- `python test_uci.py`: **54/54 통과**, python-chess 의존 3개 건너뜀.
- `python -m unittest -v test_aspiration.py`: **9/9 통과**.
- `python -m unittest -v test_tal_depth.py`: **7/7 통과**.
- `python test_tactics.py`: **10/10 통과**.
- `python -m unittest -q test_v044.py test_v045.py test_v046.py test_tal_style.py`: **37/37 통과**.
- `python perft.py` 기본 6개 국면 및 Zobrist **271,312개 노드** 확인 통과.
- `test_pvs.py`는 9개 항목 진행 후 **일괄 실행이 시간 초과로 미완료**. 이미 끝난 8개는 통과했고, UCI 항목은 별도로 통과함. 장시간 `test_pvs`와 `perft.py --deep`, `test_engine.py --full` **완료하지 못했습니다**.
- 현재 환경에 Stockfish 실행 파일과 `python-chess`가 없어 외부 검증/Stockfish 실전 대국은 **실행하지 않았습니다**.

**이번 기능 두 개 모두 기본 OFF**입니다. PVS는 기존대로 ON, Aspiration·TacticalChecks·AttackActivity·Initiative·KingSafety 등 기존 선택적 옵션의 기본 설정을 변경하지 않았습니다. 실제 paired-game Elo 및 공격의 건전성 검증이 끝나기 전까지 기본값을 바꾸지 마세요.

## 사용법

```bash
python uci.py                  # engine.bat / engine.sh도 그대로 사용
python test_tactical_ordering.py
python test_engine.py --quick
python test_uci.py
python bench_tal_forcing.py --depth 4 --output tal_forcing_depth4_v0411.json
```

GUI/UCI에서 실험 시:

```text
setoption name TacticalOrdering value true
setoption name TacticalChecks value true
setoption name CheckContinuation value true
isready
go depth 4
```

`CheckContinuation`만 켜고 `TacticalChecks`를 끄면 기존 탐색과 같습니다.

## 다음 단계

1. Stockfish 및 독립적인 체스 라이브러리가 있는 환경에서 유한 깊이의 Tal 후보를 **강제 루트 수 탐색**으로 교차 검증.
2. 동일 오프닝·색상·시간제한으로 단일 엔진의 옵션 OFF/ON을 **순차·짝지은 대국**에서 검증 (Stockfish의 UCI_Elo 설정을 실제 Elo로 단정 금지).
3. 희생을 더 많이 하는지보다 **희생 후 공격 지속성, 전술 오류율, 실전 점수율**을 별도로 측정. 실제 성능 저하가 있다면 실험 옵션은 OFF로 유지.

기존 프로젝트는 하나뿐입니다. 버전 ZIP은 복구·변경 이력 보존용입니다.
