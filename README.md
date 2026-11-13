# Tal Lab v0.5.4 — 분석 중심 웹사이트

**기존 v0.5.3 Python 체스 엔진을 유지하고, 대국이 아닌 '국면 분석'을 메인 화면으로 변경**했습니다.

- **메인 주소 `/` 또는 `/analysis`**: 체스 분석실. 백/흑 모두 직접 수를 둘 수 있고, 엔진이 자동으로 응수하지 않습니다.
- **예전 대국 모드 `/play`**: 유지. 기존 URL의 대국 기능은 삭제하지 않았습니다.
- **깊이별 실시간 업데이트**: Iterative deepening에서 **완료한** 각 깊이의 최선수, 평가(백 기준), 예상 수순(PV), 경과 시간과 노드를 기록합니다. 현재 계산 중인 깊이도 따로 표시합니다.
- **최소 *목표* 깊이와 최대 깊이**: 기본 목표 5, 최대 8. 기존 대국 모드의 '제한시간의 절반 경과 시 다음 깊이를 시작하지 않음' 휴리스틱을 **분석 모드에서만 비활성화**했습니다. 선택한 최대 시간 내에 다음 깊이까지 계속 계산을 시도합니다.
- **안전 시간 상한**: 10/20/30/45/60초. 특정 깊이까지 무조건 도달하겠다는 보장은 아닙니다. 서버의 안전 상한에 먼저 걸리면 `target_not_reached`로 표시하고 마지막 완료 깊이만 결과로 보존합니다.
- **기보 분석**: FEN 입력, 마스터 기물 희생 국면 선택, 판 위에서 양쪽 수 직접 진행, 한 수 무르기, 시작 국면, 추천수 적용, 판 뒤집기.
- **공격 성향은 실험 옵션**: Balanced 평가를 기본값으로 유지. TacticalChecks, AttackActivity, Initiative, TacticalOrdering, CheckContinuation, Aspiration, KingSafety, LMR 옵션을 필요할 때 켤 수 있습니다. 이 기능이 실전 실력을 높였다는 뜻은 아닙니다.
- **보안 및 세션 관리**: 기존 Render 기본 인증, 브라우저별 세션, 로그인 시도 제한, 동시 검색 보호 기능을 유지합니다.

## GitHub / Render 업그레이드

1. 기존 GitHub 저장소(`tal-lab-chess`)는 **삭제하지 않습니다.**
2. 배포용 `tal_lab_update_v054_github.zip`을 압축 해제하고, 안의 모든 파일과 `web` 폴더를 **저장소 최상위**에 업로드하고 Commit하세요. **같은 경로는 새 파일로 교체**되며, 변경하지 않은 기존 파일은 그대로 둡니다.
3. Render의 `Deploys`에서 **최신 커밋이 Live**인지 확인합니다.
4. 기존 사이트 주소 `https://tal-lab-chess.onrender.com/`는 이제 분석실이고, 기존 대국 화면은 `https://tal-lab-chess.onrender.com/play`입니다.
5. 접속 계정(`TAL_SITE_USER`/`TAL_SITE_PASSWORD`)은 변경하지 않아도 됩니다.

> 아직 Render 웹사이트에 새 코드가 실제 반영된 것은 아닙니다. GitHub에 업데이트한 뒤 자동 배포가 완료되어야 합니다.

## 로컬 실행

Python 3가 설치된 폴더에서 `python web_server.py --no-browser` 실행 후 `http://127.0.0.1:8000/`로 접속합니다. Windows에서는 `start_web.bat`를 사용할 수 있습니다. **별도 웹 프레임워크나 패키지는 필요하지 않습니다.**

## API

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | `/api/analysis/state` | 현재 국면, 완료 깊이, 계산 중 깊이, PV/평가/기록 |
| GET | `/api/analysis/cases` | 등록된 마스터 사례의 FEN, 역사적 수 |
| POST | `/api/analysis/fen` | `{ "fen": "..." }` FEN 불러오기 |
| POST | `/api/analysis/move` | `{ "uci": "e2e4" }` 수 진행 |
| POST | `/api/analysis/undo` | 마지막 직접 진행한 수 되돌리기 |
| POST | `/api/analysis/reset` | 시작 국면으로 |
| POST | `/api/analysis/start` | `{ "min_depth": 5, "max_depth": 8, "seconds": 30, "options": {} }` |
| POST | `/api/analysis/stop` | 현재 분석 중단 |

분석 진행 중에도 GET 요청으로 상태를 가져올 수 있으며, 브라우저에서 약 600ms마다 요청합니다. 웹 서버의 메인 요청 스레드는 검색 완료를 기다리지 않습니다.

## 테스트

```
python -m unittest -v test_v054
python -m unittest -q test_v054 test_web test_cloud test_v052 test_v053
node --check web/analysis.js  # Node.js가 있다면 선택적으로 확인
```

- 현재 버전의 신규 분석 테스트와 기존 서버/웹 회귀 테스트를 합친 **52개**가 통과했습니다.
- `analysis.js` JavaScript 문법과 HTML ID 참조를 정적으로 확인했습니다.
- 전체 장시간 엔진 회귀 시험과 외부 Stockfish 상대 Elo 평가는 **이번 업데이트에서 완료하지 않았습니다**.
- 웹 브라우저 자동 렌더링 검증은 실행 환경에서 로컬 접속이 차단되어 완료하지 못했습니다. 서버/API 테스트는 통과했지만 실제 배포 후 브라우저에서 확인해야 합니다.

## 분석 결과 해석 주의

- 이 엔진의 'DEPTH 5'는 그 깊이까지 **완료된 탐색**을 뜻하며, 현재 더 깊은 탐색이 진행 중이어도 결과는 보수적으로 유지합니다.
- **최소 깊이는 '목표'이지 하한 보장이 아닙니다.** 특히 Render 무료 인스턴스에서는 복잡한 국면의 깊이 6 이상이 시간 상한 안에 끝나지 않을 수 있습니다.
- 마스터의 역사적 희생 수와 엔진의 선택이 일치한다고 해서 그 수가 객관적으로 최선인 것은 아닙니다. 일반적인 Elo, 전술 정확도, 희생 건전성은 별도로 평가해야 합니다.
- 서버가 절전/재시작되면 메모리에 저장된 FEN/분석 결과는 초기화됩니다. 보존하려는 FEN은 복사해 두세요.

## 다음 개발 후보

깊이별 PV 변화 이력을 저장하고, **MultiPV(상위 여러 후보 수)** 및 각 희생 후보를 강제로 탐색한 점수와 상대 최선 방어의 비교를 추가하면 정확한 희생 연구에 유용합니다.
