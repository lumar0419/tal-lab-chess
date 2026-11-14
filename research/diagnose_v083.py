"""Match depths on the four diagnostic FENs and separate accept/decline."""
import argparse
import json
from pathlib import Path
from research.benchmark_v083 import FOCUS, PROFILES
from research.deep_benchmark import ROOT, run
from research.diagnose_kasparov import explain
from research.measure_search import stockfish_line
from research.sacrifice_cases import positions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--stockfish', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=float, default=6)
    p.add_argument('--reference-seconds', type=float, default=8)
    args = p.parse_args()

    import chess
    import chess.engine
    report = {'tal_seconds': args.seconds, 'reference_seconds': args.reference_seconds,
              'depth_cap': 8, 'positions': []}
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as ref:
        ref.configure({'Threads': 1, 'Hash': 32})
        report['reference'] = dict(id=ref.id, threads=1, hash_mib=32)
        for case in positions():
            if case['id'] not in FOCUS:
                continue
            move = case['historical_uci']
            probes = {'historical': (None, [move]), 'defender': (move, None)}
            if case['id'].startswith('kasparov'):
                probes |= {'accept': (move, ['c5d4']), 'decline': (move, ['a7b6'])}
            entry = {'case': case, 'probes': {}}
            report['positions'].append(entry)
            root = chess.Board()
            for uci in case['history']:
                root.push_uci(uci)
            for name, (after, roots) in probes.items():
                board = root.copy()
                if after:
                    board.push_uci(after)
                ref.configure({'Clear Hash': None})
                data = ref.analyse(board, chess.engine.Limit(time=args.reference_seconds),
                                   multipv=3 if roots is None else 1,
                                   root_moves=[chess.Move.from_uci(m) for m in roots] if roots else None)
                tested = {'reference_attacker_pov': [stockfish_line(line, root.turn) for line in data],
                          'tal': {}}
                entry['probes'][name] = tested
                for label in ('v082', 'v083_checks', 'bridge'):
                    flags, baseline = PROFILES[label]
                    result = run(args.baseline if baseline else ROOT, case, after=after, roots=roots,
                                 depth=8, seconds=args.seconds, multipv=3 if roots is None else 1, options=flags)
                    result['leaf_evaluation'] = explain(case, after, result['rows'])
                    tested['tal'][label] = result
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
                print(case['id'], name, [(label, r['rows'][-1]['depth'], r['rows'][-1]['lines'][0]['score'])
                                         for label, r in tested['tal'].items()], flush=True)


if __name__ == '__main__':
    main()
