import json,sys
from pathlib import Path
sys.path.insert(0, str(Path('tal-v091').resolve()))
from board import Board
from deep_analysis import analyze_deep
cases=json.loads(Path(__file__).with_name('control-cases.json').read_text())['rows']
controls=[r for r in cases if 'forbidden' in r['case']]
results=[]
for r in controls:
    case=r['case']
    report=analyze_deep(Board(case['fen']),4,candidate=case['forbidden'])
    results.append(dict(case=case,report=report))
Path('evidence-v091/false-offers.json').write_text(json.dumps(results,indent=2)+'\n')
for r in results:
    case=r['case']; report=r['report']
    forced=next(c for c in report['candidates'] if c['move']==case['forbidden'])
    print(case['id'],report['root_move'],forced['verification'],forced['comparison'],
          forced['defenses'][-1]['pv'][0] if forced['defenses'] else None)
