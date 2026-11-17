# Python 체스 엔진 비교 — v0.9.4

2026-11-17(한국 시간) 공개 저장소를 직접 읽었다. 아래 성능 숫자는 외부 개발자가 공개한 주장/실험이며 이번 작업에서 독립 재측정한 값이 아니다. Lichess, Stockfish UCI_Elo, CCRL 척도는 서로 환산하지 않는다. Tal Lab의 기력 향상 근거로 사용하지 않는다.

| 구분 | Tal Lab | PyCheckmate | Numbfish | Pygin | Sunfish |
|---|---|---|---|---|---|
| 언어/실행 구조 | 순수 Python 120칸 mailbox, PyPy/선택적 Cython/Pyodide | 순수 Python mailbox, PyPy UCI subprocess, CPython GUI | Sunfish 계열 Python, NumPy 및 TFLite native 추론 | 배포 엔진의 노드 루프·수 생성·make/unmake·평가는 C; Python은 반복 심화·시간·책 | Python immutable position/string, 기본 PST 증분 평가; 별도 NNUE 실험 |
| 평가 방식 | material/PST/폰/비숍쌍 tapered, 기존 KS/activity/initiative는 opt-in | material/PST/mobility/pawn/rook/minor quality/king/mopup, Texel | HalfKP NNUE 2×256 accumulator + TFLite head, 종반 PST | HCE + NNUE hybrid, qsearch stand-pat은 HCE | classic PST; nnue_4k는 PST + 작은 신경망 residual |
| 탐색 알고리즘 | iterative negamax/PVS/aspiration/TT/QS, 선택적 LMR/null/RFP/futility/LMP/IIR, 루트 SEE 희생 연장 | alpha-beta/aspiration/TT/QS/SEE/null/LMR/check extension | MTD-bi, null/TT, Sunfish 계열 QS | C negamax/PVS/QS, selective pruning, NNUE lazy evaluation | MTD-bi/C*, TT bound, null, QS |
| 주요 최적화 | incremental hash, pawn/eval cache, evasion generation, PyPy/Cython | AI용 간소 move/undo와 증분 hash, precomputed mobility rays, 프로파일 후 채택 | NumPy accumulator sparse update, TFLite inference | 노드당 Python↔C 경계 제거, SIMD/TT/전용 noisy generator, 일부 증분 eval | 증분 PST, 간결한 position 연산, NNUE의 Python big-int packed arithmetic |
| 성능 검증 방식 | 규칙 oracle/perft, 전술·역사 모음, paired UCI match, 이번 grouped Texel/새 quiet holdout | bench, fastchess SPRT wrapper, calibration, 실제 봇 대국 review | 저자 보고 Sunfish 상대 30판, Lichess 약 2300 | 자체 A/B 수천~1만판, SPRT/고정판수 구분, 별도 rating ladder | pytest/프로토콜 검사/fastchess, NNUE 증분·대칭성 인증 및 자체 대국 |
| Tal Lab 적용 가능성 | 검증 원칙 강화 | **게임 단위 분리, 검증 실패 시 기각, 오프닝 색 교환, 실제 artifact 측정 우선 적용** | accumulator 설계 참고; 모델/런타임/규칙 누락을 그대로 가져오지 않음 | profile에 근거해 보드와 탐색의 큰 경계를 C로 이관하는 별도 실험 | 노드 동일성 검사, 증분 평가, 작은 residual 접근 검토; 탐색 전체 교체 근거는 없음 |

## 직접 확인한 소스

- [PyCheckmate 고정 커밋](https://github.com/pdloc06/PyCheckmate/tree/edd4049bb314147402f638db9a92f52150c94162) — `edd4049bb314147402f638db9a92f52150c94162`

- [numbfish 고정 커밋](https://github.com/dimdano/numbfish/tree/97fcbbca1ab9f724b806b5b90ceff6541ac0b46f) — `97fcbbca1ab9f724b806b5b90ceff6541ac0b46f`

- [Pygin 고정 커밋](https://github.com/IchNukeDichWeg/Pygin/tree/ff12d8de40eead6ddd257a3b36f4d5b3f20957d4) — `ff12d8de40eead6ddd257a3b36f4d5b3f20957d4`

- [sunfish 고정 커밋](https://github.com/thomasahle/sunfish/tree/e396948acbd80cdcbad3dccfb07e878fba9df8f4) — `e396948acbd80cdcbad3dccfb07e878fba9df8f4`

- PyCheckmate: `engine/eval.py`, `engine/search.py`, `engine/tools/tune.py`, `engine/tools/sprt.py`, `README.md`, `LICENSE`.
- Numbfish: `numbfish.py`, NNUE/추론 관련 파일, `requirements.txt`, `README.md`, `LICENSE`.
- Pygin: `engine.py`, `cengine.py`, `csearch.c`, `movegen.c`, `eval_c.c`, `NNUE/`, `README.md`, `LICENSE`.
- Sunfish: `sunfish.py`, `nnue_4k/README.md`, `LICENSE.md`.
- Stockfish: 공식 `sf_19` release의 `src/nnue/nnue_architecture.h`, feature/accumulator 구현 및 `Copying.txt`. 실행 파일 출처와 SHA-256은 `evidence/v094/environment.json`.

## PyCheckmate에서 배운 실험 설계

튜너는 승/무/패 결과에 sigmoid(score)를 맞추는 MSE를 사용한다. K를 먼저 맞추고, 학습 오차보다 holdout 검증을 우선한다. README는 725,000개 quiet 국면으로 튜닝했다고 설명하지만 도구의 기본 로드 상한은 메모리 때문에 200,000개다. 실제 실행 크기는 별도 확인 대상이다. EPD의 512줄 블록은 동일 게임 그룹의 **근사**일 뿐 완전한 누수 방지가 아니라는 소스 주석도 확인했다.

Tal Lab은 이번에 PGN 전체 수순의 SHA-256으로 게임을 식별하고 게임별 70/15/15 분할을 먼저 한다. 같은 국면은 전역에서 한 번만 남기고, 제공된 두 경기와 기존 JSON 테스트 FEN은 제외한다. K/좌표별 정수 가중치는 학습 세트로만 맞추며, validation으로 pass를 선택한 다음 test MSE를 한 번 계산한다. 두 실전 기보는 학습에 넣지 않는다. 구현은 독립 작성한 `research/texel_v094.py`다.

PyCheckmate의 작은 자기 대국 데이터로 실패한 튜닝과, 빠른 NPS만으로 충분하지 않다는 분석은 참고 가치가 있다. 개발자가 보고한 PyPy movegen 약 2.3배와 전체 search 약 1.3배도 Tal Lab에 그대로 대입하지 않는다. Tal Lab의 이번 프로파일에서는 평가 외에도 수 생성·공격 검사·make/unmake가 큰 비중을 차지했다.

SPRT는 외부 엔진의 수식을 대충 복제하지 않았다. 후속 실험은 검증된 fastchess의 paired/pentanomial 통계를 사용하고, 사전에 [0,5] Elo, alpha=beta=0.05, 오프닝·시간제한·최대판수를 고정해야 한다. 지금의 소규모 fixed-budget 경기는 screening이며 SPRT 통과가 아니다.

## NNUE 및 native 비교에서 주의할 점

Numbfish의 NumPy 배열 연산과 TFLite는 native 라이브러리 비용을 포함한다. README는 약 14K NPS 대 Sunfish 54K NPS에도 대부분 이겼다고 보고한다. 이는 평가 정확도가 속도 손실을 상쇄할 가능성을 보이는 저자 사례이며, 30판으로 일반적인 상대적 기력을 확정할 수 없다. underpromotion 및 en-passant accumulator 누락, 2회 반복 처리 문제를 명시하고 있어 규칙 구현을 재사용할 근거가 되지 않는다.

Pygin의 현재 배포 구조는 단순히 Python에서 수 생성만 C로 호출하는 엔진이 아니다. 전체 per-node 루프가 C다. 저자의 약 50배 속도, 약 3164±15 rating ladder와 누적 +474 Elo는 자체 실험이다. 특히 README 스스로 공식 CCRL 등재가 아니라 CCRL-rated 상대 두 엔진에 대한 자체 배치 추정이라고 구분한다. 누적 개선과 최신 통합 버전의 직접 측정도 구분해야 한다.

Sunfish README의 '4KB NNUE' 문구만 인용하면 부정확하다. 현재 `nnue_4k/README.md`는 엔진 약 3,800바이트와 가장 작은 모델 7.5MB를 명시하고 전체 4096바이트 목표가 아직 미해결이라고 정정한다. big-int packed accumulator는 흥미롭지만 lane overflow, clipping, antisymmetry의 엄격한 검증이 선행되어야 한다.

## 라이선스와 재사용 판단

| 대상 | 확인한 라이선스 | 이번 처리 |
|---|---|---|
| Tal Lab | 루트에 명시적 LICENSE 파일 없음 | 소유자 저장소 내 독립 구현만 수정. 제3자에게 포괄적인 재배포 권한이 있다고 가정하지 않음 |
| PyCheckmate | MIT, Copyright 2026 Loc Pham; 일부 기물 SVG 별도 CC BY-SA | 아이디어/측정 방법만 참고. 코드를 복사할 경우 MIT 고지와 저작권 필요, SVG는 별도 조건 |
| Pygin | MIT, Copyright 2026 IchNukeDichWeg | 코드/모델 미복사. 재사용 시 MIT 고지 및 모델·학습자료의 별도 출처 확인 |
| Numbfish | GPL-3.0 텍스트; Stockfish 유래 가중치 | 코드·가중치 미복사. 결합/배포 시 GPL 의무 및 모델 원출처를 별도 검토 |
| Sunfish | GPL-3.0 텍스트 | 코드/모델 미복사. 별도 엔진 실험과 코드 결합을 구분 |
| Stockfish | GPL-3.0 | 공식 실행 파일을 독립 검증 프로세스로만 실행. 저장소에 바이너리/모델 재배포하지 않음 |
| Lichess 공개 PGN | CC0-1.0, database.lichess.org | 원본 URL·해시·샘플 조건 기록. 결과 라벨과 FEN 파생 표본 보존 |

MIT가 표시되어도 신경망 가중치·외부 데이터·이미지에 동일 조건이 적용된다고 가정하지 않는다. Tal Lab 엔진은 Stockfish/PyCheckmate/Numbfish/Pygin/Sunfish를 런타임에 호출하거나 import하지 않는다. 검증용 python-chess/NumPy/Zstandard는 개발 도구에만 필요하다.
