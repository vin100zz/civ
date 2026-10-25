// "Turn" panel of the person playing: what needs a decision, what threatens, which units
// still wait for orders, and how the cities are doing.

import { store, U, emit, leader, plural, turnsFor, queueGroups } from '../state.js';
import { send } from '../net.js';
import { icon, vetMark } from '../icons.js';
import { play, queue, activate, decisions } from '../play.js';
import { movesText } from './unitbar.js';
import { unitImage } from '../renderer/sprites.js';
import { turnNews, toneOf } from '../news.js';

const NEWS_SHOWN = 6;           // the newest events; the others behind "N more"
const NEWS_LOOK = { bad: 'alert', good: 'check', info: 'scroll' };
let newsOpen = null;            // the turn whose whole list of news is shown

function newsRows(me, key) {
  const rows = [...turnNews()].reverse().map((event) => {
    const tone = toneOf(event, me);
    const located = event.x !== undefined;
    const inner = `<span class="mark">${icon(NEWS_LOOK[tone], 15, 2)}</span><span class="text">${event.text}</span>`;
    return located
      ? `<button class="news-row ${tone}" data-x="${event.x}" data-y="${event.y}">${inner}<span class="link">Show</span></button>`
      : `<div class="news-row ${tone}">${inner}</div>`;
  });
  if (rows.length <= NEWS_SHOWN) return rows;
  if (newsOpen === key) return [...rows, '<button class="news-more" data-news-more>Show fewer</button>'];
  return [...rows.slice(0, NEWS_SHOWN), `<button class="news-more" data-news-more>${rows.length - NEWS_SHOWN} more</button>`];
}

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
  // A city living on its food box for long is only stopped short, until its famine is near.
  if (city.food_surplus < 0) list.push(['food_surplus', 'food', city.famine.near ? 'bad' : 'warn']);
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
  const marks = wrong.map(([field, glyph, l]) => {
    const title = field === 'food_surplus' && city.famine ? `Famine in ${plural(city.famine.turns, 'turn')}` : PROBLEM[field][l];
    return `<span class="${l}" title="${title}">${icon(glyph, 14, 2)}</span>`;
  }).join('');
  const flags = [];
  // The turns before the production is done, next to it.
  if (!city.idle) {
    const turns = turnsFor(city.cost - city.shields, city.surplus);
    const pace = turns === null ? ' bad' : turns <= 1 ? ' good' : '';
    flags.push(`<span class="flag turns${pace}" title="${turns === null ? 'No shields to spare: never done' : 'Turns left'}">`
      + `${icon('hourglass', 11, 2)}${turns === null ? '∞' : Math.max(1, turns)}</span>`);
  }
  if (city.governed) flags.push(`<span class="flag icon" title="Governor">${icon('cog', 12, 2)}</span>`);
  if (city.queue && city.queue.length) {
    // What comes next, and the turns before each is done, in its tooltip.
    const next = queueGroups(city.queue).map((g) =>
      `${g.name}${g.count > 1 ? ` ×${g.count}` : ''}${g.turns === null ? '' : ` (${g.turns})`}`).join(', ');
    flags.push(`<span class="flag queued" title="Then: ${next}">+${city.queue.length}</span>`);
  }
  const cells = COLUMNS.map(([field, , kind]) => {
    const cause = wrong.find(([f]) => f === field);
    const value = city[field];
    const faint = value === 0 && (!cause || field === 'unhappy');
    const classes = [faint ? 'faint' : kind, cause ? `cause ${cause[2]}` : ''].join(' ');
    return `<span class="cell"><span class="${classes}">${value}</span></span>`;
  }).join('');
  return `<button class="city-row${city.id === store.selectedCity ? ' selected' : ''}" data-city="${city.id}">
    <span class="size" style="background:${color}">${city.size}</span>
    <span class="name ${level}"><span>${city.capital ? '★ ' : ''}${city.name}</span>${marks}</span>
    <span class="making"><span><span class="what${city.idle ? ' bad' : ''}">${city.idle ? 'Nothing' : city.production}</span>${flags.join('')}</span>
      <span class="bar thin"><span style="width:${city.idle ? 0 : Math.min(100, 100 * city.shields / city.cost)}%;background:var(--shield)"></span></span></span>${cells}</button>`;
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
    <span class="body"><b>${text}</b>${detail ? `<span>${detail}</span>` : ''}</span>${icon('right', 16, 2)}</button>`;
}

// What must be decided before the turn can end (play.js decisions).
function decisionRows() {
  const target = { proposal: (d) => `data-proposal="${d.id}"`, research: () => 'data-research',
    city: (d) => `data-city="${d.id}"` };
  return decisions().map((d) => todo(d.text, d.detail, target[d.kind](d), d.glyph));
}

// The rates the server proposes to stop the treasury losing gold, for a tooltip.
export function balanceText(balance) {
  const [tax, luxury, science] = balance.rates;
  const gold = balance.gold >= 0 ? `+${balance.gold}` : balance.gold;
  return `Tax ${tax}% · Lux ${luxury}% · Sci ${science}%: ${gold} gold per turn`;
}

export function balanceButton(balance) {
  return `<button class="btn small" data-balance title="${balanceText(balance)}">${balance.gold >= 0 ? 'Balance' : 'Raise taxes'}</button>`;
}

export function applyBalance(balance) {
  const [tax, luxury, science] = balance.rates;
  send({ cmd: 'action', action: 'rates', tax, luxury, science });
}

// The treasury is about to sell a building: where, and the rates that would avoid it.
function treasuryRow(alert, me) {
  return `<div class="alert treasury ${alert.level}">
    <button class="alert-main" data-x="${alert.x}" data-y="${alert.y}">
      <span class="mark">${icon('coin', 18)}</span>
      <span class="body"><b>${alert.text}</b><span>${alert.detail}</span></span></button>
    ${me.balance ? balanceButton(me.balance) : ''}</div>`;
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
  const waiting = queue();
  const scroll = container.scrollTop;

  const toDecide = decisionRows();
  const advice = adviceRows(me);
  const alerts = (state.alerts || []).map((alert) => alert.kind === 'treasury' ? treasuryRow(alert, me) : `
    <button class="alert" data-x="${alert.x}" data-y="${alert.y}">
      <span class="mark">${icon('alert', 18)}</span><span class="body"><b>${alert.text}</b></span>
      <span class="link">Show</span></button>`);

  // Why a unit left to itself is back in the person's hands (a sentry woken up, a blocked way).
  const reasons = new Map((state.notes || []).filter((note) => note.reason).map((note) => [note.unit, note.reason]));
  const units = waiting.map((unit) => {
    const definition = store.unitDefs[unit[U.TYPE]];
    const near = nearestCity(unit, cities);
    const place = !near ? '' : near.distance === 0 ? `In ${near.city.name}` : `Near ${near.city.name}`;
    const reason = reasons.get(unit[U.ID]);
    const on = unit[U.ID] === play.unit;
    return `<button class="unit-row${on ? ' on' : ''}" data-unit="${unit[U.ID]}">
      <span class="unit-portrait" style="background:${me.color}">${unitImage(definition)}</span>
      <span class="body"><b>${definition.name}${unit[U.VETERAN] ? vetMark() : ''}</b>
        ${reason || place ? `<span>${reason ? `<span class="reason">${reason}</span>${place ? ' · ' : ''}` : ''}${place}</span>` : ''}</span>
      ${on ? '<span class="state">Active</span>' : `<span class="sub">${movesText(unit[U.MOVES])}</span>`}</button>`;
  });

  // Always in the same order, the order of their founding.
  const cityRows = [...cities].sort((a, b) => a.id - b.id).map((city) => cityRow(city, me.color));
  const columns = COLUMNS.map(([, glyph, kind, title]) =>
    `<span class="cell ${kind}" title="${title}">${icon(glyph, 15)}</span>`).join('');

  const newsKey = `${state.seed}:${state.turn}`;
  const news = newsRows(id, newsKey);
  const heading = (text, count) => `<div class="turn-head label"><span>${text}</span><span>${count}</span></div>`;
  container.innerHTML = `
    <div class="panel-head">
      <div class="titles"><h1>${play.waiting ? 'The others are playing…' : 'Turn'}</h1></div>
    </div>
    ${toDecide.length ? `${heading('To decide before ending the turn', toDecide.length)}<div class="turn-list">${toDecide.join('')}</div>` : ''}
    ${advice.length ? `${heading('Worth a look', advice.length)}<div class="turn-list">${advice.join('')}</div>` : ''}
    ${alerts.length ? `${heading('Alerts', alerts.length)}<div class="turn-list">${alerts.join('')}</div>` : ''}
    ${news.length ? `${heading('Since your last turn', turnNews().length)}<div class="turn-list tight">${news.join('')}</div>` : ''}
    ${heading('Units awaiting orders', waiting.length)}
    ${units.length ? `<div class="turn-list tight">${units.join('')}</div>` : ''}
    <div class="city-cols"><span class="label">Cities<span>${cities.length}</span></span>
      ${cities.length ? columns : ''}</div>
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
  const moreNews = container.querySelector('[data-news-more]');
  if (moreNews) {
    moreNews.addEventListener('click', () => {
      newsOpen = newsOpen === newsKey ? null : newsKey;
      renderTurn(container);
    });
  }
  container.querySelectorAll('[data-proposal]').forEach((row) => {
    row.addEventListener('click', () => emit('open-proposal', Number(row.dataset.proposal)));
  });
  const balance = container.querySelector('[data-balance]');
  if (balance) balance.addEventListener('click', () => applyBalance(me.balance));
  const research = container.querySelector('[data-research]');
  if (research) research.addEventListener('click', () => emit('open-research'));
  container.querySelectorAll('[data-empire]').forEach((row) => {
    row.addEventListener('click', () => emit('show-tab', 'civ'));
  });
}
