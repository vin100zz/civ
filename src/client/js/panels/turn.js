// "Turn" panel of the person playing: what needs a decision, what threatens, which units
// still wait for orders, and how the cities are doing.

import { store, U, emit, player, leader, turnsFor } from '../state.js';
import { icon } from '../icons.js';
import { play, queue, activate, decisions } from '../play.js';
import { movesText } from './unitbar.js';

// The columns of the city table after its production: [field, icon, class, title].
const COLUMNS = [
  ['food_surplus', 'food', 'food', 'Food per turn'],
  ['surplus', 'shield', 'shield', 'Shields per turn'],
  ['trade', 'trade', 'trade', 'Trade per turn'],
  ['unhappy', 'unhappy', 'bad', 'Unhappy citizens'],
];

// What is wrong with a city, in the order its icons follow the name: [field, icon, level].
// 'bad' already costs something next turn; 'warn' stops the city short of it.
function problems(city) {
  const list = [];
  if (city.food_surplus < 0) list.push(['food_surplus', 'food', 'bad']);
  else if (city.food_surplus === 0) list.push(['food_surplus', 'food', 'warn']);
  if (city.surplus < 0) list.push(['surplus', 'shield', 'bad']);
  else if (city.surplus === 0) list.push(['surplus', 'shield', 'warn']);
  if (city.unhappy > city.happy) list.push(['unhappy', 'unhappy', 'bad']);
  else if (city.growth_disorder) list.push(['unhappy', 'unhappy', 'warn']);
  return list;
}

const PROBLEM = {
  food_surplus: { bad: 'Famine', warn: 'No growth' },
  surplus: { bad: 'Units without support', warn: 'No production' },
  unhappy: { bad: 'Civil disorder', warn: 'Disorder if it grows' },
};

function cityRow(city, color) {
  const wrong = problems(city);
  const level = wrong.some(([, , l]) => l === 'bad') ? 'bad' : wrong.length ? 'warn' : '';
  const marks = wrong.map(([field, glyph, l]) =>
    `<span class="${l}" title="${PROBLEM[field][l]}">${icon(glyph, 14, 2)}</span>`).join('');
  const turns = city.idle ? null : turnsFor(city.cost - city.shields, city.surplus);
  const when = city.idle ? '<span class="bad">—</span>'
    : turns === null ? '<span class="bad">∞</span>'
      : turns <= 1 ? '<span class="good">1</span>' : turns;
  const flags = [];
  if (city.governed) flags.push(`<span class="flag icon" title="Governor">${icon('cog', 12, 2)}</span>`);
  if (city.buy !== null && !city.idle) flags.push(`<span class="flag gold" title="Buy">${city.buy}g</span>`);
  const cells = COLUMNS.map(([field, , kind]) => {
    const cause = wrong.find(([f]) => f === field);
    const value = city[field];
    const faint = value === 0 && (!cause || field === 'unhappy');
    const classes = [faint ? 'faint' : kind, cause ? `cause ${cause[2]}` : ''].join(' ');
    return `<span class="cell"><span class="${classes}">${value}</span></span>`;
  }).join('');
  return `<button class="city-row" data-city="${city.id}">
    <span class="size" style="background:${color}">${city.size}</span>
    <span class="name ${level}"><span>${city.capital ? '★ ' : ''}${city.name}</span>${marks}</span>
    <span class="making"><span><span class="what${city.idle ? ' bad' : ''}">${city.idle ? 'Nothing' : city.production}</span>${flags.join('')}</span>
      <span class="bar thin"><span style="width:${city.idle ? 0 : Math.min(100, 100 * city.shields / city.cost)}%;background:var(--shield)"></span></span></span>
    <span class="when">${when}</span>${cells}</button>`;
}

function nearestCity(unit, cities) {
  let best = null;
  const w = store.map.width;
  for (const city of cities) {
    const dx = Math.abs(city.x - unit[U.X]);
    const distance = Math.max(Math.min(dx, w - dx), Math.abs(city.y - unit[U.Y]));
    if (!best || distance < best.distance) best = { city, distance };
  }
  return best;
}

function todo(text, detail, attributes, glyph, advice = false) {
  return `<button class="todo${advice ? ' advice' : ''}" ${attributes}><span class="mark">${icon(glyph, 18)}</span>
    <span class="body"><b>${text}</b><span>${detail}</span></span>${icon('right', 16, 2)}</button>`;
}

// What must be decided before the turn can end (play.js decisions).
function decisionRows() {
  const target = { proposal: (d) => `data-proposal="${d.id}"`, research: () => 'data-research',
    city: (d) => `data-city="${d.id}"` };
  return decisions().map((d) => todo(d.text, d.detail, target[d.kind](d), d.glyph));
}

// What is worth a look but does not hold the turn.
function adviceRows(me) {
  const rows = [];
  if (me.cities && me.forecast.science === 0 && me.government !== 'anarchy') {
    rows.push(todo('Your scientists have nothing to work with',
      'Raise the science rate, or let your cities grow', 'data-empire', 'flask', true));
  }
  if (me.can_launch) {
    rows.push(todo('Your spaceship can be launched', `${me.flight_years} years to Alpha Centauri`,
      'data-empire', 'rocket', true));
  }
  return rows;
}

export function renderTurn(container) {
  const state = store.state;
  const id = leader();
  if (id === null || !state.me) {
    container.innerHTML = '<p class="empty"><b>Nobody is playing</b>Start a new game and pick '
      + '"Play a civilization" to lead one yourself.</p>';
    return;
  }
  const me = state.me;
  const cities = state.cities.filter((city) => city.owner === id);
  const enemies = me.at_war.map((other) => player(other).nation);
  const waiting = queue();
  const scroll = container.scrollTop;

  const toDecide = decisionRows();
  const advice = adviceRows(me);
  const alerts = (state.alerts || []).map((alert) => `
    <button class="alert" data-x="${alert.x}" data-y="${alert.y}">
      <span class="mark">${icon('alert', 18)}</span><span class="body"><b>${alert.text}</b></span>
      <span class="link">Show</span></button>`);

  const units = waiting.map((unit) => {
    const definition = store.unitDefs[unit[U.TYPE]];
    const near = nearestCity(unit, cities);
    const place = !near ? '' : near.distance === 0 ? `In ${near.city.name}` : `Near ${near.city.name}`;
    const on = unit[U.ID] === play.unit;
    return `<button class="unit-row${on ? ' on' : ''}" data-unit="${unit[U.ID]}">
      <span class="unit-portrait" style="background:${me.color}"><img src="/resources/unit/${definition.sprite}.png" alt=""></span>
      <span class="body"><b>${definition.name}${unit[U.VETERAN] ? ' <small>veteran</small>' : ''}</b>
        ${place ? `<span>${place}</span>` : ''}</span>
      ${on ? '<span class="state">Active</span>' : `<span class="sub">${movesText(unit[U.MOVES])}</span>`}</button>`;
  });

  // Always in the same order, the order of their founding.
  const cityRows = [...cities].sort((a, b) => a.id - b.id).map((city) => cityRow(city, me.color));
  const columns = COLUMNS.map(([, glyph, kind, title]) =>
    `<span class="cell ${kind}" title="${title}">${icon(glyph, 15)}</span>`).join('');

  const heading = (text, count) => `<div class="turn-head label"><span>${text}</span><span>${count}</span></div>`;
  container.innerHTML = `
    <div class="panel-head">
      <div class="titles"><h1>${play.waiting ? 'The others are playing…' : 'Your turn'}</h1></div>
      ${enemies.length ? `<span class="pill war" title="At war with ${enemies.join(', ')}">At war with ${enemies.join(', ')}</span>` : ''}
    </div>
    ${toDecide.length ? `${heading('To decide before ending the turn', toDecide.length)}<div class="turn-list">${toDecide.join('')}</div>` : ''}
    ${advice.length ? `${heading('Worth a look', advice.length)}<div class="turn-list">${advice.join('')}</div>` : ''}
    ${alerts.length ? `${heading('Alerts', alerts.length)}<div class="turn-list">${alerts.join('')}</div>` : ''}
    ${heading('Units awaiting orders', waiting.length)}
    ${units.length ? `<div class="turn-list tight">${units.join('')}</div>` : ''}
    <div class="city-cols"><span class="label">Cities<span>${cities.length}</span></span>
      ${cities.length ? `<span class="when" title="Turns left">${icon('hourglass', 14)}</span>${columns}` : ''}</div>
    <div class="city-rows">${cityRows.join('') || '<span class="sub quiet">No city yet: found one with your Settlers (B).</span>'}</div>`;
  container.scrollTop = scroll;

  container.querySelectorAll('[data-unit]').forEach((row) => {
    row.addEventListener('click', () => activate(Number(row.dataset.unit)));
  });
  container.querySelectorAll('[data-city]').forEach((row) => {
    row.addEventListener('click', () => {
      const city = cities.find((c) => c.id === Number(row.dataset.city));
      emit('select-city', city.id);
      emit('center', { x: city.x, y: city.y });
    });
  });
  container.querySelectorAll('[data-x]').forEach((row) => {
    row.addEventListener('click', () =>
      emit('locate', { x: Number(row.dataset.x), y: Number(row.dataset.y) }));
  });
  container.querySelectorAll('[data-proposal]').forEach((row) => {
    row.addEventListener('click', () => emit('open-proposal', Number(row.dataset.proposal)));
  });
  const research = container.querySelector('[data-research]');
  if (research) research.addEventListener('click', () => emit('open-research'));
  container.querySelectorAll('[data-empire]').forEach((row) => {
    row.addEventListener('click', () => emit('show-tab', 'civ'));
  });
}
