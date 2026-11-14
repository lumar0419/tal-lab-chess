# Tal Lab v0.8.7 전술 탐색 검증

기준은 개발판 v0.8.6 `7eae64d6e2e4be8eb4de8b9b84f0f2b0fa6092be`입니다. 작업 시작 시 원격 GitHub `main`은 `4b91b757a49b2b33ae1fdbebd00fd350bc905442`였습니다. 검증은 `development/engine-v087`에서 진행했습니다.

## 개발 메모에서 바로잡은 전제

v0.8.6의 본탐색은 이미 체크를 받는 모든 노드의 깊이를 1반수 늘립니다. 정적 탐색의 `TacticalChecks`와 `CheckContinuation`은 별개의 옵션입니다. v0.8.7은 이 기존 연장을 모두 허용하는 기준 설정, 연장 없음, 경로당 최대 두 번을 비교했습니다. 연장 예산이 0이어도 정적 탐색에서 합법적인 체크 회피와 메이트 처리를 유지합니다.

| 연구 프로필 | 변경 |
|---|---|
| `baseline` | v0.8.6 기준 코드와 기존 설정 |
| `candidate` | v0.8.7 코드와 기존 설정 |
| `unextended` | 체크 연장 없음 |
| `bounded` | 경로당 체크 연장 2회 |
| `null` | null-move 가지치기 |
| `threat` | 가상 패스 뒤 짧은 강제 메이트 위협에 한해 1반수 연장 |
| `combined` | 체크 연장 2회 + null-move 가지치기 + 위협 연장 |

Null-move는 비PV 내부에서 깊이 3 이상, 체크 밖, 50수 청구에서 충분히 떨어진 국면, 현재 쪽에 폰과 킹 외 기물이 2개 이상인 경우에만 시도합니다. 정적 평가가 컷 기준 이상인 경우에만 가지치기 프로브를 실행하며, 가상 패스로 메이트 점수를 반환하는 컷은 사용하지 않습니다. 위협을 검사할 때는 별도 메이트 범위의 창을 사용합니다. 가상 국면은 이력과 TT에서 분리하고, 패스 후 앙파상은 해제하며, 중단 시에 보드·해시를 복구합니다. 위협 탐색은 조용한 전술 전반을 판별하는 기능보다 범위가 좁습니다. Null-move는 선택적 가지치기이므로 해당 프로필에서 얻은 루트 순위와 점수는 독립적인 지정 수 탐색으로 재검토했습니다. [Null Move Pruning 배경](https://www.chessprogramming.org/Null_Move_Pruning)

## Kasparov–Topalov 1999

기보 이력을 보존한 두 규칙 구현에서 FEN을 대조했습니다. 검색 기준점은 `24.Rxd4 cxd4 25.Re7+ Kb6 26.Qxd4+ Kxa5`입니다. 다음 표의 cp는 해당 국면의 착수 쪽 기준입니다. 한 엔진 내에서 후보를 비교하는 데 사용했습니다. [원본 대국 PGN](https://github.com/kerry-huang-nyu/chessRobot/blob/main/kasparov_topalov_1999.pgn)

| 분기 | Tal Lab v0.8.6, 지정 수 검색 4초 | Stockfish 17.1, 지정 수 검색 3초 |
|---|---|---|
| `27.b4+` / `27.Qc3` | 깊이 6에서 −455 / −353cp | +454 / −257cp |
| `27.b4+ Ka4 28.Ra7` / `28.Qc3` | 깊이 6에서 −712 / −445cp | +320 / +110cp |
| `28.Ra7` 뒤 흑의 응수 | 4초와 7초 모두 `...Bxd5`가 1위이며 흑 +712cp | 3초 `...Bb7`, 8초 `...Rc8`이 1위이며 두 응수 모두 흑 열세 |

`28...Bxd5` 지정 수를 7초 검색하면 Tal Lab은 깊이 6에서 흑 +481cp와 `29.Kb2`를 반환했습니다. Stockfish 8초는 흑 −956cp와 `29.Qc3`를 반환했습니다. 다른 방어인 `28...Bb7 29.Rxb7`에서는 Tal Lab이 `...Nd5`를, Stockfish가 `...Qd5`를 선택했습니다. 체크 연장이나 패스 실험을 켠 뒤에도 위 분기에서 공격 보상이 실질적으로 개선되지 않았습니다.

`24.Rxd4` 루트 자유 탐색에서 Null-move 단독은 30초·MultiPV 3으로 깊이 6에 도달해 `Rxd4`를 3위(−67cp)에 올렸습니다. 초기 측정과 교대 재측정 두 번 모두 같은 순위와 점수였고, 기본은 세 번 모두 상위 3개 밖이었습니다. 기본과 다른 실험의 완료 깊이도 6이었습니다. Null-move의 PV는 `24...cxd4 25.Qxd4+`로 이어졌습니다. `Rxd4`를 지정해 독립적으로 탐색하자 깊이 6에서 기준, Null-move, 결합 모두 −383cp를 반환했습니다. Stockfish 5초 자유 탐색은 `Rxd4`를 1위(−39cp)에 뒀습니다. 실험 결과에서 `Rxd4`의 상태는 **Sacrifice Candidate**입니다.

### 같은 깊이에서 비용 비교

Intel Xeon Platinum 8573C, Python 3.12.14, TT 60,000 엔트리, 조건별 새 프로세스, 동일 비교 묶음은 단일 논리 CPU에서 순차 실행했습니다. 묶음 간에는 여러 검증이 동시에 실행돼 벽시계 시간은 공유 CPU 부하의 영향을 받았습니다. 30초 총노드는 중단된 다음 반복도 포함합니다. 고정 깊이 비교는 마지막 깊이까지의 총노드입니다.

| `Rxd4` 국면 고정 깊이 6 | 기준 노드 | 제한 2회 노드 | Null-move 노드 | 결합 노드 |
|---|---:|---:|---:|---:|
| MultiPV 1 | 667,111 | 653,567 | 400,106 | 505,909 |
| MultiPV 3 | 1,064,248 | 1,057,203 | 691,623 | 896,716 |

깊이 4와 5에서는 Null-move 노드 수가 기본보다 많았습니다. 깊이 6의 절감 폭은 MultiPV 1에서 40.0%, MultiPV 3에서 35.0%였습니다. 깊이 6 MultiPV 3 시점의 상위 후보 변경은 독립 지정 탐색에서 보존되지 않았습니다. 10초 실측에서는 네 설정이 모두 깊이 5였고 `Rxd4`가 출력에 없었습니다. 5초 국면 비교에서 Null-move는 Lasker `15.Bxh7+` 직전과 Rubinstein `22...Rxc3` 직전 MultiPV 1의 깊이를 1씩 늘렸으나 해당 착수를 1위로 찾지 못했습니다. Lasker 첫 희생은 세 설정 모두 5초 MultiPV 3에서 2위였습니다. 두 번째 `17.Bxg7`과 Rubinstein의 희생, Tal의 Botvinnik전 `...Nf4`와 Larsen전 `Nd5`는 해당 실험의 상위 후보에 들지 않았습니다. 전체 깊이별 수순·점수·노드·시간·NPS 및 Stockfish 독립 비교는 `evidence/`에 있습니다.

## 별도 퍼즐 검증

[Lichess 퍼즐 데이터베이스](https://database.lichess.org/#puzzles)의 2026-11-01 CC0 덤프를 사용했습니다. 압축 파일의 SHA-256은 `7b0d235fa40cfd7fdb7df1fec56a96b3b6ee1496b32ed2eb05be90d0ebf94253`입니다. 평점 1500–2400, 인기도 90 이상, 시도 500회 이상 조건에서 대국 ID를 먼저 해시해 두 묶음으로 나눴습니다. 각 묶음에서 장수순·비메이트 희생, 수비, 기타 전술을 8개씩 고정 추출했습니다. 대국 ID 중복은 0개입니다. 원본 CSV가 지정한 첫 수를 적용한 뒤 다음 수를 퍼즐 정답으로 삼고 전체 해법의 합법성을 python-chess로 확인했습니다. 퍼즐 정답 첫 수의 순위를 측정하며, 전체 해법을 완주하는 비율이나 퍼즐 주제 전체의 대표성은 이 표본으로 추정하기 어렵습니다. 독립 비교는 Stockfish 17.1, Threads 1, Hash 32 MiB, 국면별 해시 초기화, 기본 1초입니다.

개발용 24개에서 기준·연장 2회·null-move·위협 단독·결합은 1초 MultiPV 3 정답 1위 20/24, 상위 3위 23/24였습니다. 체크 연장 제거는 완료 깊이 합이 89에서 105로 늘었지만 1위 18/24, 상위 3위 22/24, 희생 상위 3위 6/8로 떨어졌습니다. 이 결과를 근거로 체크 연장 제거를 검증용 후보에서 제외했습니다. 나머지 비교 프로필의 매개변수는 검증 자료를 보고 조정하지 않았습니다.

### 검증용 24국면, MultiPV 3

| 3초 결과 | v0.8.6 기준 | 체크 연장 2회 | Null-move | 결합 |
|---|---:|---:|---:|---:|
| 퍼즐 정답 1위 | 20/24 | 18/24 | 19/24 | 18/24 |
| 퍼즐 정답 상위 3위 | 21/24 | 20/24 | 21/24 | 20/24 |
| 긴 희생 정답 상위 3위 | 7/8 | 6/8 | 7/8 | 6/8 |
| 방어 정답 1위 | 8/8 | 8/8 | 8/8 | 8/8 |
| Stockfish 최선수 일치 | 20/24 | 18/24 | 19/24 | 18/24 |
| 완료 깊이 합 | 142 | 141 | 142 | 141 |

1초에는 네 설정 모두 정답 1위 17/24, 상위 3위 20/24, 긴 희생 상위 3위 6/8, 방어 1위 8/8이었습니다. 완료 깊이 합은 기준 118, 제한 119, Null-move 120, 결합 119였습니다. `Rh6+`가 1초에 기준 2위에서 제한·결합 3위로, 3초에는 기준 1위에서 세 실험 모두 2위로 내려갔습니다. 3초에 기본이 1위로 찾은 `Bxh7+`는 제한·결합에서 상위 3개 밖이었습니다. 두 국면 모두 실험이 한 반수 낮게 완료된 조건이 있었으므로 탐색 기법의 단독 오류로 단정하기 어렵습니다. 검증용 퍼즐에서 새로 상위 3개에 오른 정답은 없었습니다. [Rh6+](https://lichess.org/training/RqQNy) · [Bxh7+](https://lichess.org/training/58cMq)

### 페어 대국

Stockfish 17.1의 Skill Level 0, 단일 스레드를 기준으로 같은 오프닝에서 색을 바꿔 순차 대국했습니다. 80ms 명령에서 기준 4승, 체크 연장 제한 1승 3패, Null-move 3승 1패, 결합 3승 1무였습니다. 이 실행은 Tal Lab 기본 `Move Overhead`를 포함하는 예비 측정입니다. 이를 0으로 설정한 별도의 200ms 실행에서도 기준 4승, Null-move 3승 1무였고, 같은 오프닝·색의 대응 표본에서 점수율 차이는 −12.5%p였습니다. 대응 표본 4쌍, 약화된 상대, 공유 CPU 환경이므로 기력이나 Elo 차이를 추정하기에는 부족합니다. 두 실행에 시간패나 엔진 오류는 없었습니다.

## 회귀와 배포

독립 정답이 있는 대조 16개에서 각 프로필이 0.4초·MultiPV 1과 3 각각 16/16이었습니다. 강제 메이트는 각각 9/9, 부정확한 수의 최선 선택은 0/4였습니다. 별도의 희생 판정에서 불리한 예시 3개를 기본·제한·Null-move·결합에 각각 입력했고, 12건 중 지원 또는 검증 희생으로 판정한 경우는 0건입니다. 시간 제한에서 충분한 깊이를 완료하지 못한 일부 결과는 **Sacrifice Candidate**에 머물렀습니다.

고정 깊이 4, 실전 23국면, MultiPV 1·3의 v0.8.6과 v0.8.7 기본 비교 46쌍에서 모든 완료 반복의 후보·점수·PV·노드 기록이 같았습니다. v0.8.7의 기본 검색은 기존 체크 연장을 유지하고 새 패스 옵션을 기본 비활성화합니다. 새 설정은 UCI 및 연구 도구에서 명시적으로 켤 수 있습니다.

Python 단위 테스트 199개, 전체 엔진 테스트 216개, 프런트엔드 확인 22개를 통과했습니다. `perft.py --deep` 검사와 271,312개 노드의 Zobrist 재계산 대조도 통과했습니다. 서버 자동 분석 선점·우선순위 검사는 Python 단위 테스트에 포함됩니다.

Node에서 웹 워커와 같은 Pyodide 0.27.7 및 동일 소스를 실행했습니다. PGN `1.e4 e5 2.Nf3 Nc6`의 첫 착수 뒤, 네이티브 서버 분석 코드와 깊이 5·MultiPV 3의 버전·순위·점수·PV·노드가 일치했습니다. Chromium은 이 실행 환경에서 소켓 권한 제한으로 실행되지 않아, 브라우저 전체 동작과 실제 효과음 출력은 검증하지 못했습니다.

UCI는 최종 재실행에서 70/70을 통과했습니다. 최초 실행에서 상대경로 `PYTHONPATH`를 사용해 작업 폴더를 바꾸는 대국 도구 하위 프로세스 9건이 python-chess를 읽지 못했습니다. 의존성 경로를 절대경로로 고쳐 재실행했습니다. 새 옵션의 UCI 등록 및 실제 합법 수 반환도 확인했습니다.

## 재현

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -q
python test_engine.py --full
python test_uci.py
python perft.py --deep
zstdcat lichess_db_puzzle.csv.zst | python -m research.lichess_sample --output lichess-splits.json
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --puzzles lichess-splits.json --split holdout --profiles baseline bounded null combined --seconds 1 3 --multipv 3 --reference-seconds 1 --output holdout.json
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --case ply47 --profiles baseline bounded null combined --depths 4 5 6 --multipv 1 3 --reference-seconds 3 --output kasparov-fixed.json
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --case ply47 --profiles baseline null --seconds 30 --multipv 3 --repeats 2 --reference-seconds 5 --output kasparov-null-repeat.json
python -m research.kasparov_followup --baseline "$baseline" --stockfish "$stockfish" --seconds 4 --reference-seconds 3 --output kasparov-branches.json
python match.py --engine1 'python uci.py' --engine2 "$stockfish" --variant baseline: --variant null:ExperimentalNullMove=true --opt2 Threads=1 --opt2 Hash=32 --opt2 'Skill Level=0' --opt1 Hash=16 --opt1 'Move Overhead=0' --games 4 --movetime 200 --pgn stockfish-null-match.pgn --label v087-null --seed 88 --no-strength-check
```

다음 실험은 Null-move에서 베타 컷이 난 뒤 실제 합법 수로 재탐색하는 검증을 추가하고, 자유 탐색과 지정 탐색의 `Rxd4` 점수 차이가 줄어드는지 확인하는 것입니다. 공격 보상 측정에서는 `28...Bxd5 29.Qc3`와 `28...Bb7 29.Rxb7`의 양쪽 후속 수를 고정해 계산이 갈리는 시점과 별도 희생 퍼즐의 회귀를 함께 재검증할 수 있습니다.
