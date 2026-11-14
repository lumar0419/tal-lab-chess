'use strict';
const $ = id => document.getElementById(id);
const PIECE = {K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'};
const LABEL = {q:'퀸',r:'룩',b:'비숍',n:'나이트',p:'폰',k:'킹'};
let state = null;
let orientation = 'white';
let selected = null;
let busy = false;
let polling = null;
let localWorker=null,localResult=null,localTicket=0,localWatchdog=null;
let measurement=null,positionRevision=0;
const localScores=new Map();
let lastFen = '';
const AUTO_KEY = 'tal_lab_analysis_auto_v055';
let autoEnabled = true;
let autoTimer = null;
let autoSequence = 0;
function restoreAutoPreference(){
  try {autoEnabled = localStorage.getItem(AUTO_KEY) !== 'off';} catch {autoEnabled = true;}
  $('auto-analyze').checked = autoEnabled;
  showAutoPreference();
}
function showAutoPreference(){
  $('auto-mode-label').textContent=autoEnabled?'ON':'OFF';
  $('auto-mode-label').classList.toggle('off',!autoEnabled);
}
function setAutoPreference(on){
  autoEnabled=!!on;
  try {localStorage.setItem(AUTO_KEY, autoEnabled?'on':'off');} catch {}
  $('auto-analyze').checked=autoEnabled;
  showAutoPreference();
  if(!autoEnabled) cancelAuto();
}
function cancelAuto(){
  autoSequence++;
  if(autoTimer!==null){clearTimeout(autoTimer);autoTimer=null;}
}
function currentSettings(){
  const min=Number($('min-depth').value),max=Number($('max-depth').value);
  if(!Number.isInteger(min)||!Number.isInteger(max)||min>max){
    message('최대 깊이가 최소 목표 깊이 이상이어야 해요.');
    return null;
  }
  const options={};
  for(const box of document.querySelectorAll('input[data-option]'))options[box.dataset.option]=box.checked;
  return {min_depth:min,max_depth:max,seconds:Number($('analysis-seconds').value),multipv:Number($('multipv').value),options};
}
// One bounded search per new position; a changed setting explicitly replaces
// the current search. No endless restart on time cap, idle polls, or reload.
function scheduleAuto(restart=false,delay=350){
  if(!autoEnabled||!state||state.outcome)return;
  if(state.deep&&state.active&&!restart)return;
  cancelAuto();
  const ticket=autoSequence,fen=state.fen,epoch=state.epoch;
  autoTimer=setTimeout(async()=>{
    autoTimer=null;
    if(ticket!==autoSequence||!autoEnabled||!state||state.fen!==fen||state.epoch!==epoch)return;
    if(busy){scheduleAuto(restart,250);return;}
    if(!restart && state.status!=='idle')return;
    const config=currentSettings();if(!config)return;
    try{
      const result=await api(restart?'/api/analysis/restart':'/api/analysis/auto',
                             {...config,expected_fen:fen,expected_epoch:epoch,automatic:true});
      if(ticket!==autoSequence||!autoEnabled)return;
      if(state && result.fen===state.fen)apply(result);
    }catch(e){if(ticket===autoSequence)message(e.message);}
  },delay);
}


async function serverApi(url, data) {
  const opts = data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)};
  let response;
  try { response = await fetch(url,opts); } catch {throw new Error('서버에 연결할 수 없어요.');}
  let result;
  try { result = await response.json(); } catch {throw new Error('서버 응답이 올바르지 않아요.');}
  if (!response.ok) throw new Error(result.error || '요청을 처리할 수 없어요.');
  if (response.headers.get('X-Tal-Session-Reset') === '1') message('서버가 재시작되어 분석 세션이 초기화됐어요.');
  return result;
}
function message(text) { $('message').textContent = text || ''; }
function scoreLabel(cp) {
  if (cp === undefined || cp === null) return '—';
  if (Math.abs(cp) >= 99000) {
    const ply = 100000 - Math.abs(cp);
    return (cp >= 0 ? 'M' : '-M') + Math.max(1,Math.ceil(ply/2));
  }
  return (cp>=0?'+':'')+(cp/100).toFixed(2);
}
function fenSquare(file,rank){return file+String(rank);}
function pieceAt(square){return state.board[8-Number(square[1])][square.charCodeAt(0)-97];}
function label(square,piece){return square + (piece === '.'?' 빈칸':(piece === piece.toUpperCase()?' 백 ':' 흑 ')+ (LABEL[piece.toLowerCase()] || piece));}
function renderBoard() {
  if (!state) return;
  const ranks = orientation === 'white' ? [8,7,6,5,4,3,2,1] : [1,2,3,4,5,6,7,8];
  const files = orientation === 'white' ? 'abcdefgh' : 'hgfedcba';
  const targets = selected ? state.legal.filter(m=>m.startsWith(selected)).map(m=>m.slice(2,4)) : [];
  const best = state.completed?.pv?.[0] || '';
  const board = $('analysis-board');
  const fragment = document.createDocumentFragment();
  for (let r=0;r<8;r++) for (let f=0;f<8;f++) {
    const square = fenSquare(files[f],ranks[r]);
    const piece = pieceAt(square);
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'square '+ ((ranks[r]+files[f].charCodeAt(0)-97)%2===1?'dark':'light');
    el.dataset.square = square;
    el.setAttribute('role','gridcell');
    el.setAttribute('aria-label',label(square,piece));
    if (square===state.check) el.classList.add('king-check');
    if (square===selected) el.classList.add('selected');
    if (square===best.slice(0,2)) el.classList.add('best-from');
    if (square===best.slice(2,4)) el.classList.add('best-to');
    if (targets.includes(square)) el.classList.add('legal-target', ...(piece!=='.'?['occupied']:[]));
    if (piece!=='.') {
      const span=document.createElement('span');span.className='piece '+(piece===piece.toUpperCase()?'white-piece':'black-piece');span.textContent=PIECE[piece];span.setAttribute('aria-hidden','true');el.appendChild(span);
    }
    if (f===0) {const c=document.createElement('span');c.className='coordinate coord-rank';c.textContent=String(ranks[r]);el.appendChild(c);}
    if (r===7) {const c=document.createElement('span');c.className='coordinate coord-file';c.textContent=files[f];el.appendChild(c);}
    el.addEventListener('click',()=>onSquare(square));
    el.draggable = piece!=='.';
    el.addEventListener('dragstart',e=>{if(piece==='.') {e.preventDefault();return;}e.dataTransfer.setData('text/plain',square);});
    el.addEventListener('dragover',e=>e.preventDefault());
    el.addEventListener('drop',e=>{e.preventDefault();tryMove(e.dataTransfer.getData('text/plain'),square);});
    fragment.appendChild(el);
  }
  board.replaceChildren(fragment);
  renderArrows();
}
function onSquare(square){
  if (busy || !state) return;
  if (selected===square){selected=null;renderBoard();return;}
  if (selected && state.legal.some(m=>m.startsWith(selected+square))){tryMove(selected,square);return;}
  const p=pieceAt(square);
  selected=(p!=='.' && (p===p.toUpperCase()) === (state.side_to_move==='white')) ? square : null;
  renderBoard();
}
function tryMove(from,to){
  if (!state || busy || !from) return;
  const moves=state.legal.filter(m=>m.startsWith(from+to));
  if (!moves.length) return;
  if (moves.length>1){showPromotion(moves);return;}
  selected=null;action('/api/analysis/move',{uci:moves[0]});
}
function showPromotion(moves){
  const choices=$('promotion-choices');choices.replaceChildren();
  for(const p of ['q','r','b','n']){
    const move=moves.find(m=>m.endsWith(p));if(!move)continue;
    const btn=document.createElement('button');btn.type='button';btn.textContent=PIECE[state.side_to_move==='white'?p.toUpperCase():p];btn.setAttribute('aria-label',LABEL[p]+' 승격');
    btn.addEventListener('click',()=>{$('promotion-modal').hidden=true;selected=null;action('/api/analysis/move',{uci:move});});choices.appendChild(btn);
  }
  $('promotion-modal').hidden=false;
}
function apply(next, initialize=false) {
  const changed = next.fen !== lastFen;
  lastFen = next.fen;
  state = next;
  if(next.engine_implementation){
    $('compute-mode').title='실행 엔진: '+next.engine_implementation;
    $('engine-implementation').textContent='실행 엔진: '+next.engine_implementation;
    $('nodes-display').title='실행 엔진: '+next.engine_implementation;
  }
  if(changed){selected=null;$('fen-input').value=next.fen;$('deep-candidate').value='';$('sacrifice-result').textContent='새 국면입니다. 후보를 선택해 검증하세요.';}
  if(initialize){$('min-depth').value=next.min_depth;$('max-depth').value=next.max_depth;$('analysis-seconds').value=next.seconds;$('multipv').value=next.multipv||3;}
  $('turn-badge').textContent=(state.side_to_move==='white'?'WHITE':'BLACK')+' TO MOVE';
  const ongoing=state.active;
  $('live-indicator').textContent=ongoing?'SEARCHING':state.status.toUpperCase().replaceAll('_',' ');
  $('live-indicator').classList.toggle('running',ongoing);
  $('start-analysis').disabled=ongoing;
  $('start-deep').disabled=ongoing&&!state.automatic;
  $('stop-analysis').disabled=!ongoing;
  const latest=state.completed;
  $('live-score').textContent=latest?scoreLabel(latest.score):'—';
  $('best-move').textContent=(latest?.best_san ? latest.best_san + '  ·  ' + latest.pv[0] : latest?.pv?.[0]) || '아직 완료된 깊이 없음';
  $('completed-depth').textContent=latest?.depth??'—';
  $('searching-depth').textContent=ongoing?state.attempting||'대기':'—';
  $('elapsed').textContent=state.elapsed.toFixed(1)+'s';
  const budget=state.deep?.budget;
  $('target-depth').textContent=state.deep?(budget?`${budget}초`:'대기'):`${state.min_depth} → ${state.max_depth}`;
  $('depth-progress').style.width=(budget?Math.min(100,state.elapsed/budget*100):(latest?.depth||0)/state.max_depth*100).toFixed(1)+'%';
  $('live-pv').textContent=latest?.pv?.length?(latest.pv_san?.length ? latest.pv_san : latest.pv).join(' → '):'아직 완료된 깊이가 없어요. 계산 중입니다.';
  $('nodes-display').textContent=Number(latest?.nodes||0).toLocaleString('ko-KR')+' nodes';
  const labels={idle:'자동 분석 대기 중입니다.',running:'새 깊이를 계산 중입니다.',completed:'분석이 완료됐습니다.',target_not_reached:'시간 상한 때문에 최소 목표 깊이에 도달하지 못했습니다.',stopped:'사용자가 분석을 중단했습니다.',preempted:'다른 요청을 처리하기 위해 분석을 중단했습니다.',busy:'다른 분석으로 서버가 바쁩니다.',error:'분석 중 오류가 발생했습니다.'};
  $('analysis-state-label').textContent=labels[state.status]||state.status;
  if(state.error) message(state.error);
  renderBoard();renderIterations();renderCandidates();renderGame();renderDeep();
  clearTimeout(polling);
  if(ongoing) polling=setTimeout(refresh,600);
  if(changed && !initialize){
    // Cancel any queued analysis from the previous position and debounce a new one.
    scheduleAuto(false);
  }
}
function renderDeep(){
  const report=state.deep;
  $('download-deep').disabled=!report?.root?.length;
  const root=$('deep-report');
  if(!report){root.textContent='';return;}
  const phases={queued:'서버 대기',root:'전체 합법수 탐색 · MultiPV 1',screen:'희생 후보 탐색',
    compare:'지정 수 재탐색',defense:'상대 차례의 독립 방어 탐색',done:'심층 분석 종료'};
  const rootProof=report.root_proof;
  const phaseText=phases[report.phase]||report.phase;
  const summary=rootProof?.status==='proved'?`${phaseText} · ${rootProof.move} 강제 메이트 ${rootProof.max_plies}반수`:phaseText;
  root.textContent=[summary,...report.candidates.map(item=>{
    const cmp=item.comparison;
    const reply=item.defenses.at(-1);
    const score=cmp?` · 깊이 ${cmp.depth} 백 ${scoreLabel(cmp.score)} / 기준 ${scoreLabel(cmp.reference_score)}`:'';
    const defense=reply?` · 방어 깊이 ${reply.depth} 백 ${scoreLabel(reply.score)} · ${reply.pv.join(' → ')}`:'';
    const defenses=reply&&item.offer?(item.defense_accepts?' · 수락':' · 거절'):'';
    const proof=item.proof?.status==='proved'?` · 강제 메이트 ${item.proof.max_plies}반수`:'';
    const loss=item.material_under_defense?.sustained_piece_loss;
    const category=item.offer?'즉시 포획 가능한 희생 후보':loss?`${loss.ply}반수에서 기물 손실 관측`:'비교 후보';
    return `${item.move} · ${item.reference?'전체 탐색 기준수 · ':''}${category}${score}${defense}${defenses}${proof}${item.draw_claim?' · 무승부 청구 가능':''}`;
  })].join('\n');
}
function renderCandidates(){
  const root=$('multipv-results');
  if(!root)return;
  root.replaceChildren();
  const lines=state?.completed?.candidates||[];
  if(!lines.length){
    const p=document.createElement('p');p.className='empty-history';
    p.textContent='해당 깊이에서 모든 후보 탐색을 완료하면 표시됩니다.';
    root.appendChild(p);return;
  }
  const turnWhite=state.side_to_move==='white';
  const best=turnWhite?lines[0].score:-lines[0].score;
  lines.forEach((line,idx)=>{
    const move=line.pv?.[0]; if(!move)return;
    const card=document.createElement('button');card.type='button';
    card.className='multipv-card';card.setAttribute('aria-label',`후보 ${idx+1} ${line.best_san||move}, 평가 ${scoreLabel(line.score)}, 예상 수순 확인`);
    const label=document.createElement('span');label.className='multipv-label';label.textContent=`#${idx+1}  ${line.best_san||move}${line.sacrifice?" · 희생 후보":""}`;
    const score=document.createElement('strong');score.textContent=scoreLabel(line.score);
    const details=document.createElement('small');
    const difference=Math.max(0,best-(turnWhite?line.score:-line.score));
    const mateDifference=Math.abs(best)>=99000||Math.abs(line.score)>=99000;
    details.textContent=`최선수 대비 ${difference===0?'동일 평가':mateDifference?'메이트 점수 차이':(difference/100).toFixed(2)+'폰'} · ${(line.pv_san?.length?line.pv_san:line.pv||[]).join(' → ')}`;
    card.append(label,score,details);
    card.addEventListener('click',()=>{
      $('sacrifice-move').value=move;
      document.querySelectorAll('.multipv-card').forEach(el=>el.classList.remove('focused'));
      card.classList.add('focused');
      $('live-pv').textContent=(line.pv_san?.length?line.pv_san:line.pv||[]).join(' → ');
    });
    root.appendChild(card);
  });
}
function renderIterations(){
  const root=$('iteration-history');root.replaceChildren();
  if(!state.iterations.length){const p=document.createElement('p');p.className='empty-history';p.textContent='국면을 불러오면 자동으로 깊이별 최선수와 평가가 나타납니다.';root.appendChild(p);return;}
  for(const result of state.iterations){
    const row=document.createElement('div');row.className='iteration-row';
    for(const [content,cls] of [[result.depth,'depth-pill'],[result.best_san||result.pv?.[0]||'—','move-pill'],[scoreLabel(result.score),''],[result.seconds.toFixed(1)+'s','']]){
      const col=document.createElement('span');col.className=cls;col.textContent=String(content);row.appendChild(col);
    }
    root.appendChild(row);
  }
  root.scrollTop=root.scrollHeight;
}
async function refresh(){
  polling=null;
  const revision=positionRevision;
  try{const next=await api('/api/analysis/state');if(revision===positionRevision&&!busy)apply(next);}
  catch(e){message(e.message);polling=setTimeout(refresh,1800);}
}
async function action(path,data={}){
  if(busy)return;busy=true;cancelAuto();clearTimeout(polling);positionRevision++;
  try{const next=await api(path,data);message('');apply(next);if(path==='/api/analysis/move')playMoveSound();}
  catch(e){message(e.message);}
  finally{busy=false;if(autoEnabled&&state?.status==='idle')scheduleAuto(false);}
}
async function loadMaster(){
  try{
    const cases=await api('/api/analysis/cases');
    const select=$('master-select');select.replaceChildren();
    const empty=document.createElement('option');empty.value='';empty.textContent='희생 국면을 선택하세요';select.appendChild(empty);
    for(const item of cases.positions){const option=document.createElement('option');option.value=item.fen;option.textContent=`${item.master} · ${item.label} (${item.year})`;option.dataset.description=`${item.theme} · 실제 착수: ${item.historical_uci} · 최선수 보장 아님`;select.appendChild(option);}
    select.addEventListener('change',()=>{
      if(!select.value)return;
      $('master-description').textContent=select.selectedOptions[0].dataset.description;
      $('fen-input').value=select.value;
      action('/api/analysis/fen',{fen:select.value});
    });
  }catch(e){$('master-description').textContent='기보 데이터를 불러오지 못했어요.';}
}
$('load-fen').addEventListener('click',()=>action('/api/analysis/fen',{fen:$('fen-input').value.trim()}));
$('copy-fen').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(state.fen);message('FEN을 복사했어요.');}catch{message('클립보드에 복사할 수 없어요.');}});
$('undo-position').addEventListener('click',()=>action('/api/analysis/undo'));
$('reset-position').addEventListener('click',()=>action('/api/analysis/reset'));
$('flip-position').addEventListener('click',()=>{orientation=orientation==='white'?'black':'white';renderBoard();});
$('best-position').addEventListener('click',()=>{const mv=state?.completed?.pv?.[0];if(mv)action('/api/analysis/move',{uci:mv});else message('완료된 분석 결과가 없어요.');});
$('start-analysis').addEventListener('click',()=>{
  cancelAuto();
  const config=currentSettings();
  if(config)action('/api/analysis/start',{...config,expected_epoch:state?.epoch});
});
$('start-deep').addEventListener('click',()=>{
  cancelAuto();
  return action('/api/analysis/start',{deep:true,seconds:Number($('deep-seconds').value),multipv:1,
    profile:$('deep-profile').value,candidate:$('deep-candidate').value.trim(),expected_fen:state?.fen,expected_epoch:state?.epoch});
});
$('download-deep').addEventListener('click',()=>{
  if(!state.deep?.root?.length)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify({fen:state.fen,base_fen:state.base_fen,moves:state.moves,analysis:state.deep},null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='tal-lab-deep-analysis.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('stop-analysis').addEventListener('click',()=>{
  setAutoPreference(false); // An explicit stop must never auto-restart.
  action('/api/analysis/stop');
});
$('auto-analyze').addEventListener('change',()=>{
  setAutoPreference($('auto-analyze').checked);
  if(autoEnabled && state && !state.active && !state.outcome){
    if(!state.deep)scheduleAuto(state.status!=='idle');
  } else if(!autoEnabled && state){
    action('/api/analysis/stop');
  }
});
for(const control of document.querySelectorAll('#min-depth,#max-depth,#analysis-seconds,#multipv,input[data-option]')){
  control.addEventListener('change',()=>{
    if(autoEnabled && state && !state.outcome&&!state.deep)scheduleAuto(true,650);
  });
}
$('promotion-cancel').addEventListener('click',()=>{$('promotion-modal').hidden=true;});
$('promotion-modal').addEventListener('click',e=>{if(e.target===$('promotion-modal'))$('promotion-modal').hidden=true;});
(async()=>{
  restoreAutoPreference();
  try{
    apply(await api('/api/analysis/state'),true);
    loadMaster();
    if(autoEnabled && state && state.status==='idle' && !state.outcome){
      scheduleAuto(false,250);
    }
  }catch(e){message(e.message);}
})();

function renderArrows(){
  const svg=$('candidate-arrows');svg.replaceChildren();
  const ns='http://www.w3.org/2000/svg';
  function element(name,attrs){const el=document.createElementNS(ns,name);for(const [key,value] of Object.entries(attrs))el.setAttribute(key,value);return el;}
  const arrows=TalVisuals.arrows(state.completed?.candidates,state.side_to_move,orientation,state.legal);
  for(const arrow of arrows.reverse()){
    const [x,y]=arrow.from,[tx,ty]=arrow.to,dx=tx-x,dy=ty-y,len=Math.hypot(dx,dy),ux=dx/len,uy=dy/len;
    const endx=tx-ux*22,endy=ty-uy*22;
    const group=element('g',{'data-move':arrow.move,opacity:'.85'});
    group.append(element('line',{x1:x,y1:y,x2:endx,y2:endy,stroke:arrow.color,'stroke-width':arrow.width,'stroke-linecap':'round'}));
    group.append(element('polygon',{points:`${tx},${ty} ${endx-uy*17},${endy+ux*17} ${endx+uy*17},${endy-ux*17}`,fill:arrow.color}));
    const badge=element('text',{x:x+ux*30-uy*(15+(arrow.rank-1)*24),y:y+uy*30+ux*(15+(arrow.rank-1)*24),fill:'#101c1b','font-size':24,'font-weight':900,stroke:arrow.color,'stroke-width':2,'paint-order':'stroke'});badge.textContent=arrow.rank;group.append(badge);svg.append(group);
  }
}
let audioContext;
function unlockAudio(){
  if(!$('move-sound').checked)return;
  try{audioContext ||= new (window.AudioContext||window.webkitAudioContext)();audioContext.resume().catch(()=>{});}catch{}
}
document.addEventListener('pointerdown',unlockAudio);
document.addEventListener('keydown',unlockAudio);
$('move-sound').addEventListener('change',unlockAudio);
function playMoveSound(){
  if(!$('move-sound').checked||!audioContext||audioContext.state!=='running')return;
  const tone=audioContext.createOscillator(),gain=audioContext.createGain(),t=audioContext.currentTime;
  tone.type='sine';tone.frequency.setValueAtTime(660,t);tone.frequency.exponentialRampToValueAtTime(330,t+.07);
  gain.gain.setValueAtTime(.06,t);gain.gain.exponentialRampToValueAtTime(.001,t+.09);
  tone.connect(gain);gain.connect(audioContext.destination);tone.start(t);tone.stop(t+.1);
  tone.onended=()=>{tone.disconnect();gain.disconnect();};
}

function selectedBackend(){
  const mode=$('compute-mode').value;
  return mode==='auto'?(measurement?.choice||'server'):mode;
}
function stopLocal(){
  localTicket++;clearTimeout(localWatchdog);localWatchdog=null;
  if(localWorker){localWorker.terminate();localWorker=null;}
  if(localResult){
    const deep=localResult.deep?{...localResult.deep,outcome:'cancelled'}:null;
    localResult={...localResult,deep,active:false,status:'stopped'};
  }
}
function mergeLocal(next,base){
  const merged={...base,...next,epoch:base.epoch,game_moves:base.game_moves,cursor:base.cursor,tags:base.tags,game_scores:base.game_scores};
  if(next.completed){localScores.set(historyKey(base),{ply:base.cursor,score:next.completed.score,depth:next.completed.depth,multipv:next.multipv,backend:'local',options:next.options});}
  return merged;
}
function historyKey(s,ply=s.cursor){return s.base_fen+'|'+(s.game_moves||s.moves).slice(0,ply).map(m=>m.uci).join(' ');}
async function api(url,data){
  const starts=['/api/analysis/start','/api/analysis/auto','/api/analysis/restart'];
  if(starts.includes(url) && state && data?.options){
    const previous=localScores.get(historyKey(state));
    if(previous && Object.keys(data.options).some(key=>previous.options?.[key]!==data.options[key])){
      localScores.delete(historyKey(state));
    }
  }
  if(starts.includes(url)&&selectedBackend()==='local'){
    if(data.expected_fen&&data.expected_fen!==state.fen)return state;
    stopLocal();
    const id=localTicket;
    const revision=positionRevision;
    const position=state;
    const stopped=await serverApi('/api/analysis/stop',{});
    if(id!==localTicket||revision!==positionRevision)return state;
    if(stopped.fen!==position.fen||historyKey(stopped)!==historyKey(position)){
      localResult=null;
      return stopped;
    }
    const base={...stopped,game_scores:(stopped.game_scores||[]).filter(point=>point.ply!==stopped.cursor)};
    localResult={...base,...data,deep:data.deep?{profile:data.profile,phase:'queued',budget:data.seconds,candidates:[]}:null,automatic:!!data.automatic,active:true,status:'running',completed:null,iterations:[],elapsed:0,attempting:0,error:null};
    localWorker=new Worker('/engine-worker.js');
    const worker=localWorker;
    function fail(error){if(id!==localTicket)return;stopLocal();localResult={...localResult,status:'error',error:'로컬 분석 실패: '+error};apply(localResult);}
    localWatchdog=setTimeout(()=>fail('런타임 로드 또는 계산 시간 초과. 서버 CPU를 선택할 수 있습니다.'),(data.seconds+90)*1000);
    worker.onerror=e=>fail(e.message||'Worker 오류');
    worker.onmessage=({data:message})=>{
      if(message.id!==id||id!==localTicket||state.fen!==base.fen)return;
      if(message.kind==='error'){fail(message.error);return;}
      localResult=mergeLocal(message.state||message.result,base);
      if(message.kind==='done'){clearTimeout(localWatchdog);worker.terminate();localWorker=null;}
      apply(localResult);
    };
    // The worker reconstructs a new session with its own revision counter.
    const settings={...data};
    delete settings.expected_epoch;
    worker.postMessage({id,kind:'analyze',position:base,settings});
    return localResult;
  }
  if(url==='/api/analysis/state'&&localResult)return localResult;
  if(url==='/api/analysis/stop'&&localResult){
    stopLocal();
    const stopped=await serverApi(url,data);
    if(stopped.fen!==localResult.fen||historyKey(stopped)!==historyKey(localResult)){
      localResult=null;
      return stopped;
    }
    localResult={...localResult,epoch:stopped.epoch};
    return localResult;
  }
  if(data!==undefined&&url!=='/api/analysis/benchmark'&&url!=='/api/analysis/sacrifice'){
    stopLocal();localResult=null;
    if(['/api/analysis/fen','/api/analysis/reset','/api/analysis/pgn'].includes(url))localScores.clear();
  }
  return serverApi(url,data);
}
$('compute-mode').addEventListener('change',async()=>{
  if(busy)return;
  cancelAuto();clearTimeout(polling);positionRevision++;stopLocal();localResult=null;
  busy=true;
  try{apply(await serverApi('/api/analysis/stop',{}));
    $('compute-status').textContent='선택: '+(selectedBackend()==='local'?'로컬 CPU':'서버 CPU')+($('compute-mode').value==='auto'&&!measurement?' · 측정 전 기본값':'');
  }catch(e){message(e.message);}finally{busy=false;}
  if(autoEnabled)scheduleAuto(true);
});
function localBenchmark(){
  return new Promise((resolve,reject)=>{
    const worker=new Worker('/engine-worker.js');
    const timer=setTimeout(()=>{worker.terminate();reject(new Error('로컬 벤치마크 시간 초과'));},120000);
    const done=()=>{clearTimeout(timer);worker.terminate();};
    worker.onerror=e=>{done();reject(new Error(e.message||'Worker 오류'));};
    worker.onmessage=({data})=>{if(data.kind==='done'){done();resolve(data.result);}else if(data.kind==='error'){done();reject(new Error(data.error));}};
    worker.postMessage({id:1,kind:'benchmark'});
  });
}
$('benchmark-compute').addEventListener('click',async()=>{
  if(busy)return;busy=true;cancelAuto();setAutoPreference(false);clearTimeout(polling);positionRevision++;
  $('benchmark-compute').disabled=true;stopLocal();localResult=null;measurement=null;
  try{
    apply(await serverApi('/api/analysis/stop',{}));
    $('compute-status').textContent='같은 2국면 · 깊이 3 · MultiPV 3 · 각 3회 측정 중…';
    // Sequential runs avoid competition between the benchmark processes.
    const server=await serverApi('/api/analysis/benchmark',{}),local=await localBenchmark();
    const signature=s=>JSON.stringify(s.samples.map(x=>x.results));
    if(server.benchmark_id!==local.benchmark_id||signature(server)!==signature(local))throw new Error('두 장치의 탐색 결과가 달라 자동 선택을 적용하지 않습니다.');
    const choice=local.median_seconds<server.median_seconds*.85?'local':'server';
    measurement={server,local,choice};
    $('compute-status').textContent=`중앙값: 서버 ${server.median_seconds.toFixed(3)}초 / 로컬 ${local.median_seconds.toFixed(3)}초 · 자동 선택: ${choice==='local'?'로컬':'서버'} CPU. 다운로드·통신 시간 제외, 15% 이내 차이는 서버 유지. 자동 분석 OFF.`;
  }catch(e){$('compute-status').textContent='측정 미완료: '+e.message+' · 자동 모드는 서버 CPU 사용';}
  finally{busy=false;$('benchmark-compute').disabled=false;}
});
$('pgn-file').addEventListener('change',async()=>{
  const file=$('pgn-file').files[0];if(!file)return;
  if(file.size>131072){message('PGN은 128 KiB 이하로 선택하세요.');return;}
  $('pgn-input').value=await file.text();
});
$('load-pgn').addEventListener('click',()=>action('/api/analysis/pgn',{pgn:$('pgn-input').value}));
for(const [id,ply] of [['game-first',()=>0],['game-prev',()=>Math.max(0,state.cursor-1)],['game-next',()=>Math.min(state.game_moves.length,state.cursor+1)],['game-last',()=>state.game_moves.length]]){
  $(id).addEventListener('click',()=>action('/api/analysis/navigate',{ply:ply()}));
}
function renderGame(){
  const moves=state.game_moves||[],cursor=state.cursor||0;
  $('game-position').textContent=`${state.tags?.White||'White'} — ${state.tags?.Black||'Black'} · ${cursor} / ${moves.length} 반수`;
  const root=$('game-moves');root.replaceChildren();
  moves.forEach((m,i)=>{const b=document.createElement('button');b.type='button';b.className='game-move'+(cursor===i+1?' current':'');b.textContent=`${i+1}. ${m.san}`;b.setAttribute('aria-label',`${i+1}번째 반수 ${m.san}`);b.onclick=()=>action('/api/analysis/navigate',{ply:i+1});root.append(b);});
  const svg=$('evaluation-graph'),ns='http://www.w3.org/2000/svg';svg.replaceChildren();
  const axis=document.createElementNS(ns,'path');axis.setAttribute('d','M20 90H580');axis.setAttribute('stroke','#6c817b');svg.append(axis);
  const scores=new Map((state.game_scores||[]).map(p=>[p.ply,p]));
  for(let i=0;i<=moves.length;i++){const p=localScores.get(historyKey(state,i));if(p&&!scores.has(i))scores.set(i,p);}
  if(state.completed)scores.set(cursor,{...state.completed,ply:cursor,backend:state===localResult?'local':'server'});
  for(const p of scores.values()){
    const x=20+560*p.ply/Math.max(1,moves.length),y=90-70*Math.max(-500,Math.min(500,p.score))/500;
    const dot=document.createElementNS(ns,'circle');dot.setAttribute('cx',x);dot.setAttribute('cy',y);dot.setAttribute('r',p.ply===cursor?7:5);dot.setAttribute('fill',p.backend==='local'?'#90cfff':'#e6cc91');dot.setAttribute('tabindex','0');dot.setAttribute('role','button');dot.setAttribute('aria-label',`${p.ply} 반수 ${scoreLabel(p.score)}, 깊이 ${p.depth}`);
    const title=document.createElementNS(ns,'title');title.textContent=`${p.ply} 반수 · ${scoreLabel(p.score)} · depth ${p.depth} · ${p.backend||'server'}`;dot.append(title);
    dot.onclick=()=>action('/api/analysis/navigate',{ply:p.ply});dot.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();dot.onclick();}};svg.append(dot);
    if(Math.abs(p.score)>=99000){const t=document.createElementNS(ns,'text');t.setAttribute('x',x);t.setAttribute('y',y+(y<90?18:-10));t.setAttribute('fill','#e6cc91');t.textContent='M';svg.append(t);}
  }
}
function sacrificeSummary(result){
  if(!result.depth)return `${result.move} · 완료된 방어 탐색 깊이 없음`;
  const defenses=(result.defenses||[]).map(line=>`${line.move} (${line.response==='accepts'?'수락':'거절'}, 백 ${scoreLabel(line.score)})`).join(', ');
  const proof=result.proof?.status==='proved'?` · ${result.proof.max_plies}반수 이내 강제 메이트` : '';
  const claim=result.defender_draw_claim?' · 방어 측 무승부 청구 가능':'';
  return `${result.move} · ${result.label}${proof} · 방어 깊이 ${result.defense_depth} · 백 평가 ${scoreLabel(result.score)}${claim} · 방어 ${defenses} · 수순 ${result.pv.join(' → ')}`;
}
async function runSacrifice(discover){
  if(busy||state.active){message('분석을 중단한 뒤 검증하세요.');return;}
  busy=true;cancelAuto();const fen=state.fen;$('sacrifice-result').textContent='후보와 상대 방어 수순 계산 중…';
  try{
    const result=await serverApi('/api/analysis/sacrifice',{discover,uci:$('sacrifice-move').value.trim(),expected_fen:fen});
    if(state.fen!==fen)return;
    if(discover){
      if(result.ranked_moves.length)$('sacrifice-move').value=result.ranked_moves[0];
      const prefix=result.scan_complete?'즉시 수락 가능한 후보':'제한 시간 내 확인한 후보';
      $('sacrifice-result').textContent=[`${prefix} ${result.offers_found}개 · 완료한 후보 순위 ${result.ranked_moves.join(', ')||'없음'}`,
        ...result.candidates.map(sacrificeSummary)].join('\n');
    }else $('sacrifice-result').textContent=sacrificeSummary(result);
  }catch(e){$('sacrifice-result').textContent=e.message;}
  finally{busy=false;}
}
$('verify-sacrifice').addEventListener('click',()=>runSacrifice(false));
$('discover-sacrifice').addEventListener('click',()=>runSacrifice(true));
