"""Paired fixed-depth benchmark. Baseline differs ONLY in evasion filtering."""
import argparse,json,platform,time,statistics
from pathlib import Path
from board import Board,START_FEN
from search import Searcher
import evaluate

def main():
    p=argparse.ArgumentParser();p.add_argument('--depth',type=int,default=4);p.add_argument('--repeats',type=int,default=3);p.add_argument('--output',default='benchmark-results.json');a=p.parse_args()
    cases=[{'id':'start','fen':START_FEN},{'id':'kiwipete','fen':'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1'}]
    cases+=json.loads(Path('master_sacrifice_cases.json').read_text())['positions']
    result={'python':platform.python_version(),'platform':platform.platform(),'depth':a.depth,'multipv':3,'repeats':a.repeats,'cases':[]}
    for case in cases:
        rows={False:[],True:[]}
        for trial in range(a.repeats):
            for enabled in ([False,True] if trial%2==0 else [True,False]):
                evaluate.clear_pawn_cache();s=Searcher(tt_size=60000);s.fast_evasions=enabled;groups=[]
                t=time.perf_counter();s.search(Board(case['fen']),max_depth=a.depth,time_limit=10,full_time=True,multipv=3,on_info=None,on_multipv=groups.append)
                elapsed=time.perf_counter()-t
                rows[enabled].append({'seconds':elapsed,'nodes':s.nodes,'depth':groups[-1][0].depth if groups else 0,'lines':[(l.pv[0].uci(),l.score) for l in groups[-1]] if groups else []})
        old=statistics.median(r['seconds'] for r in rows[False]);new=statistics.median(r['seconds'] for r in rows[True])
        equal=all(r['depth']==a.depth and r['lines']==rows[False][0]['lines'] and r['nodes']==rows[False][0]['nodes'] for batch in rows.values() for r in batch)
        result['cases'].append({'id':case['id'],'baseline':rows[False],'filtered':rows[True],'speedup':old/new,'identical_tree_result':equal})
        print(case['id'],round(old/new,3),'same tree/result:',equal,flush=True)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
