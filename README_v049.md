# MyEngine v0.4.9 — PVS 탐색 최적화

이 프로젝트는 기존 **하나의 체스 엔진** v0.4.8을 이어서 수정한 것입니다. 이번 버전은 주로 **Principal Variation Search(PVS)**로 기존 Alpha-Beta 탐색을 가속합니다. 기물 희생에 임의의 보너스를 추가하거나 평가 함수의 성향을 바꾸지 않았습니다. 미하일 탈처럼 적극적이면서도 건전한 수를 찾기 위해 **같은 시간에 더 깊이 계산하는 기반**을 만드는 단계입니다.

## 바뀐 파일

- `search.py` — `Searcher.pvs` 옵션(기본 **True**), PVS null-window probe와 재탐색, 탐색 횟수 계측(`pvs_probes`, `pvs_researches`). 기존 Alpha-Beta 탐색은 `pvs=False`로 실행할 수 있습니다. `ENGINE_VERSION`을 0.4.9로 변경.
- `uci.py` — `option name PVS type check default true` 추가. GUI에서 `setoption name PVS value false/true`로 전환할 수 있습니다. 전환 시 TT를 비워 서로 다른 탐색 경로를 공정하게 비교합니다. UCI 버전 0.4.9.
- `test_pvs.py` — 동일 깊이/전체 창 비교, 50수·메이트·언더프로모션, PVS null-window alpha-beta 경계, TT ON/OFF, 루트 제한, 외부 정지, 보드 상태, 기존 공격 옵션과 조합, GUI UCI 명령 테스트.
- `bench_pvs.py` — 같은 FEN, 같은 깊이, 각 실행마다 새 TT를 사용하는 PVS ON/OFF 고정 깊이 벤치마크(번갈아 실행, 반복 중앙값, JSON 출력).
- `test_tal_depth.py` — 진단 결과 버전 검사 0.4.9 반영(기존 테스트 보존).
- `pvs_depth4_v049.json`, `pvs_depth5_quick_v049.json` — 실제 측정 결과.
- `README_v048.md` — 이전 버전 설명서 보존.

## 작동 방식

1. 각 노드의 **첫 번째 합법수**는 기존처럼 전체 탐색 창 `(-beta, -alpha)`에서 탐색합니다.
2. **두 번째 이후 합법수**는 `(-alpha-1, -alpha)`라는 1센티폰 폭의 창으로 일단 시험합니다.
3. 좁은 창 결과가 `alpha < score < beta`이면 **반드시 전체 창으로 다시 탐색**하여 정확한 점수와 PV를 확보합니다.
4. `score <= alpha`는 fail-low 경계로 사용하고, `score >= beta`는 fail-high 경계로 사용합니다.
5. PVS 사용을 위한 추가적인 선택적 가지치기나 불확실한 희생 보너스는 넣지 않았습니다. 50수/동형반복, TT 메이트 점수, 승격 등 기존 규칙을 변경하지 않았습니다.

## 벤치마크 결과 (이 실행 환경의 실측, Elo 아님)

명령:

```bash
python bench_pvs.py --depth 4 --repeats 3 --json-output pvs_depth4_v049.json
python bench_pvs.py --depth 5 --repeats 2 --quick --json-output pvs_depth5_quick_v049.json
```

11개 국면에서 깊이 4 PVS OFF/ON 탐색 점수 **11/11 일치**. 각 국면별 중앙 실행 시간 비율의 중앙값은 **93.2%**(약 6.8% 단축), 탐색 노드 비율의 중앙값은 **92.7%**였습니다. 어떤 국면은 거의 변화가 없었고 일부에서는 근소하게 느려졌습니다.

| 깊이 4 국면 | 기존 Alpha-Beta 노드 | PVS 노드 | 기존 시간 중앙값 | PVS 시간 중앙값 |
|---|---:|---:|---:|---:|
| Kiwipete | 91,768 | 66,510 | 1.563s | 1.045s |
| Position 6 | 68,886 | 36,318 | 1.125s | 0.515s |
| Botvinnik–Tal 1960 대표 국면 | 146,440 | 100,158 | 2.059s | 1.290s |
| Tal–Benko 1959 대표 국면 | 31,036 | 31,614 | 0.373s | 0.377s |

깊이 5 대표 **4개 국면**에서 점수 **4/4 일치**, 시간 비율의 중앙값 **80.5%**(약 19.5% 단축), 노드 비율 중앙값 **93.5%**였습니다. 이 수치는 이 컴퓨터의 단기 측정이므로 다른 환경에서 반복 확인해야 합니다.

**주의:** PVS는 이론적으로 전체 창 Alpha-Beta와 동일한 결과를 얻기 위한 탐색 순서 최적화입니다. 수 선택을 일부러 공격적으로 바꾼 기능은 아닙니다. **Stockfish 대국, Elo 향상, Tal 역사적 수 선택률 향상은 아직 검증하지 않았습니다.** 탈의 역사적 수가 최선이라는 뜻도 아닙니다.

## 실제 검증

- PVS 회귀: 기존 9개 테스트가 한 차례 모두 통과했고, 추가된 공격형 평가 프로필 조합 테스트도 별도로 통과했습니다(총 **10개 테스트**, 개별 및 분할 실행). PVS OFF와 ON을 비교했습니다.
- `python test_engine.py --quick`: **158/158 통과**, `python-chess` 교차 검증 1개 건너뜀.
- `python test_uci.py`: **54/54 통과**, 외부 라이브러리가 필요한 테스트 3개 건너뜀.
- `python test_tal_depth.py`, `test_tal_style.py`, `test_v046.py`, `test_v045.py`, `test_v044.py`, `test_tactics.py`: 각각 **7/7, 7/7, 8/8, 11/11, 11/11, 10/10 통과**.
- `python perft.py`: 기본 Perft와 Zobrist 검증(271,312개 노드) 통과. `--deep`는 시작 국면·Kiwipete·Position 3~5의 최고 깊이까지 정답을 확인했지만, Position 6 depth 4 및 마지막 Zobrist 검증 전에 실행 시간 제한으로 중단되어 **전체 심화 테스트 통과로 기록하지 않습니다.**
- `test_engine.py --full`은 실행 시간 제한으로 **미완료**. 전체 테스트가 통과했다고 주장하지 않습니다.

## 실행법

```bash
python uci.py                # UCI GUI의 엔진으로 등록
python test_pvs.py           # 신규 PVS 회귀
python test_engine.py --quick
python test_uci.py
python bench_pvs.py --depth 4 --repeats 3
```

UCI 옵션 예시:

```text
setoption name PVS value true
setoption name TacticalChecks value true
setoption name AttackActivity value true
setoption name Initiative value true
```

각 옵션의 전술적/실전적 효과는 별도로 확인해야 하므로 PVS 외의 세 공격 옵션과 KingSafety는 이전 버전처럼 기본 OFF를 유지합니다.

## 다음 단계

PVS로 확보한 탐색 여유가 **실제 같은 시간에 더 깊은 정확한 공격 수순을 발견하는지** 기록합니다. 이후 탈의 역사적 희생 4개에 대해 같은 시간·깊이에서 강제 수의 점수와 PV를 다시 확인하고, 필요한 경우에만 후보 수 정렬이나 정당한 전술 확장을 **한 가지씩** 실험합니다. 점수 보너스로 무의미한 희생을 장려하지 않습니다.
