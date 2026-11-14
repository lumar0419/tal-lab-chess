# v0.9.3 측정 자료

보고서는 [VALIDATION_v093.md](../../VALIDATION_v093.md)입니다. 측정 환경은 Intel Xeon 2.30GHz 4코어, CPython 3.13.18입니다.

- `index.json`: 실행별 설정, 문제 수, 정답 수, 평균 완료 깊이.
- `tuning-*.json`: 조정용 표본(`evidence/v088/suite.json`) 결과. `8s`는 짝수 번째 287문제입니다.
- `rejected-*.json`: 채택하지 않은 실험 스위치의 결과. 이 파일들의 `options`에 있는 `one_reply_extension`, `sel_threat`, `singular_extension`, `sac_follow_extension`, `sel_malus`는 최종 코드에 없습니다.
- `verify-suite.json`, `verify-*.json`: 독립 표본과 그 결과. id 앞의 `h92:`·`h91:`·`dev:`·`hist:`는 출처입니다.
- `ladder-*.json`: 역사 국면 300초 반복 심화. 완료한 깊이마다 점수(백 기준), PV, 노드, 시간.
- `false-offers.json`: 불건전한 희생 대조군의 4초 심층 분석 요약.
- `deep-tactical-lasker_bxh7-60.json`: 전술 프로필 60초 심층 분석 보고서.

결과 행은 `id, expected, move, ok, score, depth, nodes, time`입니다. 반복별 PV는 용량 때문에 뺐습니다.

## 재현

```bash
python -m research.suite_runner run --suite evidence/v088/suite.json --output base.json --seconds 2 --options '{"lmr": true}'
python -m research.suite_runner run --suite evidence/v088/suite.json --output tactical.json --seconds 2 --profile tactical
python -m research.suite_runner compare --suite evidence/v088/suite.json base.json tactical.json
python -m research.suite_runner run --suite evidence/v093/verify-suite.json --output verify.json --seconds 10 --profile tactical
python -m research.ladder_v093 --case lasker_bauer_1889_ply29 --profile tactical --seconds 300 --output bxh7.json
python -m deep_analysis --fen "r4rk1/1b2bppp/ppq1p3/2pp3n/5P2/1P1BP3/PBPPQ1PP/R4RK1 w - - 0 15" --seconds 60 --output deep.json
```

원래 측정은 `--shard i --shards 4`로 네 조각을 코어 4개에 고정해 동시에 돌렸습니다. 시간 제한 실험이므로 다시 돌리면 몇 문제씩 달라집니다. `--nodes N`을 쓰면 시간 대신 고정 노드 수로 재현 가능한 비교를 할 수 있습니다.
