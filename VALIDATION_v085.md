# Tal Lab v0.8.5 전술 분기 진단

기준은 개발판 v0.8.4 `5cf5ae61515781007ee9ed06612c29c5e3a2bc47`이고 GitHub main은 `4b91b757a49b2b33ae1fdbebd00fd350bc905442`입니다. 이전 버전에서 생성한 원본 로그 및 새 비교는 ZIP의 `evidence/`에 있습니다. 서로 다른 엔진의 cp를 같은 척도로 취급하지 않았습니다.

## Kasparov–Topalov 1999, 24.Rxd4

기보를 양쪽 구현에서 처음부터 재생한 FEN은 다음과 같습니다. [대국 PGN](https://github.com/kerry-huang-nyu/chessRobot/blob/main/kasparov_topalov_1999.pgn)

```text
b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24
```

v0.8.4 지정 수는 깊이 5/6/7에서 −370/−383/−105cp였습니다. Stockfish 17.1은 방어 재탐색 5초·MultiPV 3에서 거절 수 `...Kb6` −32cp, `...Rhe8` 및 `...Bxd5` 각각 0cp를 우선했습니다. 이 비교는 각 엔진의 완료 깊이와 탐색 예산 범위에 한합니다.

| 고정한 흑 방어 | Tal Lab과 Stockfish가 처음 다르게 둔 수 |
|---|---|
| `...cxd4` 수락 | 바로 `25.Qxd4+` / `25.Re7+` |
| `...Kb6` 거절 | `25.b4` 뒤 `...cxb4` / `...Qxf4` |
| `...Rhe8` 거절 | `25.Rxe8 Nxe8` 뒤 `Qxd6` / `Qxf7+` |
| `...Bxd5` 거절 | `Qxd6` / `Rxd5` |

수락 뒤 Tal Lab 깊이 5에서 `Qxd4+` −105, `Re7+` −412cp였습니다. 독립 Stockfish 5초 MultiPV 3은 깊이 23에서 `Re7+` +83, `Qxd4+` −218cp였습니다. 다시 각 수를 단독 지정한 Stockfish는 `Re7+` +224, `Qxd4+` −250cp였으므로 방향이 반복됐고 크기는 달랐습니다.

| 수락 직후 지정 후보, Tal Lab 깊이 5 | Qxd4+ | Re7+ |
|---|---:|---:|
| 기본 | −105 | −412 |
| 조용한 체크 1회 | −105 | −391 |
| 연속 체크 | −105 | −363 |
| 캡처 뒤 체크 | −149 | −363 |
| LMR | −105 | −412 |
| PVS 끔 | −105 | −412 |
| TT 끔 | −105 | −412 |
| 공격 수 정렬 | −105 | −412 |
| AttackActivity | −103 | −397 |
| Initiative | −100 | 깊이 4까지만 완료, −390 |
| KingSafety | −128 | 깊이 4까지만 완료, −386 |

`Re7+`는 합법 응수가 **8개**인 체크입니다. 적은 방어 수만 보는 방식으로는 이 수를 확실히 보존하기 어렵습니다. `Re7+ Kb6 Qxd4+ Kxa5`까지 고정하면 Stockfish는 `27.b4+`를 찾았고, Tal Lab은 `27.Qc3`를 골랐습니다. `b4+ Ka4`까지 주었을 때에도 Tal Lab은 `Qc3`에 −455cp를 매겼고 Stockfish는 `Ra7`을 +383cp로 1위에 뒀습니다. Tal Lab이 체크 하나를 추가하면 해소되는 차이보다 범위가 큽니다. 분석한 가지에서 수평선 효과는 확인했고, 더 긴 공격과 평가 함수의 기여도를 완전히 분리하지는 못했습니다.

## 일반화와 대조

- Rubinstein `22...Rxc3`에서 Tal Lab은 기본 지정 깊이 6 −128cp, 이전 연속 체크 대조에서는 같은 깊이 −38cp였습니다. 5초 자유 탐색에는 포함되지 않았습니다. Stockfish는 수락 `...Rxc3 23.gxh4`보다 `23.Bxb7`을 더 강한 방어로 봤습니다.
- Lasker `15.Bxh7+`는 5초·MultiPV 3의 여러 설정에서 2위였습니다. `17.Bxg7`은 같은 시간에 기존 연속 체크로 두 MultiPV 설정 모두 1위였고, 합법 응수 두 개 제한을 추가하면 두 설정에서 놓쳤습니다. 이 회귀 때문에 해당 제한을 기본 적용하지 않았습니다.
- Tal의 Botvinnik전 `21...Nf4`와 Larsen전 `16.Nd5`는 기본 1초 실전 비교에서 상위 3개 밖입니다. Stockfish는 후자를 지정 탐색보다 `Ne2`를 선호했습니다. Tal의 수를 정답으로 두지 않았습니다.
- Kasparov의 별도 1985년 Karpov전 두 국면을 추가했습니다. Tal Lab과 python-chess 모두 전체 23개 국면의 FEN과 착수 SAN을 검증했습니다. [1985년 제16국 기보](https://chessmotion.com/explore/famous-chess-games/karpov-kasparov-game-16)
- 정적 탐색에서 50수 도달을 예약할 수 있는 조용한 방어는 이전 −485cp, 수정 후 0cp입니다. 3회 반복 예약 대조도 −400→0cp였습니다. 검색 루트와 바로 아래 정적 국면에서 기보 이력으로 입증되는 반복 청구를 검사하며, 트리 안에서 최초 반복을 무승부로 근사하는 기존 정책은 유지합니다. 메이트 우선, 스테일메이트, 보드·해시 복원을 각각 확인했습니다. [FIDE 경기 규정](https://handbook.fide.com/chapter/E012023)
- 정적 탐색 깊이 1의 `...Bxf1 Ra8#` 함정은 일반 연속 체크 및 응수 제한 옵션에서 회피했습니다. 1초 또는 깊이 4에서는 기본 두 버전도 회피했습니다. 일반화된 실전 향상으로 집계하지 않았습니다.

## 비교 실행

```bash
python -m pip install -r requirements-dev.txt
python -m research.branch_diagnostic --source /path/to/v084 --stockfish /path/to/stockfish --seconds 5 --reference-seconds 5 --output branches.json
python -m research.tactical_benchmark --baseline /path/to/v084 --stockfish /path/to/stockfish --case ply47 --depths 4 5 6 --output fixed.json
python -m research.tactical_benchmark --baseline /path/to/v084 --stockfish /path/to/stockfish --case ply47 --seconds 1 5 10 30 --output timed.json
python -m research.tactical_benchmark --baseline /path/to/v084 --stockfish /path/to/stockfish --suite controls --seconds 1 --output controls.json
python -m unittest discover -q
```

새 조용한 체크 선별은 수의 종류와 합법 응수 개수만 사용합니다. 역사적 착수, Stockfish 수순과 기물 희생 여부는 탐색 점수나 순서에 주입하지 않습니다.
