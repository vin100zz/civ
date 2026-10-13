// "Empire" panel of the person playing: its budget and its government (its dealings with the
// others are in the World panel). Another civilization shows what is known of it.

import { store, emit, player, leader, plural, inkOn } from '../state.js';
import { send } from '../net.js';
import { icon } from '../icons.js';
import { governmentName } from './civs.js';
import { balanceButton, applyBalance } from './turn.js';

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
  // The treasury loses gold: the rates that would stop it, one click away.
  const fix = me.balance ? `<div class="rates-fix"><span class="bad">${me.forecast.gold} gold per turn</span>${balanceButton(me.balance)}</div>` : '';
  return `${heading('Budget', `no rate above ${me.max_rate}% under ${governmentName(me.government)}`)}
    <div class="rates">${rows.join('')}${fix}</div>`;
}

function government(me) {
  const others = me.governments.filter((id) => id !== me.government);
  let body;
  if (me.government === 'anarchy') {
    body = `<span class="sub">Anarchy until turn ${me.anarchy_until}: no taxes, no science.</span>`;
  } else if (!others.length) {
    body = '<span class="sub">No other government known yet: research Monarchy or The Republic.</span>';
  } else {
    body = `<div class="chips">${others.map((id) =>
      `<button class="btn small" data-revolution="${id}">Revolution: ${governmentName(id)}</button>`).join('')}</div>`;
  }
  return `${heading('Government')}
    <div class="block"><b class="big-name">${governmentName(me.government)}</b>${body}</div>`;
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
      <div class="titles"><h1>Empire</h1>
        <span class="who">${me.leader} of the ${me.nation} · ${plural(me.cities, 'city')} · ${plural(me.population, 'citizen')}${level ? ` · ${level.name}` : ''}</span></div>
    </div>
    ${budget(me)}${government(me)}${spaceship(me)}`;
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
  const balance = container.querySelector('[data-balance]');
  if (balance) balance.addEventListener('click', () => applyBalance(me.balance));
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
