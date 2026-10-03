// The "Game" dialog (new game, saved games) and the end-of-game screen.

import { send } from './net.js';
import { store, emit, player, yearLabel, inkOn, swatch } from './state.js';
import { icon } from './icons.js';
import { governmentName } from './panels/civs.js';

const $ = (id) => document.getElementById(id);
const VICTORY = {
  conquest: ['Conquest victory', 'conquer the world', 'sword'],
  spaceship: ['Spaceship victory', 'reach Alpha Centauri', 'rocket'],
  score: ['Victory on score', 'have the greatest civilization', 'trophy'],
};
let players = 7;
let mapChoice = null;         // shape, relief and climate of the next new game

// Pictogram of each map shape: [cx, cy, rx, ry] blobs in a 36 x 22 box. A blob drawn inside
// another one is a hole (a lake, an inner sea).
const SHAPE_GLYPHS = {
  continents: [[9, 8, 7, 5], [26, 14, 8, 6], [21, 4, 2.5, 2], [6, 18, 2, 1.5]],
  small_islands: [[5, 5, 2, 2], [15, 4, 2, 2], [27, 5, 2, 2], [9, 12, 2, 2], [20, 11, 2, 2],
    [31, 12, 2, 2], [5, 18, 2, 2], [15, 18, 2, 2], [26, 18, 2, 2]],
  medium_islands: [[7, 6, 4, 3], [20, 5, 4, 3], [31, 9, 3.5, 3], [11, 16, 4, 3], [24, 16, 4, 3]],
  large_islands: [[8, 7, 6, 4.5], [25, 6, 7, 4.5], [17, 16, 7, 4.5], [32, 17, 3, 2.5]],
  two_continents: [[9, 11, 7.5, 9], [27, 11, 7.5, 9]],
  continents_islands: [[10, 8, 7, 5.5], [25, 14, 7, 5.5], [24, 4, 1.8, 1.8], [33, 6, 1.8, 1.8],
    [5, 18, 1.8, 1.8], [13, 18, 1.8, 1.8]],
  pangaea: [[18, 11, 16, 9]],
  pangaea_lakes: [[18, 11, 16, 9], [10, 10, 2.5, 2], [19, 7, 2, 1.6], [24, 13, 3, 2],
    [15, 15, 2, 1.5]],
  inner_sea: [[18, 11, 16, 9.5], [18, 11, 9, 4.5]],
  world_belt: 'M0,6C6,3 11,8 18,6S30,3 36,6V16C30,19 24,14 18,16S6,19 0,16Z',
};

function shapeGlyph(id) {
  const blobs = SHAPE_GLYPHS[id];
  if (!blobs) return '';
  const path = typeof blobs === 'string' ? blobs : blobs.map(([cx, cy, rx, ry]) =>
    `M${cx - rx},${cy}a${rx},${ry} 0 1,0 ${2 * rx},0a${rx},${ry} 0 1,0 ${-2 * rx},0Z`).join('');
  return `<svg viewBox="0 0 36 22" aria-hidden="true"><path d="${path}" fill="currentColor" fill-rule="evenodd"/></svg>`;
}

function refreshMapChoice() {
  for (const button of $('map-shapes').children) {
    button.setAttribute('aria-pressed', String(button.dataset.shape === mapChoice.shape));
  }
  const shape = store.rules.map_shapes.find((s) => s.id === mapChoice.shape);
  $('shape-hint').textContent = shape ? shape.description : '';
  for (const group of document.querySelectorAll('[data-map-level]')) {
    for (const button of group.children) {
      button.setAttribute('aria-pressed',
        String(Number(button.dataset.level) === mapChoice[group.dataset.mapLevel]));
    }
  }
}

function setPlayers(count) {
  const max = store.rules ? store.rules.defaults.max_players : 14;
  players = Math.min(max, Math.max(2, count));
  $('players').textContent = players;
}

export function setDialogStatus(text, tone = '') {
  const status = $('dialog-status');
  status.textContent = text;
  status.className = `sub ${tone}`;
}

export function refreshSaves() {
  const rows = store.saves.map((name) => `
    <div class="save-row"><span class="name" title="${name}">${name}</span>
      <button class="btn small" data-load="${name}">Load</button></div>`);
  $('saves').innerHTML = rows.join('')
    || '<div class="save-none">No saved game yet. Saves appear here, most recent first.</div>';
}

// Called for each new set of rules and game: defaults of the form.
export function resetGameDialog() {
  const state = store.state;
  setPlayers(state.players.filter((p) => !p.barbarian).length);
  $('players-hint').textContent = `2 to ${store.rules.defaults.max_players}, plus the barbarians.`;
  $('map-info').textContent = `Map ${store.map.width} × ${store.map.height}`;
  // The choices of the observer survive a new game; the defaults only apply the first time.
  const shapes = store.rules.map_shapes;
  if (!mapChoice || !shapes.some((s) => s.id === mapChoice.shape)) {
    mapChoice = { ...store.rules.defaults.map };
  }
  $('map-shapes').innerHTML = shapes.map((s) =>
    `<button data-shape="${s.id}" title="${s.description}">${shapeGlyph(s.id)}<span>${s.name}</span></button>`).join('');
  refreshMapChoice();
  refreshSaves();
}

export function openGameDialog(focus) {
  const dialog = $('game-dialog');
  if (store.state) $('save-name').value = `seed${store.state.seed}-turn${store.state.turn}`;
  setDialogStatus('Loading a save replaces the current game for every connected observer.');
  if (!dialog.open) dialog.showModal();
  const field = $(focus === 'save' ? 'save-name' : 'seed');
  field.focus();
  field.select();
}

function startNewGame() {
  const seed = parseInt($('seed').value, 10);
  send({ cmd: 'new_game', seed: Number.isFinite(seed) ? seed : null, players, map: mapChoice });
  $('game-dialog').close();
}

function save() {
  const name = $('save-name').value.trim();
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(name)) {
    setDialogStatus('Use letters, digits, - and _ for the name.', 'error');
    return;
  }
  send({ cmd: 'save', name });
}

export function initDialogs() {
  const dialog = $('game-dialog');
  document.querySelectorAll('dialog [data-close]').forEach((button) => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
  for (const element of document.querySelectorAll('dialog')) {
    // A click on the backdrop closes the dialog (not a drag that merely ends there).
    let pressed = false;
    element.addEventListener('mousedown', (e) => { pressed = e.target === element; });
    element.addEventListener('click', (e) => {
      if (pressed && e.target === element) element.close();
    });
  }
  $('players-less').addEventListener('click', () => setPlayers(players - 1));
  $('players-more').addEventListener('click', () => setPlayers(players + 1));
  $('btn-dice').addEventListener('click', () => {
    $('seed').value = 1 + Math.floor(Math.random() * 99999);
  });
  $('map-shapes').addEventListener('click', (e) => {
    const button = e.target.closest('[data-shape]');
    if (!button) return;
    mapChoice.shape = button.dataset.shape;
    refreshMapChoice();
  });
  for (const group of document.querySelectorAll('[data-map-level]')) {
    group.addEventListener('click', (e) => {
      const button = e.target.closest('[data-level]');
      if (!button) return;
      mapChoice[group.dataset.mapLevel] = Number(button.dataset.level);
      refreshMapChoice();
    });
  }
  $('btn-start').addEventListener('click', startNewGame);
  $('seed').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') startNewGame();
  });
  $('btn-do-save').addEventListener('click', save);
  $('save-name').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') save();
  });
  $('saves').addEventListener('click', (e) => {
    const button = e.target.closest('[data-load]');
    if (!button) return;
    send({ cmd: 'load', name: button.dataset.load });
    dialog.close();
  });
}

// ── Game over ────────────────────────────────────────────────────────────────

function scoreChart(players) {
  const history = store.history;
  const field = store.historyFields.indexOf('score');
  if (field < 0 || history.length < 2) return '';
  let max = 1;
  for (const row of history) {
    for (const p of players) if (row.players[p.id]) max = Math.max(max, row.players[p.id][field]);
  }
  const step = Math.max(1, Math.ceil(history.length / 200));
  const lines = players.map((p) => {
    const points = [];
    for (let i = 0; i < history.length; i += step) {
      const values = history[i].players[p.id];
      if (!values) continue;
      const x = 8 + 392 * i / (history.length - 1);
      points.push(`${x.toFixed(1)},${(190 - 180 * values[field] / max).toFixed(1)}`);
    }
    return `<polyline points="${points.join(' ')}" fill="none" stroke="${p.color}" stroke-linejoin="round"
      stroke-width="${p.id === store.state.winner ? 2.5 : 1.5}" opacity="${p.alive ? 1 : 0.5}"
      vector-effect="non-scaling-stroke"/>`;
  });
  return `<svg viewBox="0 0 408 200" preserveAspectRatio="none" role="img"
      aria-label="Score of each civilization over the whole game">
    <line x1="8" x2="400" y1="190" y2="190" stroke="#283040" vector-effect="non-scaling-stroke"/>
    <line x1="8" x2="400" y1="100" y2="100" stroke="#1D2430" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>
    <line x1="8" x2="400" y1="10" y2="10" stroke="#1D2430" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>
    ${lines.join('')}</svg>`;
}

export function showGameOver() {
  const state = store.state;
  const dialog = $('gameover');
  const winner = state.winner !== null && state.winner !== undefined ? player(state.winner) : null;
  const [label, deed, mark] = VICTORY[state.victory] || ['Game over', 'win the game', 'trophy'];
  const civs = state.players.filter((p) => !p.barbarian).sort((a, b) => b.score - a.score);
  const best = Math.max(1, civs[0] ? civs[0].score : 1);
  const alive = civs.filter((p) => p.alive).length;
  let story = winner ? `Led by ${winner.leader}.` : 'Nobody wins this game.';
  if (winner && state.victory === 'spaceship' && winner.spaceship && winner.spaceship.launched_turn !== null) {
    story += ` Launched on turn ${winner.spaceship.launched_turn}, landed on turn ${winner.spaceship.arrival_turn}.`;
  } else if (winner) {
    story += ` ${winner.cities} cities, ${winner.population} citizens, ${winner.techs} advances.`;
  }
  const color = winner ? winner.color : '#8A95A5';
  const rows = civs.map((p, i) => `
    <div class="standing${winner && p.id === winner.id ? ' winner' : ''}${p.alive ? '' : ' dead'}">
      <span class="rank">${i + 1}</span>
      <span class="who">${swatch(p.color)}<b>${p.nation}</b>
        <span class="sub">${p.leader} · ${p.alive ? governmentName(p.government) : 'destroyed'}</span></span>
      <span class="n">${p.cities}</span><span class="n">${p.population}</span><span class="n">${p.techs}</span>
      <span class="total"><span class="bar thin"><span style="width:${100 * p.score / best}%;background:${p.color}"></span></span>
        <b>${p.score}</b></span>
    </div>`).join('');

  dialog.innerHTML = `
    <div class="over-head">
      <span class="over-mark" style="background:${color};color:${inkOn(color)}">${icon(mark, 44, 1.5)}</span>
      <div class="titles">
        <span class="eyebrow">${label} · ${yearLabel(state.year)} · turn ${state.turn}</span>
        <h1>${winner ? `The ${winner.nation} ${deed}.` : 'Game over.'}</h1>
        <p>${story}</p>
      </div>
    </div>
    <div class="over-body">
      <section class="standings">
        <div class="standing-cols label"><span class="rank">#</span><span class="who">Final standings</span>
          <span class="n">Cities</span><span class="n">Pop.</span><span class="n">Advances</span>
          <span class="total" style="color:var(--text)">Score</span></div>
        ${rows}
      </section>
      <section class="over-side">
        <div class="between"><h2>Score over the game</h2>
          <span class="sub">${store.history.length ? yearLabel(store.history[0].year) : ''} to ${yearLabel(state.year)}</span></div>
        ${scoreChart(civs)}
        <div class="stats">
          <div class="stat"><b>${civs[0] ? civs[0].score : 0}</b><span>Best score</span></div>
          <div class="stat"><b>${alive}<small class="muted"> / ${civs.length}</small></b><span>Civilizations left</span></div>
        </div>
        <div class="over-actions">
          <button class="btn primary" data-over="new">New game</button>
          <div class="two" style="gap:8px">
            <button class="btn" data-over="history">Review history</button>
            <button class="btn" data-over="map">Browse the map</button>
          </div>
        </div>
      </section>
    </div>`;
  dialog.querySelectorAll('[data-over]').forEach((button) => {
    button.addEventListener('click', () => {
      dialog.close();
      if (button.dataset.over === 'new') openGameDialog('seed');
      if (button.dataset.over === 'history') emit('show-tab', 'chart');
    });
  });
  if (!dialog.open) dialog.showModal();
}
