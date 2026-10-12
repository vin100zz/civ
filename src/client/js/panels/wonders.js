// "Wonders" panel: every wonder of the rules, in their order. A built one shows its city, the
// civilization holding it and the year it was completed, or the city it was lost with; the
// others whether they can still be built: by the person (in one of its cities already, or
// within reach), after an advance, or no longer, once an advance has made them obsolete.

import { store, emit, leader, player, plural, turnsFor, yearLabel } from '../state.js';
import { icon } from '../icons.js';
import { setTips } from '../tips.js';
import { techName } from './civs.js';

const STAR = '<svg class="icon" width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
  + '<path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.2l-5.7 3.1 1.2-6.4-4.7-4.4 6.4-.8z"/></svg>';

// The city of the person furthest along on the wonder, if one is building it.
function makingIn(wonderId, id) {
  const cities = store.state.cities.filter((city) => city.owner === id && city.item
    && city.item[0] === 'building' && city.item[1] === wonderId);
  return cities.sort((a, b) => b.shields - a.shields)[0] || null;
}

function progress(city) {
  const turns = turnsFor(city.cost - city.shields, city.surplus);
  return `${city.shields}/${city.cost}${turns === null ? '' : ` · ${plural(turns, 'turn')}`}`;
}

const done = (city) => Math.min(100, Math.round((100 * city.shields) / city.cost));

// What a wonder stands at: 'built', 'lost' (with its city), 'making' (by the person), 'late'
// (obsolete before anyone built it), 'can' (the person knows its advance) or 'needs'.
function stage(wonder, definition, me, making) {
  if (wonder.built) return wonder.lost ? 'lost' : 'built';
  if (making) return 'making';
  if (wonder.obsolete) return 'late';
  if (me && (!definition.requires || me.tech_list.includes(definition.requires))) return 'can';
  return 'needs';
}

// Built: a square in the colour of the civilization holding it, with a star (grey once lost).
// Otherwise an outline: dashed green within the person's reach, filling up while one of its
// cities builds it.
function mark(wonder, kind, making) {
  if (kind === 'built') return `<span class="wonder-mark" style="background:${player(wonder.owner).color}">${STAR}</span>`;
  if (kind === 'lost') return `<span class="wonder-mark lost">${STAR}</span>`;
  if (kind === 'making') return `<span class="wonder-mark open"><i style="height:${done(making)}%"></i></span>`;
  return `<span class="wonder-mark ${kind === 'needs' ? 'open' : kind}"></span>`;
}

function row(wonder, definition, kind, me, making) {
  const stopped = kind === 'built' && wonder.obsolete;
  const name = `<span class="name"><span>${definition.name}</span>${stopped ? icon('lost', 13, 2) : ''}</span>`;
  const year = `<span class="year">${wonder.year === null ? '' : yearLabel(wonder.year)}</span>`;
  let rest;
  let target = '';
  if (kind === 'built') {
    rest = `<span class="where"><span>${wonder.city}</span><small>${player(wonder.owner).nation}</small></span>${year}`;
    target = `data-city="${wonder.city_id}" data-x="${wonder.x}" data-y="${wonder.y}"`;
  } else if (kind === 'lost') {
    rest = `<span class="where">${wonder.city ? `<span>${wonder.city}</span><small>destroyed</small>` : '<span>Lost</span>'}</span>${year}`;
  } else if (kind === 'making') {
    rest = `<span class="underway"><span><b>${making.name}</b><span>${progress(making)}</span></span>
      <span class="bar thin"><span style="width:${done(making)}%"></span></span></span>`;
    target = `data-city="${making.id}" data-x="${making.x}" data-y="${making.y}"`;
  } else {
    const status = {
      late: 'Too late',
      can: 'You can build it',
      needs: me ? `Needs ${techName(definition.requires)}` : 'Not built yet',
    }[kind];
    rest = `<span class="note">${status}</span>`;
  }
  const tag = target ? 'button' : 'div';
  return `<${tag} class="wonder-row${stopped ? ' obsolete' : ''}" data-kind="${kind}" data-tip="${wonder.id}" ${target}>${mark(wonder, kind, making)}${name}${rest}</${tag}>`;
}

function tip(wonder, definition, kind, me, making) {
  const era = definition.requires && store.techDefs[definition.requires]
    ? store.techDefs[definition.requires].era : '';
  const rows = [];
  if (kind === 'built' || kind === 'lost') {
    if (kind === 'built') rows.push(['City', `${wonder.city} · ${player(wonder.owner).nation}`]);
    else if (wonder.city) rows.push(['City', `${wonder.city}, destroyed`]);
    if (wonder.year !== null) {
      const builder = wonder.builder !== wonder.owner ? player(wonder.builder) : null;
      rows.push(['Built', `${yearLabel(wonder.year)}${builder ? `, by the ${builder.nation}` : ''}`]);
    }
    let status = '<span class="good">Working</span>';
    if (kind === 'lost') status = '<span class="muted">Lost with its city: nobody can build it again</span>';
    else if (wonder.obsolete) status = `<span class="muted">No longer works: ${techName(definition.obsolete_by)} is known</span>`;
    rows.push(['Status', status]);
  } else {
    const known = me && definition.requires && me.tech_list.includes(definition.requires);
    if (definition.requires) {
      rows.push(['Requires', known ? `<span class="good">${techName(definition.requires)} ✓</span>` : techName(definition.requires)]);
    }
    rows.push(['Cost', `${definition.cost} shields`]);
    if (making) rows.push(['Building', `${making.name} · ${progress(making)}`]);
    if (wonder.obsolete) {
      rows.push(['Too late', `<span class="muted">${techName(definition.obsolete_by)} is known: nobody can build it any more.</span>`]);
    }
  }
  return `<div class="tip-title">${mark(wonder, kind, making)}<span>${definition.name}</span>`
    + `${era ? `<span class="mono">${era[0].toUpperCase()}${era.slice(1)}</span>` : ''}</div>`
    + `<p class="tip-text">${definition.description}</p>`
    + `<dl class="tip-rows">${rows.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join('')}</dl>`;
}

export function renderWonders(container) {
  const id = leader();
  const me = id !== null ? store.state.me : null;
  const wonders = store.state.wonders || [];
  const tips = new Map();
  const rows = wonders.map((wonder) => {
    const definition = store.buildingDefs[wonder.id];
    const making = me && !wonder.built ? makingIn(wonder.id, id) : null;
    const kind = stage(wonder, definition, me, making);
    tips.set(wonder.id, tip(wonder, definition, kind, me, making));
    return row(wonder, definition, kind, me, making);
  });
  const built = wonders.filter((wonder) => wonder.built).length;

  const scroll = container.scrollTop;
  container.innerHTML = `
    <div class="panel-head"><div class="titles"><h1>Wonders</h1></div>
      <span class="count"><b>${built}</b> of ${wonders.length} built</span></div>
    <div class="wonder-cols"><span class="name">Wonder</span><span class="where">City</span><span class="year">Year</span></div>
    <div class="wonder-rows">${rows.join('')}</div>`;
  container.scrollTop = scroll;
  setTips(container, tips);

  // A city of the person (or any, for the observer) opens; a foreign one is shown on the map.
  container.querySelectorAll('button[data-city]').forEach((button) => {
    button.addEventListener('click', () => {
      const cityId = Number(button.dataset.city);
      const x = Number(button.dataset.x);
      const y = Number(button.dataset.y);
      const city = store.state.cities.find((c) => c.id === cityId);
      if (city && (id === null || city.owner === id)) {
        emit('select-city', cityId);
        emit('center', { x, y });
      } else {
        emit('locate', { x, y });
      }
    });
  });
}
