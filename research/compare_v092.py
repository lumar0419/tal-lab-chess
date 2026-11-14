"""Alternating fresh-process comparisons, identical hardware/settings/TT.

python -m research.compare_v092 --baseline ../baseline-v091 --output evidence/v092/fixed.json
"""
import argparse
import hashlib
import json
import os
import platform
import statistics
import shutil
import subprocess
import sys
from pathlib import Path


def probe(root, task, launcher=None):
    command = [sys.executable, '-m', 'research.probe_search']
    if launcher:
        command = [sys.executable, str(Path(root)/'native_engine.py'), 'research.probe_search']
    if shutil.which('/usr/bin/time'):
        command = ['/usr/bin/time','-f','MAXRSS_KIB=%M',*command]
    p = subprocess.run(command, cwd=root, input=json.dumps(task), text=True,
                       capture_output=True, check=True)
    result = json.loads(p.stdout)
    for line in p.stderr.splitlines():
        if line.startswith('MAXRSS_KIB='):
            result['max_rss_kib']=int(line.split('=')[1])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--depth', type=int, default=5)
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--suite')
    args = parser.parse_args()
    root = Path.cwd()
    source = Path(args.suite) if args.suite else root/'evidence/v091/development.json'
    suite = json.loads(source.read_text())
    if not args.suite:
        suite = [c for c in suite if c['suite'] in ('ecm','iq4')][:4] + [
            c for c in suite if c['suite']=='historical'][:4]
    report = dict(python=platform.python_version(), platform=platform.platform(),
                  affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
                  baseline=str(Path(args.baseline).resolve()), native=args.native,
                  depth=args.depth, seconds=args.seconds, repeats=args.repeats, cases=[])
    report['source_hashes'] = {label:{f:hashlib.sha256((source/f).read_bytes()).hexdigest()
        for f in ('board.py','evaluate.py','search.py')} for label,source in
        [('base',Path(args.baseline)),('new',root)]}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    for case in suite:
        result = dict(id=case['id'], category=case.get('category',case.get('suite')),
                      bm=case.get('bm'), runs={'base':[], 'new':[]})
        for repeat in range(args.repeats):
            for label in (('base','new') if repeat%2==0 else ('new','base')):
                task = dict(fen=case['fen'], depth=args.depth if args.seconds is None else 40,
                            tt=300000, options={'lmr':True})
                if args.seconds:
                    task['seconds'] = args.seconds
                data = probe(args.baseline if label=='base' else str(root), task,
                             launcher=args.native and label=='new')
                result['runs'][label].append(data)
        result['median_seconds'] = {k:statistics.median(r['elapsed'] for r in v)
                                    for k,v in result['runs'].items()}
        result['exact_fixed_tree'] = all(
            [(x['depth'],x['nodes'],x['lines']) for x in b['rows']]==
            [(x['depth'],x['nodes'],x['lines']) for x in n['rows']]
            for b,n in zip(result['runs']['base'],result['runs']['new'])) if not args.seconds else None
        report['cases'].append(result)
        out.write_text(json.dumps(report,indent=2)+'\n')
        print(case['id'],result['median_seconds'],result['exact_fixed_tree'],flush=True)


if __name__=='__main__':
    main()
