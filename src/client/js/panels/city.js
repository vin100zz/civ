// "City" panel: what a city produces and how its citizens feel. For the observer, why the AI
// builds what it builds; for the person leading the city, the levers to manage it.

import { store, U, player, leader, emit, inkOn, plural, turnsFor } from '../state.js';
import { send } from '../net.js';
import { icon } from '../icons.js';

const LAND = 450;           // pixels of the land view (css/style.css)
const FACE = {
  happy: ['var(--good)', 'M8.5 14c1 1.4 2.2 2 3.5 2s2.5 -.6 3.5 -2'],
  content: ['var(--soft)', 'M8.5 15h7'],
  unhappy: ['var(--bad)', 'M8.5 16c1-1.4 2.2-2 3.5-2s2.5 .6 3.5 2'],
};
const SPECIALIST = { entertainer: 'E', taxman: 'T', scientist: 'S' };
const SPECIALIST_NOTE = { entertainer: '2 luxuries', taxman: '2 gold', scientist: '2 science' };
let drawTile = null;        // (ctx, tx, ty, px, py, size): the map's own terrain drawing
let sellAsked = null;       // building the person was asked to confirm the sale of

export function setTileRenderer(renderer) {
  drawTile = renderer;
}

function signed(value) {
  return `${value >= 0 ? '+' : ''}${value}`;
}

function act(action, fields) {
  send({ cmd: 'action', action, ...fields });
}

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

function unitList(units, clickable) {
  if (!units.length) return '<span class="muted">None</span>';
  if (clickable) {
    // The person picks a unit of its city to give it orders.
    return units.map((unit) => {
      const definition = store.unitDefs[unit[U.TYPE]];
      const state = unit[U.ORDER] !== 'none' ? unit[U.ORDER] : unit[U.ABOARD] ? 'aboard' : '';
      return `<button class="chip big" data-unit="${unit[U.ID]}" title="Give orders to this unit">${definition.name}
        ${unit[U.VETERAN] ? '<span class="muted">veteran</span>' : ''}${state ? `<span class="muted">${state}</span>` : ''}</button>`;
    }).join('');
  }
  const counts = new Map();
  for (const unit of units) {
    const name = store.unitDefs[unit[U.TYPE]].name + (unit[U.VETERAN] ? ' (veteran)' : '');
    counts.set(name, (counts.get(name) || 0) + 1);
  }
  return [...counts].map(([name, count]) =>
    `<span class="chip big">${name}${count > 1 ? ` <span class="muted">×${count}</span>` : ''}</span>`).join('');
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

// What the person may have the city build.
function productionChooser(c) {
  const manage = c.manage;
  const surplus = c.stats.shield_surplus;
  const current = manage.current ? manage.current.join(':') : null;
  const groups = { Units: [], Buildings: [], Wonders: [] };
  for (const option of manage.options) {
    const unit = option.kind === 'unit' ? store.unitDefs[option.id] : null;
    const building = unit ? null : store.buildingDefs[option.id];
    const name = (unit || building).name;
    let detail = `${option.cost} shields`;
    if (unit) {
      detail += unit.pop_cost ? ` · ${plural(unit.pop_cost, 'citizen')}` : ` · A${unit.attack} D${unit.defense} M${unit.moves}`;
    } else if (building.upkeep) {
      detail += ` · ${building.upkeep} gold a turn`;
    }
    const turns = turnsFor(option.cost - c.shields, surplus);
    const on = `${option.kind}:${option.id}` === current;
    const when = on ? '<em>Building</em>'
      : turns === null ? '<span class="sub">—</span>'
        : turns <= 1 ? '<span class="sub good">next turn</span>' : `<span class="sub">${plural(turns, 'turn')}</span>`;
    const row = `<button class="option${on ? ' on' : ''}" data-kind="${option.kind}" data-item="${option.id}"
        aria-pressed="${on}" title="${(building && building.description) || name}">
      <span class="between"><b>${name}</b>${when}</span><small>${detail}</small></button>`;
    groups[unit ? 'Units' : building.wonder ? 'Wonders' : 'Buildings'].push(row);
  }
  const blocks = Object.entries(groups).filter(([, rows]) => rows.length).map(([title, rows]) => `
    <div class="option-group"><span class="label">${title}</span><div class="options">${rows.join('')}</div></div>`);
  return `
    <div class="stack" style="gap:10px">
      <div class="between"><h2>${manage.current ? 'Change production' : 'Choose what to build'}</h2>
        <label class="switch" title="A governor chooses the production the way an AI city would">
          <input type="checkbox" id="city-governor" ${manage.governed ? 'checked' : ''}><i></i>Governor</label></div>
      ${c.shields && manage.current ? `<span class="sub">The ${plural(c.shields, 'shield')} already gathered are kept.</span>` : ''}
      ${blocks.join('')}
    </div>`;
}

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
        <button id="city-center" class="btn small" style="height:40px">Centre on map</button>
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
  if (store.selectedCity === null || !detail || detail.id !== store.selectedCity) {
    container.innerHTML = `<p class="empty"><b>No city selected</b>Click a city on the map to see
      what it produces and how its citizens feel${leader() === null ? ', and why the AI builds what it builds' : ''}.</p>`;
    return;
  }
  if (detail.foreign) {
    renderForeign(container, detail);
    return;
  }
  const c = detail;
  const s = c.stats;
  const manage = leader() === c.owner ? c.manage : null;
  const owner = player(c.owner);
  const siblings = store.state.cities.filter((city) => city.owner === c.owner);
  const position = siblings.findIndex((city) => city.id === c.id);
  const worked = c.tiles.filter((t) => t.worked).length;

  const buildings = c.buildings.map((id) => {
    const building = store.buildingDefs[id];
    const label = `${building.wonder ? '★ ' : ''}${building.name}
      ${building.upkeep ? `<span class="trade">${building.upkeep}g</span>` : ''}`;
    if (manage && manage.sellable.includes(id)) {
      const asked = sellAsked === `${c.id}:${id}`;
      return `<button class="chip big${asked ? ' war' : ''}" data-sell="${id}"
        title="${building.description || building.name} · click to sell for ${building.cost} gold">${asked ? `Sell for ${building.cost} gold?` : label}</button>`;
    }
    return `<span class="chip big" title="${building.description || ''}">${label}</span>`;
  }).join('') || '<span class="muted">None</span>';

  const foodPercent = Math.min(100, 100 * c.food / c.food_box);
  const growth = turnsFor(c.food_box - c.food, s.food_surplus);
  const foodNote = s.food_surplus < 0 ? '<span class="bad">starving</span>'
    : growth === null ? 'not growing' : `grows in ${plural(growth, 'turn')}`;
  const building = c.production && (!manage || manage.current);
  const shieldPercent = building && c.production_cost ? Math.min(100, 100 * c.shields / c.production_cost) : 0;
  const done = building && c.production_cost ? turnsFor(c.production_cost - c.shields, s.shield_surplus) : null;
  const doneNote = !building || !c.production_cost ? ''
    : done === 0 ? '<b class="good">done next turn</b>'
      : done === null ? '<span class="bad">no progress</span>' : `${plural(done, 'turn')}`;
  const decided = c.decision
    ? `${c.decision.bought ? 'bought' : 'decided'} on turn ${c.decision.turn}` : '';
  const mood = c.disorder ? ['Civil disorder', 'var(--bad)']
    : c.celebrating ? ['Celebrating', 'var(--gold)'] : ['In order', 'var(--good)'];
  const specialists = Object.entries(c.specialists).filter(([, count]) => count > 0)
    .map(([kind, count]) => `${count} ${kind}`).join(', ');

  let purchase = `<span class="sub">${c.buy_cost ? `buy now: ${c.buy_cost} gold` : decided}</span>`;
  if (manage && c.buy_cost && building) {
    purchase = manage.can_buy
      ? `<button class="btn small primary" id="city-buy">Buy for ${c.buy_cost} gold</button>`
      : `<button class="btn small" disabled title="Not enough gold, or already bought this turn">Buy for ${c.buy_cost} gold · you have ${manage.gold}</button>`;
  }
  const scroll = container.scrollTop;

  container.innerHTML = `
    <div class="panel-head city-head">
      <span class="avatar" style="background:${owner.color};color:${inkOn(owner.color)}">${c.size}</span>
      <div class="titles"><h1>${c.capital ? '★ ' : ''}${c.name}</h1>
        <span class="who">${manage ? 'Your city' : owner.nation} · size ${c.size} · founded turn ${c.founded_turn}
          · <span class="mono">${c.x}, ${c.y}</span></span></div>
      <div class="city-nav">
        <span class="sub">City ${position + 1} of ${siblings.length}</span>
        <div class="arrows">
          <button data-step="-1" aria-label="Previous city" title="Previous city">${icon('left', 16, 2)}</button>
          <button data-step="1" aria-label="Next city" title="Next city">${icon('right', 16, 2)}</button>
        </div>
        <button id="city-center" class="btn small" style="height:40px">Centre on map</button>
        <button id="city-close" class="btn ghost icon" aria-label="Close the city panel" title="Close (Esc)">${icon('close', 18, 2)}</button>
      </div>
    </div>
    <div class="city-body">
      <div class="city-left">
        <div class="between"><h2>Land</h2><span class="sub">${worked} of ${c.tiles.length} tiles worked</span></div>
        ${landGrid(c, owner, manage)}
        <div class="land-legend">
          <span><i style="background:var(--food)"></i>Food</span>
          <span><i style="background:var(--shield)"></i>Shields</span>
          <span><i style="background:var(--trade)"></i>Trade</span>
          <span class="worked-key"><i></i>Worked tile</span>
        </div>
        ${manage ? `<div class="hint"><span>Click a tile to put a citizen to work on it, a worked tile to free its
          citizen. The mayor places everybody again when the city grows.</span>
          <button class="btn small" id="city-arrange">Let the mayor arrange</button></div>` : ''}
        <h2 style="margin-top:10px">Buildings <small>· ${s.building_upkeep} gold per turn${manage && manage.sellable.length ? ' · click one to sell it' : ''}</small></h2>
        <div class="chips">${buildings}</div>
        <div class="two" style="margin-top:10px">
          <div class="stack" style="gap:8px"><h2>Units in the city</h2><div class="chips">${unitList(c.units_here, Boolean(manage))}</div></div>
          <div class="stack" style="gap:8px"><h2>Units supported</h2><div class="chips">${unitList(c.units_supported, false)}</div></div>
        </div>
      </div>
      <div class="city-right">
        <div class="stack" style="gap:10px">
          <div class="between"><h2>Citizens</h2>
            <span class="sub">${s.happy} happy · ${s.content} content · ${s.unhappy} unhappy${specialists ? ` · ${specialists}` : ''}</span></div>
          <div class="citizens">${citizens(s, c.specialists, manage, c.size)}
            <span class="order" style="color:${mood[1]}">${mood[0]}</span></div>
        </div>
        <div class="card">
          <div class="between" style="align-items:center"><span class="sub">Building</span>${purchase}</div>
          <div class="between"><span class="big">${building ? c.production : '<span class="bad">Nothing</span>'}</span>
            ${building && c.production_cost ? `<span class="soft" style="font-size:13px"><b style="color:var(--text)">${c.shields}</b> / ${c.production_cost} shields · ${doneNote}</span>` : ''}</div>
          <div class="bar"><span style="width:${shieldPercent}%;background:var(--shield)"></span></div>
        </div>
        <div class="ledger">
          <div class="ledger-row"><i style="background:var(--food)"></i><span class="what">Food</span>
            <span class="value ${s.food_surplus < 0 ? 'bad' : 'food'}">${signed(s.food_surplus)}</span>
            <div class="detail"><span>${s.food} produced · box ${c.food} / ${c.food_box} · ${foodNote}</span>
              <div class="bar thin"><span style="width:${foodPercent}%;background:var(--food)"></span></div></div></div>
          <div class="ledger-row"><i style="background:var(--shield)"></i><span class="what">Shields</span>
            <span class="value ${s.shield_surplus < 0 ? 'bad' : 'shield'}">${signed(s.shield_surplus)}</span>
            <div class="detail"><span>${s.shields} produced · ${s.shield_upkeep} to support units</span></div></div>
          <div class="ledger-row"><i style="background:var(--trade)"></i><span class="what">Trade</span>
            <span class="value trade">${s.trade}</span>
            <div class="detail"><span>${s.corruption} lost to corruption · luxury ${s.luxury} · tax ${s.tax} · <span class="sci">science ${s.science}</span></span></div></div>
          ${s.pollution ? `<div class="ledger-row"><i style="background:var(--bad)"></i><span class="what">Pollution</span>
            <span class="value bad">${s.pollution}</span>
            <div class="detail"><span>each turn a tile around the city may be polluted</span></div></div>` : ''}
          ${c.trade_routes.length ? `<div class="ledger-row"><i style="background:var(--gold)"></i><span class="what">Routes</span>
            <span class="value">${c.trade_routes.length}</span>
            <div class="detail"><span>${c.trade_routes.join(', ')}</span></div></div>` : ''}
        </div>
        ${manage ? productionChooser(c) : decisionBlock(c, decided)}
      </div>
    </div>`;
  container.scrollTop = scroll;
  paintLand(container, c);

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
      const key = `${c.id}:${chip.dataset.sell}`;
      if (sellAsked === key) {
        sellAsked = null;
        act('sell', { city: c.id, building: chip.dataset.sell });
      } else {
        sellAsked = key;
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
