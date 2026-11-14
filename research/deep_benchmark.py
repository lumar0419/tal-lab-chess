"""Sequential paired timing; pin the process externally if available."""
import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

from research.measure_search import compare_reference
from research.sacrifice_cases import positions
from board import START_FEN

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'baseline': {},
    'candidate': {},
    'quiet_checks': {'qsearch_quiet_checks': True},
    'check_continuation': {'qsearch_quiet_checks': True, 'check_continuation': True},
}


def run(source, case, *, depth=14, seconds=None, multipv=1, roots=None,
        after=None, options=None, tt=60000, prefix=(), evaluation=None):
    # Archived histories begin at the standard position; diagram-only cases use FEN.
    history = case.get('history')
    fen = case['fen'] if history is None else START_FEN
    params = dict(fen=fen, history=history or [], expected_fen=case['fen'], depth=depth,
                  seconds=seconds, multipv=multipv, roots=roots, after=after,
                  options=options or {}, tt=tt, prefix=list(prefix), evaluation=evaluation or {})
    proc = subprocess.run([sys.executable, str(ROOT/'research/probe_search.py')],
                          cwd=source, env=dict(os.environ, PYTHONPATH=str(source.resolve())),
                          input=json.dumps(params), capture_output=True, text=True,
                          check=True, timeout=(seconds or 120)+12)
    return json.loads(proc.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--cases', nargs='+', default=['kasparov_topalov_1999_ply47'])
    parser.add_argument('--seconds', nargs='+', type=float, default=[1,5,10,30,60])
    parser.add_argument('--multipv', nargs='+', type=int, default=[1,3])
    parser.add_argument('--profiles', nargs='+', choices=PROFILES, default=['baseline', 'candidate'])
    parser.add_argument('--reference-seconds', type=float, default=5)
    args = parser.parse_args()
    import chess.engine
    cases = {case['id']: case for case in positions()}
    report = {'platform': platform.platform(), 'python': sys.version,
              'affinity': sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
              'max_depth': 14, 'tt_entries': 60000, 'rows': [], 'references': {}}
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as ref:
        ref.configure({'Threads':1,'Hash':32})
        report['reference_settings'] = dict(id=ref.id, threads=1, hash_mb=32,
                                            seconds_per_search=args.reference_seconds)
        for name in args.cases:
            case = cases[name]
            historical = case['historical_uci']
            reference = compare_reference(ref, case['fen'], args.reference_seconds, historical)
            report['references'][name] = reference
            top = reference['candidates'][0]['move']
            for budget in args.seconds:
                for pv in args.multipv:
                    profiles = list(args.profiles)
                    if len(report['rows']) // len(profiles) % 2:
                        profiles.reverse()
                    for label in profiles:
                        source = args.baseline if label == 'baseline' else ROOT
                        options = PROFILES[label]
                        result = run(source, case, seconds=budget, multipv=pv, options=options)
                        last = result['rows'][-1] if result['rows'] else dict(depth=0, lines=[])
                        result.update(case=name, version=label, options=options,
                                      time_limit=budget, multipv=pv,
                                      completed_depth=last['depth'],
                                      historical_rank=next((i for i,l in enumerate(last['lines'],1)
                                                            if l['move']==historical),None),
                                      reference_top1=bool(last['lines'] and last['lines'][0]['move']==top))
                        report['rows'].append(result)
                        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                        print(name,label,budget,pv,last['depth'],
                              last['lines'][0]['move'] if last['lines'] else None,flush=True)


if __name__ == '__main__':
    main()
