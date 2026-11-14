"""Fixed snapshot sample with stable, large Stockfish preference as a proxy.

This intentionally reports a reference agreement metric, separate from
the independent exhaustive mate oracle and from historical move matching.
"""
import argparse
import json
from pathlib import Path

from measure_search import ROOT, compare_reference, last, run_search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import chess.engine
    pool = [line for line in (ROOT/'v044_positions.txt').read_text().splitlines()
            if line and not line.startswith('#')]
    indexes = range(0, min(len(pool), 60), 3)
    report = {'selection': 'indices 0,3,...,57 from archived v044_positions.txt; two reference searches',
              'reference_seconds': [.25, .75], 'reference_multipv': 3,
              'minimum_gap_cp': 75, 'tal_seconds': .7, 'tal_multipv': 1,
              'tal_max_depth': 9, 'repeats': 2, 'positions': []}
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as reference:
        reference.configure({'Threads': 1, 'Hash': 32})
        report['reference'] = {'id': reference.id, 'threads': 1, 'hash_mb': 32}
        for index in indexes:
            fen = pool[index]
            short = compare_reference(reference, fen, .25)['candidates']
            long = compare_reference(reference, fen, .75)['candidates']
            match = short[0]['move'] == long[0]['move']
            finite = all(line['cp'] is not None for line in short[:2]+long[:2])
            eligible = match and finite and all(
                group[0]['cp'] - group[1]['cp'] >= 75 for group in (short, long))
            row = {'index': index, 'fen': fen, 'reference_short': short,
                   'reference_long': long, 'eligible': eligible}
            if eligible:
                runs = {'baseline': [], 'candidate': []}
                pairs = [('baseline', args.baseline), ('candidate', ROOT)]
                for order in (pairs, pairs[::-1]):
                    for name, source in order:
                        result = run_search(source, fen, 9, 1, .7)
                        result['reference_match'] = bool(last(result)['lines'] and
                            last(result)['lines'][0]['move'] == long[0]['move'])
                        runs[name].append(result)
                row['runs'] = runs
                print(index, long[0]['move'],
                      {key: sum(run['reference_match'] for run in group)
                       for key, group in runs.items()}, flush=True)
            report['positions'].append(row)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')


if __name__ == '__main__':
    main()
