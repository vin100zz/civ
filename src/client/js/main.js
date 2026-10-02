// Wires everything together: connection, map, panels, the top bar and the dialogs.

import { connect, send } from './net.js';
import { store, on, emit, handleMessage, yearLabel } from './state.js';
import { icon, mountIcons } from './icons.js';
import { MapView, MISSION_COLORS } from './renderer/map.js';
import { Minimap } from './renderer/minimap.js';
import { preload, setOnLoad } from './renderer/sprites.js';
import { renderCivs, renderCiv } from './panels/civs.js';
import { renderCity, setTileRenderer } from './panels/city.js';
import { renderTech, resetTechLayout } from './panels/tech.js';
import { renderChart } from './panels/chart.js';
import { renderLog } from './panels/log.js';
import {
  initDialogs, openGameDialog, resetGameDialog, refreshSaves, setDialogStatus, showGameOver,
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

const panels = {
  civs: () => renderCivs($('panel-civs')),
  civ: () => renderCiv($('panel-civ')),
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

function syncDock() {
  const dock = $('dock');
  dock.classList.toggle('full', WORKSPACES.includes(activeTab));
  dock.classList.toggle('wide', activeTab === 'city' && store.selectedCity !== null);
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
  legend.hidden = !store.options.missions;
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
  if (store.selectedPlayer !== null) send({ cmd: 'player', id: store.selectedPlayer });
  if (store.selectedCity !== null) send({ cmd: 'city', id: store.selectedCity });
}

// ── Server events ───────────────────────────────────────────────────────────

on('init', () => {
  preload(store.rules);
  resetTechLayout();
  resetGameDialog();
  gameOverSeen = null;
  mapView.setMarker(null);
  $('world-size').textContent = `${store.map.width} × ${store.map.height}`;
  refreshPovList();
  refreshClock();
  mapView.fitWorld();
  // Start on the first civilization's land rather than on the middle of the ocean.
  const first = store.state.units[0];
  if (first) mapView.centerOn(first[3], first[4]);
  mapView.tile = Math.max(mapView.tile, 28);
  mapView.invalidate();
  minimap.render();
  refreshLegend();
  requestDetails();
  refreshActivePanel();
});

on('turn', () => {
  refreshClock();
  mapView.invalidate();
  minimap.render();
  if (store.selectedCity !== null && !store.state.cities.some((c) => c.id === store.selectedCity)) {
    store.selectedCity = null;
    store.cityDetail = null;
  }
  requestDetails();
  refreshActivePanel();
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

// ── Selections and requests from the panels ─────────────────────────────────

on('select-player', (id) => {
  store.selectedPlayer = id;
  send({ cmd: 'player', id });
  if (activeTab === 'civs' || activeTab === 'city') showTab('civ');
  else refreshActivePanel();
});

on('select-city', (id) => {
  store.selectedCity = id;
  const city = store.state.cities.find((c) => c.id === id);
  if (city) {
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
  showTab(store.selectedPlayer !== null ? 'civ' : 'civs');
});

on('center', ({ x, y }) => mapView.centerOn(x, y));
on('locate', ({ x, y }) => {
  mapView.centerOn(x, y);
  mapView.setMarker({ x, y });
});
on('show-tab', showTab);
on('back-to-map', () => showTab(mapTab));

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
$('gameover-pill').addEventListener('click', showGameOver);

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

window.addEventListener('keydown', (e) => {
  if (document.querySelector('dialog[open]')) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.code === 'Space') {
    e.preventDefault();
    send({ cmd: store.playing ? 'pause' : 'play' });
  } else if (e.key === 'n' || e.key === 'N') {
    send({ cmd: 'step' });
  } else if (e.key === 'Escape') {
    if (WORKSPACES.includes(activeTab)) showTab(mapTab);
    else if (activeTab === 'city' && store.selectedCity !== null) emit('close-city');
  }
});

connect(handleMessage, (online) => {
  $('connection').className = `status ${online ? 'on' : 'off'}`;
  $('connection-label').textContent = online ? 'Live' : 'Offline';
});
