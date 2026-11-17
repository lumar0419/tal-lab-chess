# Tal Lab NNUE 계획 — v0.9.5 이후의 독립 실험

v0.9.4에서는 Classical Evaluation을 유지한다. NNUE 추론·학습·모델 배포는 구현하지 않았다. 다른 엔진의 성공은 Tal Lab에서의 성능 보장이 아니다. 소스 기준은 `PYTHON_ENGINE_COMPARISON_v094.md`에 고정했다.

## 먼저 비교할 구조

첫 모델은 768개 piece-square 입력 → 64 또는 128 hidden → 1 output의 작은 residual로 시작한다. 양쪽 관점 accumulator를 사용하고 출력은 동일한 가중치로 `f(white)-f(black)`를 계산해 정확한 색 대칭을 강제한다. 기존 classical 점수와 합산하되 크기 제한도 ablation한다. classical, residual NNUE, NNUE-only를 별도 실험하고 기본 엔진은 classical로 남긴다. 킹 위치를 충분히 표현하지 못하면 4~8 king bucket을 별도 후보로 비교한다.

예상 가중치 크기(설계 추정, 실측 아님): int16 768×64는 약 96KiB, ×128은 약 192KiB이며 head/bias/메타데이터가 추가된다. 8개 king bucket이면 첫 층이 약 8배 커진다. 작은 크기라도 Python 정수·객체 리스트로 저장하면 메모리가 크게 늘어나므로 연속 배열과 실제 RSS를 재야 한다.

Stockfish 19의 실제 소스는 HalfKAv2_hm뿐 아니라 FullThreats, PP_3Wide와 L1=1024, L2=L3=32, 8 layer stacks를 사용한다. 옛 HalfKP 설명을 최신 Stockfish 구조라고 부르지 않는다. Tal Lab의 첫 실험에 이 구조를 그대로 이식할 이유는 없다.

## 데이터·학습

1. CC0 PGN 또는 자체 대국에서 게임 단위 분할, 중복 수순/국면 제거, source hash를 보존한다. 이번 두 사용자 경기와 역사 희생 문제는 진단/회귀 전용으로 격리한다.
2. 먼저 10만~100만 quiet 국면을 목표로 수집하되 유효 표본 수와 게임 수를 함께 보고한다. 체크·승격·교환 중 국면에는 별도 QS 라벨링 정책이 필요하다. 이번 9,297개 표본은 NNUE 학습 성공을 주장할 근거가 아니다.
3. 결과 라벨과 고정 버전 기준 엔진의 WDL/평가 라벨을 분리해 저장한다. Stockfish CP를 승률로 무조건 선형 변환하지 않는다. teacher 목표와 승패 혼합 비율도 validation으로 선택한다.
4. PyTorch 등으로 offline 학습하고, quantization 전후 오차·클리핑·overflow를 확인한다. 모델에는 구조 버전, 체크섬, 가중치/데이터 라이선스, 학습 설정과 검증 결과를 붙인다.
5. 학습과 validation으로 후보를 잠근 뒤 독립 test를 한 번 평가한다. test를 보고 다시 조정하면 새 test가 필요하다. 정적 loss 개선만으로 엔진에 채택하지 않는다.

## 증분 업데이트와 규칙 정확성

보통 수는 출발 feature를 빼고 도착 feature를 더한다. 포획, 앙파상(도착 칸과 다른 칸의 폰 제거), 승격(폰 제거 + 새 기물 추가), 캐슬링(킹과 룩 동시 이동), null move(기물 변화 없음, 관점만 전환), king-bucket 이동(해당 accumulator 재구축)을 각각 처리한다. make/unmake stack에는 원복에 충분한 정보가 있어야 한다.

매 수의 증분 점수와 완전 재계산 점수가 일치해야 한다. promotion/underpromotion/EP/castling, 무작위 합법 대국, mirror, 중단 예외 후 복원, TT와 eval cache의 model-id 격리를 검사한다. Numbfish가 문서화한 EP accumulator 누락을 재현하지 않아야 한다. 신경망의 승률이 높아도 불법수·해시·반복 문제를 정당화할 수 없다.

## 실행 환경별 실험

| 환경 | 우선 후보 | 실제 확인할 비용/제약 |
|---|---|---|
| CPython | 순수 Python 기준 구현 + NumPy/작은 C kernel 비교 | 배열 복사, 함수 경계, activation/head 추론이 작은 네트워크의 이득을 상쇄할 수 있음 |
| PyPy | 순수 Python 또는 typed array loop | CPython용 NumPy/확장 호출과 JIT 경계 비용. CPython 수치를 재사용하지 않음 |
| Cython/C | accumulator + head를 하나의 큰 호출 단위로 | 노드당 ctypes 왕복 금지, saturating integer 계산과 signed overflow 검사 |
| Pyodide | classical fallback + 작은 WASM/NumPy 후보 | 초기 모델 다운로드, wasm 메모리, cross-language 호출, Worker 취소와 CDN 실패 |
| Render/UCI | 명시적 EvalBackend/Model 옵션과 checksum | 모델 미설치·불일치 시 조용한 오동작 없이 classical로 명시적 fallback |

Pygin처럼 전체 탐색 핫패스를 native로 옮기는 실험은 NNUE와 분리한다. 이번 Tal Lab CPU profile은 수 생성, 공격 판정, make/unmake의 비용도 크다는 점을 보여준다. 평가만 가속한 속도와 전체 엔진 NPS를 구분한다. Numba는 JIT 준비 시간과 Pyodide 미지원/제약을 고려해 선택적 backend로만 검토한다.

## 채택 조건

- 동일 노드에서 판단 개선, 동일 시간에서 정확도 및 완료 깊이, microbenchmark/RSS/startup 모두 기록.
- 전술·수비·quiet holdout와 Lasker/Rubinstein 희생 회귀, Kasparov 목표 및 불건전한 희생 대조군 유지.
- 색 교환 오프닝으로 classical 대비 사전 등록한 fastchess SPRT 또는 충분한 고정판수 독립 대국. 매치의 시간패/불법수/메모리 pressure를 기력 패배와 분리.
- 짧은 시간뿐 아니라 실제 사용 조건인 60초 분석, MultiPV 1/2/3을 각각 검사.
- 재현 가능한 모델/데이터 권한과 브라우저 fallback을 갖춘 경우에만 기본값 변경을 검토.

가중치는 별도 데이터 저작물로 취급한다. MIT 코드라는 이유로 모델이 자유롭게 재배포 가능하다고 가정하지 않는다. Stockfish 계열 GPL 코드/가중치와 Tal Lab의 독립 구현·학습을 구분한다. 모델 로딩에는 pickle 같은 실행 가능한 직렬화 대신 크기 검증을 하는 명시적 바이너리 형식을 권장한다.
