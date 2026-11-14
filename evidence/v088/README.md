# v0.8.8 검증 원본

| 경로 | 내용 |
|---|---|
| `suite.json` | Arasan 저장소(`jdart1/arasan-chess` `99adddf`, MIT, Copyright 1994-2026 Jon Dart)의 `tests/wacnew.epd`, `ecmgcp.epd`, `iq4.epd`에서 Stockfish 16 1초 최선수가 정답과 같은 574국면. `see`는 정답 수의 정적 교환 평가 |
| `suite2.json` | v0.8.7 `evidence/lichess-splits.json` 48국면과 `research.sacrifice_cases` 23국면을 같은 형식으로 옮긴 것 |
| `results/wac_*`, `hold*`, `s2_3_*`, `hist10_*` | 전폭(`base`)과 선택적(`new`, `final`) 실행 결과. 국면별 수·점수·완료 깊이·노드·시간 |
| `results/ab_*`, `r2_*`, `r3_*`, `r4_*` | 구성 요소별 비교와 채택하지 않은 실험 (WAC, 1초) |
| `results/fd_087.json`, `fd_final.json` | 기본 설정 고정 깊이 4, 120국면. 두 파일의 내용이 같음 |
| `match/v088.*` | Stockfish 16 `UCI_Elo=1700` 페어 대국 80판 |
| `match/h2h.*` | 선택적 vs 전폭 맞대결 40판 |
| `tests/` | 최종 소스의 테스트 로그 |
| `scripts/` | 위 결과를 만든 스크립트 원본. 측정 환경의 절대 경로가 들어 있음. 정리한 도구는 `research/epd_suite.py`, `research/suite_runner.py` |

결과 파일의 `<v0.8.7>`은 첨부 ZIP 원본, `<v0.8.8>`은 이 소스와 탐색 코드가 같은 측정용 사본입니다. 대국 기록의 엔진 이름은 버전 문자열을 올리기 전이라 `MyEngine 0.8.7`로 남아 있습니다.
