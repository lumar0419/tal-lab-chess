"""Compare two engines on the same branch, then re-root and force both choices."""
import argparse
import json
from pathlib import Path

from notation import san_for_move
from research.deep_benchmark import run
from research.measure_search import stockfish_line
from research.sacrifice_cases import positions, replay_case
from sacrifice import balance
import evaluate

DEFAULT_CASE = 'kasparov_topalov_1999_ply47'
KASPAROV_REPLIES = ('c5d4', 'a7b6', 'h8e8', 'a8d5')
CHECKS = {'qsearch_quiet_checks': True, 'check_continuation': True}
ABLATIONS = {
    'baseline': ({}, {}, 60000),
    'quiet_check': ({'qsearch_quiet_checks': True}, {}, 60000),
    'continuation': (CHECKS, {}, 60000),
    'capture_bridge': (CHECKS | {'qsearch_capture_bridge': True}, {}, 60000),
    'lmr': ({'lmr': True}, {}, 60000),
    'alpha_beta': ({'pvs': False}, {}, 60000),
    'no_tt': ({}, {}, 0),
    'ordering': ({'tactical_ordering': True}, {}, 60000),
    'attack_activity': ({}, {'ATTACK_ACTIVITY': True}, 60000),
    'initiative': ({}, {'INITIATIVE': True}, 60000),
    'king_safety': ({}, {'KING_SAFETY': True}, 60000),
}


def position_after(case, moves=()):
    board = replay_case(case)
    for uci in moves:
        board.push_uci(uci)
    return board


def trace(case, moves, prefix=()):
    board = position_after(case, prefix)
    attacker = position_after(case).side
    material = balance(board, attacker)
    rows = []
    for uci in moves:
        move = board.parse_uci(uci)
        if move is None:
            raise ValueError(f'Illegal PV move {uci} in {board.fen()}')
        san = san_for_move(board, move)
        capture = board.board[move.to] != '.' or (move.to == board.ep and board.board[move.frm] in 'Pp')
        board.make_move(move)
        terms, phase, dead = evaluate.eval_terms(board)
        rows.append(dict(uci=uci, san=san, fen=board.fen(), gives_check=board.in_check(),
                         capture=capture, promotion=bool(move.promo), phase=phase, dead=dead,
                         white_terms_mg_eg=terms, attacker_material_change=balance(board, attacker)-material,
                         attacker_static_cp=evaluate.evaluate_white(board)*(1 if attacker == 0 else -1)))
    return rows


def first_difference(first, second):
    for idx, (a, b) in enumerate(zip(first, second)):
        if a != b:
            return idx, a, b
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=8)
    parser.add_argument('--reference-seconds', type=float, default=8)
    parser.add_argument('--cases', nargs='+', default=[DEFAULT_CASE])
    args = parser.parse_args()
    import chess
    import chess.engine

    records = {row['id']: row for row in positions()}
    report = dict(tal_time_cap=args.seconds, reference_time_cap=args.reference_seconds, cases=[])
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        engine.configure({'Threads': 1, 'Hash': 32})
        report['reference'] = dict(id=engine.id, threads=1, hash_mib=32)

        def reference(case, prefix, multipv, roots=None):
            board = chess.Board()
            for uci in case['history'] + list(prefix):
                board.push_uci(uci)
            assert board.fen(en_passant='fen') == position_after(case, prefix).fen()
            engine.configure({'Clear Hash': None})
            info = engine.analyse(board, chess.engine.Limit(time=args.reference_seconds), multipv=multipv,
                                  root_moves=[chess.Move.from_uci(m) for m in roots] if roots else None)
            return [stockfish_line(line, chess.Board(case['fen']).turn) for line in info]

        def save():
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')

        for case_id in args.cases:
            case = records[case_id]
            history_move = case['historical_uci']
            item = dict(case=case, forced_sacrifice=run(args.source, case, roots=[history_move], depth=8,
                                                      seconds=args.seconds), branches=[])
            report['cases'].append(item)
            save()
            item['ref_defenses'] = reference(case, [history_move], 3)
            item['tal_defenses'] = run(args.source, case, prefix=[history_move], depth=8,
                                       seconds=args.seconds, multipv=3)
            replies = KASPAROV_REPLIES if case_id == DEFAULT_CASE else tuple(
                dict.fromkeys(row['move'] for row in item['ref_defenses'][:2]))
            for reply in replies:
                prefix = [history_move, reply]
                ref_lines = reference(case, prefix, 3)
                tal = run(args.source, case, prefix=prefix, depth=8, seconds=args.seconds, multipv=3)
                tal_line = tal['rows'][-1]['lines'][0]['pv']
                ref_line = ref_lines[0]['pv']
                diff = first_difference(tal_line, ref_line)
                result = dict(prefix=prefix, fen=position_after(case, prefix).fen(),
                              tal=tal, reference=ref_lines, tal_trace=trace(case, tal_line, prefix),
                              reference_trace=trace(case, ref_line, prefix), divergence=None)
                item['branches'].append(result)
                save()
                if diff is not None:
                    idx, tal_move, ref_move = diff
                    common = prefix + tal_line[:idx]
                    node = position_after(case, common)
                    result['divergence'] = dict(common=common, fen=node.fen(),
                        turn='white' if node.side == 0 else 'black', tal_choice=tal_move, ref_choice=ref_move,
                        tal_san=trace(case, [tal_move], common)[0]['san'],
                        ref_san=trace(case, [ref_move], common)[0]['san'], probes={})
                    for choice in (tal_move, ref_move):
                        probes = {}
                        result['divergence']['probes'][choice] = probes
                        for name, (opts, evaluation, tt) in ABLATIONS.items():
                            if name != 'baseline' and (case_id != DEFAULT_CASE or reply != 'c5d4'):
                                continue
                            probes[name] = run(args.source, case, prefix=common, roots=[choice], depth=6,
                                               seconds=args.seconds, options=opts, evaluation=evaluation, tt=tt)
                        probes['reference_attacker_pov'] = reference(case, common, 1, roots=[choice])
                print(case_id, reply, result['divergence'] and (result['divergence']['tal_san'],
                      result['divergence']['ref_san']), flush=True)
                save()


if __name__ == '__main__':
    main()
