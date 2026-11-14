'use strict';
// A pinned Python runtime executes the SAME Python source as the server.
let ROOT='https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
let ready;
async function initialize(){
  importScripts(ROOT+'pyodide.js');
  const py=await loadPyodide({indexURL:ROOT});
  const files=['version.py','board.py','evaluate.py','search.py','notation.py','analysis_server.py','benchmark.py','pgn_io.py','sacrifice.py','search_gate.py','deep_analysis.py'];
  for(const name of files){const r=await fetch('/engine/'+name);if(!r.ok)throw new Error('엔진 소스 로드 실패');py.FS.writeFile('/home/pyodide/'+name,await r.text());}
  return py;
}
self.onmessage=async({data})=>{
  const {id,kind,position,settings,runtimeBase}=data;
  try{
    if(runtimeBase){
      const runtime=new URL(runtimeBase,self.location.href);
      const local=runtime.origin===self.location.origin&&runtime.pathname==='/runtime/pyodide/v0.27.7/';
      const pinned=runtime.href==='https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
      if(!local&&!pinned)throw new Error('허용되지 않은 브라우저 런타임 경로');
      ROOT=runtime.href;
    }
    const py=await(ready ||= initialize());
    self.emitState=json=>self.postMessage({id,kind:'progress',state:JSON.parse(json)});
    py.globals.set('request_json',JSON.stringify({position,settings}));
    const code=kind==='benchmark'?`from benchmark import run_benchmark
import json
json.dumps(run_benchmark())`:`import json, threading
from analysis_server import AnalysisSession
from notation import san_for_move
from js import emitState
request = json.loads(request_json)
a = AnalysisSession(threading.Lock(), san_for_move=san_for_move, background=False,
    on_update=lambda state: emitState(json.dumps(state)))
a.set_fen(request['position']['base_fen'])
for move in request['position']['moves']:
    a.move(move['uci'])
a.start(request['settings'])
json.dumps(a.state())`;
    const result=JSON.parse(await py.runPythonAsync(code));
    self.postMessage({id,kind:'done',result});
  }catch(error){self.postMessage({id,kind:'error',error:String(error.message||error)});}
};
