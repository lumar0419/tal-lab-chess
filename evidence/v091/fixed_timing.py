import json, os, subprocess, sys, time
from pathlib import Path
root=Path.cwd()
suite=json.loads(Path(__file__).with_name('development.json').read_text())
positions=[r for r in suite if r['suite'] in ('ecm','iq4')][:4] + [r for r in suite if r['suite']=='historical'][:4]
rows=[]
for case in positions:
    times={'base':[],'new':[]}
    for colors in (('base','new'),('new','base')):
        for label in colors:
            repo=root/('tal-v090' if label=='base' else 'tal-v091')
            task=dict(fen=case['fen'],depth=5,tt=300000,options={'lmr':True})
            proc=subprocess.run([sys.executable,'-m','research.probe_search'],input=json.dumps(task),
                                cwd=repo,text=True,capture_output=True,check=True)
            result=json.loads(proc.stdout)
            for sample in result['rows']:
                del sample['seconds']
            times[label].append(result)
    rows.append(dict(id=case['id'],runs=times))
    print(case['id'],[round(x['elapsed'],3) for x in times['base']],
          [round(x['elapsed'],3) for x in times['new']],flush=True)
Path('evidence-v091/fixed-timing.json').write_text(json.dumps(rows,indent=2)+'\n')
