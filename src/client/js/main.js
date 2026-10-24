// Wires everything together: connection, map, panels, the top bar and the dialogs, for the
// observer and for the person leading a civilization.

import { connect, send } from './net.js';
import { store, on, emit, yearLabel, leader, player, plural, turnsFor, U } from './state.js';
import { initReplay, receive, replaying, settling, skipReplay } from './replay.js';
import { icon, mountIcons } from './icons.js';
import { MapView, MISSION_COLORS } from './renderer/map.js';
import { Minimap } from './renderer/minimap.js';
import { preload, setOnLoad } from './renderer/sprites.js';
import { renderCivs, renderCiv, techName, governmentName } from './panels/civs.js';
import { renderCity, setTileRenderer } from './panels/city.js';
import { renderTech, resetTechLayout } from './panels/tech.js';
import { renderChart } from './panels/chart.js';
import { renderReplay, receiveReplay, resetReplay, replayKey, playFromStart } from './panels/replay.js';
import { renderLog } from './panels/log.js';
import { renderTurn } from './panels/turn.js';
import { renderCities } from './panels/cities.js';
import { renderWonders } from './panels/wonders.js';
import { renderSpace, spaceBadge } from './panels/space.js';
import { renderEmpire } from './panels/empire.js';
import { renderUnitBar } from './panels/unitbar.js';
import { initToasts, toast, clearToasts } from './toasts.js';
import { hideTips, setTips, initHints } from './tips.js';
import {
  play, activate, endTurn, handleKey, clickTile, aimAt, releaseAt, hoverTile, queue, activeUnit, setMode,
  pendingDecisions, whyNotEnd,
} from './play.js';
import {
  initDialogs, openGameDialog, resetGameDialog, refreshSaves, setDialogStatus, showGameOver,
  openResearchDialog, openProposal, openWarConfirm, openDefeat,
} from './dialogs.js';

const $ = (id) => document.getElementById(id);
mountIcons();
initHints();
const mapView = new MapView($('map'), $('tooltip'));
const minimap = new Minimap($('minimap'), mapView);
// A sprite has loaded, or a unit picture of the panels is ready (several at once: one redraw).
let picturesDue = false;
setOnLoad(() => {
  mapView.invalidate();
  if (picturesDue) return;
  picturesDue = true;
  requestAnimationFrame(() => {
    picturesDue = false;
    if (['turn', 'cities', 'tech'].includes(activeTab)) panels[activeTab]();
    refreshCity();
    renderUnitBar($('unit-bar'));
  });
});
mapView.onViewChange = () => minimap.render();
setTileRenderer((...args) => mapView.drawTile(...args));
initDialogs();
initToasts($('toasts'));

const panels = {
  turn: () => renderTurn($('panel-turn')),
  civs: () => renderCivs($('panel-civs')),
  civ: () => (leader() !== null ? renderEmpire($('panel-civ')) : renderCiv($('panel-civ'))),
  cities: () => renderCities($('panel-cities')),
  wonders: () => renderWonders($('panel-wonders')),
  space: () => renderSpace($('panel-space')),
  tech: () => renderTech($('panel-tech')),
  chart: () => renderChart($('panel-chart')),
  replay: () => renderReplay($('panel-replay')),
  log: () => renderLog($('panel-log')),
};
// Science, History and Replay take the whole width; a city opens in a window over the map.
const WORKSPACES = ['tech', 'chart', 'replay'];
let activeTab = 'civs';
let mapTab = 'civs';         // the last tab that leaves the map in view
let gameOverSeen = null;     // "seed:turn" of the finished game already announced
let defeatSeen = null;       // seed of the game whose loss was already announced
const prompted = { turn: null, research: false, proposals: new Set() };   // asked this turn
initReplay(mapView, () => WORKSPACES.includes(activeTab));

function syncDock() {
  $('dock').classList.toggle('full', WORKSPACES.includes(activeTab));
  document.body.classList.toggle('sheet-open', WORKSPACES.includes(activeTab));
}

// The window of the selected city, over the map. Until the city asked for comes, it keeps
// showing the previous one, or stays invisible if it was closed (its width is already known).
function refreshCity() {
  const sheet = $('panel-city');
  const id = store.selectedCity;
  sheet.hidden = id === null;
  if (id === null) {
    sheet.innerHTML = '';
  } else if (store.cityDetail && store.cityDetail.id === id) {
    sheet.classList.remove('waiting');
    renderCity(sheet);
  } else if (!sheet.innerHTML) {
    sheet.classList.add('waiting');
  }
  fitInset();
}

// The map centres what it shows in the part the city window leaves free.
function fitInset() {
  mapView.inset = store.selectedCity === null ? 0 : $('panel-city').offsetWidth + 12;
}
new ResizeObserver(fitInset).observe($('panel-city'));

function showTab(name) {
  activeTab = name;
  if (!WORKSPACES.includes(name)) mapTab = name;
  if (name !== 'log') mapView.setMarker(null);
  $('tooltip').hidden = true;
  hideTips();
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
  refreshCity();
}

function refreshClock() {
  const state = store.state;
  if (!state) return;
  const max = store.rules.max_turns;
  $('year').textContent = yearLabel(state.year);
  $('turn').innerHTML = `Turn ${state.turn} <span class="muted">of ${max}</span>`;
  $('turn-progress').style.width = `${Math.min(100, 100 * state.turn / max)}%`;
  $('gameover-pill').hidden = !state.finished;
  if (state.finished && gameOverSeen !== `${state.seed}:${state.turn}`) {
    gameOverSeen = `${state.seed}:${state.turn}`;
    showGameOver();
  }
  refreshPlanet();
  refreshSpaceBadge();
}

// On the Space button of the rail: the turns before the first spaceship in flight lands,
// in red when it is a rival's.
function refreshSpaceBadge() {
  const badge = spaceBadge();
  const element = $('space-badge');
  element.hidden = !badge;
  if (!badge) return;
  element.textContent = badge.turns;
  element.classList.toggle('rival', badge.rival);
}

// The state of the planet in the top bar, once pollution has appeared: polluted tiles, a gauge of
// the warming, the spaceships in flight. Its tooltip names each figure.
function refreshPlanet() {
  const state = store.state;
  const warming = state.warming && (state.warming.level || state.warming.count) ? state.warming : null;
  const ships = state.players.filter((p) => p.spaceship && p.spaceship.arrival_turn !== null
    && p.spaceship.arrival_turn > state.turn);
  const parts = [];
  const tip = [];
  const row = (name, label, value) => tip.push(`<span data-i>${icon(name, 15)}</span><span>${label}</span><b>${value}</b>`);
  if (state.polluted) {
    parts.push(`<span>${icon('cloud', 17)}<b>${state.polluted}</b></span>`);
    row('cloud', 'Pollution', plural(state.polluted, 'tile'));
  }
  if (warming) {
    const share = Math.min(1, warming.level / warming.threshold);
    parts.push(`<span><span class="thermo">${icon('thermo', 17)}</span>`
      + `<span class="bar"><span style="width:${Math.max(4, 100 * share)}%"></span></span></span>`);
    row('thermo', 'Global warming', `${warming.level} / ${warming.threshold}`);
  }
  for (const p of ships) {
    const turns = p.spaceship.arrival_turn - state.turn;
    parts.push(`<span>${icon('rocket', 17)}<b>${turns}</b></span>`);
    row('rocket', `${p.name} spaceship`, plural(turns, 'turn'));
  }
  $('planet').hidden = !parts.length;
  const level = warming ? warming.level / warming.threshold : 0;
  const chip = $('planet');
  chip.className = `chip-btn planet${level >= 0.75 ? ' warm-2' : level >= 0.5 ? ' warm-1' : ''}`;
  chip.innerHTML = parts.join('<i class="sep"></i>');
  setTips($('topbar'), new Map([['planet', `<div class="tip-planet">${tip.join('')}</div>`]]));
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

// Observer or player: which controls show.
function syncMode() {
  document.body.classList.toggle('play', leader() !== null);
}

function refreshPlayBar() {
  const me = store.state.me;
  if (leader() === null || !me) return;
  const gold = me.forecast.gold;
  // A building is about to be sold for want of gold (human/report.py).
  const treasury = (store.state.alerts || []).find((alert) => alert.kind === 'treasury');
  const turns = me.researching
    ? turnsFor(me.research_cost + 1 - me.research_progress, me.forecast.science) : null;
  const progress = me.research_cost ? Math.min(100, 100 * me.research_progress / me.research_cost) : 0;
  const research = me.researching
    ? `<button class="chip-btn" data-chip="research" data-hint="Research">
        <span class="sci">${icon('flask', 17)}</span><b>${techName(me.researching)}</b>
        <span class="bar thin"><span style="width:${progress}%;background:var(--sci)"></span></span>
        <span class="muted">${turns === null ? 'no science' : plural(turns, 'turn')}</span>${
  me.research_goal ? `<span class="goal">${icon('flag', 14, 2)}${techName(me.research_goal)}</span>` : ''}</button>`
    : `<button class="chip-btn lead" data-chip="research" data-hint="Research"><span>${icon('flask', 17)}</span><b>Choose research</b></button>`;
  // A revolution lasts until the start of turn `anarchy_until`.
  const anarchy = me.government === 'anarchy';
  const turnsLeft = anarchy && me.anarchy_until ? me.anarchy_until - store.state.turn : 0;
  $('empire-chips').innerHTML = `
    <button class="chip-btn${anarchy ? ' anarchy' : ''}" data-chip="empire" data-hint="Government">
      <span>${icon('crown', 17)}</span><b>${governmentName(me.government)}</b>${turnsLeft > 0 ? `<span>${plural(turnsLeft, 'turn')}</span>` : ''}</button>
    <button class="chip-btn${treasury ? ` alarm ${treasury.level}` : ''}" data-chip="empire" data-hint="Treasury">
      <span class="trade">${icon(treasury ? 'alert' : 'coin', 17)}</span><b class="num">${me.gold}</b><span class="muted">gold</span>
      <span class="${gold < 0 ? 'bad' : 'soft'}">${gold >= 0 ? '+' : ''}${gold}</span></button>
    ${research}
    <button class="chip-btn split" data-chip="empire" data-hint="Tax rates">
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
  // Greyed out while a decision waits, but still hoverable: its hint says which one.
  button.setAttribute('aria-disabled', String(Boolean(why)));
  button.dataset.hint = why || 'End your turn';
  button.dataset.key = why ? '' : 'Enter';
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
    case 'disorder': case 'famine': case 'disband': case 'unit_lost': case 'pollution':
      return mine ? ['bad', 0] : null;          // the misfortunes of others seen in passing
    case 'city_destroyed': case 'meltdown': return mine ? ['bad', 0] : ['info', 0];
    case 'barbarians': return ['bad', 0];
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
  for (const alert of state.alerts || []) {
    toast({ text: alert.text, detail: alert.detail || '', tone: 'bad', x: alert.x, y: alert.y });
  }
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
  if (activeTab === 'turn' || activeTab === 'cities') panels[activeTab]();
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
  resetReplay();
  mapView.setMarker(null);
  clearToasts();
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
  refreshCity();
  if (me !== null) showTab('turn');
  else if (activeTab === 'turn' || activeTab === 'cities') showTab('civs');
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
  mapView.slide(store.moves, 420, false);
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
on('replay', receiveReplay);

on('city', () => {
  mapView.invalidate();
  refreshCity();
});

on('player', () => {
  if (store.options.missions) mapView.invalidate();
  refreshLegend();
  if (activeTab === 'civ' || activeTab === 'tech') refreshActivePanel();
});

on('play', refreshPlay);
// The turn is over: what was opened during it closes, the next one starts on the Turn panel.
on('turn-ended', () => {
  showMapOptions(false);
  if (store.selectedCity !== null) emit('close-city');
  showTab('turn');
});
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
  if (activeTab === 'civs' || activeTab === 'turn') showTab('civ');
  else refreshActivePanel();
});

on('select-city', (id) => {
  if (store.selectedCity === null) mapView.holdView();   // given back when the window closes
  store.selectedCity = id;
  const city = store.state.cities.find((c) => c.id === id);
  if (city && leader() === null) {
    store.selectedPlayer = city.owner;
    send({ cmd: 'player', id: city.owner });
  }
  send({ cmd: 'city', id });
  if (WORKSPACES.includes(activeTab)) showTab(mapTab);
  refreshActivePanel();        // the window, and the row of the city in the lists
  // A city clicked where the window now lies moves into the free part of the map.
  if (city) mapView.bring(city.x, city.y);
  mapView.invalidate();
});

on('close-city', () => {
  store.selectedCity = null;
  store.cityDetail = null;
  hideTips();
  refreshActivePanel();
  mapView.restoreView();
  mapView.invalidate();
});

on('center', ({ x, y }) => mapView.centerOn(x, y));
on('focus', ({ x, y }) => mapView.reveal(x, y));
on('locate', ({ x, y }) => {
  if (WORKSPACES.includes(activeTab)) showTab(mapTab);
  mapView.centerOn(x, y);
  mapView.setMarker({ x, y });
});
on('show-tab', showTab);
on('back-to-map', () => showTab(mapTab));
on('play-replay', () => {
  playFromStart();
  showTab('replay');
});
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

// The map layers, in a panel under the gear of the top bar.
function showMapOptions(open) {
  const panel = $('map-options');
  const button = $('btn-options');
  if (open) {
    const rect = button.getBoundingClientRect();
    panel.style.top = `${rect.bottom + 10}px`;
    panel.style.left = `${Math.max(8, rect.left - 6)}px`;
  } else if (panel.contains(document.activeElement)) {
    document.activeElement.blur();        // the keys go back to the game
  }
  panel.hidden = !open;
  button.setAttribute('aria-expanded', String(open));
}
$('btn-options').addEventListener('click', () => showMapOptions($('map-options').hidden));
$('map-options').addEventListener('change', (e) => {
  const option = e.target.dataset.option;
  if (!option) return;
  store.options[option] = e.target.checked;
  refreshLegend();
  mapView.invalidate();
});
// A click elsewhere closes the panel; on the map it does nothing more (no unit moves by mistake).
window.addEventListener('mousedown', (e) => {
  if ($('map-options').hidden || e.target.closest('#map-options, #btn-options')) return;
  showMapOptions(false);
  if (e.target === $('map')) e.stopPropagation();
}, true);
window.addEventListener('resize', () => showMapOptions(false));
$('zoom-in').addEventListener('click', () => mapView.zoomBy(1.25));
$('zoom-out').addEventListener('click', () => mapView.zoomBy(1 / 1.25));
$('zoom-fit').addEventListener('click', () => {
  mapView.fitWorld();
  minimap.render();
});

// The person's orders on the map.
mapView.onTileClick = clickTile;
mapView.onTileContext = () => leader() !== null;     // no browser menu over the map while playing
mapView.onAimStart = aimAt;
mapView.onAimEnd = releaseAt;
mapView.onTileHover = hoverTile;
mapView.describeMove = describeMove;

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('map-options').hidden) {
    showMapOptions(false);
    e.preventDefault();
    return;
  }
  if (document.querySelector('dialog[open]')) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (replaying()) {
    // The others are moving: these keys go straight to the person's turn.
    if (['Escape', 'Enter', ' '].includes(e.key)) skipReplay();
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape' && !play.mode) {
    if (WORKSPACES.includes(activeTab)) showTab(mapTab);
    else if (store.selectedCity !== null) emit('close-city');
    return;
  }
  if (activeTab === 'replay' && replayKey(e)) {
    e.preventDefault();
    return;
  }
  if (leader() !== null) {
    // No orders while a fight is being settled, nor while the camera is still on the last
    // move: the unit they would go to is not in view yet.
    if (settling() || mapView.lagging || handleKey(e)) e.preventDefault();
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

// The top bar only speaks of the connection once it is lost.
connect(receive, (online) => {
  $('connection').hidden = online;
});
