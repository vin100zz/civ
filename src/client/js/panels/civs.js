// "World" panel: every player at a glance. "Empire" panel: one civilization in detail,
// including what its AI wants and why.

import { store, emit, player, leader, yearLabel, swatch, inkOn, plural } from '../state.js';
import { icon } from '../icons.js';
import { MISSION_COLORS } from '../renderer/map.js';
import { latestEvents } from './log.js';

const TRAIT = {
  mood: ['Friendly', 'Neutral', 'Aggressive'],
  policy: ['Perfectionist', 'Neutral', 'Expansionist'],
  ideology: ['Militaristic', 'Neutral', 'Civilized'],
};
const SORTS = [['score', 'Score'], ['cities', 'Cities'], ['population', 'Population'],
  ['techs', 'Advances'], ['units', 'Units'], ['gold', 'Gold']];
const RELATION = { war: ['War', 'bad'], peace: ['Peace', 'good'] };
const MISSIONS_SHOWN = 7;
let sortBy = 'score';
let allMissions = false;

function techName(id) {
  return id && store.techDefs[id] ? store.techDefs[id].name : '—';
}

function governmentName(id) {
  const government = store.rules.governments.find((g) => g.id === id);
  return government ? government.name : id;
}

function signed(value) {
  return `${value >= 0 ? '+' : ''}${value}`;
}

// Civilizations still in the game, the best first.
export function ranking() {
  return store.state.players.filter((p) => !p.barbarian && p.alive)
    .sort((a, b) => b.score - a.score);
}

// "structural 4/4 · component 2/2 · module 1/3", against what a launch requires.
function spaceshipLabel(p) {
  const ship = p.spaceship;
  if (!ship) return '';
  const minimum = store.rules.spaceship.min_parts;
  const built = Object.keys(minimum).map((part) =>
    `${part} ${ship.parts[part] || 0}/${minimum[part]}`).join(' · ');
  if (ship.arrival_turn !== null) {
    const left = Math.max(0, ship.arrival_turn - store.state.turn);
    return `<span class="good">in flight</span>, arrives in ${left} turns (${built})`;
  }
  return Object.values(ship.parts).some((count) => count > 0) ? built : '';
}

// ── World ────────────────────────────────────────────────────────────────────

// What a person knows of the world: its own figures, and of the civilizations it has met
// their name, their government and how they stand with it. The others are only counted.
function renderKnownWorld(container) {
  const state = store.state;
  const me = state.me;
  const others = state.players.filter((p) => !p.barbarian && p.id !== me.id);
  const met = others.filter((p) => p.met);
  const unknown = others.filter((p) => !p.met && p.alive).length;
  const relation = (p) => (me.relations.find((r) => r.player === p.id) || {}).state;
  const rows = met.map((p) => {
    const state_ = relation(p);
    const seen = store.state.cities.filter((city) => city.owner === p.id).length;
    const pill = !p.alive ? '<span class="pill">Destroyed</span>'
      : state_ === 'war' ? '<span class="pill war">War</span>'
        : state_ === 'peace' ? '<span class="pill peace">Peace</span>' : '';
    return `<button class="civ-row${p.id === store.selectedPlayer ? ' selected' : ''}" data-player="${p.id}">
      <span class="civ-line"><span class="name">${swatch(p.color)}<span>${p.nation}</span></span>${pill}</span>
      <span class="civ-meta" style="padding-left:20px"><span class="who">${p.leader}${p.government ? ` · ${governmentName(p.government)}` : ''}
        · ${plural(seen, 'city')} seen${p.wonders ? ` · ${plural(p.wonders, 'wonder')}` : ''}</span></span></button>`;
  });
  const events = latestEvents(5).map((event) => {
    const who = event.player !== undefined ? player(event.player) : null;
    const where = event.x !== undefined ? ` data-x="${event.x}" data-y="${event.y}"` : '';
    return `<button class="event-row"${where}>
      <span class="when">${yearLabel(event.year)}</span>
      <span class="dot" style="background:${who ? who.color : '#8A95A5'}"></span>
      <span class="what">${event.text}</span></button>`;
  });
  container.dataset.mode = 'play';
  container.innerHTML = `
    <div class="panel-head">
      <div class="titles"><h1>The known world</h1>
        <span class="sub">${met.length} met · ${unknown} still unknown</span></div>
    </div>
    <div id="civs-body">
      <button class="civ-row${me.id === store.selectedPlayer ? ' selected' : ''}" data-player="${me.id}">
        <span class="civ-line"><span class="name">${swatch(me.color)}<span>${me.nation} · you</span></span>
          <span class="score">${me.score}</span></span>
        <span class="civ-meta" style="padding-left:20px"><span class="who">${plural(me.cities, 'city')} · ${plural(me.population, 'citizen')}
          · ${plural(me.techs, 'advance')} · ${plural(me.units, 'unit')} · ${me.gold} gold</span></span></button>
      ${rows.join('') || '<p class="empty"><b>Nobody in sight</b>Explore: other civilizations share this world.</p>'}
      ${events.length ? `
        <div class="between" style="margin-top:14px;border-top:1px solid var(--line);padding:14px 20px 6px">
          <span class="label">Latest news</span>
          <button class="link" data-chronicle>Open chronicle</button>
        </div>${events.join('')}` : ''}
    </div>
    <div class="panel-foot">You only know of the others what you have seen and what the whole world is told.</div>`;
  container.querySelector('#civs-body').addEventListener('click', (e) => {
    const row = e.target.closest('[data-player]');
    if (row) return emit('select-player', Number(row.dataset.player));
    const event = e.target.closest('[data-x]');
    if (event) return emit('locate', { x: Number(event.dataset.x), y: Number(event.dataset.y) });
    if (e.target.closest('[data-chronicle]')) emit('show-tab', 'log');
    return undefined;
  });
}

function buildWorld(container) {
  const options = SORTS.map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
  container.dataset.mode = 'observer';
  container.innerHTML = `
    <div class="panel-head">
      <div class="titles"><h1>Civilizations</h1><span class="sub" id="civs-count"></span></div>
      <label class="sub" for="civs-sort">Sort</label>
      <select id="civs-sort" class="select">${options}</select>
    </div>
    <div id="civs-body"></div>
    <div class="panel-foot">Select a civilization for its empire and AI plan. Click a city on the
      map for its production.</div>`;
  container.querySelector('#civs-sort').addEventListener('change', (e) => {
    sortBy = e.target.value;
    renderCivs(container);
  });
  container.querySelector('#civs-body').addEventListener('click', (e) => {
    const row = e.target.closest('[data-player]');
    if (row) return emit('select-player', Number(row.dataset.player));
    const event = e.target.closest('[data-x]');
    if (event) return emit('center', { x: Number(event.dataset.x), y: Number(event.dataset.y) });
    if (e.target.closest('[data-chronicle]')) emit('show-tab', 'log');
    return undefined;
  });
}

export function renderCivs(container) {
  const state = store.state;
  if (!state) return;
  if (leader() !== null && state.me) {
    renderKnownWorld(container);
    return;
  }
  if (container.dataset.mode !== 'observer') buildWorld(container);
  const civs = state.players.filter((p) => !p.barbarian);
  const alive = civs.filter((p) => p.alive).sort((a, b) => b[sortBy] - a[sortBy] || b.score - a.score);
  const dead = civs.filter((p) => !p.alive);
  const barbarians = state.players.filter((p) => p.barbarian && (p.units > 0 || p.cities > 0));
  const best = Math.max(1, ...alive.map((p) => p[sortBy]));
  const wars = new Set();
  for (const p of alive) {
    for (const other of p.at_war) wars.add(`${Math.min(p.id, other)}-${Math.max(p.id, other)}`);
  }
  container.querySelector('#civs-count').textContent =
    `${alive.length} alive${dead.length ? ` · ${dead.length} destroyed` : ''}`;

  const sorted = (key) => (key === sortBy ? ' sorted' : '');
  const rows = alive.map((p, i) => {
    const enemies = p.at_war.map((id) => player(id).nation);
    const flying = p.spaceship && p.spaceship.arrival_turn !== null
      && p.spaceship.arrival_turn > state.turn;
    return `<button class="civ-row${p.id === store.selectedPlayer ? ' selected' : ''}" data-player="${p.id}">
      <span class="civ-line">
        <span class="rank">${i + 1}</span>
        <span class="name">${swatch(p.color)}<span>${p.nation}</span></span>
        <span class="n">${p.cities}</span><span class="n">${p.population}</span>
        <span class="n">${p.techs}</span><span class="n">${p.units}</span>
        <span class="n">${p.gold}</span><span class="score">${p.score}</span>
      </span>
      <span class="civ-meta">
        <span class="who">${p.leader} · ${governmentName(p.government)}</span>
        ${enemies.length ? `<span class="war" title="At war with ${enemies.join(', ')}">At war with ${enemies.join(', ')}</span>` : ''}
        ${flying ? '<span class="war ship">Spaceship in flight</span>' : ''}
        <span class="bar thin"><span style="width:${100 * p[sortBy] / best}%;background:${p.color}"></span></span>
      </span></button>`;
  });
  const deadRows = dead.map((p) => `
    <button class="dead-row${p.id === store.selectedPlayer ? ' selected' : ''}" data-player="${p.id}">
      <span class="swatch" style="border-color:${p.color}"></span><span class="name">${p.nation}</span>
      <span class="sub">${p.leader}</span>
      <span class="end">${p.techs} advances · final score ${p.score}</span></button>`);
  const others = barbarians.map((p) => `
    <button class="dead-row" data-player="${p.id}">
      <span class="swatch" style="border-color:${p.color}"></span><span>${p.nation}</span>
      <span class="end">${p.units} units · ${p.cities} cities</span></button>`);
  const events = latestEvents(4).map((event) => {
    const who = event.player !== undefined ? player(event.player) : null;
    const where = event.x !== undefined ? ` data-x="${event.x}" data-y="${event.y}"` : '';
    return `<button class="event-row"${where}>
      <span class="when">${yearLabel(event.year)}</span>
      <span class="dot" style="background:${who ? who.color : '#8A95A5'}"></span>
      <span class="what">${event.text}</span></button>`;
  });

  container.querySelector('#civs-body').innerHTML = `
    <div class="section" style="padding-top:16px">
      <div class="stats">
        <div class="stat"><b>${state.cities.length}</b><span>Cities</span></div>
        <div class="stat"><b>${state.units.length}</b><span>Units</span></div>
        <div class="stat"><b${wars.size ? ' class="bad"' : ''}>${wars.size}</b><span>Wars</span></div>
        <div class="stat"><b>${alive.length}<small class="muted"> / ${civs.length}</small></b><span>Alive</span></div>
      </div>
    </div>
    <div class="civ-cols label">
      <span class="rank">#</span><span style="flex:1">Civilization</span>
      <span class="n${sorted('cities')}">Cities</span><span class="n${sorted('population')}">Pop.</span>
      <span class="n${sorted('techs')}">Techs</span><span class="n${sorted('units')}">Units</span>
      <span class="n${sorted('gold')}">Gold</span><span class="score${sorted('score')}">Score</span>
    </div>
    ${rows.join('')}
    ${dead.length ? `<div class="label" style="padding:16px 20px 6px">Destroyed</div>${deadRows.join('')}` : ''}
    ${others.length ? `<div class="label" style="padding:16px 20px 6px">Outside the ranking</div>${others.join('')}` : ''}
    ${events.length ? `
      <div class="between" style="margin-top:14px;border-top:1px solid var(--line);padding:14px 20px 6px">
        <span class="label">Latest events</span>
        <button class="link" data-chronicle>Open chronicle</button>
      </div>${events.join('')}` : ''}`;
  container.querySelector('#civs-sort').value = sortBy;
}

// ── Empire ───────────────────────────────────────────────────────────────────

function aiSection(p) {
  if (!p.ai || !p.ai.needs) return '';
  const needs = Object.entries(p.ai.needs).filter(([, count]) => count > 0)
    .map(([name, count]) => `<span class="chip">${name[0].toUpperCase()}${name.slice(1)} <b>${count}</b></span>`)
    .join('') || '<span class="muted">Nothing missing</span>';
  const targets = (p.ai.targets || []).map((name) =>
    `<button class="chip war" data-city-name="${name}">${name}</button>`).join('');
  const notes = (p.ai.notes || []).map((n) => `<div>${n}</div>`).join('');
  const research = (p.ai.research || []).slice(0, 4).map(([id, score]) =>
    `<span class="chip">${techName(id)} <b>${score}</b></span>`).join('');
  const expeditions = (p.ai.expeditions || []).map((e) => `
    <button class="row-btn" data-x="${e.goal[0]}" data-y="${e.goal[1]}">
      <span class="c-kind">${e.kind === 'settle' ? 'Colony' : 'Invasion'}</span>
      <span class="c-note">${e.stage} · ${e.ship === null ? 'no ship yet' : 'ship ready'}</span>
      <span class="sub">since turn ${e.started}</span></button>`).join('');

  const every = [...(p.ai.missions || [])].sort((a, b) => b.priority - a.priority);
  const active = every.filter((m) => m.kind !== 'defend');
  const garrison = every.length - active.length;
  const shown = allMissions ? every : active.slice(0, MISSIONS_SHOWN);
  const top = Math.max(1, ...every.map((m) => m.priority));
  const missions = shown.map((m) => `
    <button class="row-btn" data-x="${m.x}" data-y="${m.y}">
      <span class="c-kind"><span class="ring" style="color:${MISSION_COLORS[m.kind] || '#fff'}"></span>
        ${m.kind[0].toUpperCase()}${m.kind.slice(1).replaceAll('_', ' ')}</span>
      <span class="c-note">${m.note || '—'}</span>
      <span class="c-units">${m.units}/${m.capacity}</span>
      <span class="c-prio"><span class="bar thin"><span style="width:${100 * m.priority / top}%"></span></span>
        <b>${Math.round(m.priority)}</b></span></button>`).join('');
  const summary = allMissions
    ? `${every.length} missions, garrisons included`
    : `${shown.length} of ${active.length} missions${garrison ? ` · ${garrison} garrison missions hidden` : ''}`;
  const more = every.length > shown.length || allMissions
    ? `<button class="link" data-all-missions>${allMissions ? 'Show fewer' : 'Show all'}</button>` : '';

  return `
    <div class="ai">
      <div class="ai-title"><span class="ai-badge">AI</span><h2>What it wants, and why</h2>
        <span class="sub">decided turn ${p.ai.turn}</span></div>
      <dl class="kv">
        <dt>Missing</dt><dd class="chips">${needs}</dd>
        ${targets ? `<dt>War targets</dt><dd class="chips">${targets}</dd>` : ''}
        ${notes ? `<dt>Decisions</dt><dd>${notes}</dd>` : ''}
        ${research ? `<dt>Next research</dt><dd class="chips">${research}</dd>` : ''}
      </dl>
      ${expeditions ? `<div class="rows"><div class="rows-head label">Expeditions across the sea</div>${expeditions}</div>` : ''}
      <div class="rows">
        <div class="rows-head label"><span class="c-kind">Mission</span><span class="c-note">Detail</span>
          <span class="c-units">Units</span><span class="c-prio">Priority</span></div>
        ${missions || '<div class="row-btn muted">None</div>'}
        <div class="rows-foot"><span>${summary}</span>${more}</div>
      </div>
    </div>`;
}

export function renderCiv(container) {
  const detail = store.playerDetail;
  if (store.selectedPlayer === null || !detail || detail.id !== store.selectedPlayer) {
    container.innerHTML = `<p class="empty"><b>No civilization selected</b>
      Pick one in the World panel, or click its land on the map.</p>`;
    return;
  }
  const p = detail;
  const ranks = ranking();
  const rank = ranks.findIndex((other) => other.id === p.id);
  const traits = Object.entries(p.personality)
    .map(([trait, value]) => TRAIT[trait][value + 1]).filter((label) => label !== 'Neutral');
  const progress = p.research_cost ? Math.min(100, 100 * p.research_progress / p.research_cost) : 0;
  const turnsLeft = p.science > 0 && p.research_cost
    ? Math.ceil(Math.max(0, p.research_cost - p.research_progress) / p.science) : null;
  const relations = p.relations.filter((r) => r.state !== 'no_contact').map((r) => {
    const other = player(r.player);
    const [label, tone] = RELATION[r.state] || [r.state, 'soft'];
    return `<button class="relation" data-player="${other.id}">
      <span class="swatch small" style="background:${other.color}"></span>
      <span class="name">${other.nation}</span><span class="since">since turn ${r.since}</span>
      <span class="state ${tone}">${label}</span></button>`;
  }).join('');
  const strangers = p.relations.filter((r) => r.state === 'no_contact')
    .map((r) => player(r.player).nation);
  const status = !p.alive ? 'destroyed' : rank >= 0 ? `rank ${rank + 1} of ${ranks.length}` : '';
  const ship = spaceshipLabel(p);
  const scroll = container.scrollTop;

  container.innerHTML = `
    <div class="panel-head empire-head">
      <span class="avatar" style="background:${p.color};color:${inkOn(p.color)}">${p.nation[0]}</span>
      <div class="titles"><h1>${p.nation}</h1>
        <span class="who">${p.leader} · ${governmentName(p.government)}${status ? ` · ${status}` : ''}</span></div>
      <div class="arrows">
        <button data-step="-1" aria-label="Previous civilization" title="Previous civilization">${icon('left', 16, 2)}</button>
        <button data-step="1" aria-label="Next civilization" title="Next civilization">${icon('right', 16, 2)}</button>
      </div>
    </div>
    <div class="section">
      <div class="chips">${(traits.length ? traits : ['Balanced']).map((t) => `<span class="trait">${t}</span>`).join('')}</div>
      <div class="stats">
        <div class="stat"><b class="trade">${p.gold}<small class="${p.income < 0 ? 'bad' : 'good'}"> ${signed(p.income)}</small></b><span>Gold · per turn</span></div>
        <div class="stat"><b>${p.cities}</b><span>Cities</span></div>
        <div class="stat"><b>${p.population}</b><span>Citizens</span></div>
        <div class="stat"><b>${p.units}</b><span>Units</span></div>
      </div>
      <div class="sub" style="margin-top:-6px">${p.wonders} wonder${p.wonders === 1 ? '' : 's'} · ${p.ships} ship${p.ships === 1 ? '' : 's'} · ${p.aircraft} aircraft · score ${p.score}</div>
      <div class="stack tight">
        <div class="between"><span class="h2">Trade split</span>
          <span class="sub"><span class="trade">Tax ${p.rates[0]}%</span> · <span style="color:#C79BF2">Luxury ${p.rates[1]}%</span> · <span class="sci">Science ${p.rates[2]}%</span></span></div>
        <div class="bar"><span style="width:${p.rates[0]}%;background:var(--trade)"></span><span style="width:${p.rates[1]}%;background:#C79BF2"></span><span style="width:${p.rates[2]}%;background:var(--sci)"></span></div>
      </div>
      <div class="stack tight">
        <div class="between"><span class="h2">Researching ${techName(p.researching)}</span>
          <span class="sub">${p.research_progress} / ${p.research_cost} · +${p.science} per turn${turnsLeft !== null ? ` · <span style="color:var(--text)">${turnsLeft} turn${turnsLeft === 1 ? '' : 's'}</span>` : ''}</span></div>
        <div class="bar"><span style="width:${progress}%;background:var(--sci)"></span></div>
        <span class="sub">${p.techs} advances known</span>
      </div>
      ${ship ? `<div class="stack tight"><span class="h2">Spaceship</span><span class="sub">${ship}</span></div>` : ''}
      <div class="stack">
        <span class="h2">Relations</span>
        ${relations || '<span class="sub">No contact with anyone yet.</span>'}
        ${strangers.length && relations ? `<span class="sub">No contact yet: ${strangers.join(', ')}</span>` : ''}
      </div>
    </div>
    ${aiSection(p)}`;
  container.scrollTop = scroll;

  container.querySelectorAll('[data-x]').forEach((row) => {
    row.addEventListener('click', () =>
      emit('center', { x: Number(row.dataset.x), y: Number(row.dataset.y) }));
  });
  container.querySelectorAll('[data-player]').forEach((row) => {
    row.addEventListener('click', () => emit('select-player', Number(row.dataset.player)));
  });
  container.querySelectorAll('[data-city-name]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const city = store.state.cities.find((c) => c.name === chip.dataset.cityName);
      if (city) emit('center', { x: city.x, y: city.y });
    });
  });
  container.querySelectorAll('[data-step]').forEach((button) => {
    button.addEventListener('click', () => {
      const index = Math.max(0, rank);
      const next = ranks[(index + Number(button.dataset.step) + ranks.length) % ranks.length];
      if (next) emit('select-player', next.id);
    });
  });
  const toggle = container.querySelector('[data-all-missions]');
  if (toggle) {
    toggle.addEventListener('click', () => {
      allMissions = !allMissions;
      renderCiv(container);
    });
  }
}

export { techName, governmentName, yearLabel };
