// "City" panel: what a city produces and how its citizens feel. For the observer, why the AI
// builds what it builds; for the person leading the city, the levers to manage it.
// The panel shows figures and bars; what they are made of is told by their tooltips.

import { store, U, player, leader, emit, inkOn, plural, turnsFor, queueGroups } from '../state.js';
import { send } from '../net.js';
import { icon, vetMark, specialistIcon } from '../icons.js';
import { setTips } from '../tips.js';
import { ORDER_MARK, TASK_MARK } from '../renderer/map.js';
import { unitImage } from '../renderer/sprites.js';
import { governmentName } from './civs.js';

const LAND = 450;           // pixels of the land view (css/style.css)
const FACE = {
  happy: ['var(--good)', 'M8.5 14c1 1.4 2.2 2 3.5 2s2.5 -.6 3.5 -2'],
  content: ['var(--soft)', 'M8.5 15h7'],
  unhappy: ['var(--bad)', 'M8.5 16c1-1.4 2.2-2 3.5-2s2.5 .6 3.5 2'],
};
const SPECIALIST_NOTE = { entertainer: '2 luxuries', taxman: '2 gold', scientist: '2 science' };
// What a unit is busy with, for its tooltip.
const DOING = {
  fortified: 'Fortified', fortify: 'Fortifying', sentry: 'On sentry duty', road: 'Building a road',
  railroad: 'Building a railroad', irrigate: 'Irrigating', mine: 'Digging a mine',
  fortress: 'Building a fortress', clean: 'Cleaning up pollution',
};
const TASKS = { goto: 'On its way', explore: 'Exploring by itself', work: 'Working by itself' };
let drawTile = null;        // (ctx, tx, ty, px, py, size): the map's own terrain drawing
let sellAsked = null;       // building the person was asked to confirm the sale of

export function setTileRenderer(renderer) {
  drawTile = renderer;
}

function signed(value) {
  return value ? `${value > 0 ? '+' : '−'}${Math.abs(value)}` : '0';
}

// What is taken away: "−3", or a plain "0".
function taken(value) {
  return value ? `−${value}` : '0';
}

function act(action, fields) {
  send({ cmd: 'action', action, ...fields });
}

// A figure followed by the icon of what it counts.
function amount(value, glyph, tone) {
  return `<span class="amount ${tone}">${value}${icon(glyph, 14, 2)}</span>`;
}

function gold(value) {
  return amount(value, 'coin', 'trade');
}

// ── Tooltips ────────────────────────────────────────────────────────────────

function tipTitle(html, aside = '') {
  return `<div class="tip-title">${html}${aside ? `<span class="mono">${aside}</span>` : ''}</div>`;
}

function tipRows(rows, fit = false) {
  if (!rows.length) return '';
  return `<dl class="tip-rows${fit ? ' fit' : ''}">${rows.map(([name, value]) =>
    `<dt>${name}</dt><dd>${value}</dd>`).join('')}</dl>`;
}

// What a bar is made of: [attributes of the color key, name, figure] for each of its parts.
function tipKeys(rows) {
  return `<div class="tip-keys">${rows.map(([key, name, figure]) =>
    `<i ${key}></i><span>${name}</span><b>${figure}</b>`).join('')}</div>`;
}

function tipSums(rows) {
  return `<dl class="tip-sums">${rows.map(([name, figure]) =>
    `<dt>${name}</dt><dd>${figure}</dd>`).join('')}</dl>`;
}

function tipStats(definition) {
  const stats = [['Attack', definition.attack], ['Defence', definition.defense], ['Moves', definition.moves]];
  return `<div class="tip-stats">${stats.map(([name, value]) =>
    `<div><span>${name}</span><b>${value}</b></div>`).join('')}</div>`;
}

function key(color, faint = false) {
  return `${faint ? 'class="faint" ' : ''}style="background:${color}"`;
}

// ── Citizens and land ───────────────────────────────────────────────────────

function citizens(stats, specialists, manage, size) {
  const faces = [];
  for (const mood of ['happy', 'content', 'unhappy']) {
    const [color, mouth] = FACE[mood];
    for (let i = 0; i < stats[mood]; i++) {
      faces.push(`<span class="face"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="${color}"
        stroke-width="1.6" stroke-linecap="round" role="img" aria-label="${mood} citizen">
        <circle cx="12" cy="12" r="9.5" fill="var(--raise)"/><path d="M9 10v.6M15 10v.6"/><path d="${mouth}"/></svg></span>`);
    }
  }
  const others = [];
  const canChange = manage && size >= store.rules.specialist_min_size;
  for (const kind of Object.keys(SPECIALIST_NOTE)) {
    for (let i = 0; i < (specialists[kind] || 0); i++) {
      others.push(canChange
        ? `<button class="specialist" data-specialist="${kind}" title="${kind}: ${SPECIALIST_NOTE[kind]} · click to change its job">${specialistIcon(kind)}</button>`
        : `<span class="specialist" title="${kind}: ${SPECIALIST_NOTE[kind]}">${specialistIcon(kind)}</span>`);
    }
  }
  // One line: when it runs short, every citizen overlaps the one before by the same amount.
  return faces.join('') + (faces.length && others.length ? '<span class="sep"></span>' : '') + others.join('');
}

// The food, shield and trade icons (icons.js) drawn on the land: filled, with a dark halo so
// they read on any terrain, each in a box that fits its shape. Overlapping, a pictogram is cut
// out of the one below by a ring of the pad's colour; the open trade arrows by a square.
const PICTO = {
  food: { box: '3.5 4 18 18', solid: '<path d="M12 12c0-4 3-6.5 8-6.5 0 4.5-3 7-8 6.5z"/><path d="M12 15c0-3-2.5-5-7-5 0 3.5 2.5 5.5 7 5z"/>', line: '<path d="M12 21v-9"/>' },
  shield: { box: '2.5 2.5 19 19', solid: '<path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z"/>', line: '' },
  trade: { box: '2 2 20 20', solid: '', line: '<path d="M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4"/>', cut: '<rect x="3" y="3" width="18" height="18" rx="3"/>' },
};
// In pixels of a 90 px tile (css/style.css scales them with the land view): 18 px pictograms in
// the 84 px a pad leaves. In a packet of one resource they overlap by about a third, less for
// the open arrows; 3 px between packets, which tighten by up to 3 px a pictogram to keep one line.
const PICTO_SIZE = 18;
const PAD_ROOM = 84;
const PACKED = { food: 12, shield: 11, trade: 14 };
const APART = 3;
const SQUEEZE = 3;

function picto(kind, shift) {
  const shape = PICTO[kind];
  const cut = !shift ? '' : shape.cut ? `<g class="cut box">${shape.cut}</g>` : `<g class="cut">${shape.solid}${shape.line}</g>`;
  const style = shift ? ` style="margin-left:calc(${shift.toFixed(1)} * var(--u))"` : '';
  return `<svg class="land-glyph ${kind}" viewBox="${shape.box}"${style} aria-hidden="true">${cut}`
    + `<g class="halo">${shape.solid}</g><g class="halo line">${shape.line}</g>`
    + `<g class="tone">${shape.solid}</g><g class="tone line">${shape.line}</g></svg>`;
}

// n pictograms of one resource, `step` px apart; a packet wider than the pad is squeezed to fit.
function packet(kind, n, step, gap) {
  const s = n > 1 ? Math.min(step, (PAD_ROOM - PICTO_SIZE) / (n - 1)) : 0;
  const icons = Array.from({ length: n }, (_, i) => picto(kind, i ? s - PICTO_SIZE : 0));
  return `<span class="packet"${gap ? ` style="margin-left:calc(${gap} * var(--u))"` : ''}>${icons.join('')}</span>`;
}

// Packets on one line, tightened a little when they run short; null when they do not fit.
function packedLine(groups) {
  const joints = groups.reduce((sum, [, n]) => sum + n - 1, 0);
  const width = groups.reduce((w, [kind, n], i) => w + PICTO_SIZE + PACKED[kind] * (n - 1) + (i ? APART : 0), 0);
  const squeeze = width > PAD_ROOM && joints ? (width - PAD_ROOM) / joints : 0;
  if (width > PAD_ROOM && groups.length > 1 && (!joints || squeeze > SQUEEZE)) return null;
  return {
    width: Math.min(width, PAD_ROOM),
    html: groups.map(([kind, n], i) => packet(kind, n, PACKED[kind] - squeeze, i ? APART : 0)).join(''),
  };
}

// Every way to cut a list into consecutive parts.
function splits(list) {
  if (list.length <= 1) return [[list]];
  const out = [[list]];
  for (let i = 1; i < list.length; i++) {
    for (const rest of splits(list.slice(i))) out.push([list.slice(0, i), ...rest]);
  }
  return out;
}

// One pictogram per point, as in Civ 1: food, shields then trade, each resource a packet, on
// as few lines as fit, the most even first. A line never cuts a packet.
function yieldPad(yields) {
  const groups = ['food', 'shield', 'trade'].map((kind, i) => [kind, yields[i]]).filter(([, n]) => n > 0);
  if (!groups.length) return '';
  let best = null;
  for (const split of splits(groups)) {
    const lines = split.map(packedLine);
    if (lines.some((line) => !line)) continue;
    const widest = Math.max(...lines.map((line) => line.width));
    if (!best || lines.length < best.lines.length || (lines.length === best.lines.length && widest < best.widest)) {
      best = { lines, widest };
    }
  }
  return `<span class="land-pad">${best.lines.map((line) => `<span class="land-line">${line.html}</span>`).join('')}</span>`;
}

function landGrid(detail, owner, manage) {
  const byOffset = new Map(detail.tiles.map((t) => [`${t.dx},${t.dy}`, t]));
  const workable = manage ? new Set(manage.workable.map(([dx, dy]) => `${dx},${dy}`)) : null;
  const cells = [];
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      const tile = byOffset.get(`${dx},${dy}`);
      if (!tile) {
        cells.push('<div class="land-cell blank"></div>');
        continue;
      }
      const index = tile.y * store.map.width + tile.x;
      const terrain = store.terrains[store.map.terrain[index]];
      const center = dx === 0 && dy === 0;
      const classes = ['land-cell'];
      if (tile.worked) classes.push('worked');
      if (center) classes.push('center');
      // With culture, the city works only tiles inside the borders of its civilization.
      const outside = 'owner' in tile && tile.owner !== detail.owner;
      const border = !outside ? ''
        : tile.owner === null ? ' — outside the borders, culture will claim it'
          : ` — ${player(tile.owner).nation} territory`;
      if (outside) classes.push(tile.owner === null ? 'outside' : 'taken');
      // The city square as on the map, its size above the yields of its tile.
      const mark = center ? `<span class="city-square" style="background:${owner.color}"></span>`
        + `<span class="city-size" style="color:${inkOn(owner.color)}">${detail.size}</span>` : '';
      // Only the worked tiles show what they yield.
      const yields = center || tile.worked ? yieldPad(tile.yields) : '';
      if (!manage) {
        cells.push(`<div class="${classes.join(' ')}" title="${terrain.name}${tile.worked ? ' — worked' : border}">${mark}${yields}</div>`);
        continue;
      }
      // The person moves its citizens by clicking: the centre hands the city back to its mayor.
      const usable = center || tile.worked || workable.has(`${dx},${dy}`);
      const title = center ? 'Let the mayor place the citizens'
        : tile.worked ? `${terrain.name} — worked · click to free its citizen`
          : usable ? `${terrain.name} · click to work this tile`
            : `${terrain.name}${border || ' — taken by another city or an enemy'}`;
      if (!usable && !outside) classes.push('taken');
      cells.push(`<button class="${classes.join(' ')}" data-dx="${dx}" data-dy="${dy}" title="${title}"
        aria-pressed="${tile.worked}" ${usable ? '' : 'disabled'}>${mark}${yields}</button>`);
    }
  }
  return `<div class="land${manage ? ' manage' : ''}"><canvas id="city-land"></canvas><div class="land-grid">${cells.join('')}</div></div>`;
}

function paintLand(container, detail) {
  const canvas = container.querySelector('#city-land');
  if (!canvas || !drawTile) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = LAND * ratio;
  canvas.height = LAND * ratio;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const size = LAND / 5;
  const reach = new Set(detail.tiles.map((t) => `${t.dx},${t.dy}`));
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      // The corners are out of the city's reach: no terrain.
      if (!reach.has(`${dx},${dy}`)) continue;
      drawTile(ctx, detail.x + dx, detail.y + dy, (dx + 2) * size, (dy + 2) * size, size);
    }
  }
}

// ── Units ───────────────────────────────────────────────────────────────────

function spriteBox(definition, color) {
  return `<span class="unit-card small" style="background:${color}">${unitImage(definition)}</span>`;
}

// A unit drawn as on the map: heavy outline when fortified, hatched on sentry, a letter for
// what it is doing (with the turns its work still takes), another for what it was left to do
// by itself, a gold dot for a veteran.
// `click` is what a click on the card does: 'orders' activates the unit, 'center' centres
// the map on it, nothing otherwise.
function unitCard(unit, tip, click, count) {
  const definition = store.unitDefs[unit[U.TYPE]];
  const order = unit[U.ORDER];
  const classes = ['unit-card'];
  if (order === 'fortified' || order === 'fortify') classes.push('fortified');
  if (order === 'sentry') classes.push('sentry');
  const mark = ORDER_MARK[order];
  const task = TASK_MARK[unit[U.TASK]];
  const inner = unitImage(definition)
    + (mark ? `<span class="mark">${mark}${unit[U.WORK_LEFT] ? `<small>${unit[U.WORK_LEFT]}</small>` : ''}</span>` : '')
    + (task ? `<span class="mark task">${task}</span>` : '')
    + (unit[U.VETERAN] ? '<i class="vet"></i>' : '')
    + (count > 1 ? `<span class="count">${count}</span>` : '');
  const name = `${definition.name}${count > 1 ? ` ×${count}` : ''}`;
  const attributes = `class="${classes.join(' ')}" style="background:${player(unit[U.OWNER]).color}" data-tip="${tip}"`;
  if (click === 'orders') {
    return `<button ${attributes} data-unit="${unit[U.ID]}" aria-label="${name}: give it orders">${inner}</button>`;
  }
  if (click === 'center') {
    return `<button ${attributes} data-x="${unit[U.X]}" data-y="${unit[U.Y]}" aria-label="${name}: centre the map on it">${inner}</button>`;
  }
  return `<span ${attributes} role="img" aria-label="${name}">${inner}</span>`;
}

// "Building a road by itself, 2 turns left", "On sentry duty"...
function doingText(unit) {
  if (unit[U.ABOARD]) return 'Aboard a ship';
  const doing = DOING[unit[U.ORDER]];
  if (doing && unit[U.WORK_LEFT]) {
    return `${doing}${unit[U.TASK] ? ' by itself' : ''}, ${plural(unit[U.WORK_LEFT], 'turn')} left`;
  }
  return TASKS[unit[U.TASK]] || doing;
}

function unitTip(unit, count, rows) {
  const definition = store.unitDefs[unit[U.TYPE]];
  const doing = doingText(unit);
  const title = `${spriteBox(definition, player(unit[U.OWNER]).color)}<span>${definition.name}${
    unit[U.VETERAN] ? vetMark() : ''}</span>`;
  return tipTitle(title, count > 1 ? `×${count}` : '') + tipStats(definition)
    + tipRows(doing ? [['Orders', doing], ...rows] : rows, true);
}

// What a unit costs its city each turn, an icon a point as in the original game: nothing
// under a unit the city keeps for free.
function costPips([shields, food, unhappy]) {
  const pips = (count, glyph, tone) =>
    (count ? `<span class="${tone}">${icon(glyph, 12, 2).repeat(count)}</span>` : '');
  return `<span class="pips">${pips(shields, 'shield', 'shield')}${pips(food, 'food', 'food')}${
    pips(unhappy, 'unhappy', 'bad')}</span>`;
}

// The same, for the tooltip of the unit.
function costRows(unit, [shields, food, unhappy]) {
  const paid = [shields && amount(shields, 'shield', 'shield'), food && amount(food, 'food', 'food')]
    .filter(Boolean).join(' ');
  const kept = store.unitDefs[unit[U.TYPE]].needs_support && !shields;
  const upkeep = paid ? `${paid} <span class="soft">per turn</span>`
    : kept ? 'Kept for free' : '<span class="soft">None</span>';
  const rows = [['Upkeep', upkeep]];
  if (unhappy) rows.push(['Unhappy', `${amount(unhappy, 'unhappy', 'bad')} <span class="soft">citizens</span>`]);
  return rows;
}

// The units of a list, as cards. The person picks one to give it orders, so each has its
// own; otherwise the units alike share a card. `about(unit)` gives the rows of the tooltip.
// With `costs` (unit id -> [shields, food, unhappy]), each unit has its card, its costs under it.
function unitTray(units, tips, prefix, about, click, costs = null) {
  if (!units.length) return '<span class="muted">None</span>';
  const groups = new Map();
  for (const unit of units) {
    const rows = about(unit);
    const alike = click === 'orders' || costs ? unit[U.ID]
      : [unit[U.TYPE], unit[U.ORDER], unit[U.VETERAN], unit[U.ABOARD], JSON.stringify(rows)].join('|');
    if (!groups.has(alike)) groups.set(alike, { unit, rows, count: 0 });
    groups.get(alike).count += 1;
  }
  const cards = [...groups.values()].map(({ unit, rows, count }) => {
    const tip = `${prefix}:${unit[U.ID]}`;
    tips.set(tip, unitTip(unit, count, rows));
    const card = unitCard(unit, tip, click, count);
    return costs ? `<div class="unit-slot">${card}${costPips(costs[unit[U.ID]])}</div>` : card;
  });
  return `<div class="unit-tray">${cards.join('')}</div>`;
}

// ── Bars ────────────────────────────────────────────────────────────────────

// A stock filling up to `full`: what is there, then what the next turn brings (or takes).
function stock(have, next, full, color) {
  if (!full) return '<div class="stock"></div>';
  const share = (value) => `${Math.max(0, Math.min(100, 100 * value / full))}%`;
  const kept = Math.max(0, Math.min(have, have + next));
  const parts = [];
  if (kept > 0) parts.push(`<span style="width:${share(kept)};background:${color}"></span>`);
  if (have > kept) parts.push(`<span class="lose" style="width:${share(have - kept)}"></span>`);
  if (next > 0 && have < full) {
    parts.push(`<span class="next" style="width:${share(Math.min(next, full - have))};background:${color}"></span>`);
  }
  return `<div class="stock">${parts.join('')}</div>`;
}

// Turns left, or why there is no saying.
function eta(turns, never, tone = 'bad') {
  if (turns === null) return `<span class="eta ${tone}">${never}</span>`;
  const count = Math.max(1, turns);
  return `<span class="eta"><b>${count}</b> turn${count === 1 ? '' : 's'}</span>`;
}

// One part of what the turn makes, as wide as its share.
function part(tone, share, glyph, figure) {
  return `<span class="part tag ${tone}" style="flex-grow:${share}">${icon(glyph, 13, 2)}${figure}</span>`;
}

function made(figure, glyph) {
  return `<span class="made"><b>${figure}</b>${icon(glyph, 14, 2)}</span>`;
}

function ledgerRow(glyph, tone, name, value, valueTone, detail, tip = '') {
  return `<div class="ledger-row"${tip ? ` data-tip="${tip}"` : ''}>
    <span class="icon-box ${tone}">${icon(glyph, 18, 1.9)}</span><span class="what">${name}</span>
    <span class="value ${valueTone}">${value}</span><div class="detail">${detail}</div></div>`;
}

// The "We love the King" day: the city celebrates, or starts or stops at the end of the turn,
// and what it brings under the government.
function celebrationState(c, s, owner, tips) {
  const party = c.celebration;
  const label = !party.next ? 'Celebration ends' : party.now ? 'Celebrating' : 'Celebration next turn';
  const foot = !party.next ? 'The city no longer meets the condition: the celebration stops at the end of this turn.'
    : party.now ? '' : 'The celebration starts at the end of this turn.';
  tips.set('celebration', tipTitle(`<span>'We love the ${party.title}' day</span>`, governmentName(owner.government))
    + tipRows([
      ['Needs', `${Math.ceil(c.size / 2)} happy, none unhappy`],
      ['Now', `${s.happy} happy, ${s.unhappy} unhappy`],
      ['Effect', party.effect || 'None under this government'],
    ])
    + (foot ? `<div class="tip-foot">${foot}</div>` : ''));
  return `<span class="city-state ${party.next ? 'gold' : 'ends'}" data-tip="celebration">${label}</span>`;
}

// Food, shields, trade and pollution: the surplus, then where what is made goes.
function ledger(c, tips) {
  const s = c.stats;
  const rows = [];

  // Food: the box filling up until the city grows, or a celebration making it grow each turn.
  const growth = turnsFor(c.food_box - c.food, s.food_surplus);
  const starving = s.food_surplus < 0;
  const famine = c.famine;
  const rapture = c.celebration?.growth_in;
  tips.set('food', tipTitle('<span>Food</span>', `box of ${c.food_box}`)
    + tipKeys([
      [key('var(--food)'), 'In the box', c.food],
      [key(starving ? 'var(--bad)' : 'var(--food)', !starving), 'Next turn', signed(s.food_surplus)],
      [key('var(--line)'), 'Before the city grows', Math.max(0, c.food_box - c.food - Math.max(0, s.food_surplus))],
    ])
    + tipSums([
      ['Produced', s.food],
      ['Eaten by the citizens', taken(s.food_eaten - s.food_settlers)],
      ['Eaten by Settlers', taken(s.food_settlers)],
    ])
    + (rapture ? `<div class="tip-foot">The celebration adds one citizen at the end of ${
      rapture === 1 ? 'each turn' : 'each turn from the next one'}, as long as some food is left over.</div>` : '')
    + (famine ? `<div class="tip-foot">The box runs out in ${plural(famine.turns, 'turn')}: the city then loses a
      citizen, or a Settlers unit it supports.</div>` : ''));
  // A city living on its box for long is not in danger yet: in red only when the famine is near.
  const due = famine ? `<span class="eta famine${famine.near ? ' near' : ''}">famine in <b>${famine.turns}</b> turn${famine.turns === 1 ? '' : 's'}</span>`
    : rapture ? '<span class="eta party"><b>+1</b> per turn</span>' : eta(growth, 'no growth', 'none');
  rows.push(ledgerRow('food', 'food', 'Food', signed(s.food_surplus), !starving ? 'food' : famine.near ? 'bad' : 'warn',
    stock(c.food, s.food_surplus, c.food_box, 'var(--food)') + due, 'food'));

  // Shields: what is left for the production once the units are paid.
  const kept = Math.max(0, s.shield_surplus);
  tips.set('shields', tipTitle('<span>Shields</span>', `${s.shields} produced`)
    + tipKeys([
      [key('var(--shield)'), 'For the production', signed(s.shield_surplus)],
      [key('var(--line-3)'), 'Support of the units', taken(s.shield_upkeep)],
    ]));
  rows.push(ledgerRow('shield', 'shield', 'Shields', signed(s.shield_surplus),
    s.shield_surplus < 0 ? 'bad' : 'shield',
    `<div class="parts">${kept ? `<span class="part kept" style="flex-grow:${kept}"></span>` : ''}${
      s.shield_upkeep ? part('support', Math.max(1, Math.min(s.shield_upkeep, s.shields)), 'sword', s.shield_upkeep) : ''
    }</div>${made(s.shields, 'shield')}`, 'shields'));

  // Trade: what corruption leaves, shared between luxuries, taxes and science.
  const net = s.trade - s.corruption;
  const shares = [[s.luxury, 'lux', 'gem'], [s.tax, 'tax', 'coin'], [s.science, 'science', 'flask']]
    .filter(([figure]) => figure > 0)
    .map(([figure, tone, glyph]) => part(tone, figure, glyph, figure)).join('');
  tips.set('trade', tipTitle('<span>Trade</span>', `${s.trade} produced`)
    + tipKeys([
      [key('repeating-linear-gradient(135deg, #B8473F 0 2px, #5A2623 2px 4px)'), 'Lost to corruption', taken(s.corruption)],
      [key('#C79BF2'), 'Luxury', s.luxury],
      [key('var(--trade)'), 'Tax', s.tax],
      [key('var(--sci)'), 'Science', s.science],
    ]));
  rows.push(ledgerRow('trade', 'trade', 'Trade', signed(net), 'trade',
    `<div class="parts">${shares || net > 0 ? `<span class="parts" style="flex-grow:${Math.max(1, net)}">${shares}</span>` : ''}${
      s.corruption ? part('lost', s.corruption, 'lost', s.corruption) : ''
    }</div>${made(s.trade, 'trade')}`, 'trade'));

  // Culture, with culture rules: what it makes each turn and the next tile of its borders.
  if ('culture' in c) {
    const next = c.culture_next;
    const span = next === null ? 0 : next - c.culture_from;
    const turns = next === null ? null : turnsFor(next - c.culture, c.culture_rate);
    const full = c.land >= c.area;
    tips.set('culture', tipTitle('<span>Culture</span>', `${c.culture} in all`)
      + tipRows([
        ['Per turn', signed(c.culture_rate)],
        ['Territory', `${c.land} of the ${c.area} tiles around the city`],
        ['Beyond', `${c.beyond} of ${c.beyond_max} tiles`],
        ['Next tile', next === null ? (c.beyond >= c.beyond_max ? 'None: the borders are complete'
          : 'None: the rest is foreign territory or out of reach') : `at ${next} culture`],
      ])
      + '<div class="tip-foot">The culture of a city wins it the tiles of its outer ring one by one, the best free '
      + 'tile first, then beyond: the corners of its square and a third ring, the nearest first. Its citizens only '
      + 'work the territory of their civilization; nobody may found a city in it. Temples, Theatres, Museums and '
      + 'wonders add culture; a city in disorder makes none.</div>');
    const due = next === null ? `<span class="eta none">${c.beyond >= c.beyond_max ? 'complete' : 'blocked'}</span>`
      : eta(turns, 'never', 'none');
    rows.push(ledgerRow('mask', 'culture', 'Culture', signed(c.culture_rate), 'culture',
      (next === null ? '<div class="stock"></div>' : stock(c.culture - c.culture_from, c.culture_rate, span, 'var(--culture)'))
      + due + `<span class="made"><b>${c.land}</b>/${c.area}</span>`, 'culture'));
  }

  // Pollution, once the city gives off more than the land takes.
  const fumes = c.pollution;
  if (fumes && s.pollution > 0) {
    const given = fumes.industry + fumes.citizens;
    tips.set('pollution', tipTitle('<span>Pollution</span>', `${fumes.risk}% per turn`)
      + tipKeys([
        [key('var(--bad)'), 'Industry', fumes.industry],
        [key('#8C3B36'), 'Citizens', fumes.citizens],
        ['class="mark"', 'Tolerated', taken(fumes.tolerance)],
      ]));
    rows.push(ledgerRow('cloud', 'bad', 'Pollution', `${fumes.risk}%`, 'bad',
      `<div class="parts">${fumes.industry ? part('industry', fumes.industry, 'factory', fumes.industry) : ''}${
        fumes.citizens ? part('people', fumes.citizens, 'people', fumes.citizens) : ''}${
        fumes.tolerance < given ? `<i class="tolerated" style="left:${100 * fumes.tolerance / given}%"></i>` : ''
      }</div><span class="made"></span>`, 'pollution'));
  }

  if (c.trade_routes.length) {
    rows.push(ledgerRow('route', 'gold', 'Routes', c.trade_routes.length, '',
      `<span class="sub">${c.trade_routes.join(', ')}</span>`));
  }
  return `<div class="ledger">${rows.join('')}</div>`;
}

// ── Production ──────────────────────────────────────────────────────────────

// What the city is building, and how far it is.
function makingCard(c, manage, owner, tips, decided) {
  const s = c.stats;
  const building = c.production && (!manage || manage.current);
  const cost = building ? c.production_cost : null;

  let glyph = `<span class="making-icon">${icon('city', 22)}</span>`;
  if (building && c.item && c.item[0] === 'unit') {
    glyph = `<span class="making-icon" style="background:${owner.color}">
      ${unitImage(store.unitDefs[c.item[1]])}</span>`;
  } else if (building && c.item && store.buildingDefs[c.item[1]].wonder) {
    glyph = `<span class="making-icon">${icon('temple', 22)}</span>`;
  }

  let purchase = `<span class="sub">${c.buy_cost ? `Buy now ${gold(c.buy_cost)}` : decided}</span>`;
  if (manage && c.buy_cost && building) {
    purchase = manage.can_buy
      ? `<button class="btn small primary" id="city-buy">Buy · ${c.buy_cost}${icon('coin', 15, 2)}</button>`
      : `<button class="btn small" aria-disabled="true" title="Not enough gold, or already bought this turn">Buy · ${c.buy_cost}<span class="trade">${icon('coin', 15, 2)}</span></button>`;
  }

  let progress = '';
  if (cost) {
    const next = Math.max(0, Math.min(s.shield_surplus, cost - c.shields));
    tips.set('making', tipTitle(`<span>${c.production}</span>`, plural(cost, 'shield'))
      + tipKeys([
        [key('var(--shield)'), 'Gathered', c.shields],
        [key(s.shield_surplus < 0 ? 'var(--bad)' : 'var(--shield)', s.shield_surplus >= 0), 'Next turn', signed(s.shield_surplus)],
        [key('var(--line)'), 'Still to gather', Math.max(0, cost - c.shields - next)],
      ]));
    progress = `<div class="progress-row" data-tip="making">${stock(c.shields, s.shield_surplus, cost, 'var(--shield)')}${
      eta(turnsFor(cost - c.shields, s.shield_surplus), 'no progress')}</div>`;
  }

  return `
    <div class="card making">
      <div class="making-head">${glyph}
        <div class="titles"><span class="label">Building</span>
          <span class="big">${building ? c.production : '<span class="bad">Nothing</span>'}</span></div>
        ${purchase}</div>
      ${progress}
      ${manage ? queueRow(manage.queue, owner, tips) : ''}
    </div>`;
}

// What the city builds next, in order: one chip per item (the same unit several times in a
// row once, with its number), the turns before it is done, a cross to take one out.
function queueRow(queue, owner, tips) {
  const groups = queueGroups(queue);
  if (!groups.length) return '';
  const chips = groups.map((g) => {
    const unit = g.kind === 'unit' ? store.unitDefs[g.id] : null;
    const wonder = !unit && store.buildingDefs[g.id].wonder;
    const picture = unit
      ? `<span class="queue-pic" style="background:${owner.color}">${unitImage(unit)}</span>`
      : `<span class="queue-glyph">${icon(wonder ? 'temple' : 'city', 15)}</span>`;
    const when = g.turns === null ? '—' : g.turns;
    tips.set(`queue:${g.end}`, tipTitle(`<span>${g.name}${g.count > 1 ? ` ×${g.count}` : ''}</span>`,
      g.turns === null ? 'no progress' : `done in ${plural(g.turns, 'turn')}`));
    return `<span class="queue-chip" data-tip="queue:${g.end}">${picture}<b>${g.name}</b>${
      g.count > 1 ? `<span class="count">×${g.count}</span>` : ''}<span class="when">${when}</span>
      <button class="queue-drop" data-unqueue="${g.end}" aria-label="Take one ${g.name} out of the queue">${icon('close', 12, 2.4)}</button></span>`;
  });
  return `<div class="queue-row"><span class="label">Then</span><div class="queue-chips">${chips.join('')}</div></div>`;
}

// Why the AI builds what it builds (observer).
function decisionBlock(c, decided) {
  if (!c.decision) return '';
  const best = Math.max(0.001, ...c.decision.candidates.map((candidate) => candidate.score));
  const rows = c.decision.candidates.map((candidate, i) => `
    <div class="candidate${i === 0 ? ' chosen' : ''}">
      <span class="rank">${i + 1}</span>
      <div class="what">
        <span class="name">${candidate.name}<small>${candidate.kind}</small>${i === 0 ? '<em>Chosen</em>' : ''}</span>
        <span class="reason">${candidate.reason}</span>
      </div>
      <span class="turns">${candidate.turns ? plural(candidate.turns, 'turn') : '—'}</span>
      <div class="score"><span class="bar thin"><span style="width:${Math.max(2, 100 * candidate.score / best)}%"></span></span>
        <b>${Math.round(candidate.score * 10) / 10}</b></div>
    </div>`).join('');
  return `
    <div class="stack chooser">
      <div class="ai-title"><span class="ai-badge">AI</span><h2>Why this production</h2>
        <span class="sub">${decided}</span></div>
      <div class="option-list">${rows}</div>
    </div>`;
}

// What the person may have the city build: a name and the turns it takes.
function productionChooser(c, owner, tips) {
  const manage = c.manage;
  const surplus = c.stats.shield_surplus;
  const current = manage.current ? manage.current.join(':') : null;
  // Where each item stands in the queue (its places, from 1 = next) and when it is done.
  const queued = {};
  manage.queue.forEach((item, index) => {
    const key = `${item.kind}:${item.id}`;
    (queued[key] = queued[key] || []).push({ place: index + 1, turns: item.turns });
  });
  const groups = { Units: [], Buildings: [], Wonders: [] };
  for (const option of manage.options) {
    const unit = option.kind === 'unit' ? store.unitDefs[option.id] : null;
    const building = unit ? null : store.buildingDefs[option.id];
    const name = (unit || building).name;
    const turns = turnsFor(option.cost - c.shields, surplus);
    const when = turns === null ? 'no progress' : turns <= 1 ? 'next turn' : plural(turns, 'turn');
    const on = `${option.kind}:${option.id}` === current;
    const inQueue = queued[`${option.kind}:${option.id}`] || [];
    const tip = `option:${option.kind}:${option.id}`;
    const rows = [['Cost', amount(option.cost, 'shield', 'shield')]];
    if (unit && unit.pop_cost) rows.push(['Takes', plural(unit.pop_cost, 'citizen')]);
    if (building && building.upkeep) rows.push(['Upkeep', `${gold(building.upkeep)} <span class="soft">per turn</span>`]);
    if (building && building.description) rows.push(['Effect', building.description]);
    if (inQueue.length) {
      const last = inQueue[inQueue.length - 1];
      rows.push(['Queue', `<b class="gold">${inQueue.map((entry) => entry.place).join(' · ')}</b>${
        last.turns === null ? '' : ` <span class="soft">· done in ${plural(last.turns, 'turn')}</span>`}`]);
    }
    tips.set(tip, tipTitle(`${unit ? spriteBox(unit, owner.color) : ''}<span>${building && building.wonder ? '★ ' : ''}${name}</span>`, when)
      + (unit ? tipStats(unit) : '') + tipRows(rows)
      + '<div class="tip-foot"><span class="kbd">Ctrl</span> + click: add to the queue</div>');
    const row = `<button class="option${on ? ' on' : ''}${inQueue.length ? ' queued' : ''}" data-kind="${option.kind}" data-item="${option.id}"
        aria-pressed="${on}" aria-label="${name}, ${when}" data-tip="${tip}">
      <b>${name}</b><span class="tags">${inQueue.length ? `<span class="in-queue">+${inQueue.length}</span>` : ''}<span class="when">${turns === null ? '—' : Math.max(1, turns)}</span></span></button>`;
    groups[unit ? 'Units' : building.wonder ? 'Wonders' : 'Buildings'].push(row);
  }
  const blocks = Object.entries(groups).filter(([, rows]) => rows.length).map(([title, rows], i) => `
    <div class="option-group">
      <div class="between"><span class="label">${title}</span>${i === 0 ? '<span class="sub">turns</span>' : ''}</div>
      <div class="options${title === 'Wonders' ? ' long' : ''}">${rows.join('')}</div></div>`);
  return `
    <div class="stack chooser">
      <div class="between" style="align-items:center"><h2>${manage.current ? 'Change production' : 'Choose what to build'}</h2>
        <span class="queue-hint"><span class="kbd">Ctrl</span>+ click: queue</span>
        <label class="switch" title="A governor chooses the production the way an AI city would">
          <input type="checkbox" id="city-governor" ${manage.governed ? 'checked' : ''}><i></i>Governor</label></div>
      <div class="option-list">${blocks.join('')}</div>
    </div>`;
}

// ── The panel ───────────────────────────────────────────────────────────────

// A foreign city, for the person: only what it remembers.
function renderForeign(container, c) {
  const owner = player(c.owner);
  container.innerHTML = `
    <div class="panel-head city-head">
      <span class="avatar" style="background:${owner.color};color:${inkOn(owner.color)}">${c.size}</span>
      <div class="titles"><h1>${c.name}</h1>
        <span class="who">${owner.nation} · size ${c.size} when last seen, turn ${c.seen}
          · <span class="mono">${c.x}, ${c.y}</span></span></div>
      <div class="city-nav">
        <button id="city-center" class="btn small">Centre on map</button>
        <button id="city-close" class="btn ghost icon" aria-label="Close the city panel" title="Close (Esc)">${icon('close', 18, 2)}</button>
      </div>
    </div>
    <p class="empty"><b>A city of the ${owner.nation}</b>You know its place and its size${c.walls ? ', and that it has walls' : ''}.
      What it builds and who defends it is for your units to find out.</p>`;
  container.querySelector('#city-center').addEventListener('click', () => emit('center', { x: c.x, y: c.y }));
  container.querySelector('#city-close').addEventListener('click', () => emit('close-city'));
}

export function renderCity(container) {
  const detail = store.cityDetail;
  const tips = new Map();
  // The window keeps showing what it shows until the city asked for comes.
  if (store.selectedCity === null || !detail || detail.id !== store.selectedCity) return;
  if (detail.foreign) {
    renderForeign(container, detail);
    setTips(container, tips);
    return;
  }
  const c = detail;
  const s = c.stats;
  const manage = leader() === c.owner ? c.manage : null;
  const owner = player(c.owner);
  const siblings = store.state.cities.filter((city) => city.owner === c.owner);
  const position = siblings.findIndex((city) => city.id === c.id);

  const buildings = c.buildings.map((id) => {
    const building = store.buildingDefs[id];
    const upkeep = c.upkeeps[id];
    const sellable = Boolean(manage) && manage.sellable.includes(id);
    const name = `${building.wonder ? '★ ' : ''}${building.name}`;
    const tip = `building:${id}`;
    const rows = [];
    if (upkeep) rows.push(['Upkeep', `${gold(upkeep)} <span class="soft">per turn</span>`]);
    if (building.description) rows.push(['Effect', building.description]);
    if (sellable) rows.push(['Sells for', gold(building.cost)]);
    tips.set(tip, tipTitle(`<span>${name}</span>`, building.wonder ? 'wonder' : '') + tipRows(rows));
    const label = `${name}${upkeep ? gold(upkeep) : ''}`;
    if (!sellable) return `<span class="chip big" data-tip="${tip}">${label}</span>`;
    // The person sells with two clicks: the second one confirms.
    return sellAsked === `${c.id}:${id}`
      ? `<button class="chip big war" data-sell="${id}">Sell for ${building.cost}${icon('coin', 13, 2)} ?</button>`
      : `<button class="chip big" data-sell="${id}" data-tip="${tip}">${label}</button>`;
  }).concat(Object.entries(c.given || {}).map(([id, wonderId]) => {
    // A building a wonder provides: no upkeep, nothing to sell.
    const building = store.buildingDefs[id];
    const wonder = store.buildingDefs[wonderId];
    const tip = `given:${id}`;
    tips.set(tip, tipTitle(`<span>${building.name}</span>`, 'given') + tipRows([
      ['Given by', `★ ${wonder.name}`],
      ...(building.description ? [['Effect', building.description]] : []),
    ]));
    return `<span class="chip big given" data-tip="${tip}">${building.name}<span class="soft">★</span></span>`;
  })).join('') || '<span class="muted">None</span>';

  const decided = c.decision
    ? `${c.decision.bought ? 'bought' : 'decided'} on turn ${c.decision.turn}` : '';
  const mood = c.disorder ? `<span class="city-state bad">${icon('alert', 14, 2)}Civil disorder</span>`
    : c.celebration ? celebrationState(c, s, owner, tips) : '';

  // What the units cost the city each turn.
  const support = c.support;
  tips.set('support', tipTitle('<span>Units supported</span>', 'per turn') + tipRows([
    ['Needing support', support.units],
    ...(support.free ? [['Kept for free', support.free]] : []),
    ['Shields', amount(support.shields, 'shield', 'shield')],
    ['Food', amount(support.food, 'food', 'food')],
    ...(support.unhappy ? [['Unhappy', amount(support.unhappy, 'unhappy', 'bad')]] : []),
  ], true) + (support.unhappy ? `<div class="tip-foot">Under ${governmentName(owner.government)},
    military units away from the city make its citizens unhappy.</div>` : ''));
  const supportCost = c.units_supported.length ? `<span class="support-cost" data-tip="support">
    ${amount(support.shields, 'shield', 'shield')}${amount(support.food, 'food', 'food')}${
    support.unhappy ? amount(support.unhappy, 'unhappy', 'bad') : ''}</span>` : '';

  const here = unitTray(c.units_here, tips, 'here',
    (unit) => [['Supported by', c.homes[unit[U.ID]] || '<span class="muted">no city</span>']], manage ? 'orders' : null);
  const supported = unitTray(c.units_supported, tips, 'supported',
    (unit) => [['Location', c.places[unit[U.ID]] || `<span class="mono">${unit[U.X]}, ${unit[U.Y]}</span>`],
      ...costRows(unit, c.unit_costs[unit[U.ID]])], 'center', c.unit_costs);
  const scroll = container.scrollTop;

  container.innerHTML = `
    <div class="panel-head city-head">
      <span class="avatar" style="background:${owner.color};color:${inkOn(owner.color)}" title="${owner.nation}">${c.size}</span>
      <div class="name"><h1>${c.capital ? '★ ' : ''}${c.name}</h1>${mood}</div>
      <div class="city-nav">
        <span class="sub">City ${position + 1} of ${siblings.length}</span>
        <div class="arrows">
          <button data-step="-1" aria-label="Previous city" title="Previous city">${icon('left', 16, 2)}</button>
          <button data-step="1" aria-label="Next city" title="Next city">${icon('right', 16, 2)}</button>
        </div>
        <button id="city-center" class="btn small">Centre on map</button>
        <button id="city-close" class="btn ghost icon" aria-label="Close the city panel" title="Close (Esc)">${icon('close', 18, 2)}</button>
      </div>
    </div>
    <div class="city-body">
      <div class="city-left">
        <div class="between land-head"><h2>Land</h2>
          ${manage ? '<button class="btn small" id="city-arrange" title="The mayor places every citizen again">Let the mayor arrange</button>' : ''}</div>
        ${landGrid(c, owner, manage)}
        <h2 class="spaced">Buildings${s.building_upkeep ? `<small>${gold(s.building_upkeep)}per turn</small>` : ''}</h2>
        <div class="chips">${buildings}</div>
        <div class="two city-units">
          <div class="stack"><h2>Units in the city</h2>${here}</div>
          <div class="stack">
            <div class="between support-head"><h2>Units supported</h2>${supportCost}</div>${supported}</div>
        </div>
      </div>
      <div class="city-right">
        <div class="stack">
          <h2>Citizens</h2>
          <div class="citizens">${citizens(s, c.specialists, manage, c.size)}</div>
        </div>
        ${makingCard(c, manage, owner, tips, decided)}
        ${ledger(c, tips)}
        ${manage ? productionChooser(c, owner, tips) : decisionBlock(c, decided)}
      </div>
    </div>`;
  container.scrollTop = scroll;
  paintLand(container, c);
  setTips(container, tips);

  container.querySelector('#city-center').addEventListener('click', () => emit('center', { x: c.x, y: c.y }));
  container.querySelector('#city-close').addEventListener('click', () => emit('close-city'));
  container.querySelectorAll('.unit-card[data-x]').forEach((card) => {
    card.addEventListener('click', () => emit('center', { x: Number(card.dataset.x), y: Number(card.dataset.y) }));
  });
  container.querySelectorAll('[data-step]').forEach((button) => {
    button.addEventListener('click', () => {
      const count = siblings.length;
      const next = siblings[(Math.max(0, position) + Number(button.dataset.step) + count) % count];
      if (next) {
        emit('select-city', next.id);
        emit('center', { x: next.x, y: next.y });
      }
    });
  });
  if (!manage) return;

  // ── The person's levers ──
  container.querySelectorAll('.land-grid [data-dx]').forEach((cell) => {
    cell.addEventListener('click', () => {
      const dx = Number(cell.dataset.dx);
      const dy = Number(cell.dataset.dy);
      if (dx === 0 && dy === 0) act('arrange', { city: c.id });
      else act('tile', { city: c.id, dx, dy });
    });
  });
  container.querySelector('#city-arrange').addEventListener('click', () => act('arrange', { city: c.id }));
  container.querySelectorAll('[data-specialist]').forEach((button) => {
    button.addEventListener('click', () => act('specialist', { city: c.id, kind: button.dataset.specialist }));
  });
  container.querySelectorAll('[data-item]').forEach((button) => {
    button.addEventListener('click', (e) =>
      act(e.ctrlKey || e.metaKey ? 'queue' : 'production',
        { city: c.id, kind: button.dataset.kind, id: button.dataset.item }));
  });
  container.querySelectorAll('[data-unqueue]').forEach((button) => {
    button.addEventListener('click', () => act('unqueue', { city: c.id, index: Number(button.dataset.unqueue) }));
  });
  const buy = container.querySelector('#city-buy');
  if (buy) buy.addEventListener('click', () => act('buy', { city: c.id }));
  container.querySelectorAll('[data-sell]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const asked = `${c.id}:${chip.dataset.sell}`;
      if (sellAsked === asked) {
        sellAsked = null;
        act('sell', { city: c.id, building: chip.dataset.sell });
      } else {
        sellAsked = asked;
        renderCity(container);
      }
    });
  });
  container.querySelector('#city-governor').addEventListener('change', (e) => {
    send({ cmd: 'govern', city: c.id, on: e.target.checked });
  });
  container.querySelectorAll('[data-unit]').forEach((chip) => {
    chip.addEventListener('click', () => emit('activate-unit', Number(chip.dataset.unit)));
  });
}
