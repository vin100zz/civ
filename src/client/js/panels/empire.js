// "Empire" panel of the person playing: its budget, its government, its dealings with the
// civilizations it has met, its research. Another civilization shows what is known of it.

import { store, emit, player, leader, yearLabel, plural, swatch, inkOn, turnsFor } from '../state.js';
import { send } from '../net.js';
import { icon } from '../icons.js';
import { governmentName, techName } from './civs.js';

const RATES = [['tax', 'Tax', 'var(--trade)'], ['luxury', 'Luxury', '#C79BF2'], ['science', 'Science', 'var(--sci)']];
// When a rate moves, the others give or take in this order.
const BALANCE = { tax: ['science', 'luxury'], luxury: ['science', 'tax'], science: ['tax', 'luxury'] };

function act(action, fields = {}) {
  send({ cmd: 'action', action, ...fields });
}

// The three rates after moving one of them by `delta`, or null if the others cannot follow.
function shifted(me, kind, delta) {
  const rates = { tax: me.rates[0], luxury: me.rates[1], science: me.rates[2] };
  const target = rates[kind] + delta;
  if (target < 0 || target > me.max_rate) return null;
  rates[kind] = target;
  let rest = -delta;
  for (const other of BALANCE[kind]) {
    const room = rest > 0 ? me.max_rate - rates[other] : -rates[other];
    const moved = rest > 0 ? Math.min(rest, room) : Math.max(rest, room);
    rates[other] += moved;
    rest -= moved;
  }
  return rest === 0 ? rates : null;
}

// The year a turn was played in, from the history of the game.
function yearOf(turn) {
  const row = store.history.find((entry) => entry.turn === turn);
  return row ? yearLabel(row.year) : `turn ${turn}`;
}

function heading(text, note = '') {
  return `<div class="turn-head label"><span>${text}</span><span class="note">${note}</span></div>`;
}

function budget(me) {
  const rows = RATES.map(([kind, label, color], i) => {
    const value = me.rates[i];
    return `<div class="rate">
      <span class="what">${label}</span>
      <span class="gauge"><i style="width:${me.max_rate}%"></i><b style="width:${value}%;background:${color}"></b><u style="left:${me.max_rate}%"></u></span>
      <span class="stepper small" role="group" aria-label="${label} rate">
        <button data-rate="${kind}" data-delta="-10" aria-label="${label} down 10%" ${shifted(me, kind, -10) ? '' : 'disabled'}>${icon('minus', 14, 2)}</button>
        <output>${value}%</output>
        <button data-rate="${kind}" data-delta="10" aria-label="${label} up 10%" ${shifted(me, kind, 10) ? '' : 'disabled'}>${icon('plus', 14, 2)}</button>
      </span></div>`;
  });
  const gold = me.forecast.gold;
  const trouble = me.forecast.disorder
    ? ` · <span class="bad">${plural(me.forecast.disorder, 'city')} in disorder</span>` : '';
  return `${heading('Budget', `no rate above ${me.max_rate}% under ${governmentName(me.government)}`)}
    <div class="rates">${rows.join('')}
      <span class="sub">Next turn: <b class="${gold < 0 ? 'bad' : 'trade'}">${gold >= 0 ? '+' : ''}${gold} gold</b>
        · <b class="sci">${me.forecast.science} science</b>${trouble}</span></div>`;
}

function government(me) {
  const others = me.governments.filter((id) => id !== me.government);
  let body;
  if (me.government === 'anarchy') {
    body = `<span class="sub">Anarchy until turn ${me.anarchy_until}: no taxes, no science.</span>`;
  } else if (!others.length) {
    body = '<span class="sub">No other government known yet: research Monarchy or The Republic.</span>';
  } else {
    body = `<span class="sub">A revolution brings a few turns of anarchy first.</span>
      <div class="chips">${others.map((id) =>
    `<button class="btn small" data-revolution="${id}">Revolution: ${governmentName(id)}</button>`).join('')}</div>`;
  }
  return `${heading('Government')}
    <div class="block"><b class="big-name">${governmentName(me.government)}</b>${body}</div>`;
}

function affairs(me) {
  const met = me.relations.filter((r) => r.state !== 'no_contact');
  const unknown = me.relations.length - met.length;
  const rows = met.map((relation) => {
    const other = player(relation.player);
    const war = relation.state === 'war';
    const asked = me.proposals.includes(other.id);
    let action;
    if (asked) action = `<button class="btn small primary" data-proposal="${other.id}">Answer</button>`;
    else if (war) action = `<button class="btn small" data-peace="${other.id}">Propose peace</button>`;
    else if (me.senate) action = '<span class="sub" title="Your senate forbids it">Senate keeps peace</span>';
    else action = `<button class="btn small" data-war="${other.id}">Declare war</button>`;
    return `<div class="nation">
      ${swatch(other.color)}
      <span class="body"><span class="name"><b>${other.nation}</b>
        <span class="pill ${war ? 'war' : 'peace'}">${war ? 'War' : 'Peace'}</span></span>
        <span class="sub">${other.leader} · since ${yearOf(relation.since)}${asked ? ' · proposes peace' : ''}</span></span>
      ${action}</div>`;
  });
  return `${heading('Foreign affairs', `${met.length} met · ${unknown} still unknown`)}
    <div class="nations">${rows.join('') || '<span class="sub quiet">You have met nobody yet.</span>'}</div>`;
}

function research(me) {
  const turns = me.researching ? turnsFor(me.research_cost + 1 - me.research_progress, me.forecast.science) : null;
  const progress = me.research_cost ? Math.min(100, 100 * me.research_progress / me.research_cost) : 0;
  return `${heading('Research', `${me.techs} advances known`)}
    <div class="block row">
      <span class="sci">${icon('flask', 20)}</span>
      <span class="grow"><span class="between"><b class="big-name">${me.researching ? techName(me.researching) : 'Nothing'}</b>
        <span class="sub">${me.research_progress} / ${me.research_cost}${turns !== null ? ` · ${plural(turns, 'turn')}` : ''}</span></span>
        <span class="bar thin"><span style="width:${progress}%;background:var(--sci)"></span></span></span>
      <button class="btn small" data-research>${me.researching ? 'Change' : 'Choose'}</button>
    </div>`;
}

function spaceship(me) {
  const minimum = store.rules.spaceship.min_parts;
  const parts = Object.keys(minimum).map((part) => `${part} ${me.spaceship.parts[part] || 0}/${minimum[part]}`);
  const flying = me.spaceship.arrival_turn !== null;
  if (!flying && !me.can_launch && !Object.values(me.spaceship.parts).some((count) => count > 0)) return '';
  let body;
  if (flying) body = `<span class="sub good">In flight: lands in ${plural(Math.max(0, me.spaceship.arrival_turn - store.state.turn), 'turn')}.</span>`;
  else if (me.can_launch) body = `<button class="btn small primary" data-launch>Launch · ${me.flight_years} years of flight</button>`;
  else body = '<span class="sub">Not enough parts to launch yet.</span>';
  return `${heading('Spaceship')}<div class="block"><span class="sub">${parts.join(' · ')}</span>${body}</div>`;
}

function renderOwn(container, me) {
  const scroll = container.scrollTop;
  const level = store.rules.levels.find((entry) => entry.id === me.level);
  container.innerHTML = `
    <div class="panel-head empire-head">
      <span class="avatar" style="background:${me.color};color:${inkOn(me.color)}">${icon('crown', 22, 1.8)}</span>
      <div class="titles"><h1>Your empire</h1>
        <span class="who">${me.leader} of the ${me.nation} · ${plural(me.cities, 'city')} · ${plural(me.population, 'citizen')}${level ? ` · ${level.name}` : ''}</span></div>
    </div>
    <div class="section" style="padding-top:16px">
      <div class="stats">
        <div class="stat"><b class="trade">${me.gold}</b><span>Gold</span></div>
        <div class="stat"><b>${me.forecast.gold >= 0 ? '+' : ''}${me.forecast.gold}</b><span>Gold a turn</span></div>
        <div class="stat"><b class="sci">+${me.forecast.science}</b><span>Science</span></div>
        <div class="stat"><b>${me.score}</b><span>Score</span></div>
      </div>
    </div>
    ${budget(me)}${government(me)}${affairs(me)}${research(me)}${spaceship(me)}
    <div class="panel-foot">${me.wonders} wonder${me.wonders === 1 ? '' : 's'} · ${plural(me.units, 'unit')}
      · ${me.ships} at sea · ${me.aircraft} in the air</div>`;
  container.scrollTop = scroll;

  container.querySelectorAll('[data-rate]').forEach((button) => {
    button.addEventListener('click', () => {
      const rates = shifted(me, button.dataset.rate, Number(button.dataset.delta));
      if (rates) act('rates', rates);
    });
  });
  container.querySelectorAll('[data-revolution]').forEach((button) => {
    button.addEventListener('click', () => act('revolution', { government: button.dataset.revolution }));
  });
  container.querySelectorAll('[data-peace]').forEach((button) => {
    button.addEventListener('click', () => act('peace', { player: Number(button.dataset.peace) }));
  });
  container.querySelectorAll('[data-war]').forEach((button) => {
    button.addEventListener('click', () => emit('confirm-war', Number(button.dataset.war)));
  });
  container.querySelectorAll('[data-proposal]').forEach((button) => {
    button.addEventListener('click', () => emit('open-proposal', Number(button.dataset.proposal)));
  });
  const choose = container.querySelector('[data-research]');
  if (choose) choose.addEventListener('click', () => emit('open-research'));
  const launch = container.querySelector('[data-launch]');
  if (launch) launch.addEventListener('click', () => act('launch'));
}

// Another civilization, as far as the person knows it.
function renderForeign(container, me, other) {
  const relation = me.relations.find((r) => r.player === other.id);
  const state = relation ? relation.state : 'no_contact';
  const cities = store.state.cities.filter((city) => city.owner === other.id);
  const list = cities.map((city) => `
    <button class="row-btn" data-x="${city.x}" data-y="${city.y}">
      <span class="c-kind">${city.name}</span><span class="c-note">size ${city.size} when last seen, turn ${city.seen}</span></button>`);
  const flying = other.spaceship && other.spaceship.arrival_turn !== null;
  container.innerHTML = `
    <div class="panel-head empire-head">
      <span class="avatar" style="background:${other.color};color:${inkOn(other.color)}">${other.nation[0]}</span>
      <div class="titles"><h1>${other.nation}</h1>
        <span class="who">${other.met ? `${other.leader}${other.government ? ` · ${governmentName(other.government)}` : ''}` : 'Not met yet'}${other.alive ? '' : ' · destroyed'}</span></div>
      <button class="btn small" data-back>Your empire</button>
    </div>
    <div class="section">
      <span class="sub">You only know of a civilization what you have seen: its treasury, its science and
        its armies are its own secret.</span>
      <div class="stats">
        <div class="stat"><b>${cities.length}</b><span>Cities seen</span></div>
        <div class="stat"><b>${other.wonders}</b><span>Wonders</span></div>
        <div class="stat"><b class="${state === 'war' ? 'bad' : state === 'peace' ? 'good' : ''}">${state === 'war' ? 'War' : state === 'peace' ? 'Peace' : '—'}</b><span>With you</span></div>
        <div class="stat"><b>${flying ? plural(Math.max(0, other.spaceship.arrival_turn - store.state.turn), 'turn') : '—'}</b><span>Spaceship</span></div>
      </div>
    </div>
    ${list.length ? `<div class="rows"><div class="rows-head label">Cities you have seen</div>${list.join('')}</div>` : ''}`;
  container.querySelector('[data-back]').addEventListener('click', () => emit('select-player', me.id));
  container.querySelectorAll('[data-x]').forEach((row) => {
    row.addEventListener('click', () =>
      emit('locate', { x: Number(row.dataset.x), y: Number(row.dataset.y) }));
  });
}

export function renderEmpire(container) {
  const me = store.state.me;
  const selected = store.selectedPlayer;
  if (selected !== null && selected !== leader() && player(selected)) {
    renderForeign(container, me, player(selected));
  } else {
    renderOwn(container, me);
  }
}
