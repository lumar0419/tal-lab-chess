'use strict';
const $ = id => document.getElementById(id);
const PIECE = {K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'};
const LABEL = {q:'퀸',r:'룩',b:'비숍',n:'나이트'};
let state = null;
let orientation = 'white';
let selected = null;
let busy = false;
let polling = null;
let lastFen = '';

async function api(url, data) {
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
  if(changed){selected=null;$('fen-input').value=next.fen;}
  if(initialize){$('min-depth').value=next.min_depth;$('max-depth').value=next.max_depth;$('analysis-seconds').value=next.seconds;}
  $('turn-badge').textContent=(state.side_to_move==='white'?'WHITE':'BLACK')+' TO MOVE';
  const ongoing=state.active;
  $('live-indicator').textContent=ongoing?'SEARCHING':state.status.toUpperCase().replaceAll('_',' ');
  $('live-indicator').classList.toggle('running',ongoing);
  $('start-analysis').disabled=ongoing;
  $('stop-analysis').disabled=!ongoing;
  const latest=state.completed;
  $('live-score').textContent=latest?scoreLabel(latest.score):'—';
  $('best-move').textContent=(latest?.best_san ? latest.best_san + '  ·  ' + latest.pv[0] : latest?.pv?.[0]) || '아직 완료된 깊이 없음';
  $('completed-depth').textContent=latest?.depth??'—';
  $('searching-depth').textContent=ongoing?state.attempting||'대기':'—';
  $('elapsed').textContent=state.elapsed.toFixed(1)+'s';
  $('target-depth').textContent=`${state.min_depth} → ${state.max_depth}`;
  $('depth-progress').style.width=((latest?.depth||0)/state.max_depth*100).toFixed(1)+'%';
  $('live-pv').textContent=latest?.pv?.length?(latest.pv_san?.length ? latest.pv_san : latest.pv).join(' → '):'아직 완료된 깊이가 없어요. 계산 중입니다.';
  $('nodes-display').textContent=Number(latest?.nodes||0).toLocaleString('ko-KR')+' nodes';
  const labels={idle:'분석을 시작해 주세요.',running:'새 깊이를 계산 중입니다.',completed:'분석이 완료됐습니다.',target_not_reached:'시간 상한 때문에 최소 목표 깊이에 도달하지 못했습니다.',stopped:'사용자가 분석을 중단했습니다.',busy:'다른 분석으로 서버가 바쁩니다.',error:'분석 중 오류가 발생했습니다.'};
  $('analysis-state-label').textContent=labels[state.status]||state.status;
  if(state.error) message(state.error);
  renderBoard();renderIterations();
  clearTimeout(polling);
  if(ongoing) polling=setTimeout(refresh,600);
}
function renderIterations(){
  const root=$('iteration-history');root.replaceChildren();
  if(!state.iterations.length){const p=document.createElement('p');p.className='empty-history';p.textContent='분석을 실행하면 완료한 깊이마다 최선수와 평가가 나타납니다.';root.appendChild(p);return;}
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
  try{apply(await api('/api/analysis/state'));}
  catch(e){message(e.message);polling=setTimeout(refresh,1800);}
}
async function action(path,data={}){
  if(busy)return;busy=true;
  try{const next=await api(path,data);message('');apply(next);}
  catch(e){message(e.message);}
  finally{busy=false;}
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
  const min=Number($('min-depth').value),max=Number($('max-depth').value);
  if(min>max){message('최대 깊이가 최소 목표 깊이 이상이어야 해요.');return;}
  const opts={};for(const box of document.querySelectorAll('input[data-option]'))opts[box.dataset.option]=box.checked;
  action('/api/analysis/start',{min_depth:min,max_depth:max,seconds:Number($('analysis-seconds').value),options:opts});
});
$('stop-analysis').addEventListener('click',()=>action('/api/analysis/stop'));
$('promotion-cancel').addEventListener('click',()=>{$('promotion-modal').hidden=true;});
$('promotion-modal').addEventListener('click',e=>{if(e.target===$('promotion-modal'))$('promotion-modal').hidden=true;});
(async()=>{
  try{apply(await api('/api/analysis/state'),true);loadMaster();}
  catch(e){message(e.message);}
})();
