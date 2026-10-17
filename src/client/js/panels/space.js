// "Space" panel: the space race. Who lands on Alpha Centauri first, and whether anyone can
// still catch up; then each civilization's spaceship against what a launch needs, the parts
// its cities are building and when it could leave. The parts built are public to those who
// have met a civilization, the parts in production stay with their owner (and the observer).

import { store, emit, leader, plural, swatch, yearLabel } from '../state.js';
import { send } from '../net.js';
import { icon } from '../icons.js';

// Width of a segment of a gauge, the gap between two, and the launch line (with its margins
// and the gap it adds).
const SEG = 7;
const GAP = 2;
const LINE = 8;
// Civilizations never met (stage 'unknown') are only counted, unless their ship has left.
const ORDER = ['landed', 'flying', 'ready', 'building', 'lost', 'idle', 'unknown'];

function kinds() {
  return Object.keys(store.rules.spaceship.min_parts);
}

// The building that adds a part of that kind to the ship (SS Structural...).
function partDef(kind) {
  return store.rules.buildings.find((b) => b.part === kind);
}

function techName(id) {
  return id && store.techDefs[id] ? store.techDefs[id].name : id;
}

// Years of the space age without "AD", which takes room and says nothing there.
function yr(year) {
  return year < 0 ? yearLabel(year) : String(year);
}

function built(p, kind) {
  return p.spaceship.parts[kind] || 0;
}

// Parts still missing for a launch: {kind: count}, and their total.
function missing(p) {
  const minimum = store.rules.spaceship.min_parts;
  const lacking = {};
  let total = 0;
  for (const kind of kinds()) {
    const count = Math.max(0, minimum[kind] - built(p, kind));
    if (count) lacking[kind] = count;
    total += count;
  }
  return { lacking, total };
}

// "1 module", "3 parts".
function missingLabel({ lacking, total }) {
  const entries = Object.entries(lacking);
  return entries.length === 1 ? plural(entries[0][1], entries[0][0]) : plural(total, 'part');
}

// Share of the parts a launch needs that are built, from 0 to 1.
function readiness(p) {
  const minimum = store.rules.spaceship.min_parts;
  const need = kinds().reduce((sum, kind) => sum + minimum[kind], 0);
  const have = kinds().reduce((sum, kind) => sum + Math.min(minimum[kind], built(p, kind)), 0);
  return have / need;
}

// The last time the civilization lost its ship with its capital, as the chronicle tells.
function lostEvent(p) {
  for (let i = store.log.length - 1; i >= 0; i--) {
    const event = store.log[i];
    if (event.type === 'spaceship_lost' && event.player === p.id) return event;
  }
  return null;
}

function stage(p) {
  const ship = p.spaceship;
  if (ship.arrival_turn !== null && ship.arrival_turn <= store.state.turn) return 'landed';
  if (ship.launched_turn !== null) return 'flying';
  if (p.met === false) return 'unknown';
  const parts = kinds().some((kind) => built(p, kind) > 0);
  if (parts && missing(p).total === 0) return 'ready';
  if (parts || ship.making.length) return 'building';
  return lostEvent(p) ? 'lost' : 'idle';
}

// The civilizations still in the race, the likeliest to land first at the top.
function rows() {
  const list = store.state.players.filter((p) => !p.barbarian && p.alive)
    .map((p) => ({ p, stage: stage(p) }));
  const landing = ({ p }) => {
    const ship = p.spaceship;
    if (ship.arrival_turn !== null) return ship.arrival_turn;
    return ship.projection ? ship.projection.arrival_turn : Infinity;
  };
  return list.sort((a, b) => ORDER.indexOf(a.stage) - ORDER.indexOf(b.stage)
    || landing(a) - landing(b) || readiness(b.p) - readiness(a.p) || a.p.id - b.p.id);
}

function capitalName(id) {
  const city = store.state.cities.find((c) => c.owner === id && c.capital);
  return city ? city.name : null;
}

// ── Verdict ──────────────────────────────────────────────────────────────────

function verdict(list) {
  const me = leader();
  const turn = store.state.turn;
  const minYears = store.rules.spaceship.min_flight_years;
  const first = list[0];
  if (!first || ['lost', 'idle', 'unknown'].includes(first.stage)) return '';
  const p = first.p;
  const ship = p.spaceship;
  const mine = p.id === me;
  // A launch is heard of by everyone, even from a civilization nobody has met.
  const stranger = p.met === false;
  const they = stranger ? 'A civilization you have not met' : `The ${p.nation}`;
  let title;
  let text;
  if (first.stage === 'landed') {
    title = `${mine ? 'Your spaceship' : they} reached Alpha Centauri in ${yr(ship.arrival_year)}`;
    text = `After ${plural(ship.flight_years, 'year')} of flight.`;
  } else if (first.stage === 'flying') {
    const left = plural(ship.arrival_turn - turn, 'turn');
    title = mine ? `Your spaceship lands in ${left}, in ${yr(ship.arrival_year)}`
      : `${they} ${stranger ? 'lands' : 'land'} in ${left}, in ${yr(ship.arrival_year)}`;
    const capital = capitalName(p.id);
    if (store.state.space.earliest_landing >= ship.arrival_turn) {
      text = `Nobody can catch up: a ship leaving now would need ${plural(minYears, 'year')} at least. `
        + (mine ? `Keep ${capital || 'your capital'} safe: the ship is lost with it.`
          : `Only the fall of ${capital || 'their capital'} stops it.`);
    } else {
      const faster = list.filter((row) => row !== first && row.p.spaceship.projection
        && row.p.spaceship.projection.arrival_turn < ship.arrival_turn);
      text = faster.length
        ? `${faster.map((row) => (row.p.id === me ? 'You' : `The ${row.p.nation}`)).join(', ')} could still land first, as things stand.`
        : `Still within reach: a ship leaving now with ${plural(minYears, 'year')} of flight would land first.`;
    }
  } else {
    title = 'No spaceship has left yet';
    const projected = list.filter((row) => row.p.spaceship.projection);
    if (projected.length) {
      const next = projected[0].p;
      const plan = next.spaceship.projection;
      const leaves = plan.launch_turn === turn ? 'leaving now' : `leaving about ${yr(plan.launch_year)}`;
      text = `First to land as things stand: ${next.id === me ? 'you' : `the ${next.nation}`}, ${leaves}, `
        + `about ${yr(plan.arrival_year)} (${plural(plan.flight_years, 'year')} of flight).`;
    } else {
      const minimum = store.rules.spaceship.min_parts;
      const need = kinds().reduce((sum, kind) => sum + minimum[kind], 0);
      text = `Closest: ${p.id === me ? 'you' : `the ${p.nation}`}, `
        + `${Math.round(readiness(p) * need)} of the ${need} parts a launch needs.`;
    }
  }
  return `<div class="ss-verdict">
    <span class="ss-verdict-icon" style="color:${p.color}">${icon('rocket', 20, 1.8)}</span>
    <div><b>${title}</b><span class="sub">${text}</span></div></div>`;
}

// ── Arrival timeline ─────────────────────────────────────────────────────────

// Ships in flight (launch to landing) and the ones whose departure can be told (dotted until
// then, dashed in flight), on a scale of years with the current one marked.
function timeline(list) {
  const year = store.state.year;
  const tracks = list.filter(({ p, stage: kind }) => ['landed', 'flying'].includes(kind)
    || p.spaceship.projection).map(({ p }) => {
    const ship = p.spaceship;
    return ship.launched_turn !== null
      ? { p, from: ship.launched_year, to: ship.arrival_year, flying: true }
      : { p, from: ship.projection.launch_year, to: ship.projection.arrival_year, flying: false };
  });
  if (!tracks.length) return '';
  const lo = Math.min(year, ...tracks.map((t) => t.from)) - 1;
  const hi = Math.max(year + 12, ...tracks.map((t) => t.to)) + 1;
  const span = hi - lo;
  const step = span <= 24 ? 5 : span <= 60 ? 10 : 20;
  const [left, right, top, rowH] = [84, 368, 18, 22];
  const x = (y) => left + ((y - lo) * (right - left)) / span;
  const axis = top + tracks.length * rowH + 4;
  const marks = [];
  tracks.forEach((track, i) => {
    const y = top + i * rowH + 10;
    const { p } = track;
    const [a, b] = [x(track.from), x(track.to)];
    marks.push(`<rect x="0" y="${y - 5}" width="10" height="10" rx="3" fill="${p.color}"/>`
      + `<text x="16" y="${y + 4}" class="ss-t-soft">${p.id === leader() ? 'You' : p.nation}</text>`);
    if (track.flying) {
      marks.push(`<line x1="${a}" y1="${y}" x2="${b}" y2="${y}" stroke="${p.color}" stroke-width="4" stroke-linecap="round"/>`);
      if (track.to > year) marks.push(`<circle cx="${x(year)}" cy="${y}" r="5" fill="${p.color}" class="ss-s-panel" stroke-width="2"/>`);
      marks.push(`<path d="M${b} ${y - 6}l4.5 6-4.5 6-4.5-6z" fill="${p.color}"/>`);
    } else {
      if (a > x(year)) {
        marks.push(`<line x1="${x(year)}" y1="${y}" x2="${a}" y2="${y}" stroke="${p.color}" stroke-width="1.5" stroke-dasharray="1 3" stroke-linecap="round"/>`);
      }
      marks.push(`<line x1="${a}" y1="${y}" x2="${b}" y2="${y}" stroke="${p.color}" stroke-width="4" stroke-dasharray="6 4" opacity="0.7"/>`
        + `<path d="M${b} ${y - 6}l4.5 6-4.5 6-4.5-6z" fill="none" stroke="${p.color}" stroke-width="1.5"/>`);
    }
    marks.push(`<text x="${b + 8}" y="${y + 4}" class="${track.flying ? 'ss-t-text' : 'ss-t-soft'}">${track.flying ? '' : '≈'}${yr(track.to)}</text>`);
  });
  const ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) {
    if (Math.abs(t - year) * (right - left) < span * 32) continue;   // the current year is labelled
    ticks.push(`<line x1="${x(t)}" y1="${axis}" x2="${x(t)}" y2="${axis + 4}" class="ss-s-line"/>`
      + `<text x="${x(t)}" y="${axis + 16}" text-anchor="middle" class="ss-t-mute">${yr(t)}</text>`);
  }
  const now = x(year);
  return `<svg class="ss-timeline" viewBox="0 0 408 ${axis + 22}" role="img" aria-label="When the spaceships land">
    <line x1="${left}" y1="${axis}" x2="${right}" y2="${axis}" class="ss-s-line"/>${ticks.join('')}
    <line x1="${now}" y1="${top - 6}" x2="${now}" y2="${axis}" class="ss-s-gold" stroke-dasharray="2 3"/>
    <text x="${now}" y="${axis + 16}" text-anchor="middle" class="ss-t-gold">${yr(year)}</text>
    ${marks.join('')}</svg>`;
}

// ── Rows ─────────────────────────────────────────────────────────────────────

function groupWidth(kind) {
  const max = store.rules.spaceship.max_parts[kind];
  return max * SEG + (max - 1) * GAP + LINE + 6 + 16;
}

// One kind of part: a segment per part the ship can hold, filled when built, filling up in
// production; outlined up to the minimum a launch needs, which the gold line closes.
function gauge(p, kind) {
  const minimum = store.rules.spaceship.min_parts[kind];
  const max = store.rules.spaceship.max_parts[kind];
  const have = built(p, kind);
  const making = p.spaceship.making.filter((row) => row.part === kind);
  const segs = [];
  for (let i = 0; i < max; i++) {
    if (i < have) {
      segs.push('<i class="ss-seg on"></i>');
    } else if (i < have + making.length) {
      const row = making[i - have];
      segs.push(`<i class="ss-seg make" style="--p:${Math.min(100, Math.round((100 * row.shields) / row.cost))}%"></i>`);
    } else {
      segs.push(`<i class="ss-seg ${i < minimum ? 'req' : 'opt'}"></i>`);
    }
    if (i === minimum - 1) segs.push('<u class="launch-line"></u>');
  }
  return `<span class="ss-gauge" style="width:${groupWidth(kind)}px"><span class="ss-segs">${segs.join('')}</span><b>${have}</b></span>`;
}

function status(p, kind) {
  const ship = p.spaceship;
  switch (kind) {
    case 'landed': return '<span class="ss-state good">Landed</span>';
    case 'flying': return `<span class="ss-state fly">${icon('rocket', 14, 2)}In flight · ${plural(ship.arrival_turn - store.state.turn, 'turn')}</span>`;
    case 'ready': return '<span class="ss-state ready">Ready to launch</span>';
    case 'building': return `<span class="ss-state">${missingLabel(missing(p))} to go</span>`;
    case 'lost': return `<span class="ss-state bad">${icon('lost', 13, 2)}Lost · ${yr(lostEvent(p).year)}</span>`;
    default: return '<span class="ss-state mute">No parts yet</span>';
  }
}

// The parts its cities are building, then when the ship could leave.
function building(p) {
  const ship = p.spaceship;
  const lines = [];
  if (ship.making.length) {
    const shown = ship.making.slice(0, 3).map((row) => `<button class="ss-city" data-city="${row.city_id}" data-x="${row.x}" data-y="${row.y}">`
      + `<b>${row.city}</b> ${partDef(row.part).name} ${row.turns === null ? 'stalled' : `in ${plural(row.turns, 'turn')}`}</button>`);
    if (ship.making.length > 3) shown.push(`<span>+${ship.making.length - 3} more</span>`);
    lines.push(`<span class="ss-making">${shown.join('')}</span>`);
  }
  const plan = ship.projection;
  if (plan) {
    lines.push(`<span>Leaves ≈${yr(plan.launch_year)} · ${plural(plan.flight_years, 'year')} of flight · lands ≈${yr(plan.arrival_year)}</span>`);
  } else if (p.id === leader() || leader() === null) {
    // What no city builds yet, for those who see the cities' production.
    const { lacking } = missing(p);
    const idle = Object.entries(lacking).map(([kind, count]) =>
      [kind, count - ship.making.filter((row) => row.part === kind).length]).filter(([, count]) => count > 0);
    if (idle.length) lines.push(`<span>Not in production yet: ${idle.map(([kind, count]) => plural(count, kind)).join(', ')}</span>`);
  }
  return lines;
}

function meta(p, kind) {
  const ship = p.spaceship;
  const me = store.state.me;
  let lines = [];
  if (kind === 'landed') {
    lines = [`<span>Landed in ${yr(ship.arrival_year)} after ${plural(ship.flight_years, 'year')} of flight</span>`];
  } else if (kind === 'flying') {
    const done = (store.state.turn - ship.launched_turn) / (ship.arrival_turn - ship.launched_turn);
    lines = [`<span>${plural(ship.flight_years, 'year')} of flight · launched ${yr(ship.launched_year)} · lands <b>${yr(ship.arrival_year)}</b></span>`
      + `<span class="bar thin"><span style="width:${Math.round(100 * done)}%;background:${p.color}"></span></span>`];
  } else if (kind === 'ready') {
    const plan = ship.projection;
    lines = [plan ? `<span>${plural(ship.flight_years, 'year')} of flight if it leaves now · lands ≈${yr(plan.arrival_year)}</span>`
      : '<span>No capital: it cannot leave</span>'];
    if (p.id === leader() && me && me.can_launch) {
      lines.push(`<button class="btn small primary" data-launch>${icon('rocket', 15, 2)}Launch · ${plural(me.flight_years, 'year')} of flight</button>`);
    }
    if (ship.making.length) lines.unshift(...building(p).slice(0, 1));
  } else if (kind === 'building') {
    lines = building(p);
  } else if (kind === 'lost') {
    lines = ['<span>Lost with its capital: every part is to be built again</span>'];
  }
  return lines.map((line) => `<div class="ss-meta">${line}</div>`).join('');
}

function row({ p, stage: kind }) {
  const you = p.id === leader() ? ' · you' : '';
  const gauges = p.met === false ? '<div class="ss-meta">Parts unknown: you have not met them</div>'
    : `<div class="ss-gauges" style="--c:${p.color}">${kinds().map((k) => gauge(p, k)).join('')}</div>`;
  return `<div class="ss-row${kind === 'idle' ? ' quiet' : ''}">
    <span class="ss-line"><button class="ss-name" data-player="${p.id}">${swatch(p.color)}<span>${p.nation}${you}</span></button>${status(p, kind)}</span>
    ${gauges}${meta(p, kind)}</div>`;
}

// ── Panel ────────────────────────────────────────────────────────────────────

// The wonder the parts need (the Apollo Program), where and when it was built.
function apollo() {
  const wonderId = partDef(kinds()[0]).requires_wonder;
  if (!wonderId) return '';
  const name = store.buildingDefs[wonderId].name;
  const wonder = (store.state.wonders || []).find((w) => w.id === wonderId);
  if (!wonder || !wonder.built) return `${name} not built yet: it opens the race to everyone`;
  const where = wonder.lost ? `lost with ${wonder.city}` : wonder.city;
  return `${name} · ${where}${wonder.year === null ? '' : `, ${yearLabel(wonder.year)}`}`;
}

function rulesNote() {
  const settings = store.rules.spaceship;
  const parts = kinds().map((kind) => {
    const def = partDef(kind);
    return `<div class="ss-rule"><span class="name">${def.name}</span><span class="mono">${def.cost}</span>
      <span>${techName(def.requires)}</span><span class="mono">${settings.min_parts[kind]}–${settings.max_parts[kind]}</span></div>`;
  });
  return `<div class="ss-rules">
    <div class="ss-rule label"><span class="name">Part</span><span>Cost</span><span>Advance</span><span>Parts</span></div>
    ${parts.join('')}
    <p>A launch needs the smallest number of each part, then the ship flies
      ${plural(settings.flight_years, 'year')}: each component beyond ${settings.min_parts.component} saves
      ${settings.years_per_component} years, each structural or module beyond the minimum adds
      ${settings.years_per_mass}; ${plural(settings.min_flight_years, 'year')} at best. A ship is lost with
      its capital, even in flight; the first to land wins.</p></div>`;
}

export function renderSpace(container) {
  if (!store.state) return;
  const every = rows();
  const list = every.filter(({ stage: kind }) => kind !== 'unknown');
  const strangers = every.length - list.length;
  const started = list.some(({ stage: kind }) => !['lost', 'idle'].includes(kind));
  const flying = list.filter(({ stage: kind }) => kind === 'flying').length;
  const count = flying ? `<span class="count"><b>${flying}</b> in flight</span>` : '';
  const legend = `<div class="ss-legend" style="--c:var(--soft)">
      <span><i class="ss-seg on"></i>Built</span><span><i class="ss-seg make" style="--p:50%"></i>In production</span>
      <span><i class="ss-seg req"></i>Needed to launch</span><span><i class="ss-seg opt"></i>Optional</span>
      <span><u class="launch-line"></u>Launch line</span></div>`;
  const cols = kinds().map((kind) => `<span style="width:${groupWidth(kind)}px">${kind}</span>`).join('');

  const scroll = container.scrollTop;
  container.innerHTML = `
    <div class="panel-head"><div class="titles"><h1>Space race</h1><span class="sub">${apollo()}</span></div>${count}</div>
    ${started ? `${verdict(list)}<div class="ss-track">${timeline(list)}</div>
      <div class="ss-cols label">${cols}</div>
      ${list.map(row).join('')}
      ${strangers ? `<div class="ss-strangers">Not met yet: ${plural(strangers, 'civilization')}</div>` : ''}${legend}`
    : '<p class="empty"><b>No spaceship yet</b>Nobody has built a spaceship part so far.</p>'}
    <div class="panel-foot">${rulesNote()}</div>`;
  container.scrollTop = scroll;

  container.querySelectorAll('[data-player]').forEach((button) => {
    button.addEventListener('click', () => {
      emit('select-player', Number(button.dataset.player));
      emit('show-tab', 'civ');
    });
  });
  container.querySelectorAll('[data-city]').forEach((button) => {
    button.addEventListener('click', () => {
      emit('select-city', Number(button.dataset.city));
      emit('center', { x: Number(button.dataset.x), y: Number(button.dataset.y) });
    });
  });
  const launch = container.querySelector('[data-launch]');
  if (launch) launch.addEventListener('click', () => send({ cmd: 'action', action: 'launch' }));
}

// The badge of the rail button: turns before the first ship in flight lands, `rival` when
// it is not the person's own.
export function spaceBadge() {
  const state = store.state;
  if (!state) return null;
  const flying = state.players.filter((p) => !p.barbarian && p.spaceship
    && p.spaceship.arrival_turn !== null && p.spaceship.arrival_turn > state.turn)
    .sort((a, b) => a.spaceship.arrival_turn - b.spaceship.arrival_turn);
  if (!flying.length) return null;
  const first = flying[0];
  const me = leader();
  return { turns: first.spaceship.arrival_turn - state.turn, rival: me !== null && first.id !== me };
}
