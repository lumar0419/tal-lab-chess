# Tal Lab v0.8.3 전술 탐색 검증

기준은 v0.8.2 커밋 `6499bbadf379d9e1f81873b53268c015042c6eb1`입니다. GitHub main은 `4b91b757a49b2b33ae1fdbebd00fd350bc905442`입니다. 첨부 독립 리뷰의 속도 38.8%는 v0.7.0 대비이며, 80판 페어 대국의 점수율 차이 +8.8%p의 95% 범위는 −9.8~+27.3%p입니다. 이번 변경의 기력 개선 근거로 사용하지 않았습니다.

## 탐색 변경과 정확성

정적 탐색은 체크 중 모든 합법 회피수를, 평상시 캡처·앙파상·네 종류의 승격을 계산합니다. 실험 옵션에서 조용한 체크 후보를 상대 킹의 빈 광선과 발견 체크 차폐 기물로 생성합니다. 합법 체크의 순서도 보존했습니다. 최종 보드 합법성·실제 체크 검사는 그대로 수행합니다. 체크 연속 옵션은 최대 두 번의 조용한 체크를 허용합니다. 별도 캡처 실험은 남은 체크 예산이 2일 때 캡처 한 번으로 소비하고 체크 1회를 남깁니다. 두 번째 연속 캡처는 이 예산을 보존하지 않습니다.

TT 설정 키에 실험 옵션을 포함해 이전 검색의 점수를 혼용하지 않습니다. PVS, LMR, 50수·반복 판정, 시간 중단·보드 복원 및 완료된 MultiPV만 게시하는 정책은 그대로 사용합니다. qsearch에서 반복·50수·메이트 우선 처리도 기존 경로를 공유합니다. 실험 옵션은 기본 비활성입니다.

| 검증 | 결과 |
|---|---|
| 합법 체크 생성 | python-chess 독립 대조, 합법 체크 누락 및 순서 차이 0 |
| 첨부 회피 스크립트 | 93,453 체크 국면에서 합법 회피수 및 존재 여부 불일치 0. 첨부 대국을 입력으로 사용 |
| 첨부 MultiPV 재현 | 보관 FEN 40개, 316줄의 지정 수 점수·순위·형식 불일치 0 |
| 독립 메이트, 1초 | 기본 두 버전과 모든 실험 각각 MultiPV 1 9/9, MultiPV 3 9/9 |
| 불리한 희생 | 퀸·룩 인위 대조 3개 중 3개 불리 판정, 오판 0. 별도 퀸 포획 함정은 1초 자유 탐색의 모든 설정에서 회피 |
| 실전 21개, 1초·MultiPV 3 | v0.8.2/v0.8.3 기본 Stockfish 1위 일치 각각 6/21, 역사적 수 상위 3개 8/21 대 7/21 |

1초 실전 차이는 Kasparov의 **25.Re7+**에서 발생했습니다. 한 쌍에서 v0.8.2 깊이 4는 3위, v0.8.3 깊이 3은 후보 밖이었습니다. 두 버전의 기본 고정 깊이 트리는 일치했습니다. 이 국면의 별도 교대 재시험 4회에서는 두 버전 모두 깊이 4와 3위를 재현했습니다. 다른 기본 비교 사례에서 새로 찾아낸 전술은 관찰하지 않았습니다. 별도 정적 탐색 회귀에서 캡처 뒤 체크 실험은 `...Bxf1` 후 `Ra8#`를 계산해 잘못된 캡처 추천을 피했습니다. 이 사례는 1초 자유 탐색에서는 이미 기본 탐색으로 해결됩니다.

## 지정 탐색과 5초 자유 탐색

Stockfish 17.1, 1스레드, 해시 32 MiB, 각각 8초인 지정 수 및 상대 방어입니다. Tal Lab의 같은 깊이 수치를 공격자 관점 cp로 비교했습니다.

| 국면 | Tal Lab 기본 | 연속 체크 | 캡처 뒤 체크 | Stockfish 지정 수 |
|---|---:|---:|---:|---:|
| Kasparov 24.Rxd4, 깊이 5 | −370 | −67 | −105 | −21, 깊이 31 |
| Lasker 15.Bxh7+, 깊이 6 | −274 | −156 | −156 | +465, 깊이 24 |
| Lasker 17.Bxg7, 깊이 5 | −506 | −156 | −149 | +468, 깊이 24 |
| Rubinstein 22...Rxc3, 깊이 6 | −128 | −38 | −38 | +735, 깊이 26 |

Kasparov의 기본 지정 탐색 깊이 7은 −105였습니다. 희생을 수락한 `...cxd4` 지정 분기는 깊이 6에서 기본/연속 체크 −105, 캡처 뒤 체크 −149였습니다. Stockfish는 수락을 +432, 거절 `...Kb6`를 −19로 평가했고, 상대 루트에서 거절 수 `...Kb6`, `...Rhe8`, `...Bxd5`가 앞섰습니다. 첨부 Stockfish 16에서도 수락보다 거절이 강했고 평가 차이의 크기는 달랐습니다. Tal Lab은 여전히 수락의 위험을 과소평가합니다.

Lasker 첫 희생의 자유 탐색은 5초 MultiPV 3에서 2위였고, 두 번째 희생은 기본 후보 밖에서 연속 체크로 1위에 올랐습니다. 이 상승은 기존 v0.8.2 연속 체크에서도 발생했습니다. Rubinstein의 첫 룩 희생과 Kasparov의 `Rxd4`는 이번 5초 비교에서 모든 설정의 후보 밖이었습니다. 지정 수의 개선과 자유 탐색의 발견을 별도로 판단했습니다. 세 국면에 대해 조용한 체크의 영향을 확인했지만, 남은 차이를 평가 함수 하나의 문제로 분리할 근거는 없습니다.

고정 깊이 4에서 두 버전의 동일 연속 체크 설정은 네 국면의 MultiPV 1/3 모두 최종 수·점수·PV·노드 수가 일치했습니다. 같은 CPU 코어에서 순서를 번갈아 3회씩 실행한 별도 반복의 국면별 중앙 시간 합은 MultiPV 1에서 4.374→4.051초, MultiPV 3에서 6.733→6.106초였습니다. 각각 약 7.4%, 9.3% 감소입니다. NPS는 54,955→59,330 및 55,194→60,855였습니다. 시간, NPS, 완료 깊이 및 회차별 후보는 `focus-fixed.json`, `quiet-fixed-paired.json`, `focus-timed.json`에 있습니다. 캡처 뒤 체크는 일부 지정 점수의 발견을 앞당겼지만 자유 탐색에서 새 역사적 수를 안정적으로 발견하지 못했고, 21개 실전 비교의 완료 깊이 합이 일반 연속 체크 64에서 60으로 낮아져 연구용으로 유지합니다.

## 재현

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -q
python -m research.benchmark_v083 --baseline /path/to/v082 --stockfish /path/to/stockfish --fixed --depth 4 --repeats 3 --output fixed.json
python -m research.benchmark_v083 --baseline /path/to/v082 --stockfish /path/to/stockfish --seconds 5 --depth 9 --output timed.json
python -m research.benchmark_v083 --baseline /path/to/v082 --stockfish /path/to/stockfish --suite heldout --seconds 1 --depth 5 --output heldout.json
python -m research.benchmark_v083 --baseline /path/to/v082 --stockfish /path/to/stockfish --suite historical --seconds 1 --multipv 3 --depth 8 --output historical.json
python -m research.diagnose_v083 --baseline /path/to/v082 --stockfish /path/to/stockfish --output diagnosis.json
```

포지셔널 희생의 독립 정답률 및 실전 기력 변화는 추가 검증이 필요합니다. 다음 실험은 수락 방어의 강제 공격을 놓치는 첫 분기에서 시작해 후보 누락과 평가 오류를 분리하고, 고정 시간 재현과 독립 비메이트 전술까지 함께 검증하는 것이 적절합니다.
