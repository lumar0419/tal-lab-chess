# MyEngine v0.4.8 — 탈의 공격 선택이 왜 탐색에서 탈락하는지 진단

이 프로젝트는 **기존 하나의 체스 엔진**을 v0.4.7에서 이어서 발전시킨 것입니다. 이번 v0.4.8은 **새로운 희생 보너스나 임의의 스타일 가중치를 추가하지 않습니다.** 우선 탈의 실제 역사적 선택이 왜 얕은 탐색에서 낮은 점수를 받는지 수치로 살펴보기 위한 진단 도구를 완성했습니다. 메이트·규칙·기존 평가 구조는 변경하지 않았고, `search.py` 및 `uci.py`의 버전만 0.4.8로 변경했습니다.

## 이번 버전에서 추가한 파일

- `tal_depth_diagnostic.py` — 역사적 Tal 수와 현재 최선수의 **깊이별 정규 탐색 vs 루트 강제 탐색** 비교. 동일 프로필/깊이에서 각각 새로운 TT를 사용하며, 이력·보드 상태 복구를 검사합니다. 첫 수 직후 정적 평가, 역사적 수의 PV, PV를 따라간 물질 손익, 탐색 노드, 경과 시간, 격차 변화 등을 JSON으로 보관합니다.
- `test_tal_depth.py` — 깊이 입력 검증, PV 합법성, 정확한 루트 수 제한, 보드 상태, 기존 평가 옵션 복구, 선택적 Stockfish 호출, JSON 출력 검증 **7개**.
- `tal_depth_v048.json` — 대표 4개 국면의 baseline/combined, 깊이 2·3·4 데이터.
- `tal_depth5_baseline_v048.json` — 대표 4개 국면의 baseline, 깊이 4·5 데이터.
- `tal_benko_depth5_v048.json` — Benko전 개별 깊이 4·5 진단 예시.
- `README_v047.md` — 이전 버전 문서 보존.

## 실행 예시

동일한 프로젝트 폴더에서:

```bash
python tal_depth_diagnostic.py --quick --profiles baseline,combined --depths 2,3,4 --json-output tal_depth_v048.json
python tal_depth_diagnostic.py --quick --profiles baseline --depths 4,5 --json-output tal_depth5_baseline_v048.json
python tal_depth_diagnostic.py --case tal_benko_1959_r14_ply45 --profiles baseline --depths 2,3,4,5
```

독립적인 **Stockfish 실제 분석**을 하고 싶다면 (이 환경에서는 실행하지 못했음):

```bash
pip install chess
python tal_depth_diagnostic.py --quick --profiles baseline --depths 3,4 --stockfish stockfish --sf-depth 18 --json-output tal_with_sf.json
```

`--stockfish`를 지정한 경우에만 외부 평가가 생성됩니다. 실행 파일과 `python-chess`가 설치되어 있어야 합니다. 체스 엔진 자체는 두 프로그램에 의존하지 않습니다.

### 주의할 해석

- Tal이 역사적으로 둔 수는 **반드시 최선수인 것이 아닙니다.** 탈과 동일하게 두는 비율은 스타일 유사성의 일부 관찰이지 Elo나 객관적 정확성의 척도가 아닙니다.
- `approx_score_gap_cp`는 하나의 탐색 조건에서 **모든 수를 허용한 탐색 점수 − Tal의 수만 허용한 탐색 점수**입니다. 값이 클수록 *이 엔진의 해당 깊이*에서 Tal 수를 낮게 평가한 것이지, 역사적 수의 객관적 손실값이 아닙니다. 독립 검색의 수 정렬/TT 경로에 따라 다를 수 있습니다.
- `static_eval_after_move_cp`는 상대가 응수하기 전 **1수 후의 정적 평가**입니다. `material_delta_by_ply_cp`는 한정된 PV를 따라간 물질 변화이며, 장기적 공격 보상이나 희생의 건전성을 증명하지 않습니다.
- **깊이 부족 vs 평가 함수의 보상 누락 vs 탈의 실제 투기적 희생**은 이 보고서만으로 확정할 수 없습니다. 이를 구별하려면 더 깊은 자체 엔진 탐색과 독립적인 강한 Stockfish 분석이 필요합니다.
- 프로필 `combined`는 같은 엔진에서 TacticalChecks, AttackActivity, Initiative를 ON으로 한 설정입니다. KingSafety는 이전 실험 성적에 따라 OFF로 고정합니다.

## 실제 진단 결과

탈의 대표 수를 선택하지 않은 4개 국면에 대해 **기존 엔진 그대로** 깊이별 탐색을 실행했습니다. 아래 숫자는 센티폰이며, 반올림하지 않은 코드 출력값입니다.

| 역사적 국면 | Tal 수 | baseline d2 격차 | baseline d4 격차 | baseline d5 격차 | combined d4 격차 |
|---|---|---:|---:|---:|---:|
| Botvinnik–Tal 1960 | 21...Nf4 (`h5f4`) | +200 | +193 | +193 | +164 |
| Tal–Larsen 1965 | 16.Nd5 (`c3d5`) | +187 | +187 | +187 | +154 |
| Tal–Benko 1959 | 23.Bf8 (`h6f8`) | +358 | +235 | +245 | +217 |
| Tal–Smyslov 1959 | 14.Qh4 (`d4h4`) | +328 | +298 | +284 | +298 |

**관찰:** 탐색 깊이를 2에서 5로 높여도 baseline은 이 4개 역사적 수를 선택하지 않았습니다. Benko전은 d2→d4에서 격차가 줄었지만 d5에서는 다시 소폭 커졌습니다. 이는 단순히 '깊이 한 단계만 늘리면 탈의 희생을 찾는다'는 설명이 성립하지 않음을 보여 줍니다.

**물질과 PV의 관계:** 깊이 4 baseline에서 `Nf4`, `Nd5`, `Bf8`, `Qh4` 직후에는 모두 *즉시* 물질 손해가 0cp입니다. 그러나 현재 엔진이 예측한 응수에 따라 Nf4는 물질 약 -220~-320cp, Nd5는 -220cp, Bf8 및 Qh4는 -330cp까지 물질적 손실이 생기는 수순을 분석합니다. **이 수치는 단순히 물질 손실이 왜 탐색 평가를 낮추는지 설명하는 단서일 뿐**; 공격 보상이 없다는 뜻은 아닙니다. 특히 Benko전 깊이 5에서는 예측 PV가 바뀌어 물질 변화 양상이 달라집니다. 강제 수순이 확정된 것은 아닙니다.

실험 파일에는 각 depth에서의 실제 엔진 선택 수, 점수, PV, 탐색 노드, 타이밍, 물질 변화 기록이 모두 들어 있습니다. 이 실험에서 **Stockfish 독립 평가 / 자동 대국 / Elo 측정은 실시하지 않았습니다.**

## 회귀 테스트

```bash
python test_tal_depth.py
python test_tal_style.py
python test_v046.py
python test_v045.py
python test_v044.py
python test_tactics.py
python test_engine.py --quick
python test_uci.py
python perft.py
```

이번 환경에서 완료한 검사:

- 신규 깊이 진단 `test_tal_depth.py`: **7/7**.
- 역사적 기보 `test_tal_style.py`: **7/7**.
- `test_v046.py`: **8/8**, `test_v045.py`: **11/11**, `test_v044.py`: **11/11**, `test_tactics.py`: **10/10**.
- `test_engine.py --quick`: **158/158** (외부 python-chess 교차 검증 1개 건너뜀).
- UCI 전체 자동 테스트(외부 라이브러리 관련 3개 건너뜀): **54/54 통과**.
- 기본 Perft 6국면 및 Zobrist 271,312 노드 **통과**. 별도 심화 Perft는 국면별 최대 깊이 정답까지 로그로 확인했지만 종료 시 최종 Zobrist 검사는 이번 실행에서 완료되지 않아 심화 전체 통과로 표기하지 않습니다.
- 전체 `test_engine.py --full` 및 이번 버전의 Stockfish 자동 대국은 미실시.

## 다음 알고리즘 개선 기준

이제 Tal 수를 선택하지 않는 이유를 **물질 손해·시간이 지나서 나타나는 공격 보상·정적 평가·탐색 깊이**로 나누어 분석할 기반이 만들어졌습니다. 후속 단계에서는 Stockfish의 충분히 깊은 분석과 PV를 비교한 뒤, 실제로 전술을 놓치는 것이 입증된 경우에만 탐색 최적화(PVS, 제한적인 탐색 확장 등) 또는 보상 평가를 하나씩 실험해야 합니다. 공격적인 플레이를 만든다는 이유로 물질을 잃는 수에 무조건 보너스를 부여하지 않습니다.
