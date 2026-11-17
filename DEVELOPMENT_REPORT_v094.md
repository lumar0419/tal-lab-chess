# Tal Lab v0.9.4-dev 최종 개발 보고

이번 결과는 **위치 판단·기력 향상 미입증의 개발 Draft**다. 실제 코드, 실험, 테스트 및 원시 자료를 만들었지만 검증 실패한 평가·가지치기 변경은 제품에 적용하지 않았다. 자세한 숫자와 재현 방법은 [VALIDATION_v094.md](VALIDATION_v094.md), [evidence](evidence/v094/README.md)에 있다.

1. **기존 구조**: Python 120칸 mailbox, 증분 hash, tapered classical 평가, 반복 심화/PVS/TT/QS와 선택적 탐색, SEE 루트 희생 연장. CPython/PyPy/Cython/Pyodide와 UCI/웹 구조를 유지했다.

2. **v0.9.3 문제**: 일부 물질 이득 국면에서 상대 활동성과 장기 보상을 크게 과소평가한다. MultiPV와 선택적 탐색의 명목 깊이를 실제 전폭 계산 깊이로 읽을 수 없으며, 평가 오류와 horizon/pruning 효과를 하나로 단정할 수 없다.

3. **실전 두 경기**: 모두 합법, 첫 경기는 미종료, 둘째는 흑 메이트. 60초·전술 프로필·MultiPV 1/2로 주요 선택을 대부분 재현했다. Nxf5/Nxe5/Nxh8은 SF도 우선 선택한 반면 Rxg7/Rxh7 및 ...dxc3/...Ke8은 위치적으로 문제가 있다. 통과폰 전진은 흑의 승리 유지에 도움이 됐다. [국면별 진단](POSITIONAL_DIAGNOSTICS_v094.md).

4. **다른 엔진 비교**: PyCheckmate의 classical/실험 체계, Numbfish의 NumPy/TFLite HalfKP, Pygin의 전체 C 노드 루프, Sunfish의 MTD-bi/PST 및 신경망 residual을 실제 고정 커밋으로 조사했다. [비교표·라이선스](PYTHON_ENGINE_COMPARISON_v094.md).

5. **참고한 방법과 구현**: Texel sigmoid-MSE, validation 선택, 게임 그룹 분리, 오프닝 색 교환, profile/노드 동일성 검사를 독립 구현·활용했다. 외부 코드를 복사하지 않았고 SPRT는 후속 계획으로만 제시했다.

6. **평가 개선 후보**: 안전 mobility, king pressure/shelter, home-minor 전개와 rook file 계수를 연구용으로 구현했다. 검증 오차/전술 정확도/계산 비용이 채택을 지지하지 않아 기본값은 유지한다. 제품에는 정확한 평가 상세 및 착수 전후 설명을 추가했다.

7. **탐색 개선 후보**: quiet futility/LMP 해제를 실험했으나 정확도나 대국 개선이 입증되지 않았다. 정책 변경은 제외하고 history/killer/순서/margin/LMR 재탐색 trace만 보강했다. 기존 PV/root 보호와 PVS/TT/null/SEE 동작을 유지했다.

8. **Ablation**: A~G 및 보수적 LMR을 각각 측정했다. E는 validation 실패로 추가 계수 0이며 G는 E+F의 연구 후보이지 검증된 통합본이 아니다. 고정 100,000노드와 시간 제한 결과를 구분했다.

9. **전술 정확도**: 이전 회귀 32개·2초에서 A 28, B 25, C 27, D 28, E 28, F/G 28, 보수적 LMR 27. 기존에 공개된 표본이므로 새 독립 기력 검증이라 부르지 않는다.

10. **위치·수비 정확도**: 학습에서 분리한 새로운 48 quiet 국면·1초에서 A는 SF 1순위 24/48, cp 국면 50cp 이내 30/41. B/C/D는 각각 28/31/30개로 일관된 개선이 없다. 불리한 cp 국면의 50cp 이내는 모두 7/12였다. 짧은 SF 참조의 불확실성을 포함한다.

11. **실제 대국**: 후보 F와 최종 코드 각각 v0.9.3 상대 20판·5초+0.05초·색 교환. 둘 다 4승 11무 5패. 최종의 상대 Elo 추정 -17.4, 쌍 기준 근사 95% 범위 -110.4~+73.1로 결론 불가. 최종 검색 정책은 같으므로 시간 변동 결과를 기력 변화로 해석하지 않는다. 시간패/불법수/엔진 오류 0.

12. **Stockfish 독립 비교**: 공식 Stockfish 19, 1 thread/32MiB, 강도 제한 없이 3초 root+forced와 100,000노드를 별도 측정했다. PV/깊이/시간/노드/NPS/점수는 JSON에 보존했다. SF와 Tal의 같은 노드 수가 동일한 계산 비용은 아니다.

13. **Brilliant Sacrifice**: PyPy 60초에서 Lasker Bxh7+(처음 약 5.69초), Bxg7(0.29초), Rubinstein Rxc3(17.18초)를 찾았다. Kasparov Rxd4는 미해결. 100만 노드에서 v0.9.3과 최종 코드의 수·점수·PV·노드가 동일했다.

14. **성능·환경**: 같은 고정 깊이 4 표본에서 CPython 약 49.8k, PyPy 136.0k, Cython 93.4k NPS. 알고리즘/결과 동일성을 확인했으며 이 짧은 측정에서 장기 속도나 Elo를 추정하지 않는다. [성능 문서](PERFORMANCE_v094.md).

15. **웹 호환성**: 새 평가 상세 HTTP/UI, 착수 전후 비교, 현재 옵션의 격리된 계산을 추가했다. 정적/탐색 점수는 구분한다. 실제 Pyodide 0.27.7과 CPython의 MultiPV·심층 메이트 증명·평가 JSON 일치, 로컬 HTTP/cloud 세션 테스트 및 JS 계약 검사 통과. Render 배포와 실제 Chrome 전체 UI 검사는 하지 않았다.

16. **미해결**: 일반 기력 향상, Kasparov Rxd4, 평가/탐색 원인의 완전한 분리, 대규모 독립 긴 시간제 대국, SPRT, 실제 브라우저 화면 전체 검증, Windows native, NNUE 구현은 완료하지 않았다. 자동 튜닝은 재현 가능하게 실행했지만 최종 채택할 새 가중치를 얻지 못했다.

17. **v0.9.5 권장**: 더 다양한 게임 그룹 데이터와 teacher 라벨, 여러 seed, 소수 feature의 비용 최적화, 사전 등록한 paired 대국 검증을 우선한다. NNUE는 작은 residual 모델부터 classical과 분리해 비교하고 증분 업데이트/특수수/라이선스를 먼저 검증한다. [NNUE 로드맵](NNUE_ROADMAP.md).

18. **GitHub 반영**: 기준 `af201fb488e4ef74f35f519fb61f4081df9b184c`, 브랜치 [`development/positional-accuracy-v094`](https://github.com/lumar0419/tal-lab-chess/tree/development/positional-accuracy-v094). base는 `claude/tactical-accuracy-v093`인 Draft PR으로 검토한다. 최종 커밋 SHA와 PR URL은 작업 완료 메시지/PR에서 확인한다. main·기존 브랜치·PR #1·Render 사이트는 변경하지 않는다.

회귀: CPython/PyPy/Cython unittest 각각 276개, 빠른 엔진 159개, UCI 71개, perft/hash, 독립 규칙 oracle, frontend 및 실제 Pyodide parity를 통과했다. 새 평가 설명과 연구 데이터 준비/튜닝의 재현성을 검사했다. 로컬 통과와 GitHub Actions 원격 상태는 구분한다.
