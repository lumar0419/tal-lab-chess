# Tal Lab v0.5.3 — 정확도 및 마스터 희생 수순 연구

기존 단일 Python 체스 엔진(v0.5.2)과 Render 웹사이트를 **그대로 유지**하면서 검색 효율과 객관적인 전술 검증 기반을 개선한 버전입니다. Stockfish 소스나 사전 계산된 마스터 정답수를 실제 대국의 `search()` 안에 넣지 않습니다.

## 웹사이트에서 좋아진 점

1. **게임별 Transposition Table 재사용**: 이전 버전은 상대에게 매 응수할 때 `Searcher(tt_size=60000)`를 새로 만들었습니다. v0.5.3은 *같은 대국, 같은 옵션*에서는 하나의 Searcher/TT를 이어서 사용합니다. 새로운 대국 시작 시에는 이전 캐시를 분리합니다. 여러 웹 세션 사이에 TT를 공유하지 않습니다.
2. **정확도 우선 설정 버튼**: 웹에서 클릭하면 최대 탐색 깊이 6, 한 수당 5초, 검증되지 않은 공격 옵션 OFF로 준비합니다. 실제 대국 중 변경하려면 '새 대국 시작'을 눌러야 합니다. 5초로 시간을 길게 주면 상대적으로 느릴 수 있고 무료 서버 이용 제한도 고려해야 합니다.
3. **LMR 탐색 최적화(실험 옵션)**: Late Move Reductions가 *후순위의 조용한 비체크 수*를 먼저 한 수 얕게 검사하고, alpha를 넘으면 원래 깊이로 재탐색합니다. 캡처·승격·체크·루트·PV·킬러 수·승격 직전 폰은 줄이지 않습니다. **기본 OFF**입니다. 일부 전술은 깊은 검증을 요구하므로 LMR 도입이 Elo를 높였다고 단정하지 않습니다. 웹의 '고급 옵션 → LMR 탐색(실험)' 또는 UCI `setoption name LMR value true`로 켭니다.

## 역사적 희생 검증: 여러 마스터

- `master_sacrifices.py`: 피셔·카스파로프·안데르센의 **기록된 합법적 수순을 SAN에서 보드로 재생**해 6개의 대표 후보를 추출하고, 탈의 기존 대표 4개까지 합쳐 10개 국면을 분석합니다.
- `master_sacrifice_cases.json`: 각 국면의 FEN, SAN, UCI, 출처, 공격 주제.
- `test_v053.py`: 모든 기록의 SAN→합법수→FEN 교차 검증, 엔진/웹 캐시 테스트.
- 주의: 'Brilliant'는 평가 기관마다 정의가 다릅니다. 역사적 수와 같다고 정답/최선수/기물 희생의 건전성이 증명되는 것은 아닙니다. 1851년 Anderssen–Kieseritzky의 마지막 부분은 여러 기록에서 '전통적으로 전승된 수순'임을 명시합니다.

### 시험 방법

```bash
python test_v053.py
python -m unittest test_web test_cloud test_tactics test_v053 -q
python master_sacrifices.py --depth 3 --output master_report.json
python master_sacrifices.py --case fischer_byrne_1956_ply22 --depth 5 --lmr
```

선택적으로 **설치된 Stockfish(제한 강도 아님)**에 동일 국면의 후보 수를 비교할 수 있습니다. 이 경우 `pip install chess`와 Stockfish 실행 파일이 별도로 필요합니다.

```bash
python master_sacrifices.py --case fischer_byrne_1956_ply34 --depth 4 \
  --stockfish /path/to/stockfish --sf-depth 18 --output fischer_review.json
```

### 실제로 측정한 범위 (동일 환경, depth 5, 단발)

| 포지션 | 기존 노드 | LMR ON 노드 | 동일 최선수/점수? |
|---|---:|---:|---|
| 시작 국면 | 21,435 | 9,505 | 예 |
| Fischer 11...Na4 직전 | 157,785 | 87,388 | 예 |
| Fischer 17...Be6 직전 | 163,856 | 84,874 | 예 |
| Kasparov 24.Rxd4 직전 | 152,712 | 70,119 | 예 |

**경고:** 작은 표본이고 고정 깊이 비교일 뿐입니다. 탐색 결과가 다른 국면도 나올 수 있습니다. 시간제한 대국/전문 엔진과의 실전 대국 및 희생 건전성 검증을 별도로 완료해야 합니다.

깊이 3에서 피셔·카스파로프·안데르센 6국면과 탈의 기존 대표 4국면의 **역사적 수 선택 일치율은 1/10**이었습니다. `11...Na4`는 깊이 4에서 발견되었습니다. **현재 목표는 희생을 무작정 늘리는 것이 아니라, 상대의 최선 방어에도 성립하는 공격을 발견하는 것**입니다.

### 원본 대국 출처

- Fischer–Byrne 1956: https://www.chessworld.net/chessclubs/openingguide/game-of-the-century.asp
- Kasparov–Topalov 1999: https://github.com/kerry-huang-nyu/chessRobot/blob/main/kasparov_topalov_1999.pgn
- Anderssen–Kieseritzky 1851 (전승 수순): https://huggingface.co/datasets/tms-gvd/chess-game1-white/blob/main/anderssen_kieseritzky_1851.pgn
- Tal의 기존 검증 국면: `tal_positions.json` 참고.

## 기존 Render 사이트 업데이트

기존 GitHub 저장소의 파일을 삭제하지 마세요. **`tal_lab_update_v053_github.zip`의 압축을 풀어 그 안의 파일을 GitHub 저장소의 루트에 업로드**하고 기존 파일을 같은 경로로 교체한 후 Commit하세요. `render.yaml`이나 기존 Render 환경변수/비밀번호를 변경할 필요는 없습니다. Render에서 가장 최신 커밋이 Live인지 확인하세요. 사이트 주소는 기존과 같습니다: https://tal-lab-chess.onrender.com

재배포 시 메모리에 있던 진행 중 대국은 사라질 수 있으니 PGN을 먼저 저장하세요.

보안: 공개 서비스 비밀번호는 환경변수에만 보관하며 GitHub/이 문서에 입력하지 않습니다. 변경 후에도 모든 보안 문제가 해결되었다고 주장하지 않습니다.
