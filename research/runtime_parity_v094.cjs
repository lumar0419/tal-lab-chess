const { loadPyodide } = require(process.env.TAL_PYODIDE || 'pyodide');
const { readFileSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { spawnSync } = require('node:child_process');

async function main(){
  const source = resolve(__dirname, '..');
  const py = await loadPyodide();
  const worker = readFileSync(resolve(source,'web/engine-worker.js'),'utf8');
  const files=JSON.parse(worker.match(/const files=(\[[^\n]+\]);/)[1].replaceAll("'",'"'));
  for (const file of files) py.FS.writeFile('/home/pyodide/' + file, readFileSync(resolve(source,file),'utf8'));
  const code = `import json, threading
from analysis_server import AnalysisSession
from notation import san_for_move
from version import VERSION
a = AnalysisSession(threading.Lock(), san_for_move=san_for_move, background=False)
a.import_pgn('1.e4 e5 2.Nf3 Nc6 *')
a.navigate(1)
out = {'version': VERSION, 'results': []}
for enabled in (False, True, False):
    previous = a.state()['epoch']
    a.start({'min_depth':4,'max_depth':4,'seconds':30,'multipv':3,'options':{'selective':enabled},'expected_fen':a.state()['fen'],'expected_epoch':previous}, mode='restart')
    state = a.state()
    assert state['epoch'] > previous
    assert state['completed']['depth'] == 4 and state['options']['selective'] == enabled
    rows = [{k:v for k,v in line.items() if k != 'seconds'} for line in state['completed']['candidates']]
    out['results'].append(rows)
assert out['results'][0] == out['results'][2]
assert out['results'][0] != out['results'][1]
a.set_fen('r1bk2nr/p2p1pNp/n2B4/1p1NP2P/6P1/3P1Q2/P1P1K3/q5b1 w - - 1 22')
from deep_analysis import analyze_deep
d = analyze_deep(a.board, 5, profile='conservative', max_depth=3)
out['deep'] = {'root': d['root_move'], 'depth': d['root'][-1]['depth'],
               'comparison': d['candidates'][0]['comparison'],
               'proof': d['candidates'][0]['proof']}
assert out['deep']['root'] == 'f3f6' and out['deep']['proof']['status'] == 'proved'
a.set_fen('7k/8/8/8/8/8/p7/R6K w - - 0 1')
out['evaluation'] = a.evaluation({'expected_fen':a.board.fen(),'uci':'a1a2',
    'options':{'king_safety':True,'attack_activity':True,'initiative':False}})
assert out['evaluation']['delta'] is not None
assert out['evaluation']['before']['search_score'] is None
print(json.dumps(out))`;
  const arr=[];py.setStdout({batched:line=>arr.push(line)});
  await py.runPythonAsync(code);
  const native=spawnSync(process.env.TAL_PYTHON || 'python',['-c',code],{cwd:source,encoding:'utf8'});
  if(native.status!==0)throw new Error(native.stderr);
  const a=JSON.parse(arr.join('\n'));const b=JSON.parse(native.stdout);
  if(JSON.stringify(a)!==JSON.stringify(b))throw new Error('different results');
  writeFileSync(resolve(source,'evidence/v094/runtime-parity.json'),JSON.stringify({pyodide:a,native:b},null,2)+'\n');
  console.log('v0.9.4 Python/Pyodide 0.27.7 parity: fast MultiPV, deep matched score and 3-ply proof');
}
main().catch(error=>{console.error(error);process.exitCode=1});
