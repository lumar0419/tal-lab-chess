"""Paired full-depth and timed tactical accuracy, with separate independent reference."""
import argparse
import json
import os
from pathlib import Path
import platform

from research.branch_diagnostic import position_after
from research.deep_benchmark import ROOT, run
from research.measure_search import accepted_mates, stockfish_line
from research.sacrifice_cases import positions
from research.tactical_profiles import PROFILES
from search import MATE

FOCUS = ('kasparov_topalov_1999_ply47', 'rotlewi_rubinstein_1907_ply44',
         'lasker_bauer_1889_ply29', 'lasker_bauer_1889_ply33', 'kasparov_topalov_1999_ply49',
         'botvinnik_tal_1960_g6_ply42', 'tal_larsen_1965_g10_ply31', 'reshevsky_petrosian_1953_re6', 'karpov_kasparov_1985_g16_ply32')
CONTROLS = (
    ('queen_offer', '7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1', 'e2e4', 'd5e4'),
    ('rook_offer', '7k/8/8/3p4/8/8/4R3/4K3 w - - 0 1', 'e2e4', 'd5e4'),
    ('black_queen_offer', '4k3/4q3/8/8/3P4/8/8/7K b - - 0 1', 'e7e5', 'd4e5'),
    ('capture_loses_to_mate', '7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1', 'g2f1', 'a1a8'),
)
DRAW_DEFENSES = (
    ('quiet_defense_50_move', '7k/8/8/8/8/8/r7/6K1 w - - 99 50', ('g1h1', 'g1f1')),
)
DRAW_CAPTURES = (
    ('knight_saves_draw', '3q3k/8/2N5/8/8/8/8/6K1 w - - 0 1', 'c6d8'),
    ('bishop_saves_draw', '4r2k/8/8/8/B7/8/8/6K1 w - - 0 1', 'a4e8'),
)


def dataset(suite, chess):
    if suite in ('focus', 'historical'):
        cases = positions()
        return [c for c in cases if suite == 'historical' or c['id'] in FOCUS]
    cases = json.loads((ROOT / 'research/tactics.json').read_text())
    for case in cases:
        case['accepted'] = accepted_mates(case['fen'], case['mate_plies'])
    for name, fen, bad, reply in CONTROLS:
        board = chess.Board(fen)
        assert board.is_valid()
        board.push_uci(bad)
        assert board.is_legal(chess.Move.from_uci(reply))
        if name == 'capture_loses_to_mate':
            assert not board.is_capture(chess.Move.from_uci(reply))
            board.push_uci(reply)
            assert board.is_checkmate()
        cases.append(dict(id=name, fen=fen, forbidden=bad, refutation=reply))
    for name, fen, replies in DRAW_DEFENSES:
        board = chess.Board(fen)
        assert board.can_claim_fifty_moves()
        assert all(not board.is_capture(move) and not board.gives_check(move)
                   for move in board.legal_moves)
        cases.append(dict(id=name, fen=fen, accepted=list(replies), draw=True))
    for name, fen, good in DRAW_CAPTURES:
        board = chess.Board(fen)
        assert board.is_valid()
        board.push_uci(good)
        assert board.is_insufficient_material()
        cases.append(dict(id=name, fen=fen, accepted=[good], draw=True))
    return cases


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--stockfish', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--suite', choices=('focus', 'historical', 'controls'), default='focus')
    p.add_argument('--puzzles', type=Path, help='Use a preselected Lichess puzzle split.')
    p.add_argument('--split', choices=('development', 'holdout'), default='development')
    p.add_argument('--profiles', nargs='+', choices=PROFILES, default=['baseline', 'candidate'])
    p.add_argument('--case', action='append', help='Select one or more IDs or substrings.')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--seconds', nargs='+', type=float)
    mode.add_argument('--depths', nargs='+', type=int)
    p.add_argument('--multipv', nargs='+', choices=(1, 3), type=int, default=[1, 3])
    p.add_argument('--reference-seconds', type=float, default=2)
    p.add_argument('--repeats', type=int, default=1)
    args = p.parse_args()
    import chess
    import chess.engine
    cases = (json.loads(args.puzzles.read_text())[args.split] if args.puzzles
             else dataset(args.suite, chess))
    if args.case:
        cases = [case for case in cases if any(s in case['id'] for s in args.case)]
    if not cases:
        p.error('No cases selected')
    conditions = [(depth, None) for depth in args.depths] if args.depths else [
        (14, seconds) for seconds in (args.seconds or [1, 5])]
    report = {'python': platform.python_version(), 'platform': platform.platform(),
              'affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
              'tt_entries': 60000, 'rows': []}
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as sf:
        sf.configure({'Threads': 1, 'Hash': 32})
        report['reference'] = dict(id=sf.id, threads=1, hash_mib=32, seconds=args.reference_seconds)
        for i, case in enumerate(cases):
            historical = case.get('historical_uci')
            puzzle_move = case.get('puzzle_move')
            b = chess.Board(case['fen'])
            if case.get('history') is not None:
                b = chess.Board()
                for uci in case['history']:
                    b.push_uci(uci)
                assert b.fen(en_passant='fen') == case['fen'] == position_after(case).fen()
                assert b.san(chess.Move.from_uci(historical)) == case['historical_san']
            sf.configure({'Clear Hash': None})
            lines = [stockfish_line(x, b.turn) for x in sf.analyse(
                b, chess.engine.Limit(time=args.reference_seconds), multipv=3)]
            row = dict(case=case, reference_top3=lines, runs=[])
            report['rows'].append(row)
            for j, (depth, seconds) in enumerate(conditions):
                for mpv in args.multipv:
                    for rep in range(args.repeats):
                        labels = args.profiles if (i+j+mpv//2+rep)%2 else args.profiles[::-1]
                        for name in labels:
                            opts = PROFILES[name]
                            result = run(args.baseline if name=='baseline' else ROOT, case, depth=depth,
                                         seconds=seconds, multipv=mpv, options=opts)
                            final = result['rows'][-1] if result['rows'] else dict(depth=0, lines=[])
                            for line in final['lines']:
                                test = b.copy()
                                for uci in line['pv']:
                                    test.push_uci(uci)
                            moves = [x['move'] for x in final['lines']]
                            best = moves[0] if moves else None
                            score = final['lines'][0]['score'] if moves else None
                            correct = None
                            if 'accepted' in case:
                                target = 0 if case.get('draw') else MATE-case['mate_plies']
                                correct = best in case['accepted'] and score == target
                            elif 'forbidden' in case:
                                correct = best is not None and best != case['forbidden']
                            result.update(profile=name, options=opts, multipv=mpv, repeat=rep,
                                          limit_seconds=seconds, depth_cap=depth, completed=final['depth'],
                                          best=best, correct=correct, agrees_with_reference=best==lines[0]['move'],
                                          historical_rank=(moves.index(historical)+1 if historical in moves else None),
                                          puzzle_rank=(moves.index(puzzle_move)+1 if puzzle_move in moves else None))
                            row['runs'].append(result)
                            args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
            print(case['id'], [(r['profile'], r['multipv'], r['completed'],
                                r['puzzle_rank'] if puzzle_move else r['historical_rank'], r['correct'])
                               for r in row['runs']], flush=True)


if __name__ == '__main__':
    main()
