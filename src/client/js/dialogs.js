// The dialogs: "Game" (new game, saved games), the choice of an advance, the messages that
// ask the person for an answer, and the end-of-game screen.

import { send } from './net.js';
import { store, emit, player, yearLabel, inkOn, swatch, civColor, plural, turnsFor } from './state.js';
import { icon } from './icons.js';
import { governmentName } from './panels/civs.js';

const $ = (id) => document.getElementById(id);
const VICTORY = {
  conquest: ['Conquest victory', 'conquer the world', 'sword'],
  spaceship: ['Spaceship victory', 'reach Alpha Centauri', 'rocket'],
  score: ['Victory on score', 'have the greatest civilization', 'trophy'],
};
// The choices of the next new game. They survive from one game to the next.
const choice = { mode: 'play', civ: null, level: null, players: 7, map: null, tab: 'new' };

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

function show(dialog) {
  if (!dialog.open) dialog.showModal();
}

// ── "Game": new game and saved games ─────────────────────────────────────────

function playableCivs() {
  return store.rules.civs.filter((civ) => civ.playable);
}

function refreshChoices() {
  const playing = choice.mode === 'play';
  for (const button of $('game-mode').children) {
    button.setAttribute('aria-pressed', String(button.dataset.mode === choice.mode));
  }
  document.querySelectorAll('[data-play-field]').forEach((field) => { field.hidden = !playing; });
  for (const button of $('civ-grid').children) {
    button.setAttribute('aria-pressed', String(button.dataset.civ === choice.civ));
  }
  for (const button of $('levels').children) {
    button.setAttribute('aria-pressed', String(button.dataset.level === choice.level));
  }
  for (const button of $('map-shapes').children) {
    button.setAttribute('aria-pressed', String(button.dataset.shape === choice.map.shape));
  }
  const shape = store.rules.map_shapes.find((s) => s.id === choice.map.shape);
  $('shape-hint').textContent = shape ? shape.description : '';
  for (const group of document.querySelectorAll('[data-map-level]')) {
    for (const button of group.children) {
      button.setAttribute('aria-pressed',
        String(Number(button.dataset.level) === choice.map[group.dataset.mapLevel]));
    }
  }
  $('players').textContent = choice.players;
  const max = store.rules.defaults.max_players;
  $('players-hint').textContent = playing
    ? `You and ${plural(choice.players - 1, 'opponent')}, plus the barbarians.`
    : `2 to ${max}, plus the barbarians.`;
  const civ = playableCivs().find((c) => c.id === choice.civ);
  $('btn-start').textContent = !playing ? 'Start new game'
    : civ ? `Play as the ${civ.nation}` : 'Play a civilization drawn at random';

  for (const button of $('game-tabs').children) {
    button.setAttribute('aria-pressed', String(button.dataset.gameTab === choice.tab));
  }
  $('game-new').hidden = choice.tab !== 'new';
  $('game-saves').hidden = choice.tab !== 'saves';
  $('btn-start').hidden = choice.tab !== 'new';
}

function setPlayers(count) {
  choice.players = Math.min(store.rules ? store.rules.defaults.max_players : 14, Math.max(2, count));
  refreshChoices();
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

// Called for each new set of rules and game: fills the form, keeps the person's choices.
export function resetGameDialog() {
  const rules = store.rules;
  if (!choice.map || !rules.map_shapes.some((s) => s.id === choice.map.shape)) {
    choice.map = { ...rules.defaults.map };
    choice.players = rules.defaults.players;
  }
  if (!rules.levels.some((level) => level.id === choice.level)) choice.level = rules.defaults.level;
  if (!playableCivs().some((civ) => civ.id === choice.civ)) choice.civ = null;
  $('civ-grid').innerHTML = playableCivs().map((civ) => `
    <button data-civ="${civ.id}">${swatch(civColor(civ.id, civ.color))}
      <span class="who"><b>${civ.nation}</b><small>${civ.leader}</small></span>${icon('check', 16, 2.4)}</button>`).join('');
  $('levels').innerHTML = rules.levels.map((level) =>
    `<button data-level="${level.id}">${level.name}</button>`).join('');
  $('map-shapes').innerHTML = rules.map_shapes.map((s) =>
    `<button data-shape="${s.id}" title="${s.description}">${shapeGlyph(s.id)}<span>${s.name}</span></button>`).join('');
  refreshChoices();
  refreshSaves();
}

export function openGameDialog(focus) {
  const dialog = $('game-dialog');
  choice.tab = focus === 'save' ? 'saves' : 'new';
  if (store.state) $('save-name').value = `seed${store.state.seed}-turn${store.state.turn}`;
  setDialogStatus(`Map ${store.map.width} × ${store.map.height} · a new or loaded game replaces the current one.`);
  refreshChoices();
  show(dialog);
  const field = $(focus === 'save' ? 'save-name' : 'seed');
  field.focus();
  field.select();
}

function startNewGame() {
  const seed = parseInt($('seed').value, 10);
  const message = { cmd: 'new_game', seed: Number.isFinite(seed) ? seed : null,
    players: choice.players, map: choice.map };
  if (choice.mode === 'play') {
    const civs = playableCivs();
    message.mode = 'play';
    message.civ = choice.civ || civs[Math.floor(Math.random() * civs.length)].id;
    message.level = choice.level;
  }
  send(message);
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

// Makes `handler(button)` answer the clicks on the buttons of a group carrying `attribute`.
function pick(group, attribute, handler) {
  group.addEventListener('click', (e) => {
    const button = e.target.closest(`[${attribute}]`);
    if (!button) return;
    handler(button);
    refreshChoices();
  });
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
      if (pressed && e.target === element && !element.dataset.modal) element.close();
    });
  }
  pick($('game-tabs'), 'data-game-tab', (button) => { choice.tab = button.dataset.gameTab; });
  pick($('game-mode'), 'data-mode', (button) => { choice.mode = button.dataset.mode; });
  pick($('civ-grid'), 'data-civ', (button) => {
    choice.civ = choice.civ === button.dataset.civ ? null : button.dataset.civ;
  });
  pick($('levels'), 'data-level', (button) => { choice.level = button.dataset.level; });
  pick($('map-shapes'), 'data-shape', (button) => { choice.map.shape = button.dataset.shape; });
  for (const group of document.querySelectorAll('[data-map-level]')) {
    pick(group, 'data-level', (button) => {
      choice.map[group.dataset.mapLevel] = Number(button.dataset.level);
    });
  }
  $('civ-random').addEventListener('click', () => {
    choice.civ = null;
    refreshChoices();
  });
  $('players-less').addEventListener('click', () => setPlayers(choice.players - 1));
  $('players-more').addEventListener('click', () => setPlayers(choice.players + 1));
  $('btn-dice').addEventListener('click', () => {
    $('seed').value = 1 + Math.floor(Math.random() * 99999);
  });
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

// ── Research: the person chooses the next advance ────────────────────────────

function unlocks(techId) {
  const items = [];
  for (const unit of store.rules.units) if (unit.requires === techId) items.push(['Unit', unit.name]);
  for (const building of store.rules.buildings) {
    if (building.requires === techId) items.push([building.wonder ? 'Wonder' : 'Building', building.name]);
  }
  for (const government of store.rules.governments) {
    if (government.requires === techId) items.push(['Government', government.name]);
  }
  return items;
}

// `discovered`: the advance just found, when the dialog opens because of it.
export function openResearchDialog(discovered = null) {
  const me = store.state.me;
  if (!me) return;
  const dialog = $('research-dialog');
  let selected = me.researching && me.research_options.includes(me.researching)
    ? me.researching : me.research_options[0];
  const science = me.forecast.science;
  const turns = turnsFor(me.research_cost + 1 - (me.researching ? me.research_progress : 0), science);
  const found = discovered ? store.techDefs[discovered] : null;
  const gains = found ? unlocks(found.id).map(([, name]) => name) : [];

  const render = () => {
    const rows = me.research_options.map((id) => {
      const tech = store.techDefs[id];
      const leads = store.rules.techs.filter((t) => t.prerequisites.includes(id)).map((t) => t.name);
      const chips = unlocks(id).map(([kind, name]) =>
        `<span class="chip big"><span class="muted">${kind}</span><b>${name}</b></span>`).join('');
      const on = id === selected;
      return `<button class="advance${on ? ' on' : ''}" role="radio" aria-checked="${on}" data-tech="${id}">
        <span class="radio"></span>
        <span class="body"><b>${tech.name}</b>
          <span>${leads.length ? `Leads to ${leads.join(', ')}` : 'No later advance needs it'}</span></span>
        <span class="chips">${chips}</span></button>`;
    }).join('');
    const name = selected ? store.techDefs[selected].name : '';
    dialog.innerHTML = `
      <div class="message-head">
        <span class="message-mark sci-mark">${icon('flask', 28, 1.6)}</span>
        <div class="titles">
          <span class="eyebrow">${found ? `Advance discovered · ${yearLabel(store.state.year)}` : `Research · ${me.techs} advances known`}</span>
          <h1>${found ? found.name : me.researching ? `Researching ${store.techDefs[me.researching].name}` : 'Nothing is being researched'}</h1>
          <p>${found ? (gains.length ? `You can now build: ${gains.join(', ')}.` : 'A step towards greater things.')
    : 'The science already gathered is kept when you change your mind.'}</p>
        </div>
        <button class="btn ghost icon" data-close aria-label="Close">${icon('close', 18, 2)}</button>
      </div>
      <div class="message-body">
        <div><h2>What should your scientists study next?</h2>
          <span class="sub">The next advance needs ${me.research_cost} science${turns !== null ? `: about ${plural(turns, 'turn')} at your ${science} per turn` : ''}.</span></div>
        <div class="advances" role="radiogroup" aria-label="Advances you can research">${rows}</div>
      </div>
      <div class="message-foot">
        <button class="link" data-tree>See the whole science tree</button>
        <button class="btn primary tall" data-research ${selected ? '' : 'disabled'}>Research ${name}</button>
      </div>`;
    dialog.querySelectorAll('[data-tech]').forEach((row) => {
      row.addEventListener('click', () => {
        selected = row.dataset.tech;
        render();
      });
      row.addEventListener('dblclick', () => dialog.querySelector('[data-research]').click());
    });
    dialog.querySelector('[data-close]').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-tree]').addEventListener('click', () => {
      dialog.close();
      emit('show-tab', 'tech');
    });
    dialog.querySelector('[data-research]').addEventListener('click', () => {
      send({ cmd: 'action', action: 'research', tech: selected });
      dialog.close();
    });
  };
  render();
  show(dialog);
}

// ── Messages that wait for an answer ─────────────────────────────────────────

function message({ color, glyph, eyebrow, title, text, note = '', buttons }) {
  const dialog = $('message-dialog');
  dialog.dataset.modal = 'true';         // closed by an answer, not by a click beside it
  dialog.innerHTML = `
    <div class="message-head">
      <span class="message-mark" style="background:${color};color:${inkOn(color)}">${icon(glyph, 28, 1.6)}</span>
      <div class="titles"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1><p>${text}</p></div>
    </div>
    <div class="message-foot"><span class="sub">${note}</span>
      ${buttons.map(([label, tone], i) => `<button class="btn tall ${tone}" data-answer="${i}">${label}</button>`).join('')}
    </div>`;
  dialog.querySelectorAll('[data-answer]').forEach((button) => {
    button.addEventListener('click', () => {
      dialog.close();
      const action = buttons[Number(button.dataset.answer)][2];
      if (action) action();
    });
  });
  show(dialog);
}

function yearOf(turn) {
  const row = store.history.find((entry) => entry.turn === turn);
  return row ? yearLabel(row.year) : `turn ${turn}`;
}

export function openProposal(id) {
  const other = player(id);
  const relation = store.state.me.relations.find((r) => r.player === id);
  const answer = (accept) => () => send({ cmd: 'action', action: 'answer_peace', player: id, accept });
  message({
    color: other.color, glyph: 'scroll',
    eyebrow: `Message from the ${other.nation}`,
    title: `${other.leader} proposes a peace treaty`,
    text: `You have been at war since ${relation ? yearOf(relation.since) : 'you met'}. Under a treaty neither
      side may attack the other or enter its cities.`,
    note: 'Left unanswered, the proposal is refused when you end your turn.',
    buttons: [['Refuse', '', answer(false)], ['Accept peace', 'primary', answer(true)]],
  });
}

export function openWarConfirm(id) {
  const other = player(id);
  message({
    color: other.color, glyph: 'sword',
    eyebrow: 'Foreign affairs',
    title: `Declare war on the ${other.nation}?`,
    text: 'The treaty ends at once: your units may attack theirs and enter their cities, and theirs yours.',
    buttons: [['Keep the peace', '', null],
      ['Declare war', 'danger', () => send({ cmd: 'action', action: 'war', player: id })]],
  });
}

export function openDefeat() {
  const me = player(store.state.play.human);
  message({
    color: me.color, glyph: 'crown',
    eyebrow: `${yearLabel(store.state.year)} · turn ${store.state.turn}`,
    title: `The ${me.nation} are no more`,
    text: 'Your last city has fallen and no settlers remain to found another. The world goes on without you: '
      + 'you can watch how it ends, or start again.',
    buttons: [['Watch the rest of the game', '', null], ['New game', 'primary', () => openGameDialog('seed')]],
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
  // The person who led a civilization is told how it ended for it.
  const you = state.play ? state.play.human : null;
  const verdict = you === null || !winner ? '' : winner.id === you ? 'You win · ' : 'You lose · ';
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
      <span class="who">${swatch(p.color)}<b>${p.nation}${p.id === you ? ' (you)' : ''}</b>
        <span class="sub">${p.leader} · ${p.alive ? governmentName(p.government) : 'destroyed'}</span></span>
      <span class="n">${p.cities}</span><span class="n">${p.population}</span><span class="n">${p.techs}</span>
      <span class="total"><span class="bar thin"><span style="width:${100 * p.score / best}%;background:${p.color}"></span></span>
        <b>${p.score}</b></span>
    </div>`).join('');

  dialog.innerHTML = `
    <div class="over-head">
      <span class="over-mark" style="background:${color};color:${inkOn(color)}">${icon(mark, 44, 1.5)}</span>
      <div class="titles">
        <span class="eyebrow">${verdict}${label} · ${yearLabel(state.year)} · turn ${state.turn}</span>
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
  show(dialog);
}

