# Tal Lab v0.8.6 검증

v0.8.4 개발판 `5cf5ae61515781007ee9ed06612c29c5e3a2bc47`에서 시작했습니다. 작업 시작 시 확인한 GitHub main은 `4b91b757a49b2b33ae1fdbebd00fd350bc905442`입니다. v0.8.5 전술 분기 진단과 규칙 수정은 `1bb2a866ebfc535f20a582236b0eb7057edf5a1e`에 있습니다. [v0.8.5 분석](VALIDATION_v085.md)

v0.8.6은 검증된 무승부 청구 처리를 유지하고 연구용 희생 보고를 확장했습니다. 후보별 깊이·순위·점수·PV·물질 수지·체크 횟수와 별도 수비 탐색의 완료 깊이·주요 응수를 기록합니다. 수비 탐색 깊이가 비교에 사용한 최종 깊이보다 두 수 이상 얕으면 보상 판정을 보류합니다. 여기서 깊이의 단위는 반수(ply)입니다. 제한된 깊이에서 평가가 안정되면 엔진 지원의 근거로만 사용합니다. 검증 표시는 모든 합법 방어를 확인한 짧은 강제 메이트로 제한하며, 최대 5반수와 25,000노드의 증명 범위를 함께 기록합니다. 활동성, Initiative, 조용한 체크 응수 제한은 실험 설정으로 남겼습니다.

## 같은 환경에서 측정

Intel Xeon Platinum 8573C, Python 3.12.14, 프로필별 새 검색기, TT 60,000개 엔트리. 각 비교 실행에서 두 엔진을 동일한 단일 CPU에 고정하고 실행 순서를 교대했습니다. 시간 측정에는 공유 호스트의 스케줄링 영향이 있습니다. JSON에는 마지막 완료 깊이의 수순·점수와, 중단한 반복까지 포함한 총 벽시계 시간·총 노드·NPS를 따로 보존합니다. Stockfish 17.1은 독립 UCI 프로세스로 실행했으며 Threads 1, Hash 32 MiB, 국면마다 해시 초기화, 역사 비교 1초, Rxd4 루트 장시간 비교 8초, 수락·거절 분기별 5초를 사용했습니다. cp는 각 엔진 내부에서 해석합니다. 역사적 착수 일치율은 그 수가 객관적으로 최선임을 뜻하지 않습니다.

### Kasparov–Topalov 24.Rxd4 고정 깊이

각 쌍에서 완료 깊이, 모든 노드 수와 출력한 후보·점수·수순이 같았습니다. 최선수는 모두 `Nxc6`였고 Rxd4는 상위 후보에 들지 않았습니다.

| 깊이 | MultiPV | 시간(초) v0.8.4 → v0.8.6 | 노드(동일) | NPS v0.8.4 → v0.8.6 |
| ---: | ---: | ---: | ---: | ---: |
| 4 | 1 | 0.70 → 0.68 | 31,672 | 45,323 → 46,445 |
| 4 | 3 | 0.98 → 0.98 | 48,653 | 49,598 → 49,611 |
| 5 | 1 | 2.74 → 3.04 | 152,131 | 55,449 → 50,045 |
| 5 | 3 | 4.05 → 3.98 | 211,830 | 52,368 → 53,164 |
| 6 | 1 | 15.39 → 14.14 | 667,111 | 43,336 → 47,181 |
| 6 | 3 | 24.52 → 24.32 | 1,064,248 | 43,404 → 43,767 |

### 동일 시간

| 제한 | MultiPV | 완료 깊이 v0.8.4 → v0.8.6 | 실측 시간(초) v0.8.4 → v0.8.6 | 노드 v0.8.4 → v0.8.6 | NPS v0.8.4 → v0.8.6 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1초 | 1 | 4 → 4 | 1.01 → 1.01 | 70,584 → 72,632 | 70,130 → 71,684 |
| 1초 | 3 | 4 → 3 | 1.02 → 1.00 | 74,253 → 40,055 | 72,965 → 39,965 |
| 5초 | 1 | 5 → 5 | 5.01 → 5.00 | 263,747 → 259,651 | 52,660 → 51,922 |
| 5초 | 3 | 5 → 5 | 5.00 → 5.01 | 360,310 → 383,862 | 72,015 → 76,627 |
| 10초 | 1 | 5 → 5 | 10.01 → 10.03 | 570,947 → 539,203 | 57,062 → 53,737 |
| 10초 | 3 | 5 → 5 | 10.02 → 10.01 | 642,934 → 621,430 | 64,190 → 62,070 |
| 30초 | 1 | 6 → 6 | 30.01 → 30.00 | 1,792,487 → 1,878,503 | 59,735 → 62,609 |
| 30초 재측정 | 3 | 6 → 6 | 30.00 → 30.01 | 2,118,968 → 2,107,704 | 70,621 → 70,230 |

30초 MultiPV 3 최초 측정은 깊이 5 → 6이었고 재측정에서는 두 버전 모두 깊이 6을 완료했습니다. 1초 첫 측정의 v0.8.6 MultiPV 3은 깊이 3에서 `Qxd6`을 반환했습니다. 1초 MultiPV 3을 다섯 쌍 재측정하자 양쪽 모두 다섯 번 깊이 4와 `Nxc6`에 도달했습니다. 나머지 루트 조합도 `Nxc6`을 골랐습니다. Rxd4는 어느 조합에서도 출력 후보에 들지 않았습니다. 같은 환경의 Stockfish는 8초 MultiPV 3 깊이 25에서 Rxd4를 −35cp로 1위에 뒀습니다. 따라서 이 실험은 희생 발견이나 속도 향상을 입증하지 못합니다.

Lasker의 두 번째 비숍 희생, Rubinstein의 룩 희생, Tal의 Botvinnik전 나이트 희생과 Larsen전 포지셔널 희생도 1·5·10초와 MultiPV 1·3으로 확인했습니다. 기본 설정의 두 버전 모두 네 착수를 출력 후보로 올리지 못했습니다. Lasker의 **첫 번째** 희생은 별도 5초 대조에서 MultiPV 3 후보 2위였습니다. Kasparov의 별도 1985년 Karpov전 `16...Nd3`는 5초에서 두 버전 모두 MultiPV 1의 1위, MultiPV 3의 2위였습니다. Tal의 Larsen전 지정 희생은 역사 착수이며, 측정한 Stockfish 루트에서는 `Ne2`를 우선했습니다.

## 정확성, 새로 해결한 사례, 실험에서 놓친 사례

| 지표 | v0.8.4 | v0.8.6 |
| --- | ---: | ---: |
| 독립 정답이 있는 1초 대조, MultiPV 1 | 16/16 | 16/16 |
| 독립 정답이 있는 1초 대조, MultiPV 3 | 16/16 | 16/16 |
| 1초 강제 메이트, MultiPV 1과 3 각각 | 9/9 | 9/9 |
| 1초 불리한 착수 선택, MultiPV 1과 3 각각 | 0/4 | 0/4 |
| 역사적 착수 상위 3개, 1초 23개 | 8/23 | 8/23 |
| Stockfish 1위 일치, 역사 국면 23개 | 6/23 | 6/23 |
| 역사 국면 완료 깊이 합계, MultiPV 3 | 72 | 71 |
| 역사 국면 총 노드 ÷ 총 시간 | 38,517 NPS | 38,829 NPS |
| Python 단위 테스트 | 185 통과 | 192 통과 |

- 두 기본 버전이 찾은 역사적 착수 8개는 모두 같았습니다. Stockfish의 역사적 착수 1위는 17/23이었습니다. 이 표의 16개 대조는 세 무승부 확보, 네 부정확한 착수 회피, 아홉 메이트입니다. 최종 대조는 `v086-controls-final.json`, 깊이별 조용한 방어 대조와 합성 분류 검증은 `quiet-defense.json`과 `negative-final.json`에 있습니다.
- 50수 도달을 선언할 수 있는 조용한 수를 평가하던 정적 탐색에서 흑과 백 모두 기존 −485cp가 0cp로 고쳐졌습니다. 3회 반복을 선언하는 기보 이력은 −400cp가 0cp로 바뀌었습니다. FEN만으로 불러온 경우 반복 이력이 없고, 메이트는 청구보다 우선합니다. 양쪽 사례를 python-chess에서도 확인했습니다.
- `forcing` 실험은 Rxd4를 고정 깊이 5 MultiPV 3에서 2위로 올렸습니다. 이전 연속 체크 옵션은 같은 깊이에서 3위였습니다. 그러나 5초에서는 Rxd4를 찾지 못했고, 기존 연속 체크가 1위로 찾던 Lasker `17.Bxg7`도 MultiPV 1과 3에서 놓쳤습니다. 이 옵션을 기본 설정에서 제외했습니다. `...Bxf1 Ra8#` 함정은 깊이 1에서 연속 체크 계열로 회피했고, 깊이 4와 1초에서는 기존 기본 설정도 회피했습니다.
- Anderssen `22.Qf6+`과 Morphy `16.Qb8+`의 메이트를 각각 3반수 범위에서 증명했습니다. 기존 버전도 두 수를 발견했습니다. Rxd4는 **Sacrifice Candidate**로 남겼으며, 흑·백의 불리한 퀸 희생과 백의 불리한 룩 희생은 세 건 모두 **Unfavorable Sacrifice**였습니다.

## 회귀와 배포 범위

- v0.8.5 Python 190개, v0.8.6 Python 192개, 전체 엔진 216개, UCI 70개 모두 통과했습니다. 서버·플랫폼·안정성 대조 20개는 Python 단위 테스트 합계에 포함됩니다. 프런트엔드 13개 및 시각화 도우미 9개 확인도 통과했습니다. `perft.py --deep`의 수 생성 검사와 해시 271,312노드 검증도 통과했습니다.
- 격리된 Chrome에서 PGN `1.e4 e5 2.Nf3 Nc6`를 불러왔습니다. 1.e4 뒤 양쪽 CPU는 깊이 5·MultiPV 3에서 같은 착수·점수·PV를 냈고 화살표와 평가 그래프도 일치했습니다. 자동 분석을 켜고 다음 국면으로 이동했을 때 해당 국면의 평가 점이 추가됐습니다. 실제 이동 효과음 출력과 운영 Render 서비스는 이번에 시험하지 않았습니다.
- 독립 v0.8.4 리뷰의 기준 커밋은 이번 기준과 일치했습니다. 리뷰의 지정 수 스크립트를 v0.8.6에서 재실행해 Rxd4와 Lasker의 두 희생에서 9개 점수가 모두 일치하는 것을 확인했습니다. 리뷰의 조용한 체크 스크립트도 무작위 2,500판과 이번 기보를 재생해 362,400국면의 합법 체크 475,318개를 대조했고, 누락·잘못된 추가·순서 차이 모두 0건이었습니다. 리뷰에 남은 수동 장시간 분석 중 다른 세션의 대국 대기 제한과 신규 로그인 주소 예산은 이번 범위 밖입니다. 개발 메모가 제안한 체크 연장과 null-move는 각각의 효과를 분리해 다음 실험에서 비교할 수 있습니다.
- 기본 엔진은 v0.8.5에서 검증한 규칙 수정으로 제한했습니다. v0.8.6의 상세 보고는 연구용 명령에 추가했습니다. 기본 탐색에서 Rxd4의 수락 수순 `25.Re7+ Kb6 26.Qxd4+ Kxa5 27.b4+ Ka4 28.Ra7`에 이르는 공격 보상은 여전히 과소평가합니다. 다음 단계는 수락 분기의 수비를 충분한 예산으로 다시 순위화한 뒤, 여러 기물 손실 뒤 이어지는 강제 공격과 조용한 반박을 포함한 별도 국면에서 평가 변화가 반복되는지 확인하는 것입니다.

## 재현

다음 명령을 프로젝트 루트에서 실행합니다. `$baseline`은 v0.8.4 체크아웃이고 `$stockfish`는 외부 Stockfish 17.1 바이너리입니다. 원본 JSON과 테스트 로그는 ZIP의 `evidence/`에 있습니다.

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -q
python test_engine.py --full
python test_uci.py
python perft.py --deep
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --case ply47 --depths 4 5 6 --reference-seconds 3 --output fixed.json
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --case ply47 --seconds 1 5 10 30 --reference-seconds 8 --output timed.json
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --suite historical --seconds 1 --multipv 3 --reference-seconds 1 --output historical.json
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --suite controls --seconds 1 --reference-seconds 0.35 --output controls.json
python -m research.tactical_benchmark --baseline "$baseline" --stockfish "$stockfish" --case kasparov_topalov_1999_ply47 --case lasker_bauer_1889_ply29 --case lasker_bauer_1889_ply33 --case rotlewi_rubinstein_1907_ply44 --profiles baseline continuation forcing forcing_bridge --seconds 5 --reference-seconds 3 --output options.json
python -m research.deep_sacrifice --baseline "$baseline" --stockfish "$stockfish" --case kasparov_topalov_1999_ply47 --move d1d4 --seconds 4 --depth 6 --output sacrifice.json
```
