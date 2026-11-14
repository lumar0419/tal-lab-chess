"""Summarize saved observations; missing measurements are explicitly absent."""
from collections import defaultdict
import json
from pathlib import Path
import statistics

ROOT=Path('evidence/v092')


def read(name):
    path=ROOT/(name+'.json')
    return json.loads(path.read_text()) if path.exists() else None


def main():
    summary={}
    for name in ('fixed-python','fixed-native'):
        data=read(name)
        if not data:continue
        sums={k:sum(c['median_seconds'][k] for c in data['cases']) for k in ('base','new')}
        summary[name]=dict(cases=len(data['cases']),seconds=sums,
            speedup=sums['base']/sums['new'],same_tree=all(c['exact_fixed_tree'] for c in data['cases']))
    for name in ('runtime-cpython','runtime-pypy','runtime-cython'):
        data=read(name)
        if not data:continue
        groups=defaultdict(list)
        for r in data['runs']:
            if not r['warmup']:groups[r['id']].append(r)
        summary[name]=dict(max_rss_kib=data.get('max_rss_kib'),cases={k:dict(
            times=[r['elapsed'] for r in v],seconds=statistics.median(r['elapsed'] for r in v),
            nps=statistics.median(r['nps'] for r in v)) for k,v in groups.items()})
    ref=read('reference-holdout')
    reference={r['id']:r for r in ref['rows']} if ref else {}
    for name in ('holdout-v091','holdout-python','holdout-native','holdout-pypy',
                 'historical-v091','historical-pypy'):
        data=read(name)
        if not data:continue
        rows=data['rows'];groups=defaultdict(list)
        for r in rows:groups[r['category']].append(r)
        repeat_ids=sorted({r['repeat'] for r in rows})
        summary[name]=dict(n=len(rows),per_repeat={i:dict(correct=sum(r['correct'] for r in rows if r['repeat']==i),
            n=sum(r['repeat']==i for r in rows)) for i in repeat_ids},
            depth=statistics.mean(r['completed_depth'] for r in rows),
            nps=statistics.mean(r['nodes']/r['elapsed'] for r in rows),
            categories={k:dict(correct=sum(r['correct'] for r in v),n=len(v),
                depth=statistics.mean(r['completed_depth'] for r in v)) for k,v in groups.items()})
        if name.startswith('holdout'):
            eligible=[r for r in rows if r['id'] in reference and r.get('defense') and reference[r['id']]['defense']]
            summary[name]['sf_root_agreement']=sum(r['move']==reference[r['id']]['root'][0]['pv'][0] for r in rows)
            summary[name]['sf_defense_agreement']=dict(correct=sum(
                r['defense']['move']==reference[r['id']]['defense'][0]['pv'][0] for r in eligible),n=len(eligible))
    for name in ('ladder-v091','ladder-pypy','ladder-python-60','ladder-native-60'):
        data=read(name)
        if not data:continue
        summary[name]=dict(checkpoints=data['checkpoints'],elapsed=data.get('elapsed'),nodes=data.get('nodes'))
    for name in ('branches-v091','branches-pypy'):
        data=read(name)
        if not data:continue
        summary[name]=dict(rows=[dict(case=r['case'],prefix=r['prefix'],last=r['iterations'][-1]) for r in data['rows']],
            false_offers=[dict(id=r['case']['id'],chose_forbidden=r['chose_forbidden'],
                delta=r['candidate']['comparison'],reply=r['candidate']['defenses'][-1]['pv'][0]
                    if r['candidate']['defenses'] else None) for r in data.get('false_offers',[])])
    match=read('match')
    if match:summary['match']=match.get('summary')
    checks=read('checks')
    if checks:summary['checks']=checks
    ROOT.joinpath('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
