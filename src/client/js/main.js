// Wires everything together: connection, map, panels, the top bar and the dialogs, for the
// observer and for the person leading a civilization.

import { connect, send } from './net.js';
import { store, on, emit, handleMessage, yearLabel, leader, player, plural, turnsFor, U } from './state.js';
import { icon, mountIcons } from './icons.js';
import { MapView, MISSION_COLORS } from './renderer/map.js';
import { Minimap } from './renderer/minimap.js';
import { preload, setOnLoad } from './renderer/sprites.js';
import { renderCivs, renderCiv, techName } from './panels/civs.js';
import { renderCity, setTileRenderer } from './panels/city.js';
import { renderTech, resetTechLayout } from './panels/tech.js';
import { renderChart } from './panels/chart.js';
import { renderLog } from './panels/log.js';
import { renderTurn, setTurnMessages } from './panels/turn.js';
import { renderEmpire } from './panels/empire.js';
import { renderUnitBar } from './panels/unitbar.js';
import { initToasts, toast, clearToasts } from './toasts.js';
import {
  play, activate, endTurn, handleKey, clickTile, sendTo, hoverTile, queue, activeUnit, setMode,
  pendingDecisions, whyNotEnd,
} from './play.js';
import {
  initDialogs, openGameDialog, resetGameDialog, refreshSaves, setDialogStatus, showGameOver,
  openResearchDialog, openProposal, openWarConfirm, openDefeat,
} from './dialogs.js';

const $ = (id) => document.getElementById(id);
mountIcons();
const mapView = new MapView($('map'), $('tooltip'));
const minimap = new Minimap($('minimap'), mapView);
setOnLoad(() => {
  mapView.invalidate();
  if (activeTab === 'city') panels.city();
});
mapView.onViewChange = () => minimap.render();
setTileRenderer((...args) => mapView.drawTile(...args));
initDialogs();
initToasts($('toasts'));

const panels = {
  turn: () => renderTurn($('panel-turn')),
  civs: () => renderCivs($('panel-civs')),
  civ: () => (leader() !== null ? renderEmpire($('panel-civ')) : renderCiv($('panel-civ'))),
  city: () => renderCity($('panel-city')),
  tech: () => renderTech($('panel-tech')),
  chart: () => renderChart($('panel-chart')),
  log: () => renderLog($('panel-log')),
};
// Science and History take the whole width; the city opens a wide sheet beside the map.
const WORKSPACES = ['tech', 'chart'];
let activeTab = 'civs';
let mapTab = 'civs';         // the last tab that leaves the map in view
let gameOverSeen = null;     // "seed:turn" of the finished game already announced
let defeatSeen = null;       // seed of the game whose loss was already announced
const prompted = { turn: null, research: false, proposals: new Set() };   // asked this turn

function syncDock() {
  const dock = $('dock');
  const wide = activeTab === 'city' && store.selectedCity !== null;
  dock.classList.toggle('full', WORKSPACES.includes(activeTab));
  dock.classList.toggle('wide', wide);
  // The unit bar needs the width of the map: it steps aside for the city sheet.
  document.body.classList.toggle('sheet-open', wide || WORKSPACES.includes(activeTab));
}

function showTab(name) {
  activeTab = name;
  if (!WORKSPACES.includes(name)) mapTab = name;
  if (name !== 'log') mapView.setMarker(null);
  $('tooltip').hidden = true;
  document.querySelectorAll('#rail button').forEach((b) =>
    b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((p) =>
    p.classList.toggle('active', p.id === `panel-${name}`));
  syncDock();
  panels[name]();
}

function refreshActivePanel() {
  syncDock();
  panels[activeTab]();
}

function refreshClock() {
  const state = store.state;
  if (!state) return;
  const max = store.rules.max_turns;
  $('year').textContent = yearLabel(state.year);
  $('turn').innerHTML = `Turn ${state.turn} <span class="muted">of ${max}</span>`;
  $('turn-progress').style.width = `${Math.min(100, 100 * state.turn / max)}%`;
  $('seed-label').textContent = `seed ${state.seed}`;
  $('gameover-pill').hidden = !state.finished;
  if (state.finished && gameOverSeen !== `${state.seed}:${state.turn}`) {
    gameOverSeen = `${state.seed}:${state.turn}`;
    showGameOver();
  }
  // The state of the planet, once pollution has appeared.
  const world = [];
  if (state.polluted) world.push(`<b>${state.polluted}</b> polluted tile${state.polluted === 1 ? '' : 's'}`);
  if (state.warming && (state.warming.level || state.warming.count)) {
    world.push(`Global warming <b>${state.warming.level}/${state.warming.threshold}</b>`
      + (state.warming.count ? ` · ${state.warming.count} so far` : ''));
  }
  const ships = state.players.filter((p) => p.spaceship && p.spaceship.arrival_turn !== null
    && p.spaceship.arrival_turn > state.turn);
  for (const p of ships) {
    world.push(`${p.name} spaceship lands in <b>${p.spaceship.arrival_turn - state.turn} turns</b>`);
  }
  $('world').innerHTML = world.map((text) => `<span class="world-chip">${text}</span>`).join('');
}

let noticeTimer = null;
function showNotice({ text, ok }) {
  if ($('game-dialog').open) setDialogStatus(text, ok ? 'ok' : 'error');
  const notice = $('notice');
  notice.textContent = text;
  notice.className = ok ? '' : 'error';
  notice.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { notice.hidden = true; }, 4000);
}

function refreshPovList() {
  const select = $('pov');
  const current = store.state.pov;
  select.innerHTML = '<option value="">Everything</option>' + store.state.players
    .filter((p) => !p.barbarian)
    .map((p) => `<option value="${p.id}">${p.name}</option>`).join('');
  select.value = current === null ? '' : String(current);
}

function refreshLegend() {
  const legend = $('mission-legend');
  legend.hidden = !store.options.missions || leader() !== null;
  if (legend.hidden) return;
  const detail = store.playerDetail;
  const missions = detail && detail.id === store.selectedPlayer && detail.ai ? detail.ai.missions || [] : [];
  const kinds = [...new Set(missions.map((m) => m.kind))];
  legend.innerHTML = kinds.length
    ? `<b>AI missions · ${detail.nation}</b>` + kinds.map((kind) => `<span class="legend-item">
        <span class="ring" style="color:${MISSION_COLORS[kind] || '#fff'}"></span>${kind.replaceAll('_', ' ')}</span>`).join('')
    : '<b>AI missions</b><span>Select a civilization to see what its AI is doing.</span>';
}

function requestDetails() {
  // A person has its own affairs in every state; the observer asks for the civilization it picked.
  if (store.selectedPlayer !== null && leader() === null) send({ cmd: 'player', id: store.selectedPlayer });
  if (store.selectedCity !== null) send({ cmd: 'city', id: store.selectedCity });
}

// ── The person's side of the screen ─────────────────────────────────────────

// Observer or player: which controls show, and who the person is.
function syncMode() {
  const me = leader();
  document.body.classList.toggle('play', me !== null);
  const pill = $('mode-pill');
  if (me !== null) {
    const p = player(me);
    pill.innerHTML = `<span class="swatch small" style="background:${p.color}"></span>${p.nation}`;
  } else {
    pill.textContent = 'Observer';
  }
  document.title = me !== null ? `Civilization — ${player(me).nation}` : 'Civilization — observer';
}

function refreshPlayBar() {
  const me = store.state.me;
  if (leader() === null || !me) return;
  const gold = me.forecast.gold;
  const turns = me.researching
    ? turnsFor(me.research_cost + 1 - me.research_progress, me.forecast.science) : null;
  const progress = me.research_cost ? Math.min(100, 100 * me.research_progress / me.research_cost) : 0;
  const research = me.researching
    ? `<button class="chip-btn" data-chip="research" title="Research: ${me.research_progress} of ${me.research_cost}">
        <span class="sci">${icon('flask', 17)}</span><b>${techName(me.researching)}</b>
        <span class="bar thin"><span style="width:${progress}%;background:var(--sci)"></span></span>
        <span class="muted">${turns === null ? 'no science' : plural(turns, 'turn')}</span></button>`
    : `<button class="chip-btn lead" data-chip="research"><span>${icon('flask', 17)}</span><b>Choose research</b></button>`;
  $('empire-chips').innerHTML = `
    <button class="chip-btn" data-chip="empire" title="Treasury, and what the next turn should bring">
      <span class="trade">${icon('coin', 17)}</span><b class="num">${me.gold}</b><span class="muted">gold</span>
      <span class="${gold < 0 ? 'bad' : 'soft'}">${gold >= 0 ? '+' : ''}${gold}</span></button>
    ${research}
    <button class="chip-btn split" data-chip="empire" title="Share of trade going to taxes, luxuries and science">
      <span><i style="background:var(--trade)"></i><span class="muted">Tax</span><b>${me.rates[0]}</b></span>
      <span><i style="background:#C79BF2"></i><span class="muted">Lux</span><b>${me.rates[1]}</b></span>
      <span><i style="background:var(--sci)"></i><span class="muted">Sci</span><b>${me.rates[2]}</b></span></button>`;

  // What still asks for the person before the turn can end with a clear conscience.
  const left = queue().length;
  const pending = pendingDecisions();
  const button = $('btn-end-turn');
  const ready = !left && !pending && !play.waiting && !play.ending;
  const why = whyNotEnd();
  button.classList.toggle('primary', ready);
  button.disabled = play.waiting || play.ending;
  // Greyed out while a decision waits, but still hoverable: its tooltip says which one.
  button.setAttribute('aria-disabled', String(Boolean(why)));
  button.title = why || 'End your turn (Enter)';
  const status = $('turn-status');
  status.className = `turn-status play-only${ready ? ' ready' : ''}`;
  status.innerHTML = `<i></i>${play.waiting ? 'The others are playing…'
    : play.ending ? 'Ending the turn…'
      : left ? `${plural(left, 'unit')} waiting`
        : pending ? `${plural(pending, 'decision')} to make` : 'End the turn when ready'}`;
}

function refreshBanner() {
  const banner = $('map-banner');
  const unit = activeUnit();
  banner.hidden = play.mode !== 'goto' || !unit;
  if (banner.hidden) return;
  const name = store.unitDefs[unit[U.TYPE]].name;
  const preview = play.preview;
  let text = `<span class="muted">Click where the ${name} should go</span>`;
  if (preview && preview.kind === 'route') {
    text = `<span class="soft">${plural(preview.steps.length, 'tile')} · arrives in ${plural(preview.turns, 'turn')}</span>
      <span class="muted">Click to confirm</span>`;
  } else if (preview && preview.kind === 'no_route') {
    text = '<span class="bad">No known way there</span>';
  }
  banner.innerHTML = `<span class="gold">${icon('target', 17)}</span><b>Go to</b>${text}
    <button class="btn small" id="banner-cancel">Cancel<span class="kbd">Esc</span></button>`;
  $('banner-cancel').addEventListener('click', () => setMode(null));
}

// What the tooltip says about sending the active unit to the hovered tile.
function describeMove(tile) {
  if (play.mode === 'goto') return '';          // the banner says it all
  const preview = play.preview;
  if (!tile || !preview || preview.x !== tile.x || preview.y !== tile.y) return null;
  const where = `<span class="mono">${tile.x}, ${tile.y}</span>`;
  if (preview.kind === 'attack') {
    const foe = player(preview.defender_owner);
    const side = (color, who, base, factors, total) => `
      <div class="side"><span class="swatch small" style="background:${color}"></span>
        <span class="who"><b>${who}</b><small>${[base, ...factors].join(' · ')}</small></span><b class="total">${total}</b></div>`;
    const percent = Math.round(100 * preview.win);
    return `<div class="tip-title"><span class="bad">${icon('sword', 17, 2)}</span><span>Attack ${foe.name} ${preview.defender}</span>${where}</div>
      ${side(player(leader()).color, `Your ${preview.attacker}`, `attack ${preview.attack_base}`, preview.attack_factors, preview.attack)}
      ${side(foe.color, `${foe.name} ${preview.defender}${preview.stack > 1 ? ` · ${preview.stack} units here` : ''}`, `defence ${preview.defense_base}`, preview.defense_factors, preview.defense)}
      <div class="odds"><span class="between"><span class="soft">Chance to win</span><b class="${percent >= 50 ? 'good' : 'bad'}">${percent}%</b></span>
        <span class="bar thin"><span style="width:${percent}%;background:var(--good)"></span></span></div>
      <div class="tip-foot">${preview.reason ? `Cannot attack: ${preview.reason}` : 'Click the tile, or move onto it, to attack'}</div>`;
  }
  if (preview.kind === 'capture') {
    return `<div class="tip-title"><span>${preview.city}</span>${where}</div>
      <div class="tip-foot">Nobody defends it: move in to capture the city</div>`;
  }
  if (preview.kind === 'refused') {
    return `<div class="tip-title"><span>Cannot go there</span>${where}</div>
      <div class="tip-foot">${preview.reason[0].toUpperCase()}${preview.reason.slice(1)}</div>`;
  }
  return null;
}

// How loud an event is for the person: [tone, seconds on screen] or null to keep it quiet.
function loudness(event, me) {
  const mine = event.player === me;
  const against = event.other === me;
  switch (event.type) {
    case 'combat': return event.winner === me ? ['good', 6] : ['bad', 0];
    case 'city_captured': return mine ? ['good', 0] : ['bad', 0];
    case 'city_destroyed': case 'disorder': case 'famine': case 'disband': case 'unit_lost':
    case 'meltdown': case 'pollution': case 'barbarians': return ['bad', 0];
    case 'war': return mine || against ? ['bad', 0] : ['info', 0];
    case 'peace': case 'order': return ['good', 0];
    case 'sold': return ['info', 8];
    case 'wonder': return [mine ? 'good' : 'info', 0];
    case 'tech': return mine && event.how !== 'discover' ? ['good', 0] : null;
    case 'hut': case 'contact': case 'government': case 'trade_route': case 'civ_destroyed':
    case 'nuclear': case 'global_warming': case 'spaceship_launched': case 'spaceship_lost':
    case 'spaceship_part':
      return ['info', 0];
    default: return null;
  }
}

function announce(events, lasting) {
  const me = leader();
  for (const event of events) {
    const loud = loudness(event, me);
    if (!loud) continue;
    toast({ text: event.text, tone: loud[0], x: event.x, y: event.y, life: lasting ? loud[1] : loud[1] || 8 });
  }
}

// Start of the person's turn: what happened, then the questions waiting for an answer.
function openTurn(message) {
  const state = store.state;
  // What the order that ended the last turn by itself brought is told again: it had no time to be read.
  const carried = play.carry || [];
  play.carry = null;
  clearToasts();
  setTurnMessages([...carried, ...message.events]);
  for (const alert of state.alerts || []) toast({ text: alert.text, tone: 'bad', x: alert.x, y: alert.y });
  for (const note of state.notes || []) toast({ text: note.text, tone: 'info', x: note.x, y: note.y });
  announce(carried, true);
  announce(message.events, true);
  const found = message.events.find((e) => e.type === 'tech' && e.player === leader() && e.how === 'discover');
  prompted.discovered = found ? found.tech : null;
  ask();
}

// Asks the person the next question of the turn that has not been asked yet.
function ask() {
  const me = store.state.me;
  if (leader() === null || !me || document.querySelector('dialog[open]')) return;
  const key = `${store.state.seed}:${store.state.turn}`;
  if (prompted.turn !== key) {
    prompted.turn = key;
    prompted.research = false;
    prompted.proposals = new Set();
  }
  const proposal = me.proposals.find((id) => !prompted.proposals.has(id));
  if (proposal !== undefined) {
    prompted.proposals.add(proposal);
    openProposal(proposal);
  } else if (me.researching === null && me.research_options.length && !prompted.research) {
    prompted.research = true;
    openResearchDialog(prompted.discovered);
  }
}

function refreshPlay() {
  refreshPlayBar();
  refreshBanner();
  renderUnitBar($('unit-bar'));
  if (activeTab === 'turn') panels.turn();
  mapView.invalidate();
}

// ── Server events ───────────────────────────────────────────────────────────

on('init', () => {
  preload(store.rules);
  resetTechLayout();
  resetGameDialog();
  // Questions and verdicts of the game that was on screen do not belong to this one.
  for (const id of ['research-dialog', 'message-dialog', 'gameover']) {
    if ($(id).open) $(id).close();
  }
  gameOverSeen = null;
  mapView.setMarker(null);
  clearToasts();
  setTurnMessages([]);
  syncMode();
  $('world-size').textContent = `${store.map.width} × ${store.map.height}`;
  refreshPovList();
  refreshClock();
  mapView.fitWorld();
  const me = leader();
  // Start on the person's land, or the first civilization's, rather than on the open sea.
  const first = store.state.units.find((unit) => me === null || unit[U.OWNER] === me) || store.state.units[0];
  mapView.tile = Math.max(mapView.tile, me !== null ? 56 : 28);
  if (first) mapView.centerOn(first[3], first[4]);
  mapView.invalidate();
  minimap.render();
  refreshLegend();
  requestDetails();
  if (me !== null) showTab('turn');
  else if (activeTab === 'turn') showTab('civs');
  else refreshActivePanel();
  refreshPlay();

  const led = store.state.play;
  if (me !== null) {
    openTurn({ events: [] });
  } else if (led && !store.state.finished && !player(led.human).alive && defeatSeen !== store.state.seed) {
    defeatSeen = store.state.seed;
    openDefeat();
  }
});

on('turn', (message) => {
  refreshClock();
  mapView.slide(store.moves, 420);
  mapView.invalidate();
  minimap.render();
  if (store.selectedCity !== null && !store.state.cities.some((c) => c.id === store.selectedCity)) {
    store.selectedCity = null;
    store.cityDetail = null;
  }
  requestDetails();
  refreshActivePanel();
  if (leader() !== null) {
    refreshPlay();
    openTurn(message);
  }
});

on('update', (message) => {
  refreshClock();
  mapView.slide(store.moves);
  minimap.render();
  announce(message.events, false);
  if (store.selectedCity !== null && !store.state.cities.some((c) => c.id === store.selectedCity)) {
    store.selectedCity = null;
    store.cityDetail = null;
  } else if (store.selectedCity !== null && message.city !== store.selectedCity) {
    send({ cmd: 'city', id: store.selectedCity });
  }
  refreshActivePanel();
  refreshPlay();
});

on('state', () => {
  refreshClock();
  mapView.invalidate();
  minimap.render();
  refreshActivePanel();
});

on('status', () => {
  $('play-icon').innerHTML = icon(store.playing ? 'pause' : 'play', 18, 2.4);
  $('play-label').textContent = store.playing ? 'Pause' : 'Play';
  // Light the speed that is the closest to the server's delay.
  const buttons = [...document.querySelectorAll('#speed button')];
  const nearest = buttons.reduce((a, b) =>
    (Math.abs(Number(b.dataset.delay) - store.delay) < Math.abs(Number(a.dataset.delay) - store.delay) ? b : a));
  buttons.forEach((b) => b.setAttribute('aria-pressed', String(b === nearest)));
});

on('saves', refreshSaves);
on('notice', showNotice);

on('city', () => {
  mapView.invalidate();
  if (activeTab === 'city') refreshActivePanel();
});

on('player', () => {
  if (store.options.missions) mapView.invalidate();
  refreshLegend();
  if (activeTab === 'civ' || activeTab === 'tech') refreshActivePanel();
});

on('play', refreshPlay);
on('play-preview', () => {
  refreshBanner();
  mapView.invalidate();
  mapView.refreshTip();
});

// ── Selections and requests from the panels ─────────────────────────────────

on('select-player', (id) => {
  store.selectedPlayer = id;
  if (leader() === null) send({ cmd: 'player', id });
  else if (id === leader()) store.playerDetail = store.state.me;
  if (activeTab === 'civs' || activeTab === 'city' || activeTab === 'turn') showTab('civ');
  else refreshActivePanel();
});

on('select-city', (id) => {
  store.selectedCity = id;
  const city = store.state.cities.find((c) => c.id === id);
  if (city && leader() === null) {
    store.selectedPlayer = city.owner;
    send({ cmd: 'player', id: city.owner });
  }
  send({ cmd: 'city', id });
  showTab('city');
});

on('close-city', () => {
  store.selectedCity = null;
  store.cityDetail = null;
  mapView.invalidate();
  showTab(leader() !== null ? 'turn' : store.selectedPlayer !== null ? 'civ' : 'civs');
});

on('center', ({ x, y }) => mapView.centerOn(x, y));
on('focus', ({ x, y }) => mapView.reveal(x, y));
on('locate', ({ x, y }) => {
  if (WORKSPACES.includes(activeTab) || (activeTab === 'city' && store.selectedCity !== null)) showTab(mapTab === 'city' ? 'turn' : mapTab);
  mapView.centerOn(x, y);
  mapView.setMarker({ x, y });
});
on('show-tab', showTab);
on('back-to-map', () => showTab(mapTab));
on('open-research', () => openResearchDialog());
on('open-proposal', openProposal);
on('confirm-war', openWarConfirm);
on('activate-unit', (id) => {
  emit('close-city');
  activate(id);
});

// ── Controls ────────────────────────────────────────────────────────────────

document.querySelectorAll('#rail button').forEach((button) => {
  button.addEventListener('click', () => showTab(button.dataset.tab));
});

$('btn-play').addEventListener('click', () => send({ cmd: store.playing ? 'pause' : 'play' }));
$('btn-step').addEventListener('click', () => send({ cmd: 'step' }));
document.querySelectorAll('#speed button').forEach((button) => {
  button.addEventListener('click', () => send({ cmd: 'speed', delay: Number(button.dataset.delay) }));
});
$('pov').addEventListener('change', (e) => {
  send({ cmd: 'pov', player: e.target.value === '' ? null : Number(e.target.value) });
});
$('btn-new').addEventListener('click', () => openGameDialog('seed'));
$('btn-save').addEventListener('click', () => openGameDialog('save'));
$('btn-saves').addEventListener('click', () => openGameDialog('save'));
$('btn-game').addEventListener('click', () => openGameDialog('save'));
$('gameover-pill').addEventListener('click', showGameOver);
$('btn-end-turn').addEventListener('click', endTurn);
$('empire-chips').addEventListener('click', (e) => {
  const chip = e.target.closest('[data-chip]');
  if (!chip) return;
  if (chip.dataset.chip === 'research') openResearchDialog();
  else emit('select-player', leader());
});
for (const id of ['research-dialog', 'message-dialog']) {
  $(id).addEventListener('close', () => setTimeout(ask, 0));
}

document.querySelectorAll('.toggle').forEach((button) => {
  button.addEventListener('click', () => {
    const option = button.dataset.option;
    store.options[option] = !store.options[option];
    button.setAttribute('aria-pressed', String(store.options[option]));
    refreshLegend();
    mapView.invalidate();
  });
});
$('zoom-in').addEventListener('click', () => mapView.zoomBy(1.25));
$('zoom-out').addEventListener('click', () => mapView.zoomBy(1 / 1.25));
$('zoom-fit').addEventListener('click', () => {
  mapView.fitWorld();
  minimap.render();
});

// The person's orders on the map.
mapView.onTileClick = clickTile;
mapView.onTileContext = (tile) => {
  if (leader() === null) return false;
  sendTo(tile);
  return true;                     // no browser menu over the map while playing
};
mapView.onTileHover = hoverTile;
mapView.describeMove = describeMove;

window.addEventListener('keydown', (e) => {
  if (document.querySelector('dialog[open]')) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.key === 'Escape' && !play.mode) {
    if (WORKSPACES.includes(activeTab)) showTab(mapTab);
    else if (activeTab === 'city' && store.selectedCity !== null) emit('close-city');
    return;
  }
  if (leader() !== null) {
    if (handleKey(e)) e.preventDefault();
    return;
  }
  if (e.code === 'Space') {
    e.preventDefault();
    send({ cmd: store.playing ? 'pause' : 'play' });
  } else if (e.key === 'n' || e.key === 'N') {
    send({ cmd: 'step' });
  }
});

// A button clicked with the mouse does not keep the keyboard: the keys stay the game's.
document.addEventListener('click', (e) => {
  const button = e.target.closest('button');
  if (button && e.detail > 0 && !button.closest('dialog')) button.blur();
});

connect(handleMessage, (online) => {
  $('connection').className = `status ${online ? 'on' : 'off'}`;
  $('connection-label').textContent = online ? 'Live' : 'Offline';
});
