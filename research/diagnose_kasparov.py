"""Separate root discovery, forced sacrifice, defensive branches and leaf evaluation."""
import argparse
import json
from pathlib import Path

import evaluate
from research.deep_benchmark import ROOT, run
from research.measure_search import compare_reference, stockfish_line
from research.sacrifice_cases import positions, replay_case
from sacrifice import balance


def explain(case, after, rows):
    out = []
    for row in rows:
        for line in row['lines'][:1]:
            b = replay_case(case)
            if after:
                b.push_uci(after)
            side = b.side
            trail = []
            for uci in line['pv']:
                mv = b.parse_uci(uci)
                if mv is None:
                    raise ValueError(f'Illegal PV move: {uci}')
                b.make_move(mv)
                terms, phase, dead = evaluate.eval_terms(b)
                trail.append(dict(move=uci, fen=b.fen(), material_white=balance(b, 0),
                                  terms_white=terms, phase=phase, dead=dead,
                                  evaluation_white=evaluate.evaluate_white(b)))
            out.append(dict(depth=row['depth'], score=line['score'],
                            score_white=line['score'] if side==0 else -line['score'],
                            pv=trail))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    import chess
    import chess.engine
    case = next(c for c in positions() if c['id']=='kasparov_topalov_1999_ply47')
    move = case['historical_uci']
    report = {'case':case, 'variants':{}, 'defenses':{}}

    def save():
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as ref:
        ref.configure({'Threads':1,'Hash':32})
        report['reference'] = dict(id=ref.id, threads=1, hash_mb=32, seconds=8,
                                    root=compare_reference(ref,case['fen'],8,move))
        ref_board = chess.Board(case['fen'])
        ref_board.push_uci(move)
        ref.configure({'Clear Hash':None})
        report['reference']['defenses'] = [
            stockfish_line(i,chess.WHITE) for i in ref.analyse(ref_board,chess.engine.Limit(time=8),multipv=5)]
        save()
    variants = {
        'default': ({},60000,9,20),
        'pvs_off': ({'pvs':False},60000,6,7),
        'tt_off': ({},0,6,7),
        'lmr': ({'lmr':True},60000,6,7),
        'tactical_checks': ({'qsearch_quiet_checks':True},60000,6,7),
        'check_continuation': ({'qsearch_quiet_checks':True,'check_continuation':True},60000,6,7),
        'aspiration': ({'aspiration':True},60000,6,7),
        'tactical_ordering': ({'tactical_ordering':True},60000,6,7),
        'delta_experiment': ({'delta_pruning':True},60000,6,7),
    }
    for name,(options,tt,depth,seconds) in variants.items():
        data=run(ROOT,case,depth=depth,seconds=seconds,roots=[move],options=options,tt=tt)
        report['variants'][name]=dict(settings=dict(options=options,tt=tt,depth=depth,seconds=seconds),
                                      result=data)
        print(name,[(r['depth'],r['lines'][0]['score']) for r in data['rows']],flush=True)
        save()
    report['default_leaf_evaluation']=explain(case,None,report['variants']['default']['result']['rows'])
    for defense in dict.fromkeys(['c5d4','a7b6']+[x['move'] for x in report['reference']['defenses'][:3]]):
        data=run(ROOT,case,depth=7,seconds=7,after=move,roots=[defense])
        report['defenses'][defense]=dict(seconds=7,depth_from_defender=7,result=data,
                                          white_view=explain(case,move,data['rows']))
        save()
        print(defense,[(r['depth'], -r['lines'][0]['score']) for r in data['rows']],flush=True)
    report['defense_group']=run(ROOT,case,depth=7,seconds=10,after=move,multipv=3)
    save()


if __name__=='__main__':
    main()
