/* Dependency-free contract tests for request races and worker lifecycle.
   Real Pyodide/browser rendering is verified separately in the browser. */
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
class Element{
 constructor(){this.value='';this.checked=false;this.children=[];this.dataset={};this.events={};this.classList={add(){},remove(){},toggle(){}};this.style={};}
 setAttribute(k,v){this[k]=v;} addEventListener(k,v){this.events[k]=v;}
 append(...items){this.children.push(...items);} appendChild(x){this.append(x);} replaceChildren(...x){this.children=x;}
}
const ids={};for(const m of fs.readFileSync('web/analysis.html','utf8').matchAll(/id="([^"]+)"/g))ids[m[1]]=new Element();
const initial={fen:'start',base_fen:'start',side_to_move:'white',board:Array.from({length:8},()=>Array(8).fill('.')),legal:['e2e4','d2d4','g1f3'],moves:[],game_moves:[],cursor:0,epoch:42,game_scores:[],tags:{},active:false,status:'idle',min_depth:3,max_depth:5,seconds:10,multipv:3,iterations:[],elapsed:0};
const workers=[];class Worker{
 constructor(){workers.push(this);}postMessage(m){this.request=m;}terminate(){this.terminated=true;}
}
let response=initial;
const context=vm.createContext({console,setTimeout,clearTimeout,Worker,document:{getElementById:id=>ids[id],querySelectorAll:()=>[],createElement:()=>new Element(),createElementNS:()=>new Element(),createDocumentFragment:()=>new Element(),addEventListener(){}},window:{},navigator:{},localStorage:{getItem:()=> 'off',setItem(){}},fetch:async url=>({ok:true,headers:{get:()=>null},json:async()=>url.endsWith('/cases')?{positions:[]}:response})});
vm.runInContext(fs.readFileSync('web/analysis-visuals.js','utf8'),context);
vm.runInContext(fs.readFileSync('web/analysis.js','utf8'),context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 await new Promise(setImmediate);
 ids['compute-mode'].value='auto';assert.equal(run('selectedBackend()'),'server');
 ids['compute-mode'].value='local';
 await run("action('/api/analysis/start',{min_depth:3,max_depth:5,seconds:10,multipv:3,options:{},expected_epoch:42})");
 const first=workers.at(-1);assert.equal(first.request.settings.expected_epoch,undefined);assert.equal(first.request.position.fen,'start');assert.equal(run('state.active'),true);
 await run("action('/api/analysis/stop')");assert.equal(first.terminated,true);assert.equal(run('state.status'),'stopped');
 first.onmessage({data:{id:first.request.id,kind:'done',result:{...initial,fen:'obsolete',status:'completed'}}});
 assert.equal(run('state.fen'),'start');assert.equal(run('state.status'),'stopped');
 await run("action('/api/analysis/start',{min_depth:3,max_depth:5,seconds:10,multipv:3,options:{}})");
 const second=workers.at(-1);second.onmessage({data:{id:second.request.id,kind:'error',error:'CDN unavailable'}});
 assert.equal(run('state.active'),false);assert.equal(run('state.status'),'error');assert.match(ids.message.textContent,/CDN unavailable/);
 ids['compute-mode'].value='server';run('stopLocal();localResult=null');
 let release;
 context.fetch=async url=>({ok:true,headers:{get:()=>null},json:async()=>url.endsWith('/state')?await new Promise(resolve=>release=resolve):response});
 const oldPoll=run('refresh()');await new Promise(setImmediate);
 response={...initial,fen:'new-position'};
 await run("action('/api/analysis/fen',{fen:'new-position'})");release(initial);await oldPoll;
 assert.equal(run('state.fen'),'new-position');assert.equal(ids['candidate-arrows'].children.length,0);
 let sacrificeRequest;
 context.fetch=async (url,options)=>{
   assert.equal(url,'/api/analysis/sacrifice');
   sacrificeRequest=JSON.parse(options.body);
   return {ok:true,headers:{get:()=>null},json:async()=>({offers_found:1,scan_complete:true,
     ranked_moves:['e2e4'],candidates:[{move:'e2e4',label:'강제 메이트 희생',depth:3,defense_depth:2,
       score:99997,proof:{status:'proved',max_plies:3},defenses:[{move:'d7d5',response:'accepts',score:99997}],
       pv:['e2e4','d7d5','f1b5']}]})};
 };
 await ids['discover-sacrifice'].events.click();
 assert.deepEqual(sacrificeRequest,{discover:true,uci:'',expected_fen:'new-position'});
 assert.equal(ids['sacrifice-move'].value,'e2e4');
 assert.match(ids['sacrifice-result'].textContent,/3반수 이내 강제 메이트.*d7d5 \(수락/);
 context.document.querySelector=()=>({checked:false});
 context.fetch=async (url,options)=>{
   assert.equal(url,'/api/analysis/evaluation');
   assert.equal(JSON.parse(options.body).expected_fen,'new-position');
   const before={denominator:24,terms:{Material:{numerator:2400}},static_score:100};
   const after={denominator:24,terms:{Material:{numerator:4800}},static_score:200};
   return {ok:true,headers:{get:()=>null},json:async()=>({before,after,delta:100,
     options:{king_safety:false,attack_activity:false,initiative:false}})};
 };
 await ids['show-evaluation'].events.click();
 assert.match(ids['evaluation-result'].textContent,/정적 평가: \+1.00 → \+2.00/);
 assert.match(ids['evaluation-result'].textContent,/기본 평가/);
 ids['compute-mode'].value='local';
 ids['deep-seconds'].value='600';ids['deep-profile'].value='conservative';
 context.fetch=async()=>({ok:true,headers:{get:()=>null},json:async()=>response});
 await ids['start-deep'].events.click();
 const deep=workers.at(-1);
 assert.equal(deep.request.settings.deep,true);
 assert.equal(deep.request.settings.seconds,600);
 assert.equal(deep.request.settings.multipv,1);
 assert.equal(deep.request.settings.expected_fen,'new-position');
 deep.onmessage({data:{id:deep.request.id,kind:'progress',state:{...response,active:true,
   deep:{phase:'defense',budget:600,root:[{depth:8,pv:['e2e4']}],candidates:[{move:'e2e4',
     reference:true,comparison:{depth:8,score:25,reference_score:25},defenses:[{depth:7,score:21,pv:['e7e5']}]}]}}}});
 assert.match(ids['deep-report'].textContent,/방어 깊이 7/);
 assert.equal(ids['download-deep'].disabled,false);
 await run("action('/api/analysis/stop')");assert.equal(deep.terminated,true);
 run('clearTimeout(polling);stopLocal();cancelAuto()');
 console.log('frontend contracts passed (auto default, worker cancellation/error, stale poll, cleared arrows, sacrifice discovery, deep analysis)');
})().catch(e=>{console.error(e);process.exitCode=1;run('clearTimeout(polling);stopLocal();cancelAuto()');});
