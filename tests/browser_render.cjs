/* Real Chromium/Edge, fresh profile, same-origin WASM, actual UI actions.
   Run tools/prepare_web_runtime.py first. No Python process runs in the client.
   Python here hosts the website, just as the remote Render service will do. */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const {createInterface}=require('node:readline');
const {readFileSync,writeFileSync,mkdirSync,existsSync}=require('node:fs');
const {resolve,basename}=require('node:path');
const assert=require('node:assert/strict');
const root=resolve(__dirname,'..');

async function main(){
 const password=randomBytes(24).toString('hex');
 const child=spawn(process.env.TAL_PYTHON||'python',['tools/browser_test_server.py'],{
  cwd:root,env:{...process.env,TAL_BROWSER_TEST_PASSWORD:password,TAL_DEFAULT_COMPUTE:'local',
   TAL_PYODIDE_BASE:'/runtime/pyodide/v0.27.7/',TAL_SITE_LABEL:'Tal Lab v0.9.2 TEST'},stdio:['ignore','pipe','pipe']});
 let browser;
 const errors=[],external=[],requests=[],checks=[];
 try{
  const port=await new Promise((ok,bad)=>{
   const timer=setTimeout(()=>bad(Error('Test server did not start')),15000);
   child.once('exit',code=>{clearTimeout(timer);bad(Error('Test server exited: '+code))});
   createInterface({input:child.stdout}).once('line',line=>{clearTimeout(timer);ok(JSON.parse(line).port)});
  });
  const base='http://127.0.0.1:'+port;
  const executable=process.env.TAL_BROWSER_EXECUTABLE||(existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
  browser=await chromium.launch({executablePath:executable,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  const context=await browser.newContext({httpCredentials:{username:'browser-test',password}});
  let denyServerAnalysis=true;
  await context.route('**/*',async route=>{
   const u=new URL(route.request().url());requests.push(u.pathname);
   if(u.origin!==base){external.push(u.origin);return route.abort()}
   if(denyServerAnalysis&&/\/api\/analysis\/(start|auto|restart|sacrifice|benchmark)$/.test(u.pathname))return route.abort();
   return route.continue();
  });
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/',{waitUntil:'networkidle'});
  assert.equal(await page.locator('#compute-mode').inputValue(),'local');
  await page.waitForFunction(()=>state?.completed?.candidates?.length===3&&state.engine_implementation.includes('Pyodide'),null,{timeout:120000});
  assert.ok(requests.includes('/runtime/pyodide/v0.27.7/pyodide.asm.wasm'));
  assert.equal(external.length,0);
  assert.ok(await page.locator('#candidate-arrows line').count()>=1);
  checks.push({name:'fresh-profile-local-WASM-with-server-analysis-blocked',passed:true,
   result:await page.evaluate(()=>({version:state.version,backend:state.engine_implementation,depth:state.completed.depth,multipv:state.completed.candidates.length}))});
  await page.locator('#stop-analysis').click();
  await page.waitForFunction(()=>!state.active);
  await page.locator('#pgn-input').fill('[White "Browser"]\n[Black "Test"]\n\n1. e4 e5 2. Nf3 Nc6 *');
  await page.locator('#load-pgn').click();
  await page.waitForFunction(()=>state.game_moves.length===4);
  await page.locator('#game-last').click();await page.waitForFunction(()=>state.cursor===4);
  await page.locator('#min-depth').selectOption('3');
  await page.locator('#max-depth').selectOption('5');
  await page.locator('#analysis-seconds').selectOption('10');
  await page.locator('#start-analysis').click();
  await page.waitForFunction(()=>state.completed?.candidates?.length===3&&!state.active,null,{timeout:60000});
  assert.ok(await page.locator('#evaluation-graph circle').count()>=1);
  checks.push({name:'PGN-navigation-local-MultiPV-arrows-and-evaluation-graph',passed:true});
  denyServerAnalysis=false;
  await page.locator('#compute-mode').selectOption('server');
  await page.waitForFunction(()=>!busy);
  await page.locator('#start-analysis').click();
  await page.waitForFunction(()=>state.completed?.candidates?.length===3&&!state.active&&!state.engine_implementation.includes('Pyodide'),null,{timeout:60000});
  checks.push({name:'server-CPU-MultiPV',passed:true});
  await page.locator('summary').filter({hasText:'심층 분석'}).click();
  await page.locator('#deep-seconds').selectOption('600');await page.locator('#start-deep').click();
  await page.waitForFunction(()=>state.deep?.budget===600&&state.completed&&state.active,null,{timeout:20000});
  const downloadPromise=page.waitForEvent('download');await page.locator('#download-deep').click();
  const download=await downloadPromise;
  assert.ok(download.suggestedFilename().endsWith('.json'));
  await page.locator('#stop-analysis').click();await page.waitForFunction(()=>!state.active);
  checks.push({name:'600-second-server-job-progress-export-and-cancel',passed:true});
  await page.locator('#compute-mode').selectOption('local');await page.waitForFunction(()=>!busy);
  denyServerAnalysis=true;
  await page.locator('#start-deep').click();
  await page.waitForFunction(()=>state.deep?.budget===600&&state.completed&&state.active&&state.engine_implementation.includes('Pyodide'),null,{timeout:90000});
  await page.locator('#stop-analysis').click();await page.waitForFunction(()=>!state.active);
  checks.push({name:'600-second-local-job-progress-and-worker-cancel',passed:true});
  denyServerAnalysis=false;
  await page.locator('#compute-mode').selectOption('server');await page.waitForFunction(()=>!busy);
  await page.locator('#start-deep').click();
  await page.waitForFunction(()=>state.active&&state.deep?.budget===600);
  await page.locator('a[href="/play"]').click();
  await page.waitForSelector('#chessboard .square');
  for(let i=0;i<50;i++){
   const r=await context.request.get(base+'/api/analysis/state');
   if(!(await r.json()).active)break;
   if(i===49)throw Error('Leaving analysis did not cancel the server job');
   await new Promise(r=>setTimeout(r,100));
  }
  checks.push({name:'navigation-cancels-server-job',passed:true});
  await page.locator('#start-btn').click();
  await page.waitForFunction(()=>game&&!game.thinking&&game.moves.length===0);
  await page.locator('[data-square="e2"]').click();await page.locator('[data-square="e4"]').click();
  await page.waitForFunction(()=>game.moves.length>=2&&!game.thinking,null,{timeout:15000});
  checks.push({name:'play-screen-human-move-and-engine-reply',passed:true});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={browser:await browser.version(),browser_name:executable?basename(executable):'playwright-chromium',
   profile:'fresh',external_network_requests:external,client_invokes_native_python:false,checks};
  const out=process.env.TAL_BROWSER_REPORT||'evidence/render-test/browser-chromium.json';
  mkdirSync(resolve(root,'evidence/render-test'),{recursive:true});
  writeFileSync(resolve(root,out),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
 }finally{await browser?.close();child.kill('SIGTERM')}
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
