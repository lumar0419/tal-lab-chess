"""전술 모음을 한 설정으로 풀어 JSON 저장.
사용: run_suite.py <엔진폴더> <suite.json> <out.json> <초> <옵션 JSON> [필터: suite=wac,ecm | ids=파일] [--depth N]"""
import sys, json, time
eng, suite, out, seconds, opts = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), json.loads(sys.argv[5])
flt = sys.argv[6] if len(sys.argv) > 6 and not sys.argv[6].startswith('--') else ''
depth = int(sys.argv[sys.argv.index('--depth') + 1]) if '--depth' in sys.argv else None
sys.path.insert(0, eng)
from board import Board
from search import Searcher
import evaluate
cases = json.load(open(suite))
if flt.startswith('suite='):
    keep = set(flt[6:].split(',')); cases = [c for c in cases if c['suite'] in keep]
eval_opts = {k: opts.pop(k) for k in list(opts) if k.isupper()}
for k, v in eval_opts.items(): setattr(evaluate, k, v)
rows = []
t_all = time.time()
for c in cases:
    s = Searcher()
    for k, v in opts.items():
        if not hasattr(s, k): raise SystemExit(f'unknown option {k}')
        setattr(s, k, v)
    last = {}
    def on_info(info, last=last):
        last['depth'] = info.depth; last['score'] = info.score; last['t'] = info.seconds
        mv = info.pv[0].uci() if info.pv else None
        if mv != last.get('mv'):
            last['mv'] = mv; last['since'] = info.seconds; last['since_depth'] = info.depth
    t = time.perf_counter()
    kw = dict(max_depth=depth) if depth else dict(time_limit=seconds)
    mv, sc = s.search(Board(c['fen']), on_info=on_info, **kw)
    el = time.perf_counter() - t
    u = mv.uci() if mv else None
    rows.append({'id': c['id'], 'move': u, 'ok': u in c['bm'], 'score': sc, 'depth': last.get('depth', 0),
                 'nodes': s.nodes, 'time': round(el, 3),
                 'found_at': round(last.get('since', el), 3) if u in c['bm'] and last.get('mv') == u else None,
                 'found_depth': last.get('since_depth') if u in c['bm'] and last.get('mv') == u else None})
json.dump({'engine': eng, 'seconds': seconds, 'depth': depth, 'options': {**opts, **eval_opts}, 'rows': rows}, open(out, 'w'))
n = len(rows); ok = sum(r['ok'] for r in rows)
sac = {c['id'] for c in cases if c['sacrifice']}
print(f"{out.split('/')[-1]}: {ok}/{n} 정답, 희생 {sum(r['ok'] for r in rows if r['id'] in sac)}/{len(sac)}, "
      f"평균 깊이 {sum(r['depth'] for r in rows)/max(n,1):.2f}, 노드 {sum(r['nodes'] for r in rows):,}, {time.time()-t_all:.0f}s")
