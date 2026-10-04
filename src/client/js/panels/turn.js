// "Turn" panel of the person playing: what needs a decision, what threatens, which units
// still wait for orders, how the cities are doing, and what happened since the last turn.

import { store, U, emit, player, leader, yearLabel, plural, turnsFor } from '../state.js';
import { icon } from '../icons.js';
import { play, queue, activate, decisions } from '../play.js';
import { governmentName, techName } from './civs.js';
import { movesText } from './unitbar.js';
import { groupOf } from './log.js';

let messages = [];          // events told with the last "turn" message

export function setTurnMessages(events) {
  messages = events;
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
        <span>${place}${place ? ' · ' : ''}<span class="mono">${unit[U.X]}, ${unit[U.Y]}</span></span></span>
      ${on ? '<span class="state">Active</span>' : `<span class="sub">${movesText(unit[U.MOVES])}</span>`}</button>`;
  });

  const cityRows = [...cities].sort((a, b) => {
    const turns = (c) => (c.idle ? -1 : turnsFor(c.cost - c.shields, c.surplus) ?? 9999);
    return turns(a) - turns(b) || a.id - b.id;
  }).map((city) => {
    const turns = city.idle ? null : turnsFor(city.cost - city.shields, city.surplus);
    const when = city.idle ? '<span class="bad">idle</span>'
      : turns === null ? '<span class="bad">stalled</span>'
        : turns <= 1 ? '<span class="good">next turn</span>' : plural(turns, 'turn');
    const flags = [];
    if (city.disorder) flags.push('<span class="flag bad">Disorder</span>');
    if (city.governed) flags.push('<span class="flag">Governor</span>');
    if (city.buy !== null && !city.idle) flags.push(`<span class="flag gold">Buy ${city.buy}g</span>`);
    return `<button class="city-row" data-city="${city.id}">
      <span class="size" style="background:${me.color}">${city.size}</span>
      <span class="name">${city.capital ? '★ ' : ''}${city.name}</span>
      <span class="making"><span>${city.idle ? 'Nothing' : city.production}${flags.join('')}</span>
        <span class="bar thin"><span style="width:${city.idle ? 0 : Math.min(100, 100 * city.shields / city.cost)}%;background:var(--shield)"></span></span></span>
      <span class="when">${when}</span></button>`;
  });

  const notes = (state.notes || []).map((note) => `
    <button class="event-row" data-x="${note.x}" data-y="${note.y}">
      <span class="when">you</span><span class="dot" style="background:${me.color}"></span>
      <span class="what">${note.text}</span></button>`);
  const news = messages.filter((event) => groupOf(event.type) !== 'Economy' || event.player === id)
    .slice(-12).reverse().map((event) => {
      const who = event.player !== undefined ? player(event.player) : null;
      const where = event.x !== undefined ? ` data-x="${event.x}" data-y="${event.y}"` : '';
      return `<button class="event-row"${where}>
        <span class="when">${yearLabel(event.year)}</span>
        <span class="dot" style="background:${who ? who.color : '#8A95A5'}"></span>
        <span class="what">${event.text}</span></button>`;
    });

  const heading = (text, count) => `<div class="turn-head label"><span>${text}</span><span>${count}</span></div>`;
  container.innerHTML = `
    <div class="panel-head">
      <div class="titles"><h1>${play.waiting ? 'The others are playing…' : 'Your turn'}</h1>
        <span class="sub">${me.leader} of the ${me.nation} · ${governmentName(me.government)}</span></div>
      ${enemies.length ? `<span class="pill war" title="At war with ${enemies.join(', ')}">At war with ${enemies.join(', ')}</span>` : ''}
    </div>
    <div class="section" style="padding-top:16px">
      <div class="stats">
        <div class="stat"><b>${me.cities}</b><span>Cities</span></div>
        <div class="stat"><b>${me.units}</b><span>Units</span></div>
        <div class="stat"><b>${me.techs}</b><span>Advances</span></div>
        <div class="stat"><b>${me.score}</b><span>Score</span></div>
      </div>
    </div>
    ${toDecide.length ? `${heading('To decide before ending the turn', toDecide.length)}<div class="turn-list">${toDecide.join('')}</div>` : ''}
    ${advice.length ? `${heading('Worth a look', advice.length)}<div class="turn-list">${advice.join('')}</div>` : ''}
    ${alerts.length ? `${heading('Alerts', alerts.length)}<div class="turn-list">${alerts.join('')}</div>` : ''}
    ${heading('Units awaiting orders', waiting.length)}
    <div class="turn-list tight">${units.join('') || '<span class="sub quiet">Every unit has its orders.</span>'}</div>
    ${heading('Cities', cities.length)}
    <div class="city-rows">${cityRows.join('') || '<span class="sub quiet">No city yet: found one with your Settlers (B).</span>'}</div>
    ${notes.length || news.length ? `${heading('Since your last turn', notes.length + news.length)}${notes.join('')}${news.join('')}` : ''}
    <div class="panel-foot">Researching ${techName(me.researching)} · click a unit on the map to give it orders,
      a city to manage it.</div>`;
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
