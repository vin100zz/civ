// Wires everything together: connection, map, panels and the top bar.

import { connect, send } from './net.js';
import { store, on, handleMessage, yearLabel, player } from './state.js';
import { MapView } from './renderer/map.js';
import { Minimap } from './renderer/minimap.js';
import { preload, setOnLoad } from './renderer/sprites.js';
import { renderCivs, renderCiv } from './panels/civs.js';
import { renderCity } from './panels/city.js';
import { renderTech, resetTechLayout } from './panels/tech.js';
import { renderChart } from './panels/chart.js';
import { renderLog } from './panels/log.js';

const $ = (id) => document.getElementById(id);
const mapView = new MapView($('map'), $('tooltip'));
const minimap = new Minimap($('minimap'), mapView);
setOnLoad(() => mapView.invalidate());
mapView.onViewChange = () => minimap.render();

const panels = {
  civs: () => renderCivs($('panel-civs')),
  civ: () => renderCiv($('panel-civ')),
  city: () => renderCity($('panel-city')),
  tech: () => renderTech($('panel-tech')),
  chart: () => renderChart($('panel-chart')),
  log: () => renderLog($('panel-log')),
};
let activeTab = 'civs';

function showTab(name) {
  activeTab = name;
  document.querySelectorAll('#tabs button').forEach((b) =>
    b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((p) =>
    p.classList.toggle('active', p.id === `panel-${name}`));
  panels[name]();
}

function refreshActivePanel() {
  panels[activeTab]();
}

function refreshClock() {
  const state = store.state;
  if (!state) return;
  $('year').textContent = yearLabel(state.year);
  $('turn').textContent = `turn ${state.turn} · seed ${state.seed}`;
  const banner = $('banner');
  if (state.finished) {
    const winner = state.winner !== null ? player(state.winner) : null;
    const how = {
      conquest: 'conquer the world', spaceship: 'reach Alpha Centauri',
      score: 'have the greatest civilization',
    }[state.victory] || 'win';
    banner.textContent = winner ? `Game over — the ${winner.nation} ${how}.` : 'Game over.';
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }
  // The state of the planet, once pollution has appeared.
  const world = [];
  if (state.polluted) world.push(`☣ ${state.polluted} polluted`);
  if (state.warming && (state.warming.level || state.warming.count)) {
    world.push(`🌡 warming ${state.warming.level}/${state.warming.threshold}`
      + (state.warming.count ? ` (${state.warming.count} so far)` : ''));
  }
  const ships = state.players.filter((p) => p.spaceship && p.spaceship.arrival_turn !== null);
  for (const p of ships) {
    world.push(`🚀 ${p.name}: ${Math.max(0, p.spaceship.arrival_turn - state.turn)} turns`);
  }
  $('world').textContent = world.join(' · ');
}

function refreshSaves() {
  const select = $('saves');
  const current = select.value;
  select.innerHTML = '<option value="">Saved games…</option>'
    + store.saves.map((name) => `<option value="${name}">${name}</option>`).join('');
  if (store.saves.includes(current)) select.value = current;
}

let noticeTimer = null;
function showNotice({ text, ok }) {
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

function requestDetails() {
  if (store.selectedPlayer !== null) send({ cmd: 'player', id: store.selectedPlayer });
  if (store.selectedCity !== null) send({ cmd: 'city', id: store.selectedCity });
}

// ── Server events ───────────────────────────────────────────────────────────

on('init', () => {
  preload(store.rules);
  resetTechLayout();
  $('players').value = store.state.players.filter((p) => !p.barbarian).length;
  $('players').max = store.rules.defaults.max_players;
  refreshPovList();
  refreshSaves();
  refreshClock();
  mapView.fitWorld();
  // Start on the first civilization's land rather than on the middle of the ocean.
  const first = store.state.units[0];
  if (first) mapView.centerOn(first[3], first[4]);
  mapView.tile = Math.max(mapView.tile, 28);
  mapView.invalidate();
  minimap.render();
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
  const button = $('btn-play');
  button.textContent = store.playing ? '⏸ Pause' : '▶ Play';
  button.classList.toggle('playing', store.playing);
});

on('saves', refreshSaves);
on('notice', showNotice);

on('city', () => {
  mapView.invalidate();
  if (activeTab === 'city') renderCity($('panel-city'));
});

on('player', () => {
  if (store.options.missions) mapView.invalidate();
  if (activeTab === 'civ' || activeTab === 'tech') refreshActivePanel();
});

// ── Selections ──────────────────────────────────────────────────────────────

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

on('center', ({ x, y }) => mapView.centerOn(x, y));

// ── Controls ────────────────────────────────────────────────────────────────

document.querySelectorAll('#tabs button').forEach((button) => {
  button.addEventListener('click', () => showTab(button.dataset.tab));
});

$('btn-play').addEventListener('click', () => send({ cmd: store.playing ? 'pause' : 'play' }));
$('btn-step').addEventListener('click', () => send({ cmd: 'step' }));
$('speed').addEventListener('change', (e) => send({ cmd: 'speed', delay: Number(e.target.value) }));
$('pov').addEventListener('change', (e) => {
  send({ cmd: 'pov', player: e.target.value === '' ? null : Number(e.target.value) });
});
$('btn-new').addEventListener('click', () => {
  const seed = parseInt($('seed').value, 10);
  const players = parseInt($('players').value, 10);
  send({ cmd: 'new_game', seed: Number.isFinite(seed) ? seed : null,
         players: Number.isFinite(players) ? players : null });
});
$('btn-save').addEventListener('click', () => {
  if (!store.state) return;
  const suggestion = `seed${store.state.seed}-turn${store.state.turn}`;
  const name = window.prompt('Name of the saved game (letters, digits, - and _):', suggestion);
  if (name) send({ cmd: 'save', name: name.trim() });
});
$('btn-load').addEventListener('click', () => {
  const name = $('saves').value;
  if (name) send({ cmd: 'load', name });
  else showNotice({ text: 'Choose a saved game in the list first.', ok: false });
});
for (const [id, option] of [['opt-territory', 'territory'], ['opt-grid', 'grid'], ['opt-missions', 'missions']]) {
  $(id).addEventListener('change', (e) => {
    store.options[option] = e.target.checked;
    mapView.invalidate();
  });
}

window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.code === 'Space') {
    e.preventDefault();
    send({ cmd: store.playing ? 'pause' : 'play' });
  } else if (e.key === 'n' || e.key === 'N') {
    send({ cmd: 'step' });
  }
});

connect(handleMessage, (online) => {
  $('connection').className = `dot ${online ? 'on' : 'off'}`;
});
