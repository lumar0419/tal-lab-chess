"""Reproduce the targeted single-PV follow-up from the release report."""
import argparse
import json
from pathlib import Path

from research.deep_sacrifice import classify, tal_search
from research.measure_search import compare_reference, last
from research.sacrifice_cases import positions, replay_case

CASES = ('kasparov_topalov_1999_ply47', 'tal_larsen_1965_g10_ply31',
         'reshevsky_petrosian_1953_re6')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import chess.engine

    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as reference:
        reference.configure({'Threads': 1, 'Hash': 32})
        report = {'tal_seconds_per_search': 7, 'tal_max_depth': 9, 'tal_multipv': 1,
                  'reference': {'id': reference.id, 'seconds_per_search': 2,
                                'threads': 1, 'hash_mb': 32}, 'cases': []}
        for case in positions():
            if case['id'] not in CASES:
                continue
            board = replay_case(case)
            historical = case['historical_uci']
            blind = tal_search(board, depth=9, seconds=7)
            forced = tal_search(board, depth=9, seconds=7, forced=historical)
            result = classify(board, historical, blind, forced)
            reference_lines = compare_reference(reference, board.fen(), 2, historical)
            report['cases'].append({'case': case, 'blind': blind, 'forced': forced,
                                    'judgment': result, 'reference': reference_lines})
            print(case['id'], last(blind)['depth'], last(forced)['depth'], result['status'])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
