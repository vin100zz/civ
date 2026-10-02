// "City" tab: what a city produces, how its citizens feel, and why the AI builds what it builds.

import { store, U, player, emit } from '../state.js';
import { swatch } from './civs.js';

function citizens(stats, specialists) {
  const faces = '😀'.repeat(stats.happy) + '🙂'.repeat(stats.content) + '😠'.repeat(stats.unhappy);
  const others = '🎭'.repeat(specialists.entertainer) + '💰'.repeat(specialists.taxman)
    + '🔬'.repeat(specialists.scientist);
  return `<span class="citizens">${faces}${others ? ' ' + others : ''}</span>`;
}

function tileGrid(detail) {
  const byOffset = new Map(detail.tiles.map((t) => [`${t.dx},${t.dy}`, t]));
  const cells = [];
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      const tile = byOffset.get(`${dx},${dy}`);
      if (!tile) {
        cells.push('<div class="city-tile blank"></div>');
        continue;
      }
      const index = tile.y * store.map.width + tile.x;
      const terrain = store.terrains[store.map.terrain[index]];
      const classes = ['city-tile'];
      if (!tile.worked) classes.push('unworked');
      if (dx === 0 && dy === 0) classes.push('center');
      const [food, shields, trade] = tile.yields;
      cells.push(`<div class="${classes.join(' ')}" style="background:${terrain.color}"
        title="${terrain.name}"><b>${food}/${shields}/${trade}</b></div>`);
    }
  }
  return `<div class="city-grid">${cells.join('')}</div>`;
}

function unitList(units) {
  if (!units.length) return '<span class="muted">None</span>';
  const counts = new Map();
  for (const unit of units) {
    const name = store.unitDefs[unit[U.TYPE]].name + (unit[U.VETERAN] ? ' (veteran)' : '');
    counts.set(name, (counts.get(name) || 0) + 1);
  }
  return [...counts].map(([name, count]) =>
    `<span class="tag">${name}${count > 1 ? ' ×' + count : ''}</span>`).join('');
}

export function renderCity(container) {
  const detail = store.cityDetail;
  if (store.selectedCity === null || !detail || detail.id !== store.selectedCity) {
    container.innerHTML = '<p class="empty">Click a city on the map.</p>';
    return;
  }
  const c = detail;
  const s = c.stats;
  const owner = player(c.owner);
  const buildings = c.buildings.map((id) => {
    const building = store.buildingDefs[id];
    return `<span class="tag" title="${building.description || ''}">${building.wonder ? '★ ' : ''}${building.name}</span>`;
  }).join('') || '<span class="muted">None</span>';
  const foodPercent = Math.min(100, 100 * c.food / c.food_box);
  const shieldPercent = c.production_cost ? Math.min(100, 100 * c.shields / c.production_cost) : 0;
  const flags = [];
  if (c.capital) flags.push('capital');
  if (c.disorder) flags.push('<span class="bad">civil disorder</span>');
  if (c.celebrating) flags.push('<span class="good">celebrating</span>');

  let decision = '';
  if (c.decision) {
    const rows = c.decision.candidates.map((candidate, i) => `
      <tr class="${i === 0 ? 'chosen' : ''}">
        <td>${candidate.name}<div class="reason">${candidate.reason}</div></td>
        <td>${candidate.score}</td><td>${candidate.turns || '—'}</td></tr>`).join('');
    decision = `
      <h3>Why this production (decided turn ${c.decision.turn}${c.decision.bought ? ', bought' : ''})</h3>
      <table class="candidates"><thead><tr><th>Candidate</th><th>Score</th><th>Turns</th></tr></thead>
        <tbody>${rows}</tbody></table>`;
  }

  container.innerHTML = `
    <h2>${swatch(owner.color)}${c.name} <span class="muted">— ${owner.nation}, size ${c.size}</span></h2>
    <div>${citizens(s, c.specialists)} ${flags.join(' · ')}</div>
    <h3>Production</h3>
    <dl class="kv">
      <dt>Building</dt><dd>${c.production || '<span class="bad">nothing</span>'}
        ${c.production_cost ? `— ${c.shields}/${c.production_cost} shields` : ''}
        <div class="bar"><span style="width:${shieldPercent}%"></span></div></dd>
      <dt>Food</dt><dd><span class="food">${s.food}</span> produced,
        <span class="${s.food_surplus < 0 ? 'bad' : 'good'}">${s.food_surplus >= 0 ? '+' : ''}${s.food_surplus}</span>
        — box ${c.food}/${c.food_box}
        <div class="bar"><span style="width:${foodPercent}%; background: var(--food)"></span></div></dd>
      <dt>Shields</dt><dd><span class="shield">${s.shields}</span> produced, ${s.shield_upkeep} for units,
        <b>${s.shield_surplus >= 0 ? '+' : ''}${s.shield_surplus}</b></dd>
      <dt>Trade</dt><dd><span class="trade">${s.trade}</span> (${s.corruption} lost to corruption)
        → luxury ${s.luxury}, tax ${s.tax}, science ${s.science}</dd>
      <dt>Maintenance</dt><dd>${s.building_upkeep} gold per turn</dd>
      ${s.pollution ? `<dt>Pollution</dt><dd><span class="bad">index ${s.pollution}</span>
        — each turn a tile around the city may be polluted</dd>` : ''}
      ${c.trade_routes.length ? `<dt>Trade routes</dt><dd>${c.trade_routes.join(', ')}</dd>` : ''}
    </dl>
    <h3>Land (food / shields / trade — worked tiles are bright)</h3>
    ${tileGrid(c)}
    <h3>Buildings</h3><div>${buildings}</div>
    <h3>Units in the city</h3><div>${unitList(c.units_here)}</div>
    <h3>Units supported</h3><div>${unitList(c.units_supported)}</div>
    ${decision}
    <p><button id="city-center">Show on map</button></p>`;
  container.querySelector('#city-center').addEventListener('click', () =>
    emit('center', { x: c.x, y: c.y }));
}
