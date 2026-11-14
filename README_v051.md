# Tal Lab v0.5.1 — 피시방에서도 접속하는 체스 엔진

기존 체스 엔진 **v0.4.11**을 변경하지 않고, **v0.5.0 로컬 웹사이트에 클라우드 배포 지원을 추가**했습니다.

- **로컬 실행:** Windows에서 `start_web.bat` 더블클릭 → `http://127.0.0.1:8000` (내 컴퓨터에서만)
- **인터넷 접속:** GitHub와 Render에 한 번 배포 → 발급받은 `https://...onrender.com` 주소를 피시방 브라우저에서 사용
- **구성:** Python 표준 라이브러리만 사용. 서버는 우리의 `search.py`와 `evaluate.py`로 직접 체스 수를 계산하며 Stockfish로 대체하지 않습니다.
- **접근 보호:** 클라우드 버전은 비밀번호가 없으면 시작하지 않습니다. 브라우저별로 대국 상태가 분리됩니다.

## 처음 한 번만: GitHub + Render로 배포하기

**컴퓨터에 Git 명령어, Docker, 웹 프레임워크를 설치할 필요는 없습니다.** GitHub와 Render 계정이 필요합니다. ZIP 파일 자체를 업로드해서 실행하는 게 아니라, **압축을 푼 소스 파일**을 GitHub 저장소에 올려야 합니다.

### 1) GitHub에 업로드

1. GitHub(https://github.com)에 로그인하고, **New repository**로 예를 들어 `tal-lab-chess`라는 저장소를 만듭니다. **Private**을 선택해도 됩니다.
2. 다운로드한 `tal_lab_web_hosting_v051.zip`을 완전히 압축 해제합니다.
3. GitHub 저장소에서 **Add file → Upload files**를 선택합니다.
4. 압축 해제한 **`tal_lab_web` 폴더 안의 모든 파일과 `web` 하위 폴더**를 한 번에 끌어다 놓습니다. `tal_lab_web` 폴더 자체가 아니라 **안에 있는 내용**이 저장소의 최상위에 들어가야 합니다.
5. **Commit changes**를 누르고, 저장소 최상위에 `render.yaml`, `cloud_server.py`, `web_server.py`, `board.py`, `search.py`, `evaluate.py`와 `web/` 폴더가 보이는지 확인합니다.

**중요:** `render.yaml`을 저장소 최상위에 놓지 않으면 Render가 배포 설정을 찾지 못합니다. ZIP 파일을 그대로 업로드하지 마세요. 비밀번호를 코드 또는 `render.yaml` 파일에 직접 적지 마세요.

### 2) Render에 연결

1. Render(https://dashboard.render.com)에 로그인합니다.
2. **+ New → Blueprint**를 선택합니다.
3. GitHub 계정을 연결하고 방금 만든 `tal-lab-chess` 저장소를 선택합니다.
4. **Blueprint Path**가 `render.yaml`인지 확인합니다.
5. 배포 과정에서 `TAL_SITE_PASSWORD`를 입력하라는 메시지가 나오면 **다른 서비스에서 사용하지 않는, 12자 이상의 강력한 비밀번호**를 입력합니다. 권장 길이는 20자 이상입니다. 사용자명 `TAL_SITE_USER`는 기본 `player`입니다.
6. **Deploy Blueprint**를 누릅니다. 웹 서비스의 배포 상태가 정상(`Live`)이 되면 서비스에 표시된 `https://...onrender.com` 주소를 복사합니다.

Render에서 자동으로 `RENDER_EXTERNAL_HOSTNAME`과 `PORT`가 제공되며, 배포 시 클라우드 서버는 이를 사용하여 접속을 받습니다. Render가 제공하는 HTTPS 주소로 접속합니다. `http://127.0.0.1:8000`을 사용하지 않습니다.

### 3) 피시방에서 접속

1. Chrome/Edge에서 **시크릿 또는 InPrivate 창**을 엽니다.
2. 자신에게 발급된 **Render HTTPS 주소**를 입력합니다.
3. 로그인 창이 뜨면 **사용자명 `player`와 배포할 때 지정한 전용 비밀번호**를 입력합니다.
4. 체스판에서 바로 플레이합니다. **피시방 컴퓨터에 Python·ZIP 파일·프로그램을 설치할 필요가 없습니다.**
5. 대국 종료 전 필요한 기보는 **PGN 저장**을 누릅니다. 피시방 이용 후 비공개 창을 **모두 닫습니다**. 공용 컴퓨터는 신뢰할 수 없으므로 중요한 계정 비밀번호를 이 사이트의 비밀번호로 재사용하지 마세요.

## 무료 호스팅의 제한

- Render Free 서비스는 **15분 동안 요청이 없으면 일시 정지**할 수 있습니다. 다시 접속하면 재가동에 1분가량 걸릴 수 있습니다.
- 현재 대국과 브라우저별 세션은 **서버 메모리만** 사용합니다. 무료 서버가 재시작·재배포·일시 정지 후 다시 시작되면 진행 중인 대국이 사라질 수 있습니다. 중요한 기보는 **PGN 저장**을 사용합니다.
- 계정 시스템이나 DB 저장 기능은 없습니다. 다중 사용자 대국은 16개까지 제한되고, 서로 다른 브라우저 세션은 독립적으로 플레이합니다. 평가 옵션의 모듈 전역 플래그 충돌을 막기 위해 여러 게임의 엔진 탐색은 직렬화됩니다.
- 자기 컴퓨터가 켜져 있을 필요는 없지만, 무료 호스팅의 속도 및 대기시간은 로컬 실행과 다를 수 있습니다.
- 이 구성은 **비밀번호로 보호된 소규모 개인 테스트용**입니다. 불특정 다수를 위한 공개 서비스로 운영하려면 인증, 영구 저장소, 공격 방어, 모니터링을 추가 검토해야 합니다.

## 로컬 실행과 테스트

로컬 웹사이트:

```bash
python web_server.py
```

클라우드 서버를 **로컬에서 시험할 때만** (실제 배포에서는 `TAL_INSECURE_LOCAL_TEST`를 절대 사용하지 마세요):

```bash
# Linux/macOS의 예
TAL_PUBLIC_HOST=127.0.0.1 TAL_SITE_PASSWORD=your-local-test-password TAL_INSECURE_LOCAL_TEST=1 PORT=8002 python cloud_server.py
```

자동 테스트:

```bash
python -m unittest -v test_cloud.py test_web.py
python test_engine.py --quick
```

배포 설정은 `render.yaml`, HTTPS 인증·브라우저별 세션은 `cloud_server.py`, 원래의 로컬 서버는 `web_server.py`입니다. 서버 또는 계정의 실제 인터넷 배포는 **이 파일을 다운로드했다고 자동으로 완료되는 것은 아닙니다.**
