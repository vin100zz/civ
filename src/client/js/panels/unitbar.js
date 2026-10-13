// The bar of the active unit, at the bottom of the map, on one line: who it is, its figures,
// the orders the server says it can take (icons, the key in a corner, the rest in a tooltip),
// the other units on its tile and the turn buttons. Without a unit, how the turn stands.

import { store, U, player, leader, plural } from '../state.js';
import { icon } from '../icons.js';
import { setTips } from '../tips.js';
import {
  play, activeUnit, queue, give, keyOf, wait, skip, activate, endTurn, pendingDecisions, whyNotEnd,
} from '../play.js';
import { replaying, skipReplay } from '../replay.js';
import { unitPicture } from '../renderer/sprites.js';

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
const TASK_ICON = { goto: 'target', explore: 'compass', work: 'cog' };
const STATE = { fortified: 'Fortified', fortify: 'Fortifying', sentry: 'On sentry duty' };
const MATES = 6;                // units of the tile shown, the others behind a "+N"
const FRACTIONS = { '1/2': '½', '1/3': '⅓', '2/3': '⅔', '1/4': '¼', '3/4': '¾' };

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

// The same, short enough to sit before a slash: "1⅓", "⅔", "2".
function movesShort(points) {
  const per = store.rules.points_per_move;
  const whole = Math.floor(points / per);
  const rest = points % per;
  if (!rest) return String(whole);
  const fraction = FRACTIONS[`${rest}/${per}`] || ` ${rest}/${per}`;
  return `${whole || ''}${fraction}`.trim();
}

// A key as the corner of a button shows it.
function shortKey(key) {
  return key.replace('Shift ', '⇧');
}

function portrait(unit) {
  const definition = store.unitDefs[unit[U.TYPE]];
  return `<span class="unit-portrait" style="background:${player(unit[U.OWNER]).color}">
    <img src="${unitPicture(definition)}" alt=""></span>`;
}

function orderButton(order, tips) {
  const [label, glyph] = LOOK[order.id] || [order.id, 'more'];
  const picking = order.id === 'goto' && play.mode === 'goto';
  let sub = '';
  if (order.turns) sub = plural(order.turns, 'turn') + (order.becomes ? ` · becomes ${order.becomes}` : '');
  else if (order.city) sub = order.city;
  else if (picking) sub = 'Pick a tile';
  const key = keyOf(order.id);
  const classes = ['unit-order'];
  if (LEAD.includes(order.id)) classes.push('lead');
  if (picking) classes.push('on');
  tips.set(`order:${order.id}`, `<div class="tip-name">${label}${key ? `<span class="kbd">${key}</span>` : ''}
    ${sub ? `<small>${sub}</small>` : ''}</div>`);
  return `<button class="${classes.join(' ')}" data-order="${order.id}" data-tip="order:${order.id}"
      aria-label="${label}${sub ? ` (${sub})` : ''}" aria-pressed="${picking}">
    ${icon(glyph, 18)}${key ? `<span class="key">${shortKey(key)}</span>` : ''}</button>`;
}

// What a unit of the tile is doing: [words, icon of its badge or null].
function mateState(unit) {
  if (unit[U.ABOARD]) return ['Aboard', 'anchor'];
  const task = unit[U.TASK];
  if (TASK[task]) return [TASK[task], TASK_ICON[task]];
  const order = unit[U.ORDER];
  if (STATE[order]) return [STATE[order], order === 'sentry' ? 'eye' : 'shield'];
  if (LOOK[order]) return [LOOK[order][0], LOOK[order][1]];
  return [unit[U.MOVES] > 0 ? 'Ready' : 'No moves left', null];
}

function mate(unit, tips) {
  const definition = store.unitDefs[unit[U.TYPE]];
  const [state, glyph] = mateState(unit);
  const key = `unit:${unit[U.ID]}`;
  tips.set(key, `<div class="tip-name">${definition.name}${unit[U.VETERAN] ? ' · Veteran' : ''}
    <small>${state}</small></div>`);
  const spent = !glyph && !(unit[U.MOVES] > 0);
  return `<button class="mate${spent ? ' spent' : ''}" data-unit="${unit[U.ID]}" data-tip="${key}"
      aria-label="${definition.name} — ${state}" style="background:${player(unit[U.OWNER]).color}">
    <img src="${unitPicture(definition)}" alt="">${glyph ? `<span class="badge">${icon(glyph, 10, 2.2)}</span>` : ''}</button>`;
}

function stat(glyph, value, tip, key, tips) {
  tips.set(key, `<div class="tip-name">${tip}</div>`);
  return `<span class="unit-stat" data-tip="${key}">${icon(glyph, 15)}${value}</span>`;
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
  setTips(container, new Map());
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
  const tips = new Map();
  const definition = store.unitDefs[unit[U.TYPE]];
  const detail = play.detail && play.detail.id === unit[U.ID] ? play.detail : null;
  const list = queue();
  const position = list.findIndex((other) => other[U.ID] === unit[U.ID]);

  let doing = TASK[unit[U.TASK]] || STATE[unit[U.ORDER]] || '';
  if (detail && detail.work_turns) {
    doing = `${LOOK[unit[U.ORDER]][0]} · turn ${detail.work} of ${detail.work_turns}`;
  }
  const below = [];
  if (detail && detail.home) {
    tips.set('home', '<div class="tip-name">Home city</div>');
    below.push(`<span class="home" data-tip="home">${icon('home', 12)}${detail.home}</span>`);
  }
  if (doing) below.push(`<span>${doing}</span>`);

  const stats = [
    stat('sword', definition.attack, `Attack ${definition.attack}`, 'attack', tips),
    stat('shield', definition.defense, `Defence ${definition.defense}`, 'defence', tips),
    detail
      ? stat('boot', `${movesShort(detail.moves_left)}/${movesShort(detail.full_moves)}`,
        `${movesText(detail.moves_left)} left of ${movesLabel(detail.full_moves)}`, 'moves', tips)
      : stat('boot', movesShort(unit[U.MOVES]), `${movesText(unit[U.MOVES])} left`, 'moves', tips),
  ];
  if (detail && detail.fuel !== null) {
    stats.push(stat('fuel', detail.fuel, `Fuel for ${plural(detail.fuel, 'turn')}`, 'fuel', tips));
  }
  if (detail && detail.capacity) {
    stats.push(stat('anchor', `${detail.cargo.length}/${detail.capacity}`,
      `${detail.cargo.length} of ${detail.capacity} aboard`, 'cargo', tips));
  }

  const others = detail ? detail.stack.filter((other) => other[U.ID] !== unit[U.ID]) : [];
  let mates = others.slice(0, MATES).map((other) => mate(other, tips)).join('');
  if (others.length > MATES) {
    const rest = others.slice(MATES).map((other) => store.unitDefs[other[U.TYPE]].name);
    tips.set('more', `<div class="tip-name">${rest.join(', ')}</div>`);
    mates += `<span class="mate more" data-tip="more">+${rest.length}</span>`;
  }

  const counter = position >= 0 ? `${position + 1}/${list.length}` : `–/${list.length}`;
  tips.set('queue', `<div class="tip-name">${position >= 0 ? `Unit ${position + 1} of ${list.length}`
    : `${plural(list.length, 'unit')} waiting`}</div>`);
  tips.set('wait', '<div class="tip-name">Wait<span class="kbd">W</span><small>Come back to this unit later</small></div>');
  tips.set('skip', '<div class="tip-name">Skip turn<span class="kbd">Space</span><small>No orders this turn</small></div>');

  container.innerHTML = `
    <div class="unit-who">
      ${portrait(unit)}
      <div class="titles">
        <h2>${definition.name}${unit[U.VETERAN] ? `<span class="vet" data-tip="vet">${icon('rank', 16, 2)}</span>` : ''}</h2>
        ${below.length ? `<span class="sub">${below.join('<i>·</i>')}</span>` : ''}
      </div>
    </div>
    <div class="unit-group unit-stats">${stats.join('')}</div>
    <div class="unit-group unit-orders">${detail ? detail.orders.map((order) => orderButton(order, tips)).join('') : '<span class="sub">…</span>'}</div>
    <span class="spacer"></span>
    ${mates ? `<div class="mates">${mates}</div>` : ''}
    <div class="unit-group unit-turn">
      <span class="queue" data-tip="queue">${counter}</span>
      <button class="unit-order" data-wait data-tip="wait" aria-label="Wait">${icon('clock', 18)}<span class="key">W</span></button>
      <button class="unit-order" data-skip data-tip="skip" aria-label="Skip turn">${icon('skip', 18)}<span class="key">Spc</span></button>
    </div>`;
  if (unit[U.VETERAN]) tips.set('vet', '<div class="tip-name">Veteran</div>');
  setTips(container, tips);

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
