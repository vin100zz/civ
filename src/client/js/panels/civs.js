// "Civilizations" tab: every player at a glance. "Empire" tab: one civilization in detail,
// including what its AI wants and why.

import { store, emit, player, yearLabel } from '../state.js';

const TRAIT = {
  mood: ['friendly', 'neutral', 'aggressive'],
  policy: ['perfectionist', 'neutral', 'expansionist'],
  ideology: ['militaristic', 'neutral', 'civilized'],
};

function swatch(color) {
  return `<span class="swatch" style="background:${color}"></span>`;
}

function techName(id) {
  return id && store.techDefs[id] ? store.techDefs[id].name : '—';
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

function governmentName(id) {
  const government = store.rules.governments.find((g) => g.id === id);
  return government ? government.name : id;
}

export function renderCivs(container) {
  const state = store.state;
  if (!state) return;
  const rows = state.players
    .filter((p) => !p.barbarian || p.units > 0 || p.cities > 0)
    .map((p) => {
      const classes = ['clickable'];
      if (!p.alive) classes.push('dead');
      if (p.id === store.selectedPlayer) classes.push('selected');
      let war = p.at_war.length ? ` <span class="bad" title="At war">⚔${p.at_war.length}</span>` : '';
      if (p.spaceship && p.spaceship.arrival_turn !== null) war += ' <span title="Spaceship in flight">🚀</span>';
      return `<tr class="${classes.join(' ')}" data-player="${p.id}">
        <td>${swatch(p.color)}${p.name}${war}</td>
        <td>${p.cities}</td><td>${p.population}</td><td>${p.techs}</td>
        <td>${p.units}</td><td>${p.gold}</td><td>${p.score}</td>
        <td>${p.barbarian ? '' : governmentName(p.government)}</td></tr>`;
    });
  container.innerHTML = `
    <table>
      <thead><tr><th>Civilization</th><th>Cities</th><th>Pop.</th><th>Techs</th>
        <th>Units</th><th>Gold</th><th>Score</th><th>Government</th></tr></thead>
      <tbody>${rows.join('')}</tbody>
    </table>
    <p class="muted">Click a civilization for its details. Click a city on the map for its
      production and the reasons behind it.</p>`;
  container.querySelectorAll('tr[data-player]').forEach((row) => {
    row.addEventListener('click', () => emit('select-player', Number(row.dataset.player)));
  });
}

export function renderCiv(container) {
  const detail = store.playerDetail;
  if (store.selectedPlayer === null || !detail || detail.id !== store.selectedPlayer) {
    container.innerHTML = '<p class="empty">Select a civilization in the first tab or on the map.</p>';
    return;
  }
  const p = detail;
  const personality = Object.entries(p.personality)
    .map(([trait, value]) => TRAIT[trait][value + 1])
    .filter((label) => label !== 'neutral');
  const progress = p.research_cost ? Math.min(100, 100 * p.research_progress / p.research_cost) : 0;
  const relations = p.relations
    .filter((r) => r.state !== 'no_contact')
    .map((r) => {
      const other = player(r.player);
      return `<span class="tag ${r.state}">${swatch(other.color)}${other.name}: ${r.state}</span>`;
    }).join('') || '<span class="muted">No contact yet</span>';

  let ai = '';
  if (p.ai && p.ai.needs) {
    const needs = Object.entries(p.ai.needs).filter(([, count]) => count > 0)
      .map(([name, count]) => `<span class="tag">${name}: ${count}</span>`).join('')
      || '<span class="muted">Nothing missing</span>';
    const notes = (p.ai.notes || []).map((n) => `<div>${n}</div>`).join('');
    const targets = (p.ai.targets || []).length
      ? `<dt>War targets</dt><dd>${p.ai.targets.join(', ')}</dd>` : '';
    const missions = (p.ai.missions || []).filter((m) => m.kind !== 'defend').map((m) => `
      <tr class="clickable" data-x="${m.x}" data-y="${m.y}">
        <td>${m.kind.replaceAll('_', ' ')}</td><td>${m.note || ''}</td>
        <td>${m.units}/${m.capacity}</td><td>${m.priority}</td></tr>`).join('');
    const research = (p.ai.research || []).map(([id, score]) =>
      `<span class="tag">${techName(id)} ${score}</span>`).join('');
    const expeditions = (p.ai.expeditions || []).map((e) => `
      <tr class="clickable" data-x="${e.goal[0]}" data-y="${e.goal[1]}">
        <td>${e.kind === 'settle' ? 'colony' : 'invasion'}</td><td>${e.stage}</td>
        <td>${e.ship === null ? 'no ship yet' : 'ship ready'}</td>
        <td>since turn ${e.started}</td></tr>`).join('');
    ai = `
      <h3>What the AI wants (turn ${p.ai.turn})</h3>
      <dl class="kv"><dt>Missing</dt><dd>${needs}</dd>${targets}
        ${notes ? `<dt>Decisions</dt><dd>${notes}</dd>` : ''}
        ${research ? `<dt>Research ranking</dt><dd>${research}</dd>` : ''}</dl>
      ${expeditions ? `<h3>Expeditions across the sea</h3>
        <table><thead><tr><th>Kind</th><th>Stage</th><th>Ship</th><th></th></tr></thead>
          <tbody>${expeditions}</tbody></table>` : ''}
      <h3>Missions</h3>
      <table><thead><tr><th>Mission</th><th>Detail</th><th>Units</th><th>Priority</th></tr></thead>
        <tbody>${missions || '<tr><td colspan="4" class="muted">None</td></tr>'}</tbody></table>`;
  }

  container.innerHTML = `
    <h2>${swatch(p.color)}${p.nation} <span class="muted">— ${p.leader}</span></h2>
    <dl class="kv">
      <dt>Personality</dt><dd>${personality.join(', ') || 'balanced'}</dd>
      <dt>Government</dt><dd>${governmentName(p.government)}</dd>
      <dt>Treasury</dt><dd>${p.gold} gold
        (<span class="${p.income < 0 ? 'bad' : 'good'}">${p.income >= 0 ? '+' : ''}${p.income}</span> per turn)</dd>
      <dt>Rates</dt><dd>tax ${p.rates[0]}% · luxury ${p.rates[1]}% · science ${p.rates[2]}%</dd>
      <dt>Empire</dt><dd>${p.cities} cities, ${p.population} citizens, ${p.units} units
        (${p.ships} ships, ${p.aircraft} aircraft), ${p.wonders} wonders</dd>
      ${spaceshipLabel(p) ? `<dt>Spaceship</dt><dd class="parts">${spaceshipLabel(p)}</dd>` : ''}
      <dt>Research</dt><dd>${techName(p.researching)} — ${p.research_progress}/${p.research_cost}
        (+${p.science}/turn)<div class="bar"><span style="width:${progress}%"></span></div></dd>
      <dt>Advances</dt><dd>${p.techs}</dd>
    </dl>
    <h3>Relations</h3>
    <div>${relations}</div>
    ${ai}`;
  container.querySelectorAll('tr[data-x]').forEach((row) => {
    row.addEventListener('click', () =>
      emit('center', { x: Number(row.dataset.x), y: Number(row.dataset.y) }));
  });
}

export { swatch, techName, governmentName, yearLabel };
