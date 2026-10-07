// Play mode: the units of the person, the orders it gives them, the end of its turn.
//
// The rules stay on the server: this module sends orders and shows what comes back. Which
// unit is waiting for orders and which ones were told to wait is the person's own
// bookkeeping, and lives here.

import { send } from './net.js';
import { store, on, emit, U, leader, tileIndex, plural } from './state.js';

export const play = {
  unit: null,           // id of the active unit
  detail: null,         // its detail from the server, with the orders it can take
  mode: null,           // 'goto' while the person picks a destination
  preview: null,        // what the server says a move to the hovered tile would do
  hovered: null,        // "x,y" of the tile the preview was asked for
  waiting: false,       // the turn was ended: the other civilizations are playing
  skipped: new Set(),   // units left alone until the next turn (Space)
  later: [],            // units sent to the back of the queue (W)
  endAsked: 0,          // when Enter was first pressed while units still waited
  disbandAsked: 0,
  queued: 0,            // units that were waiting for orders after the last order
  ending: false,        // the last unit has its orders: the turn is about to end by itself
  carry: null,          // events of the order that ended the turn, told again at the next one
};
const AUTO_END_MS = 450;        // time to see the last move before the others play

const WORK = ['road', 'railroad', 'irrigate', 'mine', 'fortress', 'clean'];
// Key -> the orders it gives, the first one the unit can take wins.
const KEYS = {
  b: ['found_city', 'join_city'], r: ['road', 'railroad'], i: ['irrigate'], m: ['mine'],
  f: ['fortify', 'fortress'], p: ['clean'], s: ['sentry'], g: ['goto'], x: ['explore'],
  a: ['auto_work'], h: ['home'], u: ['disembark', 'board'], k: ['help_wonder'],
  t: ['trade_route'], v: ['wake', 'stop'],
};
const STEPS = {
  ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0],
  Numpad8: [0, -1], Numpad2: [0, 1], Numpad4: [-1, 0], Numpad6: [1, 0],
  Numpad7: [-1, -1], Numpad9: [1, -1], Numpad1: [-1, 1], Numpad3: [1, 1],
  Home: [-1, -1], PageUp: [1, -1], End: [-1, 1], PageDown: [1, 1],
};

// ── The units and their queue ───────────────────────────────────────────────

export function myUnits() {
  const me = leader();
  return me === null ? [] : store.state.units.filter((unit) => unit[U.OWNER] === me);
}

export function unitById(id) {
  return store.state.units.find((unit) => unit[U.ID] === id) || null;
}

export function activeUnit() {
  return play.unit === null ? null : unitById(play.unit);
}

function awaitsOrders(unit) {
  return unit[U.MOVES] > 0 && unit[U.ORDER] === 'none' && !unit[U.TASK]
    && !play.skipped.has(unit[U.ID]);
}

// The units waiting for orders, those sent to the back last.
export function queue() {
  const rank = (unit) => play.later.indexOf(unit[U.ID]);
  return myUnits().filter(awaitsOrders).sort((a, b) => rank(a) - rank(b) || a[U.ID] - b[U.ID]);
}

function syncHud() {
  const unit = play.waiting ? null : activeUnit();     // nobody to give orders to meanwhile
  const preview = play.preview;
  store.hud.unit = unit;
  store.hud.route = null;
  store.hud.target = null;
  if (unit && preview && preview.unit === unit[U.ID]) {
    if (preview.kind === 'route' && play.mode === 'goto') store.hud.route = preview.steps;
    if (preview.kind === 'attack' || preview.kind === 'capture') {
      store.hud.target = { x: preview.x, y: preview.y };
    }
  }
  const going = play.detail && play.detail.id === play.unit ? play.detail.destination : null;
  if (unit && going && !store.hud.route) store.hud.target = { x: going[0], y: going[1], goal: true };
}

export function activate(id, focus = true) {
  play.unit = id;
  play.detail = null;
  play.mode = null;
  play.preview = null;
  play.hovered = null;
  syncHud();
  if (id !== null) {
    send({ cmd: 'unit', id });
    const unit = unitById(id);
    if (unit && focus) emit('focus', { x: unit[U.X], y: unit[U.Y] });
  }
  emit('play');
}

export function next() {
  const list = queue();
  const following = list.find((unit) => unit[U.ID] !== play.unit) || list[0] || null;
  activate(following ? following[U.ID] : null);
}

export function wait() {
  if (play.unit === null) return;
  play.later = play.later.filter((id) => id !== play.unit).concat(play.unit);
  next();
}

export function skip() {
  if (play.unit === null) return;
  play.skipped.add(play.unit);
  next();
  settle();
}

// What the person must decide before its turn can end: peace proposals to answer, research
// to choose, cities with nothing to build. One list for the Turn panel, the End turn
// buttons and the automatic end of turn.
export function decisions() {
  const me = store.state && store.state.me;
  if (leader() === null || !me) return [];
  const list = [];
  for (const id of me.proposals) {
    list.push({ kind: 'proposal', id, glyph: 'scroll',
      text: `The ${store.state.players[id].nation} propose peace`,
      detail: 'Accept or refuse their treaty' });
  }
  if (me.researching === null && me.research_options.length) {
    list.push({ kind: 'research', glyph: 'flask', text: 'Choose what to research',
      detail: `${plural(me.research_options.length, 'advance')} within reach` });
  }
  for (const city of store.state.cities) {
    if (city.owner !== me.id || !city.idle) continue;
    list.push({ kind: 'city', id: city.id, glyph: 'city',
      text: `${city.name} needs something to build`,
      detail: city.completed ? `${city.completed} is finished` : 'Nothing in production' });
  }
  return list;
}

export function pendingDecisions() {
  return decisions().length;
}

// Why the turn cannot be ended yet, for the tooltip of the End turn buttons ('' when it can).
export function whyNotEnd() {
  const waiting = decisions();
  if (!waiting.length) return '';
  return `Decide first:\n${waiting.map((decision) => `• ${decision.text}`).join('\n')}`;
}

// As in the original game, the turn ends by itself once the last unit has its orders,
// unless a decision is still waiting. A turn with no unit to move is ended by the person:
// only an order that empties the queue ends the turn.
function settle(events = []) {
  const before = play.queued;
  play.queued = queue().length;
  if (before === 0 || play.queued > 0 || play.waiting || play.ending || pendingDecisions()) return;
  const turn = `${store.state.seed}:${store.state.turn}`;
  play.ending = true;
  play.carry = events;
  emit('play');
  setTimeout(() => {
    play.ending = false;
    const same = store.state && `${store.state.seed}:${store.state.turn}` === turn;
    if (leader() !== null && same && !play.waiting && !queue().length && !pendingDecisions()) {
      finishTurn();
    } else {
      play.carry = null;
      emit('play');
    }
  }, AUTO_END_MS);
}

// ── Orders ──────────────────────────────────────────────────────────────────

function act(action, fields) {
  send({ cmd: 'action', action, ...fields });
}

export function setMode(mode) {
  play.mode = mode;
  play.preview = null;
  play.hovered = null;
  syncHud();
  emit('play');
}

// Gives the active unit one of the orders the server listed for it.
export function give(order) {
  const unit = play.unit;
  if (unit === null || play.waiting) return;
  if (order.id === 'goto') {
    setMode(play.mode === 'goto' ? null : 'goto');
  } else if (order.id === 'explore' || order.id === 'auto_work' || order.id === 'stop') {
    const mode = { explore: 'explore', auto_work: 'work', stop: 'none' }[order.id];
    send({ cmd: 'automate', unit, mode });
  } else if (order.id === 'wake') {
    act('order', { unit, order: 'none' });
  } else if (order.id === 'fortify' || order.id === 'sentry' || WORK.includes(order.id)) {
    act('order', { unit, order: order.id });
  } else if (order.id === 'board') {
    act('board', { unit, ship: order.ship });
  } else if (order.id === 'disband') {
    if (Date.now() - play.disbandAsked > 4000) {
      play.disbandAsked = Date.now();
      emit('notice', { text: 'Disband this unit for good? Ask again to confirm.', ok: false });
      return;
    }
    play.disbandAsked = 0;
    act('disband', { unit });
  } else {
    act(order.id, { unit });        // found_city, join_city, home, disembark, help_wonder…
  }
}

// The key that gives an order to the active unit, if any ("B", "R"…).
export function keyOf(orderId) {
  const available = play.detail ? play.detail.orders.map((order) => order.id) : [];
  for (const [key, ids] of Object.entries(KEYS)) {
    if (ids.find((id) => available.includes(id)) === orderId) return key.toUpperCase();
  }
  return orderId === 'disband' ? 'Shift D' : '';
}

function step(dx, dy) {
  const unit = activeUnit();
  if (!unit || play.waiting) return;
  const y = unit[U.Y] + dy;
  if (y < 0 || y >= store.map.height) return;
  const w = store.map.width;
  act('move', { unit: unit[U.ID], x: (((unit[U.X] + dx) % w) + w) % w, y });
}

export function endTurn() {
  if (leader() === null || play.waiting) return;
  const waiting = decisions();
  if (waiting.length) {
    const others = waiting.length > 1 ? `, and ${plural(waiting.length - 1, 'other decision')}` : '';
    emit('notice', { text: `${waiting[0].text}${others}: decide before ending the turn.`, ok: false });
    return;
  }
  const left = queue().length;
  if (left && Date.now() - play.endAsked > 4000) {
    play.endAsked = Date.now();
    emit('notice', { text: `${plural(left, 'unit')} still await${left === 1 ? 's' : ''} orders. `
      + 'End the turn again to confirm.', ok: false });
    if (play.unit === null) next();
    return;
  }
  play.endAsked = 0;
  play.carry = null;
  finishTurn();
}

function finishTurn() {
  play.waiting = true;
  play.mode = null;
  play.preview = null;
  syncHud();
  // The turn is named: a second window on the same game cannot end the next one by accident.
  send({ cmd: 'end_turn', turn: store.state.turn });
  emit('play');
}

// ── Keyboard ────────────────────────────────────────────────────────────────

// Returns true when the key was an order of the person.
export function handleKey(e) {
  if (leader() === null) return false;
  if (e.key === 'Enter') {
    endTurn();
    return true;
  }
  if (e.key === 'Escape' && play.mode) {
    setMode(null);
    return true;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  const direction = STEPS[e.code] || STEPS[e.key];
  if (direction && play.unit !== null) {
    step(...direction);
    return true;
  }
  const key = e.key.toLowerCase();
  if (key === ' ') {
    skip();
    return true;
  }
  if (key === 'w') {
    wait();
    return true;
  }
  if (key === 'c') {
    const unit = activeUnit();
    if (unit) emit('center', { x: unit[U.X], y: unit[U.Y] });
    return true;
  }
  if (!play.detail || play.detail.id !== play.unit) return false;
  if (key === 'd' && e.shiftKey) {
    give({ id: 'disband' });
    return true;
  }
  for (const id of KEYS[key] || []) {
    const order = play.detail.orders.find((candidate) => candidate.id === id);
    if (order) {
      give(order);
      return true;
    }
  }
  return false;
}

// ── The map ─────────────────────────────────────────────────────────────────

function adjacent(unit, tile) {
  const w = store.map.width;
  const dx = Math.abs(unit[U.X] - tile.x);
  return Math.min(dx, w - dx) <= 1 && Math.abs(unit[U.Y] - tile.y) <= 1
    && (unit[U.X] !== tile.x || unit[U.Y] !== tile.y);
}

function goTo(unit, tile) {
  send({ cmd: 'goto', unit: unit[U.ID], x: tile.x, y: tile.y });
  setMode(null);
}

// A click on the map. Returns true when it was an order (or a selection) of the person.
export function clickTile(tile) {
  const me = leader();
  if (me === null || play.waiting) return false;
  const unit = activeUnit();
  if (play.mode === 'goto' && unit) {
    goTo(unit, tile);
    return true;
  }
  const index = tileIndex(tile.x, tile.y);
  const city = store.cityAt.get(index);
  if (city) return false;                        // the city panel opens (main.js)
  const mine = (store.unitsAt.get(index) || []).filter((other) => other[U.OWNER] === me);
  if (mine.length) {
    // Clicking a stack again goes through its units.
    const at = mine.findIndex((other) => other[U.ID] === play.unit);
    activate(mine[(at + 1) % mine.length][U.ID], false);
    return true;
  }
  if (unit && unit[U.MOVES] > 0 && adjacent(unit, tile)) {
    act('move', { unit: unit[U.ID], x: tile.x, y: tile.y });
    return true;
  }
  return false;
}

// A right click: the active unit goes there (one step, or a journey).
export function sendTo(tile) {
  const unit = activeUnit();
  if (leader() === null || play.waiting || !unit) return false;
  if (adjacent(unit, tile)) act('move', { unit: unit[U.ID], x: tile.x, y: tile.y });
  else goTo(unit, tile);
  return true;
}

// The pointer is over a tile: asks the server what going there would do, when it matters.
export function hoverTile(tile) {
  const unit = activeUnit();
  const key = tile ? `${tile.x},${tile.y}` : null;
  if (key === play.hovered) return;
  play.hovered = key;
  if (!unit || !tile || play.waiting) return;
  const index = tileIndex(tile.x, tile.y);
  const foreign = (store.unitsAt.get(index) || []).some((other) => other[U.OWNER] !== unit[U.OWNER]);
  const strangerCity = store.cityAt.get(index) && store.cityAt.get(index).owner !== unit[U.OWNER];
  if (play.mode === 'goto' || (adjacent(unit, tile) && (foreign || strangerCity))) {
    send({ cmd: 'preview', unit: unit[U.ID], x: tile.x, y: tile.y });
  } else if (play.preview) {
    play.preview = null;
    syncHud();
    emit('play-preview');
  }
}

// ── What the server answers ─────────────────────────────────────────────────

function reset() {
  play.unit = null;
  play.detail = null;
  play.mode = null;
  play.preview = null;
  play.hovered = null;
  play.waiting = false;
  play.skipped = new Set();
  play.later = [];
  syncHud();
}

on('init', () => {
  reset();
  play.carry = null;
  if (leader() !== null) next();
  play.queued = queue().length;
});

on('turn', () => {
  if (leader() === null) return;
  reset();
  next();
  play.queued = queue().length;
});

on('update', (message) => {
  if (leader() === null) return;
  if (!message.ok && message.reason) {
    emit('notice', { text: message.reason[0].toUpperCase() + message.reason.slice(1), ok: false });
  }
  if (message.unit === play.unit && message.unit_detail) play.detail = message.unit_detail;
  const unit = activeUnit();
  // The active unit is gone, spent, or busy with what it was just told: on to the next one.
  if (play.unit !== null && (!unit || (message.unit === play.unit && message.ok && !awaitsOrders(unit)))) {
    next();
  } else if (play.unit === null && queue().length) {
    next();
  } else {
    play.preview = null;
    play.hovered = null;
    syncHud();
    emit('play');
  }
  settle(message.events);
});

on('unit', (detail) => {
  if (detail.id !== play.unit) return;
  play.detail = detail;
  syncHud();
  emit('play');
});

on('preview', (preview) => {
  if (preview.unit !== play.unit) return;
  play.preview = preview;
  syncHud();
  emit('play-preview');
});
