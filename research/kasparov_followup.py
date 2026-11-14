"""Compare the next unresolved choices in the Kasparov–Topalov branch."""
import argparse
import json
from pathlib import Path

from research.branch_diagnostic import DEFAULT_CASE, position_after, trace
from research.deep_benchmark import ROOT, run
from research.measure_search import stockfish_line
from research.sacrifice_cases import positions
from research.tactical_profiles import PROFILES

ACCEPTED = ('d1d4', 'c5d4', 'e1e7', 'a7b6', 'f4d4', 'b6a5')
BRANCHES = (
    ('before_b4', ACCEPTED, ('b2b4', 'd4c3')),
    ('before_ra7', ACCEPTED + ('b2b4', 'a5a4'), ('e7a7', 'd4c3')),
    ('after_ra7', ACCEPTED + ('b2b4', 'a5a4', 'e7a7'), ('a8b7', 'a8d5')),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--reference-seconds', type=float, default=5)
    parser.add_argument('--branch', choices=[branch[0] for branch in BRANCHES])
    parser.add_argument('--profiles', nargs='+', choices=PROFILES, default=['baseline', 'bounded', 'null', 'combined'])
    args = parser.parse_args()
    import chess
    import chess.engine
    case = next(row for row in positions() if row['id'] == DEFAULT_CASE)
    report = dict(case=case, seconds=args.seconds, reference_seconds=args.reference_seconds, branches=[])
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as stockfish:
        stockfish.configure({'Threads': 1, 'Hash': 32})
        report['reference'] = dict(id=stockfish.id, threads=1, hash_mib=32)
        for index, (name, prefix, candidates) in enumerate(BRANCHES):
            if args.branch and name != args.branch:
                continue
            board = chess.Board()
            for uci in [*case['history'], *prefix]:
                board.push_uci(uci)
            fen = board.fen(en_passant='fen')
            assert fen == position_after(case, prefix).fen()
            branch = dict(name=name, prefix=prefix, fen=fen, searches=[])
            report['branches'].append(branch)
            for roots in (None, *((move,) for move in candidates)):
                multipv = 3 if roots is None else 1
                stockfish.configure({'Clear Hash': None})
                reference = [stockfish_line(line, board.turn) for line in stockfish.analyse(
                    board, chess.engine.Limit(time=args.reference_seconds), multipv=multipv,
                    root_moves=[chess.Move.from_uci(move) for move in roots] if roots else None)]
                search = dict(roots=roots, multipv=multipv, reference=reference, runs={})
                branch['searches'].append(search)
                profiles = args.profiles if (index + (multipv == 1)) % 2 else args.profiles[::-1]
                for profile in profiles:
                    record = run(args.baseline if profile == 'baseline' else ROOT, case,
                                 seconds=args.seconds, multipv=multipv, roots=roots,
                                 options=PROFILES[profile], prefix=prefix)
                    for line in record['rows'][-1]['lines'] if record['rows'] else []:
                        line['trace'] = trace(case, line['pv'], prefix)
                    search['runs'][profile] = record
                    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
                print(name, roots, [line['move'] for line in reference], flush=True)


if __name__ == '__main__':
    main()
