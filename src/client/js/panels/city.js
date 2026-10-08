// "City" panel: what a city produces and how its citizens feel. For the observer, why the AI
// builds what it builds; for the person leading the city, the levers to manage it.
// The panel shows figures and bars; what they are made of is told by their tooltips.

import { store, U, player, leader, emit, inkOn, plural, turnsFor } from '../state.js';
import { send } from '../net.js';
import { icon } from '../icons.js';
import { setTips } from '../tips.js';
import { ORDER_MARK, TASK_MARK } from '../renderer/map.js';

const LAND = 450;           // pixels of the land view (css/style.css)
const FACE = {
  happy: ['var(--good)', 'M8.5 14c1 1.4 2.2 2 3.5 2s2.5 -.6 3.5 -2'],
  content: ['var(--soft)', 'M8.5 15h7'],
  unhappy: ['var(--bad)', 'M8.5 16c1-1.4 2.2-2 3.5-2s2.5 .6 3.5 2'],
};
const SPECIALIST = { entertainer: 'E', taxman: 'T', scientist: 'S' };
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
      faces.push(`<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="${color}"
        stroke-width="1.6" stroke-linecap="round" role="img" aria-label="${mood} citizen">
        <circle cx="12" cy="12" r="9.5" fill="var(--raise)"/><path d="M9 10v.6M15 10v.6"/><path d="${mouth}"/></svg>`);
    }
  }
  const others = [];
  const canChange = manage && size >= store.rules.specialist_min_size;
  for (const [kind, letter] of Object.entries(SPECIALIST)) {
    for (let i = 0; i < (specialists[kind] || 0); i++) {
      others.push(canChange
        ? `<button class="specialist" data-specialist="${kind}" title="${kind}: ${SPECIALIST_NOTE[kind]} · click to change its job">${letter}</button>`
        : `<span class="specialist" title="${kind}: ${SPECIALIST_NOTE[kind]}">${letter}</span>`);
    }
  }
  return faces.join('') + (others.length ? `<span class="sep"></span>${others.join('')}` : '');
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
      const [food, shields, trade] = tile.yields;
      const center = dx === 0 && dy === 0;
      const classes = ['land-cell'];
      if (tile.worked) classes.push('worked');
      if (center) classes.push('center');
      const mark = center
        ? `<span class="city-mark" style="background:${owner.color};color:${inkOn(owner.color)}">${detail.size}</span>` : '';
      const yields = `<span class="yields"><span class="food">${food}</span><span class="shield">${shields}</span><span class="trade">${trade}</span></span>`;
      if (!manage) {
        cells.push(`<div class="${classes.join(' ')}" title="${terrain.name}${tile.worked ? ' — worked' : ''}">${mark}${yields}</div>`);
        continue;
      }
      // The person moves its citizens by clicking: the centre hands the city back to its mayor.
      const usable = center || tile.worked || workable.has(`${dx},${dy}`);
      const title = center ? 'Let the mayor place the citizens'
        : tile.worked ? `${terrain.name} — worked · click to free its citizen`
          : usable ? `${terrain.name} · click to work this tile` : `${terrain.name} — taken by another city or an enemy`;
      if (!usable) classes.push('taken');
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
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      drawTile(ctx, detail.x + dx, detail.y + dy, (dx + 2) * size, (dy + 2) * size, size);
    }
  }
}

// ── Units ───────────────────────────────────────────────────────────────────

function spriteBox(definition, color) {
  return `<span class="unit-card small" style="background:${color}"><img src="/resources/unit/${definition.sprite}.png" alt=""></span>`;
}

// A unit drawn as on the map: heavy outline when fortified, hatched on sentry, a letter for
// what it is doing, a gold dot for a veteran.
function unitCard(unit, tip, clickable, count) {
  const definition = store.unitDefs[unit[U.TYPE]];
  const order = unit[U.ORDER];
  const classes = ['unit-card'];
  if (order === 'fortified' || order === 'fortify') classes.push('fortified');
  if (order === 'sentry') classes.push('sentry');
  const mark = TASK_MARK[unit[U.TASK]] || ORDER_MARK[order];
  const inner = `<img src="/resources/unit/${definition.sprite}.png" alt="">`
    + (mark ? `<span class="mark">${mark}</span>` : '')
    + (unit[U.VETERAN] ? '<i class="vet"></i>' : '')
    + (count > 1 ? `<span class="count">${count}</span>` : '');
  const name = `${definition.name}${count > 1 ? ` ×${count}` : ''}`;
  const attributes = `class="${classes.join(' ')}" style="background:${player(unit[U.OWNER]).color}" data-tip="${tip}"`;
  return clickable
    ? `<button ${attributes} data-unit="${unit[U.ID]}" aria-label="${name}: give it orders">${inner}</button>`
    : `<span ${attributes} role="img" aria-label="${name}">${inner}</span>`;
}

function unitTip(unit, count, rows) {
  const definition = store.unitDefs[unit[U.TYPE]];
  const doing = unit[U.ABOARD] ? 'Aboard a ship' : TASKS[unit[U.TASK]] || DOING[unit[U.ORDER]];
  const title = `${spriteBox(definition, player(unit[U.OWNER]).color)}<span>${definition.name}${
    unit[U.VETERAN] ? ' <small>veteran</small>' : ''}</span>`;
  return tipTitle(title, count > 1 ? `×${count}` : '') + tipStats(definition)
    + tipRows(doing ? [['Orders', doing], ...rows] : rows, true);
}

// The units of a list, as cards. The person picks one to give it orders, so each has its
// own; otherwise the units alike share a card. `about(unit)` gives the rows of the tooltip.
function unitTray(units, tips, prefix, about, clickable) {
  if (!units.length) return '<span class="muted">None</span>';
  const groups = new Map();
  for (const unit of units) {
    const rows = about(unit);
    const alike = clickable ? unit[U.ID]
      : [unit[U.TYPE], unit[U.ORDER], unit[U.VETERAN], unit[U.ABOARD], JSON.stringify(rows)].join('|');
    if (!groups.has(alike)) groups.set(alike, { unit, rows, count: 0 });
    groups.get(alike).count += 1;
  }
  const cards = [...groups.values()].map(({ unit, rows, count }) => {
    const tip = `${prefix}:${unit[U.ID]}`;
    tips.set(tip, unitTip(unit, count, rows));
    return unitCard(unit, tip, clickable, count);
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

// Food, shields, trade and pollution: the surplus, then where what is made goes.
function ledger(c, tips) {
  const s = c.stats;
  const rows = [];

  // Food: the box filling up until the city grows.
  const growth = turnsFor(c.food_box - c.food, s.food_surplus);
  const starving = s.food_surplus < 0;
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
    ]));
  rows.push(ledgerRow('food', 'food', 'Food', signed(s.food_surplus), starving ? 'bad' : 'food',
    stock(c.food, s.food_surplus, c.food_box, 'var(--food)')
      + (starving ? '<span class="eta bad">starving</span>' : eta(growth, 'no growth', 'none')), 'food'));

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
      <img src="/resources/unit/${store.unitDefs[c.item[1]].sprite}.png" alt=""></span>`;
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
    </div>`;
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
    <div class="stack" style="gap:10px">
      <div class="ai-title"><span class="ai-badge">AI</span><h2>Why this production</h2>
        <span class="sub">${decided}</span></div>
      ${rows}
    </div>`;
}

// What the person may have the city build: a name and the turns it takes.
function productionChooser(c, owner, tips) {
  const manage = c.manage;
  const surplus = c.stats.shield_surplus;
  const current = manage.current ? manage.current.join(':') : null;
  const groups = { Units: [], Buildings: [], Wonders: [] };
  for (const option of manage.options) {
    const unit = option.kind === 'unit' ? store.unitDefs[option.id] : null;
    const building = unit ? null : store.buildingDefs[option.id];
    const name = (unit || building).name;
    const turns = turnsFor(option.cost - c.shields, surplus);
    const when = turns === null ? 'no progress' : turns <= 1 ? 'next turn' : plural(turns, 'turn');
    const on = `${option.kind}:${option.id}` === current;
    const tip = `option:${option.kind}:${option.id}`;
    const rows = [['Cost', amount(option.cost, 'shield', 'shield')]];
    if (unit && unit.pop_cost) rows.push(['Takes', plural(unit.pop_cost, 'citizen')]);
    if (building && building.upkeep) rows.push(['Upkeep', `${gold(building.upkeep)} <span class="soft">per turn</span>`]);
    if (building && building.description) rows.push(['Effect', building.description]);
    tips.set(tip, tipTitle(`${unit ? spriteBox(unit, owner.color) : ''}<span>${building && building.wonder ? '★ ' : ''}${name}</span>`, when)
      + (unit ? tipStats(unit) : '') + tipRows(rows));
    const row = `<button class="option${on ? ' on' : ''}" data-kind="${option.kind}" data-item="${option.id}"
        aria-pressed="${on}" aria-label="${name}, ${when}" data-tip="${tip}">
      <b>${name}</b><span class="when">${turns === null ? '—' : Math.max(1, turns)}</span></button>`;
    groups[unit ? 'Units' : building.wonder ? 'Wonders' : 'Buildings'].push(row);
  }
  const blocks = Object.entries(groups).filter(([, rows]) => rows.length).map(([title, rows], i) => `
    <div class="option-group">
      <div class="between"><span class="label">${title}</span>${i === 0 ? '<span class="sub">turns</span>' : ''}</div>
      <div class="options${title === 'Wonders' ? ' long' : ''}">${rows.join('')}</div></div>`);
  return `
    <div class="stack" style="gap:10px">
      <div class="between" style="align-items:center"><h2>${manage.current ? 'Change production' : 'Choose what to build'}</h2>
        <label class="switch" title="A governor chooses the production the way an AI city would">
          <input type="checkbox" id="city-governor" ${manage.governed ? 'checked' : ''}><i></i>Governor</label></div>
      ${blocks.join('')}
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
  if (store.selectedCity === null || !detail || detail.id !== store.selectedCity) {
    container.innerHTML = `<p class="empty"><b>No city selected</b>Click a city on the map to see
      what it produces and how its citizens feel${leader() === null ? ', and why the AI builds what it builds' : ''}.</p>`;
    setTips(container, tips);
    return;
  }
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
  }).join('') || '<span class="muted">None</span>';

  const decided = c.decision
    ? `${c.decision.bought ? 'bought' : 'decided'} on turn ${c.decision.turn}` : '';
  const mood = c.disorder ? `<span class="city-state bad">${icon('alert', 14, 2)}Civil disorder</span>`
    : c.celebrating ? '<span class="city-state gold">Celebrating</span>' : '';

  // What the units cost the city each turn.
  const support = c.support;
  tips.set('support', tipTitle('<span>Units supported</span>', 'per turn') + tipRows([
    ['Needing support', support.units],
    ...(support.free ? [['Kept for free', support.free]] : []),
    ['Shields', amount(support.shields, 'shield', 'shield')],
    ['Food', amount(support.food, 'food', 'food')],
  ], true));
  const supportCost = c.units_supported.length ? `<span class="support-cost" data-tip="support">
    ${amount(support.shields, 'shield', 'shield')}${amount(support.food, 'food', 'food')}</span>` : '';

  const here = unitTray(c.units_here, tips, 'here',
    (unit) => [['Supported by', c.homes[unit[U.ID]] || '<span class="muted">no city</span>']], Boolean(manage));
  const supported = unitTray(c.units_supported, tips, 'supported',
    (unit) => [['Location', c.places[unit[U.ID]] || `<span class="mono">${unit[U.X]}, ${unit[U.Y]}</span>`]], false);
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
        <div class="between" style="align-items:center;min-height:32px"><h2>Land</h2>
          ${manage ? '<button class="btn small" id="city-arrange" title="The mayor places every citizen again">Let the mayor arrange</button>' : ''}</div>
        ${landGrid(c, owner, manage)}
        <h2 style="margin-top:10px">Buildings${s.building_upkeep ? `<small>${gold(s.building_upkeep)}per turn</small>` : ''}</h2>
        <div class="chips">${buildings}</div>
        <div class="two" style="margin-top:10px">
          <div class="stack" style="gap:8px"><h2>Units in the city</h2>${here}</div>
          <div class="stack" style="gap:8px">
            <div class="between" style="align-items:center"><h2>Units supported</h2>${supportCost}</div>${supported}</div>
        </div>
      </div>
      <div class="city-right">
        <div class="stack" style="gap:10px">
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
    button.addEventListener('click', () =>
      act('production', { city: c.id, kind: button.dataset.kind, id: button.dataset.item }));
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
