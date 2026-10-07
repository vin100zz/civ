// The bar of the active unit, at the bottom of the map: what it is, where it stands, and
// the orders the server says it can take. Without a unit, how the turn stands.

import { store, U, player, leader, plural } from '../state.js';
import { icon } from '../icons.js';
import {
  play, activeUnit, queue, give, keyOf, wait, skip, activate, endTurn, pendingDecisions, whyNotEnd,
} from '../play.js';
import { replaying, skipReplay } from '../replay.js';

// Order id -> [label, icon].
const LOOK = {
  found_city: ['Found city', 'flag'], join_city: ['Join the city', 'people'],
  road: ['Road', 'road'], railroad: ['Railroad', 'rail'], irrigate: ['Irrigate', 'drop'],
  mine: ['Mine', 'pick'], fortress: ['Fortress', 'fortress'], clean: ['Clean up', 'broom'],
  help_wonder: ['Help the wonder', 'temple'], trade_route: ['Trade route', 'route'],
  board: ['Board', 'anchor'], disembark: ['Go ashore', 'ashore'],
  goto: ['Go to', 'target'], fortify: ['Fortify', 'shield'], sentry: ['Sentry', 'eye'],
  wake: ['Wake up', 'bell'], stop: ['Take back', 'stop'],
  explore: ['Explore', 'compass'], auto_work: ['Automate', 'cog'],
  home: ['Home city', 'home'], disband: ['Disband', 'trash'],
};
const LEAD = ['found_city', 'help_wonder', 'trade_route'];
const TASK = { goto: 'On its way', explore: 'Exploring by itself', work: 'Working by itself' };
const STATE = { fortified: 'Fortified', fortify: 'Fortifying', sentry: 'On sentry duty' };

// Movement points as moves: "1", "2/3", "1 1/3".
export function movesLabel(points) {
  const per = store.rules.points_per_move;
  const whole = Math.floor(points / per);
  const rest = points % per;
  if (!rest) return String(whole);
  return `${whole ? `${whole} ` : ''}${rest}/${per}`;
}

// "1 move", "2 moves", "2/3 move".
export function movesText(points) {
  return `${movesLabel(points)} move${points > store.rules.points_per_move ? 's' : ''}`;
}

function portrait(type, size = 56) {
  const me = player(leader());
  const definition = store.unitDefs[type];
  return `<span class="unit-portrait" style="width:${size}px;height:${size}px;background:${me.color}">
    <img src="/resources/unit/${definition.sprite}.png" alt=""></span>`;
}

function orderButton(order) {
  const [label, glyph] = LOOK[order.id] || [order.id, 'more'];
  let sub = '';
  if (order.turns) sub = plural(order.turns, 'turn') + (order.becomes ? ` · ${order.becomes}` : '');
  else if (order.city) sub = order.city;
  else if (order.id === 'goto' && play.mode === 'goto') sub = 'pick a tile';
  const key = keyOf(order.id);
  const classes = ['unit-order'];
  if (LEAD.includes(order.id)) classes.push('lead');
  if (order.id === 'goto' && play.mode === 'goto') classes.push('on');
  return `<button class="${classes.join(' ')}" data-order="${order.id}"
      aria-pressed="${order.id === 'goto' && play.mode === 'goto'}">
    ${icon(glyph, 18)}<span class="what"><b>${label}</b>${sub ? `<small>${sub}</small>` : ''}</span>
    ${key ? `<span class="kbd">${key}</span>` : ''}</button>`;
}

function mate(unit, activeId) {
  const definition = store.unitDefs[unit[U.TYPE]];
  const state = unit[U.ABOARD] ? 'aboard' : TASK[unit[U.TASK]] ? unit[U.TASK]
    : unit[U.ORDER] !== 'none' ? unit[U.ORDER] : unit[U.MOVES] > 0 ? 'ready' : 'moved';
  return `<button class="mate${unit[U.ID] === activeId ? ' on' : ''}" data-unit="${unit[U.ID]}"
      title="${definition.name} — ${state}">
    <img src="/resources/unit/${definition.sprite}.png" alt="">${definition.name}
    <small>${state}</small></button>`;
}

function idle(container) {
  const waiting = play.waiting;
  const cities = store.state.cities.filter((city) => city.owner === leader());
  const next = cities.filter((city) => !city.idle && city.cost
    && city.shields + Math.max(0, city.surplus) >= city.cost);
  const note = waiting ? '' : next.length
    ? `${next.map((city) => city.name).slice(0, 3).join(', ')} ${next.length === 1 ? 'finishes' : 'finish'} building next turn.`
    : '';
  const pending = pendingDecisions();
  const watching = replaying();
  const title = watching ? 'The other civilizations are moving…'
    : waiting ? 'The other civilizations are playing…'
    : play.ending ? 'Every unit has its orders: the turn ends'
      : pending ? `No unit to move · ${plural(pending, 'decision')} to make first` : 'No unit to move';
  container.className = 'glass play-only idle';
  container.innerHTML = `
    <span class="mark ${waiting || pending ? '' : 'good'}">${icon(waiting || play.ending ? 'hourglass' : 'check', 20, 2)}</span>
    <b>${title}</b>
    <span class="sub">${play.ending ? '' : note}</span>
    ${watching ? `<button class="btn" data-watched title="Go straight to your turn">${icon('skip', 16)}<span>Skip</span><span class="kbd">Esc</span></button>`
    : waiting || play.ending ? '' : `<button class="btn${pending ? '' : ' primary'}" data-end aria-disabled="${pending > 0}">${icon('arrow', 16, 2.2)}<span>End turn</span><span class="kbd">Enter</span></button>`}`;
  const watched = container.querySelector('[data-watched]');
  if (watched) watched.addEventListener('click', skipReplay);
  const end = container.querySelector('[data-end]');
  if (end) {
    end.title = whyNotEnd() || 'End your turn (Enter)';
    end.addEventListener('click', endTurn);
  }
}

export function renderUnitBar(container) {
  if (leader() === null) {
    container.innerHTML = '';
    return;
  }
  const unit = activeUnit();
  if (!unit || play.waiting || replaying()) {
    idle(container);
    return;
  }
  container.className = 'glass play-only';
  const definition = store.unitDefs[unit[U.TYPE]];
  const detail = play.detail && play.detail.id === unit[U.ID] ? play.detail : null;
  const list = queue();
  const position = list.findIndex((other) => other[U.ID] === unit[U.ID]);

  const where = [];
  if (detail) {
    if (detail.home) where.push(`Home city ${detail.home}`);
    where.push(detail.city ? `in ${detail.city}` : detail.aboard ? 'aboard a ship' : `on ${detail.terrain}`);
  }
  where.push(`<span class="mono">${unit[U.X]}, ${unit[U.Y]}</span>`);

  let doing = TASK[unit[U.TASK]] || STATE[unit[U.ORDER]] || '';
  if (detail && detail.work_turns) {
    doing = `${LOOK[unit[U.ORDER]][0]} · turn ${detail.work} of ${detail.work_turns}`;
  }
  if (detail && detail.destination) doing = `On its way to ${detail.destination.join(', ')}`;

  const stats = [['Attack', definition.attack], ['Defence', definition.defense],
    ['Moves', detail ? `${movesLabel(detail.moves_left)} of ${movesLabel(detail.full_moves)}`
      : movesLabel(unit[U.MOVES])]];
  if (detail && detail.fuel !== null) stats.push(['Fuel', plural(detail.fuel, 'turn')]);
  if (detail && detail.capacity) stats.push(['Aboard', `${detail.cargo.length} of ${detail.capacity}`]);

  const others = detail ? detail.stack.filter((other) => other[U.ID] !== unit[U.ID]) : [];
  const stack = others.length ? `
    <div class="mates"><span class="sub">${detail.city ? 'Also in the city' : 'Also on this tile'}</span>
      ${others.slice(0, 9).map((other) => mate(other, unit[U.ID])).join('')}
      ${others.length > 9 ? `<span class="sub">and ${others.length - 9} more</span>` : ''}</div>` : '';

  container.innerHTML = `
    <div class="unit-head">
      ${portrait(unit[U.TYPE])}
      <div class="titles">
        <div class="name"><h2>${definition.name}</h2>
          ${unit[U.VETERAN] ? '<span class="tag gold"><i></i>Veteran</span>' : ''}
          ${doing ? `<span class="tag">${doing}</span>` : ''}</div>
        <span class="sub">${where.join(' · ')}</span>
      </div>
      <div class="unit-stats">${stats.map(([label, value]) =>
    `<div><span>${label}</span><b>${value}</b></div>`).join('')}</div>
      <div class="unit-turn">
        <span class="sub">${position >= 0 ? `Unit ${position + 1} of ${list.length}` : plural(list.length, 'unit') + ' waiting'}</span>
        <button class="btn" data-wait title="Come back to this unit later">${icon('clock', 16)}<span>Wait</span><span class="kbd">W</span></button>
        <button class="btn" data-skip title="No orders this turn">${icon('skip', 16)}<span>Skip turn</span><span class="kbd">Space</span></button>
      </div>
    </div>
    <div class="unit-orders">${detail ? detail.orders.map(orderButton).join('') : '<span class="sub">…</span>'}</div>
    ${stack}`;

  container.querySelector('[data-wait]').addEventListener('click', wait);
  container.querySelector('[data-skip]').addEventListener('click', skip);
  container.querySelectorAll('[data-order]').forEach((button) => {
    button.addEventListener('click', () =>
      give(detail.orders.find((order) => order.id === button.dataset.order)));
  });
  container.querySelectorAll('[data-unit]').forEach((button) => {
    button.addEventListener('click', () => activate(Number(button.dataset.unit), false));
  });
}
