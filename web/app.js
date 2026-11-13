'use strict';

const PIECE = {K:'♔', Q:'♕', R:'♖', B:'♗', N:'♘', P:'♙', k:'♚', q:'♛', r:'♜', b:'♝', n:'♞', p:'♟'};
const PIECE_KO = {k:'킹', q:'퀸', r:'룩', b:'비숍', n:'나이트', p:'폰'};
const TAL_PRESET = {tactical_checks:true, attack_activity:true, initiative:true,
                    tactical_ordering:true, check_continuation:false, aspiration:false, king_safety:false};
const OPTION_KEYS = Object.keys(TAL_PRESET);
const $ = id => document.getElementById(id);

let game = null;
let selected = null;
let draggedFrom = null;
let orientation = 'white';
let sideChoice = 'white';
let busy = false;
let pollHandle = null;
let activePromotion = null;
let gameCount = 1;

function message(text, error=true) {
  const el = $('message');
  el.textContent = text || '';
  el.style.color = error ? '#e6a7a1' : '#bcd8b8';
}

async function api(path, payload=undefined) {
  const options = payload === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
  };
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error('체스 서버에 연결할 수 없습니다. 인터넷 연결을 확인한 뒤 새로고침해 주세요.'); }
  let data;
  try { data = await response.json(); }
  catch {
    if (response.status === 429) throw new Error('로그인 시도가 너무 많아요. 잠시 후 다시 접속해 주세요.');
    throw new Error('서버 응답을 읽을 수 없습니다.');
  }
  if (!response.ok) {
    if (response.status === 429) throw new Error('로그인 시도가 너무 많아요. 잠시 후 다시 접속해 주세요.');
    throw new Error(data.error || '요청을 처리할 수 없습니다.');
  }
  if (response.headers.get('X-Tal-Session-Reset') === '1') data.session_reset = true;
  return data;
}

function applyState(data) {
  if (data.session_reset) message('서버 재시작 또는 장시간 미사용으로 이전 대국이 초기화됐어요.');
  game = data;
  if (selected && !game.legal.some(m => m.startsWith(selected))) selected = null;
  render();
  if (pollHandle) clearTimeout(pollHandle);
  if (game.thinking) pollHandle = setTimeout(refresh, 450);
}

async function refresh() {
  pollHandle = null;
  try {
    const next = await api('/api/state');
    applyState(next);
  } catch (e) {
    message(e.message);
    pollHandle = setTimeout(refresh, 1400);
  }
}

async function action(path, payload={}) {
  if (busy) return;
  busy = true;
  try {
    const state = await api(path, payload);
    message('');
    applyState(state);
  } catch (e) {
    message(e.message);
  } finally { busy = false; }
}

function pieceAt(square) {
  const file = square.charCodeAt(0)-97;
  const rank = Number(square[1]);
  return game.board[8-rank][file];
}

function isHumanPiece(piece) {
  if (!piece || piece === '.') return false;
  return game.human === 'white' ? piece === piece.toUpperCase() : piece === piece.toLowerCase();
}

function canInteract() {
  return game && !game.thinking && !game.outcome && game.side_to_move === game.human;
}

function labelForSquare(square, piece) {
  if (piece === '.') return `${square} 빈칸`;
  return `${square} ${piece === piece.toUpperCase() ? '백' : '흑'} ${PIECE_KO[piece.toLowerCase()]}`;
}

function renderBoard() {
  if (!game) return;
  const board = $('chessboard');
  const ranks = orientation === 'white' ? [8,7,6,5,4,3,2,1] : [1,2,3,4,5,6,7,8];
  const files = orientation === 'white' ? 'abcdefgh' : 'hgfedcba';
  const last = game.last_move;
  const targets = selected ? game.legal.filter(m => m.slice(0,2) === selected).map(m => m.slice(2,4)) : [];
  const fragment = document.createDocumentFragment();
  for (let r=0; r<8; r++) {
    for (let f=0; f<8; f++) {
      const square = files[f] + ranks[r];
      const piece = pieceAt(square);
      const el = document.createElement('button');
      el.type = 'button';
      // a1/h8 are dark, a8/h1 are light, in either orientation.
      el.className = 'square ' + (((Number(square[1]) + square.charCodeAt(0)-97) % 2) === 1 ? 'dark' : 'light');
      el.dataset.square = square;
      el.setAttribute('role','gridcell');
      el.setAttribute('aria-label',labelForSquare(square,piece));
      if (last && (square === last.slice(0,2) || square === last.slice(2,4))) el.classList.add('highlight-last');
      if (square === game.check) el.classList.add('king-check');
      if (square === selected) el.classList.add('selected');
      if (targets.includes(square)) {
        el.classList.add('legal-target');
        if (piece !== '.') el.classList.add('occupied');
      }
      if (piece !== '.') {
        const span = document.createElement('span');
        span.className = 'piece ' + (piece === piece.toUpperCase() ? 'white-piece' : 'black-piece');
        span.textContent = PIECE[piece];
        span.setAttribute('aria-hidden', 'true');
        el.appendChild(span);
      }
      if (f === 0) {
        const coord = document.createElement('span');
        coord.className = 'coordinate coord-rank';
        coord.textContent = String(ranks[r]);
        el.appendChild(coord);
      }
      if (r === 7) {
        const coord = document.createElement('span');
        coord.className = 'coordinate coord-file';
        coord.textContent = files[f];
        el.appendChild(coord);
      }
      el.draggable = canInteract() && isHumanPiece(piece);
      el.addEventListener('click', () => onSquare(square));
      el.addEventListener('dragstart', event => {
        if (!canInteract() || !isHumanPiece(piece)) { event.preventDefault(); return; }
        draggedFrom = square;
        event.dataTransfer.setData('text/plain', square);
        event.dataTransfer.effectAllowed = 'move';
      });
      el.addEventListener('dragover', event => { if (draggedFrom) event.preventDefault(); });
      el.addEventListener('drop', event => {
        event.preventDefault();
        const from = draggedFrom || event.dataTransfer.getData('text/plain');
        draggedFrom = null;
        if (from) tryMove(from, square);
      });
      el.addEventListener('dragend', () => { draggedFrom = null; });
      fragment.appendChild(el);
    }
  }
  board.replaceChildren(fragment);
  $('board-loading').hidden = true;
}

function onSquare(square) {
  if (!canInteract() || busy) return;
  const piece = pieceAt(square);
  if (selected === square) { selected = null; renderBoard(); return; }
  if (selected && game.legal.some(m => m.startsWith(selected + square))) {
    tryMove(selected,square);
    return;
  }
  selected = isHumanPiece(piece) ? square : null;
  renderBoard();
}

function tryMove(from,to) {
  if (!canInteract() || busy) return;
  const candidates = game.legal.filter(m => m.startsWith(from+to));
  if (!candidates.length) {
    if (isHumanPiece(pieceAt(to))) selected = to;
    renderBoard();
    return;
  }
  if (candidates.length > 1) {
    showPromotion(candidates);
    return;
  }
  selected = null;
  action('/api/move',{uci:candidates[0]});
}

function showPromotion(candidates) {
  activePromotion = candidates;
  const choices = $('promotion-choices');
  choices.replaceChildren();
  for (const p of ['q','r','b','n']) {
    const move = candidates.find(m => m.endsWith(p));
    if (!move) continue;
    const piece = game.human === 'white' ? p.toUpperCase() : p;
    const button = document.createElement('button');
    button.type='button';
    button.textContent = PIECE[piece];
    button.title = PIECE_KO[p];
    button.setAttribute('aria-label',PIECE_KO[p]+'으로 승격');
    button.addEventListener('click',()=> {
      $('promotion-modal').hidden = true;
      activePromotion = null;
      selected = null;
      action('/api/move',{uci:move});
    });
    choices.appendChild(button);
  }
  $('promotion-modal').hidden = false;
  const first = choices.querySelector('button');
  if (first) first.focus();
}

function closePromotion() {
  activePromotion = null;
  $('promotion-modal').hidden = true;
  renderBoard();
}

function renderPlayers() {
  function setPlayer(position, color) {
    const human = color === game.human;
    $(position+'-name').textContent = human ? 'YOU' : 'TAL ENGINE';
    $(position+'-side').textContent = color.toUpperCase();
    const suffix = human ? '플레이어' : '공격 스타일을 연구하는 체스 AI';
    $(position+'-subtitle').textContent = suffix;
    const icon = document.querySelector('.'+position+'-player .player-avatar');
    icon.textContent = human ? '♙' : '♞';
    icon.className = 'player-avatar '+(human?'human-avatar':'engine-avatar');
  }
  setPlayer('top',orientation==='white'?'black':'white');
  setPlayer('bottom',orientation);
}

function renderStatus() {
  const status = $('status-pill');
  const indicator = $('status-label');
  status.classList.toggle('is-thinking',game.thinking);
  status.classList.toggle('is-over',Boolean(game.outcome));
  if (game.outcome) {
    indicator.textContent = game.outcome.reason + ' · ' + game.outcome.result;
  } else if (game.error) {
    indicator.textContent = '엔진 오류';
  } else if (game.thinking) {
    indicator.textContent = '엔진이 계산 중…';
  } else if (game.check) {
    indicator.textContent = '체크! 당신의 차례';
  } else {
    indicator.textContent = '당신의 차례';
  }
  $('bottom-subtitle').textContent = orientation === game.human
    ? (game.outcome ? '대국 종료' : game.thinking ? '엔진 생각 중' : '차례가 왔습니다')
    : '공격 스타일을 연구하는 체스 AI';
  $('undo-btn').disabled = !game.can_undo;
  $('resign-btn').disabled = Boolean(game.outcome);
  $('draw-btn').hidden = !game.claimable_draw;
  $('draw-btn').textContent = game.claimable_draw ? '½ 무승부 청구 · '+game.claimable_draw : '';
  $('game-number').textContent = 'GAME '+String(gameCount).padStart(3,'0');
  if (game.error) message(game.error);
}

function renderEvaluation() {
  const info = game.info;
  const score = $('evaluation-value');
  const caption = $('evaluation-caption');
  if (!info) {
    score.textContent = '—';
    caption.textContent = '평가 준비 중';
    $('metric-depth').textContent = '—';
    $('metric-nodes').textContent = '—';
    $('metric-time').textContent = '—';
    $('pv-text').textContent = '엔진의 첫 수를 기다리는 중입니다.';
    $('eval-meter-fill').style.width = '50%';
    return;
  }
  const centi = info.score;
  if (Math.abs(centi) > 99000) {
    const matePly = 100000 - Math.abs(centi);
    score.textContent = (centi >= 0 ? 'M' : '-M') + String(Math.max(1,Math.ceil(matePly/2)));
  } else score.textContent = (centi >= 0 ? '+' : '') + (centi / 100).toFixed(2);
  caption.textContent = centi > 35 ? '백 우세로 분석' : centi < -35 ? '흑 우세로 분석' : '균형에 가까운 형세';
  $('metric-depth').textContent = String(info.depth);
  $('metric-nodes').textContent = Number(info.nodes).toLocaleString('ko-KR');
  $('metric-time').textContent = Number(info.seconds).toFixed(2) + 's';
  $('pv-text').textContent = info.pv.length ? info.pv.join(' → ') : '계산 중…';
  const width = 50 + 44 * Math.tanh(centi / 500);
  $('eval-meter-fill').style.width = width.toFixed(1) + '%';
}

function renderHistory() {
  const list = $('move-list');
  const rows = [];
  for (let i=0;i<game.moves.length;i+=2) {
    const white = game.moves[i].san;
    const black = game.moves[i+1]?.san || '—';
    const latestWhite = i===game.moves.length-1;
    const latestBlack = i+1===game.moves.length-1;
    rows.push(`<div class="move-row"><span class="move-number">${i/2+1}.</span><span class="move-san ${latestWhite?'latest':''}">${escapeText(white)}</span><span class="move-san ${latestBlack?'latest':''}">${escapeText(black)}</span></div>`);
  }
  list.innerHTML = rows.length ? rows.join('') : '<div class="empty-history">첫 수를 두면 기보가 여기에 표시됩니다.<span>♟</span></div>';
  list.scrollTop=list.scrollHeight;
  $('move-count').textContent=game.moves.length+' MOVES';
}
function escapeText(s) { return String(s).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function render(){renderBoard();renderPlayers();renderStatus();renderEvaluation();renderHistory();}

function chosenOptions() {
  const obj = {};
  for (const input of document.querySelectorAll('input[data-option]')) obj[input.dataset.option] = input.checked;
  return obj;
}
function setPreset(options) {
  for (const input of document.querySelectorAll('input[data-option]')) input.checked = !!options[input.dataset.option];
  updatePreset();
}
function updatePreset() {
  const options = chosenOptions();
  const balanced = Object.values(options).every(v=>!v);
  const tal = OPTION_KEYS.every(key => options[key] === TAL_PRESET[key]);
  $('balanced-style').classList.toggle('active',balanced);
  $('tal-style').classList.toggle('active',tal);
}
async function startGame() {
  if (busy) return;
  if (game && game.moves.length && !game.outcome && !confirm('진행 중인 대국을 종료하고 새 대국을 시작할까요?')) return;
  const payload = {
    side:sideChoice, depth:Number($('depth-input').value),
    seconds:Number($('time-select').value),options:chosenOptions(),
  };
  selected=null;
  orientation=sideChoice;
  gameCount++;
  await action('/api/new',payload);
}

$('side-selector').addEventListener('click',e=> {
  const button=e.target.closest('button[data-side]');
  if(!button) return;
  sideChoice=button.dataset.side;
  for(const el of $('side-selector').querySelectorAll('button')) {
    const active=el===button;
    el.classList.toggle('active',active);
    el.setAttribute('aria-checked',String(active));
  }
});
$('depth-input').addEventListener('input',()=>{$('depth-value').textContent=$('depth-input').value;});
$('balanced-style').addEventListener('click',()=>setPreset(Object.fromEntries(OPTION_KEYS.map(k=>[k,false]))));
$('tal-style').addEventListener('click',()=>setPreset(TAL_PRESET));
$('advanced-toggles').addEventListener('change',updatePreset);
$('start-btn').addEventListener('click',startGame);
$('undo-btn').addEventListener('click',()=> {selected=null;action('/api/undo');});
$('flip-btn').addEventListener('click',()=> {orientation=orientation==='white'?'black':'white';selected=null;if(game)render();});
$('pgn-btn').addEventListener('click',()=> {window.location.href='/api/pgn';});
$('resign-btn').addEventListener('click',()=> {
  if(game&&!game.outcome&&confirm('정말 기권할까요?')) {selected=null;action('/api/resign');}
});
$('draw-btn').addEventListener('click',()=>action('/api/draw'));
$('promotion-cancel').addEventListener('click',closePromotion);
$('promotion-modal').addEventListener('click',e=>{if(e.target===$('promotion-modal'))closePromotion();});
document.addEventListener('keydown',e=> {if(e.key==='Escape'&&!$('promotion-modal').hidden)closePromotion();});

(async()=>{
  try {
    const state=await api('/api/state');
    orientation=state.human;
    sideChoice=state.human;
    $('depth-input').value=state.depth;
    $('depth-value').textContent=state.depth;
    $('time-select').value=String(state.seconds);
    setPreset(state.options);
    applyState(state);
  } catch (e) { $('board-loading').textContent='서버 연결 실패';message(e.message); }
})();
