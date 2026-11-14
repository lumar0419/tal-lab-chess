"""Compare default and experimental quiet checks with independent answers."""
import argparse
import json
import os
from pathlib import Path
import platform

from board import Board
from research.deep_benchmark import ROOT, run
from research.measure_search import accepted_mates, compare_reference
from research.sacrifice_cases import positions
from search import MATE

CONTINUATION = {'qsearch_quiet_checks': True, 'check_continuation': True}
PROFILES = {
    'v082': ({}, True),
    'v083': ({}, False),
    'v082_checks': (CONTINUATION, True),
    'v083_checks': (CONTINUATION, False),
    'bridge': (CONTINUATION | {'qsearch_capture_bridge': True}, False),
}
FOCUS = ('kasparov_topalov_1999_ply47', 'rotlewi_rubinstein_1907_ply44',
         'lasker_bauer_1889_ply29', 'lasker_bauer_1889_ply33')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--stockfish', required=True)
    p.add_argument('--suite', choices=('focus', 'heldout', 'historical'), default='focus')
    p.add_argument('--profiles', nargs='+', choices=PROFILES, default=list(PROFILES))
    p.add_argument('--multipv', nargs='+', type=int, choices=(1, 3), default=[1, 3])
    p.add_argument('--seconds', type=float, default=2)
    p.add_argument('--depth', type=int, default=5)
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--reference-seconds', type=float, default=2)
    p.add_argument('--fixed', action='store_true')
    args = p.parse_args()

    import chess.engine
    historical = positions()
    if args.suite == 'focus':
        cases = [case for case in historical if case['id'] in FOCUS]
    elif args.suite == 'historical':
        cases = historical
    else:
        cases = json.loads((ROOT / 'research/tactics.json').read_text())
        for case in cases:
            case['accepted'] = accepted_mates(case['fen'], case['mate_plies'])
        cases.append(dict(id='queen_capture_horizon_trap',
                          fen='7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1'))
    report = dict(cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
                  python=platform.python_version(), platform=platform.platform(),
                  max_depth=args.depth, seconds=None if args.fixed else args.seconds,
                  repeats=args.repeats, rows=[])
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as reference:
        reference.configure({'Threads': 1, 'Hash': 32})
        report['stockfish'] = dict(id=reference.id, threads=1, hash_mib=32, seconds=args.reference_seconds)
        for case in cases:
            historical_move = case.get('historical_uci')
            ref = compare_reference(reference, case['fen'], args.reference_seconds, historical_move)
            if case['id'] == 'queen_capture_horizon_trap':
                # A negative control for missing the defender's immediate mate.
                b = chess.Board(case['fen'])
                b.push_uci('g2f1')
                assert b.is_legal(chess.Move.from_uci('a1a8'))
                b.push_uci('a1a8')
                assert b.is_checkmate()
            row = dict(case=case, reference=ref, runs=[])
            report['rows'].append(row)
            for pv in args.multipv:
                for repeat in range(args.repeats):
                    order = args.profiles if (repeat + len(report['rows']) + pv // 2) % 2 else args.profiles[::-1]
                    for label in order:
                        flags, use_baseline = PROFILES[label]
                        result = run(args.baseline if use_baseline else ROOT, case, depth=args.depth,
                                     seconds=None if args.fixed else args.seconds, multipv=pv, options=flags)
                        last = result['rows'][-1] if result['rows'] else dict(depth=0, lines=[])
                        lines = last['lines']
                        moves = [line['move'] for line in lines]
                        for line in lines:
                            board = Board(case['fen'])
                            for move in line['pv']:
                                board.push_uci(move)
                        rank = moves.index(historical_move) + 1 if historical_move in moves else None
                        correct = (bool(lines) and moves[0] in case['accepted']
                                   and lines[0]['score'] == MATE - case['mate_plies']) if 'accepted' in case else None
                        result.update(profile=label, multipv=pv, repeat=repeat, completed_depth=last['depth'],
                                      historical_rank=rank, mate_correct=correct,
                                      reference_match=bool(moves and moves[0] == ref['candidates'][0]['move']),
                                      avoided_trap=(bool(moves) and moves[0] != 'g2f1'
                                                    if case['id'] == 'queen_capture_horizon_trap' else None))
                        row['runs'].append(result)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(case['id'], [(r['profile'],r['multipv'],r['completed_depth'],r['historical_rank'])
                               for r in row['runs']], flush=True)


if __name__ == '__main__':
    main()
