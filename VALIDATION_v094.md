# v0.9.4-dev 검증 — Positional Understanding & Search Accuracy

**결론: 위치적 판단이나 Elo 향상은 입증하지 못했다.** 후보 평가와 quiet 가지치기 완화를 실제 구현·실험했지만 기본 엔진에는 채택하지 않았다. 제품 변경은 정확한 평가 설명/착수 전후 비교, opt-in 탐색 진단, 연구·재현 도구와 검증 문서다. 기력 개선이 완료된 v0.9.4 정식판으로 표시하지 않고 `0.9.4-dev` Draft로 남긴다.

기준은 v0.9.3 `af201fb488e4ef74f35f519fb61f4081df9b184c`, 작업 브랜치는 `development/positional-accuracy-v094`. main/기존 v0.9.3/PR #1은 변경하거나 병합하지 않았으며 Render 배포도 수행하지 않았다. 2026-11-17 한국 시간 기준 작업이다.

## 엔진 구조와 실제 원인 진단

120칸 mailbox 보드, 증분 Zobrist, tapered material/PST/pawn/bishop-pair 평가, 반복 심화 negamax/PVS/TT/QS, 선택적 null/RFP/futility/LMP/LMR/IIR, SEE 기반 루트 희생 2반수 연장을 유지한다. 기존 KING_SAFETY/ATTACK_ACTIVITY/INITIATIVE는 기본 OFF다. 실전 기보 2개를 두 규칙 구현으로 재생했고 모든 수와 FEN이 일치했다.

사용자가 확인한 60초·전술 탐색·MultiPV 1/2에서 문제 선택을 대부분 재현했다. Stockfish 19는 첫 경기 `10.Nxf5`, `11.Nxe5`, `15.Nxh8`도 우선 선택했지만 `17.Rxg7`, `19.Rxh7`과 둘째 경기 `10...dxc3`, `11...Ke8` 뒤의 위치를 Tal보다 크게 나쁘게 평가했다. 루트 quiet 수는 futility/LMP에서 제외되고 `...Bc3`, `Qd5+`는 Tal PV에 존재한다. 따라서 단순히 포획을 싫어하도록 가중치를 바꾸거나 첫 체크를 못 봤다고 설명하지 않는다. 평가·장기 보상·하위 가지치기/수 정렬의 복합 문제이며 단독 원인은 확정하지 못했다.

상세 표, PV, 후반 통과폰 분석과 한계는 [POSITIONAL_DIAGNOSTICS_v094.md](POSITIONAL_DIAGNOSTICS_v094.md). Stockfish는 독립 프로세스 검증용이고 엔진에 코드/선택수를 이식하지 않았다.

## Ablation 정의

| 설정 | 평가 | 탐색 | 채택 |
|---|---|---|---|
| A | v0.9.3 기존 | 전술 프로필 | 기준 유지 |
| B | 새 안전 mobility N/B/R/Q | 기존 | 제외 |
| C | 새 king pressure/shelter | 기존 | 제외 |
| D | home-minor 전개 지연 MG 벌점 | 기존 | 제외 |
| E | validation 선택 Texel 가중치 | 기존 | 모든 추가 가중치 0 → A와 동일 |
| F | 기존 | quiet futility/LMP 끔 | 제외 |
| G | E | F | 미채택 후보 조합, 검증된 통합본 아님 |
| conservative | 기존 | 보수적 LMR, 전술 프로필 끔 | 진단 비교 |

연구 기능은 `research/positional_v094.py`와 별도 프로세스 UCI wrapper에만 있다. 생산 `evaluate_white()`의 빠른 경로와 검색 정책은 변경하지 않았다. 반복 이동 횟수처럼 FEN/hash에 없는 정보를 정적 평가에 넣지 않았다. 기존 PST와 겹칠 수 있는 전개 보너스도 후보로만 취급했다. rook file 항목은 튜너 후보에 포함했지만 독립 채택 근거가 없어 기본에 넣지 않았다. outpost/bad bishop/space/connected passer 전체를 구현했다고 주장하지 않는다.

## 전술 회귀: 기존 v0.9.2 holdout 32, 2초

이 표본은 이전 버전에 공개된 **회귀 표본**이며 새 독립 test라고 부르지 않는다. A와 E는 같은 알고리즘인데도 시간 제한 때문에 평균 완료 깊이가 조금 다르다. 고정 노드와 구분해야 한다.

| 설정 | 정답 /32 | 평균 완료 깊이 | 평균 사용 초 | aggregate NPS |
|---|---:|---:|---:|---:|
| A | 28 | 6.50 | 1.794 | 47,069 |
| B | 25 | 5.72 | 1.842 | 23,347 |
| C | 27 | 5.66 | 1.843 | 24,228 |
| D | 28 | 5.69 | 1.848 | 23,684 |
| E | 28 | 6.53 | 1.801 | 44,232 |
| F | 28 | 6.28 | 1.835 | 66,955 |
| G | 28 | 6.31 | 1.841 | 66,650 |
| conservative | 27 | 7.09 | 1.767 | 45,966 |

B는 기준 대비 3문제를 잃고 계산 비용도 증가했다. C는 1문제를 잃었다. D는 정답 수가 같지만 더 비쌌다. F/G는 정확도 이득을 보이지 않았다. 전술 정답률은 Elo가 아니다. 유형별 원시 집계는 `summary.json`의 `tactics.*.categories`에 있다.

## 새 quiet 위치 표본: 48개, Tal 1초 / Stockfish 1초

학습에서 분리된 test 게임의 quiet 국면 중 고정 간격으로 48개를 선정했다. SF 1순위와 정확히 같은 수인지, 후보를 강제해 재평가했을 때 루트 대비 50cp 이내인지 측정했다. SF root가 cp인 41개와 mate인 7개를 분리했다. 메이트를 30000cp라는 실제 기물 평가처럼 평균내지 않았다.

| 설정 | SF 1순위 일치 /48 | cp 국면 50cp 이내 /41 | 불리한 cp 국면 50cp 이내 /12 | 평균 깊이 | NPS |
|---|---:|---:|---:|---:|---:|
| A | 24 | 30 | 7 | 5.69 | 42,055 |
| B | 19 | 28 | 7 | 4.88 | 21,662 |
| C | 22 | 31 | 7 | 4.96 | 21,844 |
| D | 19 | 30 | 7 | 4.96 | 21,559 |
| E | 24 | 30 | 7 | 5.75 | 41,708 |
| F | 21 | 31 | 7 | 5.48 | 61,000 |
| G | 21 | 31 | 7 | 5.44 | 62,178 |
| conservative | 24 | 32 | 7 | 5.94 | 41,878 |

모든 설정이 SF mate 국면 7개 중 6개에서 같은 메이트 승패 방향을 보였다(메이트 거리 일치나 독립 증명이 아님). '불리한 국면'은 SF의 둘 차례 기준 ≤-100cp인 단순 대리 지표로, 전문가가 분류한 방어 테스트가 아니다.

참조 검색이 1초로 짧고 root/forced가 독립 탐색이라 후보가 root보다 좋게 평가되는 음수 loss도 있었다(A에서 13개). loss는 0으로 자르고 원시 값은 `reference-positional.json`에 보존했다. 이 잡음, 작은 표본, 시간 제한 때문에 1~2개 차이는 채택 근거가 아니다. 한 번의 최대 48개 통계에서 작은 향상을 찾아 선택하지 않았다.

## Texel 튜닝

Lichess 2013-01 standard rated PGN 17,761,302바이트(CC0)의 앞 10,000게임을 처리했다. 출처 URL·원본 hash·분리 정책은 manifest, 라이선스 페이지 확인은 `data-license.json`. quiet 조건은 16ply 이후 8ply 간격, 직전 포획/승격 없음, 현재 체크/종료/합법 포획 없음이다. 결과적으로 9,297국면: 학습 6,696 / validation 1,323 / test 1,278. 이 엄격한 필터와 초기 월 표본은 분포 편향이 있으므로 일반 기력 데이터셋이라고 주장하지 않는다.

동일 수순 게임 hash로 70/15/15 분할하고 국면을 전역 중복 제거했다. 사용자 두 경기 전체 FEN과 기존 v09* JSON의 알려진 국면을 제외했다. K는 train에서만 선택했고 13개 bounded 정수 계수를 좌표 하강으로 조정했다. validation으로 저장 pass를 고르고 test는 선택 후 한 번 읽었다. EPD 인접 블록을 게임 ID처럼 취급하지 않았다.

학습 MSE는 0.14880248 → 0.14801295로 줄었지만 모든 저장 pass의 validation이 baseline 0.15024777보다 나빴다. 선택 결과는 추가 가중치 0, K=0.6이다. test baseline/candidate 모두 0.15238628. 검증 실패를 숨기거나 마지막 학습 가중치를 배포하지 않았다. 9천여 표본의 단일 seed fit은 대규모 튜닝 성공이나 최적 가중치 증명이 아니다. 원시 데이터는 `texel-data.json.gz`, 모든 pass는 `texel-fit.json`에 있다.

## 실제 대국: fixed-budget screening

두 실험 모두 10개 오프닝의 백·흑 교환, 20판, 5초+0.05초, TacticalSearch=true, UCI 동일 조건이다. 한 쌍을 통계 단위로 계산한다. 다른 코어의 작업이 함께 실행된 사실은 로그의 host CPU 부하에도 남아 있다. 평균 완료 깊이가 약 2~3인 매우 짧은 시간제로, 사용자의 수당 60초 게임과 동일한 기력 실험이 아니다.

| 실험 (engine1) | 승/무/패 | 점수율 | 상대 Elo 추정 | 쌍 기준 근사 95% 범위 |
|---|---|---:|---:|---:|
| F 후보 vs v0.9.3 | 4/11/5 | 47.5% | -17.4 | -136.4 ~ +97.5 |
| 최종 v0.9.4-dev vs v0.9.3 | 4/11/5 | 47.5% | -17.4 | -110.4 ~ +73.1 |

두 실험 모두 시간패·불법수·엔진 오류 0. 최종 엔진은 기본 탐색이 동일하므로 짧은 시간제의 시간 변동에 따른 결과를 기력 향상/하락 증거로 해석하지 않는다. 10쌍의 정규 근사 범위는 거칠다. SPRT는 실행하지 않았고 통과했다고 주장하지 않는다. 외부 엔진과의 독립 대국도 이번에는 실행하지 않았다. SF 분석 대조와 실제 상대 대국을 구분한다.

## Brilliant Sacrifice

v0.9.3과 최종 코드의 4개 역사 국면을 각각 **100만 노드**로 비교: 최선수·점수·모든 완료 iteration PV/노드까지 일치했다. 해당 예산에서 Rxc3는 양쪽 모두 아직 미발견이었다. 이후 최종 엔진 PyPy로 각 60초를 실행했다.

| 국면 | 최종 수 | 처음 1위로 관측된 초 | 완료 깊이 | 역사 수 일치 |
|---|---|---:|---:|---|
| kasparov_topalov_1999_ply47 | `a5c6` | 미발견 | 11 | 아니오 |
| lasker_bauer_1889_ply29 | `d3h7` | 5.69 | 11 | 예 |
| lasker_bauer_1889_ply33 | `e5g7` | 0.29 | 10 | 예 |
| rotlewi_rubinstein_1907_ply44 | `c8c3` | 17.18 | 11 | 예 |

처음 관측된 시점은 '그 이후 모든 깊이에서 영구 1위'의 정의와 다르며 원시 iteration을 확인할 수 있다. 다른 런타임/장비의 v0.9.3 15초·44초 기록과 속도 개선 비율을 계산하지 않는다. Kasparov 24.Rxd4는 여전히 미해결이고 역사 수가 객관적 유일 최선수라는 가정도 하지 않는다.

## 정확성·플랫폼 검증

- 시작 시 v0.9.3 unittest 265개 통과.
- 최종 CPython, PyPy, 선택적 Cython 각각 unittest **276개 통과**. 신규 11개는 평가 fast/slow/설명 일치, 8가지 옵션·mirror, 전역 옵션 격리, 착수 전후 복원, dead-material override, TT 설정 무효화, trace 수/점수/노드 동일성, 연구 override 복원, 데이터 키/분할, 두 PGN 합법성, 새 HTTP API를 검사한다.
- `test_engine.py --quick` **159개**, `test_uci.py` **71개**, `perft.py` 전부 통과. perft의 hash 확인은 271,312노드.
- 독립 규칙 oracle CPython/Cython: 1,996국면·61,907간선·255,488 공격 판정, 동일 digest.
- v0.9.3과 최종 A의 실전 12개 국면·100,000노드에서 수/점수/노드/완료 깊이 동일.
- JS 구문 검사, frontend 계약(새 상세 API 포함), visual helper 검사 통과.
- 실제 Pyodide 0.27.7 WASM 런타임에서 MultiPV·옵션 전환·심층 메이트 증명·평가 상세 JSON이 CPython과 일치. 실제 브라우저 UI 전체 수동 검사는 미실행.
- 첫 UCI 검사 중 동시 대국 도구 잠금으로 일부 fault-harness가 실행되지 않았다(`uci-concurrent-attempt.log`). 대국 종료 뒤 재실행한 `final-uci.log`에서 71/71 통과했다. 잠금을 우회하거나 엔진 버그로 오분류하지 않았다.
- Render 사이트 변경/배포 없음. Windows native 빌드 미실행. 런타임 수치는 [PERFORMANCE_v094.md](PERFORMANCE_v094.md).

## 실제 통합한 기능과 남은 일

통합: on-demand 평가 설명·정확한 phase 합산·착수 전후 비교, 현재 옵션을 전역 변경 없이 적용하는 HTTP/UI, 자세한 quiet pruning/LMR trace, 연구 도구와 원시 evidence, 외부 엔진 조사·라이선스·NNUE 계획. 후보 평가/가지치기 정책은 연구 실행기에만 격리했다. 기존 포지셔널 약점은 아직 해결되지 않았다.

다음 단계는 더 큰·다양한 독립 결과/teacher 라벨 데이터, 여러 seed에서 일관된 소수 가중치, 후보 계산 비용 최적화, 사전 등록한 긴 시간제 paired SPRT/고정판수 대국이다. 새로운 비선형 NNUE는 별도 v0.9.5 실험으로 하고 classical fallback과 규칙/증분 점수 동등성을 먼저 확보한다. [NNUE_ROADMAP.md](NNUE_ROADMAP.md)에 구조·데이터·런타임·라이선스 계획을 기록했다.

외부 아이디어와 실제 구현을 구분한 [엔진 비교](PYTHON_ENGINE_COMPARISON_v094.md), 원시 결과와 명령을 모은 [evidence README](evidence/v094/README.md)를 함께 읽어야 한다. GitHub Actions 결과는 Draft PR의 실제 check 상태를 따르며 로컬 검사 통과를 원격 CI 통과로 바꾸어 쓰지 않는다.
