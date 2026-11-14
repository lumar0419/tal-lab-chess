"""Optional Stockfish cross-check. It is NEVER imported by the deployed app.
Install optional validation dependency: python -m pip install chess
Usage: python compare_reference.py --stockfish /path/to/stockfish --output report.json
"""
import argparse,json,platform,time
from pathlib import Path
from board import Board
from search import Searcher

def main():
    import chess,chess.engine
    p=argparse.ArgumentParser();p.add_argument('--stockfish',required=True);p.add_argument('--output',default='reference-results.json');a=p.parse_args()
    cases=json.loads(Path('master_sacrifice_cases.json').read_text())['positions']
    report={'python':platform.python_version(),'note':'Bounded reference comparison, not ground truth or an Elo estimate. Tal and Stockfish scores use different evaluators.','tal_limit':{'depth':4,'seconds':3,'multipv':3},'stockfish_limit':{'seconds':0.3,'threads':1,'hash_mb':32},'cases':[]}
    with chess.engine.SimpleEngine.popen_uci(a.stockfish) as engine:
        engine.configure({'Threads':1,'Hash':32});report['reference']=engine.id
        for case in cases:
            board=Board(case['fen']);s=Searcher(tt_size=60000);groups=[];t=time.perf_counter()
            s.search(board,max_depth=4,time_limit=3,full_time=True,multipv=3,on_info=None,on_multipv=groups.append)
            runtime=time.perf_counter()-t;lines=groups[-1] if groups else []
            ref=chess.Board(case['fen']);engine.configure({'Clear Hash':None})
            info=engine.analyse(ref,chess.engine.Limit(time=.3),multipv=3)
            reference=[{'move':r['pv'][0].uci(),'score_white':r['score'].white().score(),'mate_white':r['score'].white().mate(),'depth':r.get('depth')} for r in info]
            historical=chess.Move.from_uci(case['historical_uci'])
            forced=engine.analyse(ref,chess.engine.Limit(time=.3),root_moves=[historical])
            report['cases'].append({'id':case['id'],'historical':case['historical_uci'],'tal_seconds':runtime,'tal_depth':lines[0].depth if lines else 0,'tal_nodes':s.nodes,'tal':[{'move':l.pv[0].uci(),'score_white':l.score if board.side==0 else -l.score} for l in lines],'reference':reference,'top1_agreement':bool(lines and lines[0].pv[0].uci()==reference[0]['move']),'historical_reference':{'score_white':forced['score'].white().score(),'mate_white':forced['score'].white().mate(),'pv':[m.uci() for m in forced['pv']]}})
            print(case['id'],report['cases'][-1]['top1_agreement'],flush=True)
    Path(a.output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
