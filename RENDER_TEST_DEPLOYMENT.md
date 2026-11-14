# Tal Lab v0.9.2 — 별도 Render 테스트 사이트

배포 대상은 `development/render-test-v092`입니다. 검증된 v0.9.2 개발 커밋
`7a91e38256931ab70c223edae584477022f388d5`에서 분기했습니다.
`main`, `development/performance-accuracy-v092`, 기존 `tal-lab-chess.onrender.com`은 수정하지 않습니다.

**설치 없이 사용하는 방법**

접속자는 Chrome 또는 Edge에서 테스트 사이트 주소를 열고 테스트 사이트 전용 계정으로 로그인하면 됩니다.
접속자 PC에 Python, PyPy, Git, Node를 설치할 필요가 없습니다. 첫 방문에는 약 14MB의
Pyodide 런타임을 같은 사이트에서 다운로드합니다. 이후 같은 브라우저는 버전별 캐시를 이용합니다.
기본값은 **로컬 CPU · 브라우저**이며, 기존 선택 메뉴에서 **서버 CPU**로 전환할 수 있습니다.

| 선택 | 실제 계산 위치 | 접속자에게 필요한 것 |
| --- | --- | --- |
| 로컬 CPU | 브라우저 웹 워커의 Python/WebAssembly(Pyodide 0.27.7) | WebAssembly를 허용하는 최신 Chrome/Edge |
| 서버 CPU | 새 Render 서비스의 Tal Lab Python 엔진 | 웹브라우저와 인터넷 |
| 자동 | 기존 실측 비교로 선택 | 두 방식의 결과가 일치해야 자동 선택 적용 |

학교 정책이 WebAssembly 실행을 막으면 서버 CPU를 선택합니다. PC 절전·탭 폐기·브라우저 종료 시
로컬 계산을 계속할 수는 없습니다. 긴 로컬 분석 중에는 탭을 열어 두세요.
공용 PC에서는 시크릿 창을 사용하고, PGN/분석 JSON을 저장한 뒤 창을 닫는 편이 좋습니다.

**준비한 배포 설정**

이 브랜치의 루트 `render.yaml`은 기존 운영 서비스용 파일과 다른 **테스트 전용** 설정입니다.
운영 main의 `render.yaml`은 그대로입니다.

| 항목 | 값 |
| --- | --- |
| 서비스 이름 | `tal-lab-chess-v092-test` |
| Git 저장소 | `https://github.com/lumar0419/tal-lab-chess` |
| 브랜치 | `development/render-test-v092` |
| Runtime | Python / CPython 3.12.14 |
| Region | Singapore |
| Plan | Free |
| 인스턴스 수 | 1 — 세션은 프로세스 메모리에 저장 |
| Build | `python tools/prepare_web_runtime.py && python -m compileall -q board.py evaluate.py search.py web_server.py cloud_server.py analysis_server.py deep_analysis.py` |
| Start | `python cloud_server.py` |
| Health check | `/healthz` |
| 자동 배포 | OFF — 검토 후 수동 배포 |

서버는 Render의 `PORT`와 `RENDER_EXTERNAL_HOSTNAME`을 사용해 `0.0.0.0`에서 수신합니다.
`TAL_SITE_USER=player`, `TAL_SITE_PASSWORD`는 **12자 이상의 새 테스트 전용 비밀번호**를
Render에서 설정합니다. 저장소에 비밀번호를 넣지 않습니다. 기존 운영 비밀번호를 재사용할 필요가 없습니다.

추가 환경 변수는 YAML에 포함했습니다.

| 변수 | 값/역할 |
| --- | --- |
| `PYTHON_VERSION` | `3.12.14` |
| `TAL_DEFAULT_COMPUTE` | `local` — 첫 방문부터 브라우저 CPU |
| `TAL_PYODIDE_BASE` | `/runtime/pyodide/v0.27.7/` — 외부 CDN 의존 제거 |
| `TAL_SITE_LABEL` | `Tal Lab v0.9.2 TEST` — 테스트 사이트 표시 |
| `TAL_JOB_LEASE_SECONDS` | `90` — 진행 조회가 끊긴 서버 작업 취소 |
| `TAL_MAX_SESSIONS` | `32` — 동시 접속 세션 상한, 동시 CPU 계산 수는 1 |

Pyodide 원본 npm 아카이브의 고정 SHA-512를 검사하고 필요한 파일만 추출합니다.
WebAssembly 파일은 올바른 MIME으로 메모리 사용량을 제한해 스트리밍하며, 버전별 private 캐시를 사용합니다.
MPL/PSF 라이선스와 소스 위치 안내도 같은 경로에 제공합니다.
런타임 바이너리는 Git에 넣지 않고 Render 빌드 시 준비합니다. 브라우저용 Python 소스는
기존 `/engine/` 허용 목록으로 제공합니다.

**Render에 새 서비스를 만드는 절차**

Render 연결을 통한 계획 작성 또는 대시보드의 New Blueprint 중 하나를 사용합니다.
기존 운영 서비스나 기존 운영 Blueprint의 설정 화면에서 브랜치를 바꾸지 마세요.

1. 새 Blueprint를 만들고 이 저장소의 `development/render-test-v092`를 선택합니다.
2. Blueprint 경로는 루트 `render.yaml`입니다.
3. 계획에 **새 테스트 서비스 생성만** 나오는지 확인합니다. 기존 운영 서비스 수정이 나오면 적용하지 않습니다.
4. Free, Singapore, Python, 단일 인스턴스, 자동 배포 OFF를 확인합니다.
5. 새 테스트 전용 `TAL_SITE_PASSWORD`를 Render에서 입력합니다. 채팅에 비밀번호를 적을 필요는 없습니다.
6. 검토한 계획을 승인해 빌드/배포합니다. 계정의 무료 사용량 한도나 결제 조건은 Render에서 확인합니다.
7. Live가 되면 Render가 반환한 실제 `onrender.com` 주소를 사용합니다. 이름에 임의 접미사가 붙을 수 있으므로 주소를 미리 확정하지 않습니다.

브랜치가 게시된 후 다음 링크로 시작할 수도 있습니다.

[테스트 브랜치로 Deploy to Render 시작](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Flumar0419%2Ftal-lab-chess%2Ftree%2Fdevelopment%2Frender-test-v092)

대시보드에서 직접 설정한다면 반드시 브랜치를 위 값으로 선택합니다. 기본 main을 선택하면
운영용 YAML이 나타날 수 있습니다. 새 서비스를 생성하는 절차이며 기존 서비스를 재배포하는 절차가 아닙니다.

Render 연결 도구를 이용할 때는 작업 공간 확인 후 `create_new`로 계획을 만들고 `autoSync=false`를
사용합니다. **계획 작성은 배포가 아닙니다.** 검토한 계획의 실제 적용은 별도 승인이 필요합니다.
`sync:false` 환경 변수는 사용자가 제공한 값만 적용할 수 있으므로 비밀번호는 대시보드에서 입력할 수 있습니다.
대시보드에서 먼저 승인하고 나중에 환경 변수를 넣는 경우, 값을 넣기 전의 첫 배포는 실패할 수 있습니다.

**60·180·300·600초 작업과 동시 사용**

긴 분석은 HTTP 요청 하나를 10분 열어두지 않습니다. 시작 요청은 작업을 등록하고 반환하고,
화면이 짧은 진행 조회 요청으로 완료 깊이와 PV를 받습니다. 연결의 15초 소켓 제한과 분석의 600초
예산은 별개입니다. 각 시간은 상한이며 특정 탐색 깊이 도달 보장이 아닙니다.

서버 전체 CPU 슬롯은 한 개입니다. 대국/수동 분석과 빠른 분석이 심층 분석보다 우선하며,
상위 요청은 심층 작업을 선점할 수 있습니다. 대기열은 최대 32개, 통상 대기 시간은 7초이며
슬롯을 얻지 못하면 사용자에게 busy 상태를 반환합니다. 32세션이 32개 분석을 동시에 실행한다는 뜻은 아닙니다.
브라우저 로컬 분석은 각 PC에서 실행하므로 이 CPU 슬롯을 소비하지 않습니다.

중단 버튼과 국면 변경은 기존 취소 신호를 유지합니다. 다른 화면으로 이동할 때 짧은 취소 요청을
보내며, 오래된 탭이 새 작업을 중단하지 못하도록 epoch를 확인합니다. 요청을 보내지 못하고 창이 닫혀도
약 90–95초 동안 조회가 없으면 서버가 해당 세션 작업을 취소합니다. 취소는 엔진의 검사 주기에 따라 약간 지연될 수 있습니다.
TTL 만료·서버 종료 시에도 작업을 취소합니다. 서버 대국이 끝난 뒤 방문자별 TT를 계속 보관하지 않아 메모리를 제한합니다.

Render Free는 현재 0.1 CPU / 512MB이며, 15분 동안 인바운드 요청이 없으면 중지될 수 있고
다음 접속 시 기동 대기가 발생합니다. 무료 사용량 한도·재시작·배포·장애로 작업이 중단될 수 있습니다.
세션과 기보는 RAM에 있어 재시작하면 초기화됩니다. 지속 저장이나 무중단 10분 작업 보장은 추가하지 않았습니다.

**PyPy 적용 판단**

v0.9.2의 이전 동일 코드 측정에서 PyPy는 워밍업 후 빠르고 메모리는 더 사용했습니다.
이번 웹/세션 관련 테스트도 PyPy로 확인하지만, **Render Free에서의 실제 부하·메모리·장시간 성능은 미검증**입니다.
따라서 현재 배포 기본값은 CPython입니다. PyPy 서버로 자동 교체하지 않습니다.
향후 별도 실측으로 이득과 안정성을 확인한 뒤 별도 Docker 테스트를 검토할 수 있습니다.

**검증과 재현**

```sh
python tools/prepare_web_runtime.py
python -m unittest discover -q
node test_frontend.js
node test_visuals.js
npm ci
npx playwright install chromium
npm run test:browser
```

시스템 Chrome/Chromium/Edge를 지정하려면 `TAL_BROWSER_EXECUTABLE`을 해당 실행 파일 경로로 설정합니다.
`TAL_PYTHON`은 테스트용 웹 서버를 띄우는 개발자 측 Python 경로이며, 접속자 PC에 필요한 설정이 아닙니다.
브라우저 테스트는 임시 서버·임시 인증 정보·새 프로필을 사용하고 외부 네트워크를 차단합니다.
로컬 분석 중 서버 분석 API도 차단해, 결과가 실제 Pyodide에서 나왔는지 확인합니다.
테스트용 서버가 개발 머신의 Python을 사용하는 것과 브라우저가 Python 설치를 요구하는 것은 구분합니다.
Windows PC방 실기기에서 Python을 제거한 시험은 하지 않았습니다.

실행 결과는 `evidence/render-test/` 및 `RENDER_TEST_VALIDATION.md`에 정리합니다.
브라우저 테스트는 600초 작업을 실제로 시작하고 진행·저장·취소를 확인합니다. 각 브라우저에서
모든 시간 예산을 끝까지 기다리는 10분 완주 성능 시험은 아닙니다.

배포 후에는 실제 주소에서 `/healthz`, 로그인, 새 TEST 표기와 버전, 로컬/서버 MultiPV,
심층 작업 취소, PGN 불러오기, `/play` 엔진 응수를 다시 확인합니다. Live 확인 전에는 배포 완료로 보고하지 않습니다.

공식 근거:
[Blueprint 명세](https://render.com/docs/blueprint-spec),
[Blueprint 생성](https://render.com/docs/infrastructure-as-code),
[Deploy to Render 링크](https://render.com/docs/deploy-to-render),
[무료 서비스 제한](https://render.com/docs/free),
[웹 서비스 포트](https://render.com/docs/web-services).
