"""Recompute v0.9.4 report metrics from raw evidence, never hand-enter scores."""
from collections import defaultdict
import json
from pathlib import Path
import statistics

ROOT=Path('evidence/v094')


def load(name):return json.loads((ROOT/name).read_text())


def main():
    out={}
    tactics=load('ablation-tactics-2s.json')['rows']
    cases={c['id']:c for c in json.loads(Path('evidence/v092/holdout.json').read_text())}
    by=defaultdict(list)
    for r in tactics:by[r['variant']].append(r)
    out['tactics']={k:dict(n=len(rs),correct=sum(r['correct'] for r in rs),
        mean_depth=statistics.mean(r['depth'] for r in rs),
        mean_seconds=statistics.mean(r['elapsed'] for r in rs),
        nps=sum(r['nodes'] for r in rs)/sum(r['elapsed'] for r in rs),
        categories={cat:dict(n=sum(cases[r['id']]['category']==cat for r in rs),
            correct=sum(bool(r['correct']) for r in rs if cases[r['id']]['category']==cat))
            for cat in sorted({c['category'] for c in cases.values()})}) for k,rs in by.items()}
    ref={r['id']:r for r in load('reference-positional.json')['rows']}
    by=defaultdict(list)
    for r in load('ablation-positional-1s.json')['rows']:
        sf=ref[r['id']];sign=1 if sf['fen'].split()[1]=='w' else -1
        forced=sf['forced'][r['move']]
        loss=sign*(sf['root']['score_white']-forced['score_white'])
        by[r['variant']].append(dict(**r,reference_loss_cp=max(0,loss),
            raw_loss_cp=loss,exact=r['move']==sf['root']['pv'][0],
            defense=sf['root']['mate_white'] is None and sign*sf['root']['score_white']<=-100,
            root_mate=sf['root']['mate_white'] is not None,
            forced_mate=forced['mate_white'] is not None,
            same_mate_outcome=(sf['root']['mate_white'] is not None and forced['mate_white'] is not None
                and (sf['root']['mate_white']>0)==(forced['mate_white']>0))))
    out['positional']={k:dict(n=len(rs),exact=sum(r['exact'] for r in rs),
        cp_reference_n=sum(not r['root_mate'] for r in rs),
        within_50cp=sum(not r['root_mate'] and not r['forced_mate'] and r['reference_loss_cp']<=50 for r in rs),
        negative_raw_loss=sum(not r['root_mate'] and not r['forced_mate'] and r['raw_loss_cp']<0 for r in rs),
        mate_reference=sum(r['root_mate'] for r in rs),
        same_mate_outcome=sum(r['same_mate_outcome'] for r in rs),
        defense_n=sum(r['defense'] for r in rs),
        defense_within_50cp=sum(not r['forced_mate'] and r['reference_loss_cp']<=50 for r in rs if r['defense']),
        median_loss_cp=statistics.median(r['reference_loss_cp'] for r in rs if not r['root_mate'] and not r['forced_mate']),
        mean_depth=statistics.mean(r['depth'] for r in rs),
        nps=sum(r['nodes'] for r in rs)/sum(r['elapsed'] for r in rs)) for k,rs in by.items()}
    out['runtime']={}
    signatures=[]
    for runtime in ('python','pypy','native'):
        d=load(f'runtime-{runtime}.json');rs=[r for r in d['runs'] if not r['warmup']]
        signatures.append([(r['id'],r['move'],r['score'],r['nodes'],
            [(i['depth'],i['score'],i['nodes'],i['pv']) for i in r['rows']]) for r in rs])
        out['runtime'][runtime]=dict(nps=sum(r['nodes'] for r in rs)/sum(r['elapsed'] for r in rs),
            seconds=sum(r['elapsed'] for r in rs),version=d['version'],max_rss_kib=d['max_rss_kib'])
    assert signatures[0]==signatures[1]==signatures[2]
    out['runtime_signatures_equal']=True
    for name in ('candidate','final'):
        if (ROOT/f'match-{name}.json').exists():out[f'match_{name}']=load(f'match-{name}.json')['summary']
    if (ROOT/'historical-v094-1mn.json').exists():
        old=load('historical-v093-1mn.json')['rows'];new=load('historical-v094-1mn.json')['rows']
        def signature(rs):return [(r['id'],r['move'],r['score'],r['nodes'],
            [(i['depth'],i['score'],i['nodes'],i['pv']) for i in r['iterations']]) for r in rs]
        assert len(old)==len(new)==4 and signature(old)==signature(new)
        out['historical_1mn_signatures_equal']=True
    (ROOT/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if not k.startswith('match')},indent=2))


if __name__=='__main__':main()
