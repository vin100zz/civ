// "Cities" panel of the person playing: every city at a glance, one tab per concern. A tab
// shows the buildings that serve it (built, being built, missing) and what the city makes
// of it. The cities keep the order of their founding, unless a column title sorts them.

import { store, U, emit, leader, player, tileIndex, turnsFor } from '../state.js';
import { icon, specialistIcon, specialistColor } from '../icons.js';
import { setTips } from '../tips.js';
import { unitImage } from '../renderer/sprites.js';

// The tabs and their colour. The buildings and wonders of each come from the rules.
const TABS = [
  { id: 'food', label: 'Food', icon: 'food', color: 'var(--food)' },
  { id: 'production', label: 'Production', icon: 'shield', color: 'var(--shield)' },
  { id: 'trade', label: 'Trade', icon: 'trade', color: 'var(--trade)' },
  { id: 'gold', label: 'Gold', icon: 'coin', color: 'var(--gold)' },
  { id: 'science', label: 'Science', icon: 'flask', color: 'var(--sci)' },
  { id: 'happiness', label: 'Happiness', icon: 'happy', color: 'var(--good)' },
  { id: 'military', label: 'Military', icon: 'sword', color: '#D3D9E2' },
];

// The tab each kind of effect serves (a function when it depends on the effect). A building
// or a wonder goes to the tab of its first effect that serves one; a wonder that serves none
// but unlocks units (the Manhattan Project) is military.
const SERVES = {
  food_box_keep: 'food', allow_size_above: 'food', tile_food_bonus: 'food',
  yield_bonus: (effect) => ({ shields: 'production', tax: 'gold', luxury: 'gold', science: 'science' })[effect.yield],
  pollution_percent: 'production', no_population_pollution: 'production',
  corruption_percent: 'trade', tile_trade_bonus: 'trade',
  shared_knowledge: 'science', free_techs: 'science',
  content: 'happiness', happy: 'happiness', no_unhappy: 'happiness', military_unhappiness: 'happiness',
  veteran_units: 'military', defense_multiplier: 'military', nuclear_shield: 'military', unit_moves: 'military',
  acts_as_building: (effect) => tabOf(store.buildingDefs[effect.building]),
};

function tabOf(building) {
  for (const effect of building.effects) {
    const serves = SERVES[effect.type];
    const tab = typeof serves === 'function' ? serves(effect) : serves;
    if (tab) return tab;
  }
  return building.wonder && building.unlocks_units ? 'military' : null;
}

// The columns and the wonders of each tab, for the rules on screen. A column is the buildings
// whose effects share an exclusive group (the Power, Hydro and Nuclear Plants: a factory uses
// one of them only), or a building on its own: {key, ids, header, name}.
let shelves = null;

function shelvesOf(rules) {
  if (shelves && shelves.rules === rules) return shelves;
  shelves = { rules, columns: {}, wonders: {} };
  for (const t of TABS) {
    shelves.columns[t.id] = [];
    shelves.wonders[t.id] = [];
  }
  for (const building of rules.buildings) {
    const tab = tabOf(building);
    if (!tab) continue;
    if (building.wonder) {
      shelves.wonders[tab].push(building.id);
      continue;
    }
    const group = (building.effects.find((effect) => effect.group) || {}).group;
    const column = group && shelves.columns[tab].find((c) => c.group === group);
    if (column) column.ids.push(building.id);
    else {
      const header = building.short || building.name.replace(/[^A-Za-z]/g, '').slice(0, 3).toUpperCase();
      shelves.columns[tab].push({ key: building.id, ids: [building.id], group, header });
    }
  }
  for (const column of Object.values(shelves.columns).flat()) {
    const names = column.ids.map((id) => store.buildingDefs[id].name);
    column.name = names.length > 1 ? `${names.slice(0, -1).join(', ')} or ${names[names.length - 1]}` : names[0];
  }
  return shelves;
}

// What follows the buildings in each tab: the figure of the city, then [key, width, header, name]
// for the narrow columns at the end of the row.
const WIDGETS = {
  food: { value: 'Food per turn', figs: [['growth', 36, icon('hourglass', 14), 'Turns before growth']] },
  production: { value: 'Shields per turn',
    figs: [['made', 30, icon('factory', 14), 'Shields produced'], ['pollution', 36, icon('cloud', 14), 'Pollution risk']] },
  trade: { value: 'Trade per turn', legend: [['Lux', '#C79BF2'], ['Tax', 'var(--trade)'], ['Sci', 'var(--sci)']],
    figs: [['corruption', 32, icon('lost', 14), 'Corruption']] },
  gold: { value: 'Tax per turn', legend: [['Tax', 'var(--gold)'], ['Upkeep', 'var(--line-3)']],
    figs: [['upkeep', 32, 'UPK', 'Building upkeep'], ['net', 32, 'NET', 'Net gold']] },
  science: { value: 'Science per turn', figs: [['share', 36, '%', 'Share of research']] },
  happiness: { label: ['citizens', 'Citizens'], figs: [['mood', 20, icon('unhappy', 14), 'Unhappiness']] },
  military: { label: ['units', 'In the city', 'Units in the city'], figs: [['away', 34, 'AWAY', 'Units away']] },
};

const FACE = {
  happy: ['var(--good)', 'M8.5 14c1 1.4 2.2 2 3.5 2s2.5-.6 3.5-2'],
  content: ['var(--soft)', 'M8.5 15h7'],
  unhappy: ['var(--bad)', 'M8.5 16c1-1.4 2.2-2 3.5-2s2.5.6 3.5 2'],
};
const SPECIALISTS = [['entertainer', 'Entertainers'], ['taxman', 'Taxmen'], ['scientist', 'Scientists']];
const MAX_FACES = 17;       // beyond, the citizens are counted rather than drawn
const FACES_WIDTH = 144;    // pixels the faces may take in a row
const FACE_SIZE = 12;
const DOWN = '<path d="M1 1l4 4 4-4"/>';
const UP = '<path d="M1 5l4-4 4 4"/>';

let tab = 'food';
let sortBy = null;          // {key, dir: 1 ascending | -1 descending}, null: founding order

// ── The city ────────────────────────────────────────────────────────────────

const minus = (value) => (value < 0 ? `−${-value}` : String(value));
const built = (city, column) => column.ids.some((b) => city.buildings.includes(b));
// The building of the column a wonder provides to the city (the Great Wall's walls), if any.
const given = (city, column) => column.ids.find((b) => city.given && city.given[b]);
const has = (city, column) => built(city, column) || Boolean(given(city, column));
const making = (city, column) => Boolean(city.item) && city.item[0] === 'building' && column.ids.includes(city.item[1]);
const blocked = (city) => city.max_size !== null && city.size >= city.max_size;
// The city cannot grow any more without a building of this column (the Aqueduct).
const needs = (city, column) => blocked(city) && column.ids.some((b) => store.buildingDefs[b].effects
  .some((effect) => effect.type === 'allow_size_above' && effect.size === city.max_size));
const specialists = (city) => SPECIALISTS.reduce((total, [kind]) => total + (city.specialists[kind] || 0), 0);
const citizens = (city) => city.happy + city.content + city.unhappy + specialists(city);
const wondersOf = (city) => shelvesOf(store.rules).wonders[tab].filter((w) => city.buildings.includes(w));

function unitsIn(city) {
  return (store.unitsAt.get(tileIndex(city.x, city.y)) || []).filter((unit) => unit[U.OWNER] === city.owner);
}

// Turns before the city grows; 3000 and up when it starves, 2000 without growth, 1000 at its
// largest size: the order of a sort on growth.
function growthRank(city) {
  if (city.food_surplus < 0) return 3000 - Math.ceil(city.food / -city.food_surplus);
  if (city.food_surplus === 0) return 2000;
  if (blocked(city)) return 1000;
  return Math.max(1, turnsFor(city.food_box - city.food, city.food_surplus));
}

// ── Cells ───────────────────────────────────────────────────────────────────

// A figure, coloured after its tone: red with a tint when it already costs something, amber
// when it stops the city short, faint at zero.
function num(text, tone, small = false) {
  return `<span class="num${small ? ' small' : ''} ${tone}">${text}</span>`;
}

function value(figure, tone, zeroWarns) {
  const kind = figure < 0 ? 'bad chip' : figure === 0 ? (zeroWarns ? 'warn chip' : 'faint') : tone;
  return `<span class="v">${num(minus(figure), kind)}</span>`;
}

function fig(width, html) {
  return `<span class="fig" style="width:${width}px">${html}</span>`;
}

// A building of the tab: built in the tab's colour, outlined when a wonder provides it, being
// built in grey, amber when the city needs it to grow.
function buildingCell(city, column) {
  if (built(city, column)) return `<span class="bcell"><i class="built">${icon('check', 10, 3.6)}</i></span>`;
  const gift = given(city, column);
  if (gift) {
    const wonder = store.buildingDefs[city.given[gift]];
    return `<span class="bcell" title="Given by ${wonder ? wonder.name : 'a wonder'}"><i class="given">${icon('check', 10, 3.6)}</i></span>`;
  }
  if (making(city, column)) {
    const done = Math.min(100, Math.round((100 * city.shields) / city.cost));
    return `<span class="bcell"><i class="making" style="--done:${done}%"></i></span>`;
  }
  if (needs(city, column)) return '<span class="bcell"><i class="needed"></i></span>';
  return '<span class="bcell"><i></i></span>';
}

function foodWidget(city) {
  const { food, food_box: box, food_surplus: surplus } = city;
  const share = (part) => `${Math.max(0, Math.min(100, (100 * part) / box))}%`;
  const kept = Math.max(0, Math.min(food, food + surplus));
  let track = '';
  if (kept > 0) track += `<span style="width:${share(kept)};background:var(--food)"></span>`;
  if (food > kept) track += `<span class="lose" style="width:${share(food - kept)}"></span>`;
  if (surplus > 0 && food < box) {
    track += `<span class="next" style="width:${share(Math.min(surplus, box - food))};background:var(--food)"></span>`;
  }
  let growth;
  if (surplus < 0) growth = num(`↓${Math.ceil(food / -surplus)}`, 'bad', true);
  else if (surplus === 0) growth = num('∞', 'warn', true);
  else if (blocked(city)) growth = num('max', 'warn chip', true);
  else {
    const turns = Math.max(1, turnsFor(box - food, surplus));
    growth = num(turns, turns === 1 ? 'good' : 'soft', true);
  }
  return value(surplus, 'food', true) + `<span class="track">${track}</span>` + fig(36, growth);
}

function productionWidget(city) {
  const parts = [];
  if (city.surplus > 0) parts.push(`<span style="flex-grow:${city.surplus};background:var(--shield)"></span>`);
  if (city.shield_upkeep) {
    const grow = Math.max(1, Math.min(city.shield_upkeep, city.shields_made));
    parts.push(`<span style="flex-grow:${grow};background:var(--line-3)"></span>`);
  }
  if (!parts.length) parts.push('<span style="background:var(--line)"></span>');
  const risk = city.pollution_risk;
  return value(city.surplus, 'shield', true) + `<span class="segs">${parts.join('')}</span>`
    + fig(30, num(city.shields_made, 'soft', true)) + fig(36, num(risk ? `${risk}%` : '0', risk ? 'bad' : 'faint', true));
}

function tradeWidget(city) {
  const parts = [[city.luxury, '#C79BF2'], [city.tax, 'var(--trade)'], [city.science, 'var(--sci)']]
    .filter(([figure]) => figure > 0)
    .map(([figure, color]) => `<span style="flex-grow:${figure};background:${color}">${figure}</span>`);
  if (city.corruption) parts.push(`<span class="lost" style="flex-grow:${city.corruption}">${city.corruption}</span>`);
  if (!parts.length) parts.push('<span style="background:var(--line)"></span>');
  return value(city.trade, 'trade', false) + `<span class="segs tall">${parts.join('')}</span>`
    + fig(32, num(minus(-city.corruption), city.corruption ? 'bad' : 'faint', true));
}

function goldWidget(city, scale) {
  const net = city.tax - city.building_upkeep;
  const bar = (figure, color) => `<span><span style="width:${(100 * figure) / scale}%;background:${color}"></span></span>`;
  return value(city.tax, 'gold', false)
    + `<span class="pair">${bar(city.tax, 'var(--gold)')}${bar(city.building_upkeep, 'var(--line-3)')}</span>`
    + fig(32, num(minus(-city.building_upkeep), 'muted', true))
    + fig(32, num(minus(net), net < 0 ? 'bad strong' : net === 0 ? 'muted strong' : 'good strong', true));
}

function scienceWidget(city, best, total) {
  const width = best ? (100 * city.science) / best : 0;
  return value(city.science, 'sci', false)
    + `<span class="track"><span style="width:${width}%;background:var(--sci)"></span></span>`
    + fig(36, num(`${total ? Math.round((100 * city.science) / total) : 0}%`, 'muted', true));
}

function face(mood, size, margin = 0) {
  const [color, mouth] = FACE[mood];
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2.2"
    stroke-linecap="round" style="margin-left:${margin}px" role="img" aria-label="${mood} citizen">
    <circle cx="12" cy="12" r="9.5" fill="var(--raise)"/><path d="M9 10v.6M15 10v.6"/><path d="${mouth}"/></svg>`;
}

// One face per citizen, then one hat per specialist, drawn closer together in a big city;
// beyond MAX_FACES, one face per mood and one hat per kind of specialist, each with its count.
function happinessWidget(city) {
  const moods = [['happy', city.happy], ['content', city.content], ['unhappy', city.unhappy]];
  const kinds = SPECIALISTS.map(([kind, name]) => [kind, name, city.specialists[kind] || 0]);
  let people;
  if (citizens(city) > MAX_FACES) {
    const counts = moods.filter(([, count]) => count)
      .map(([mood, count]) => `<span style="color:${FACE[mood][0]}" title="${mood}">${count}${face(mood, FACE_SIZE)}</span>`);
    for (const [kind, name, count] of kinds) {
      if (count) counts.push(`<span style="color:${specialistColor(kind)}" title="${name}">${count}${specialistIcon(kind, FACE_SIZE, 2.2)}</span>`);
    }
    people = `<span class="counts">${counts.join('')}</span>`;
  } else {
    const list = [];
    for (const [mood, count] of moods) for (let i = 0; i < count; i++) list.push(['face', mood]);
    for (const [kind, name, count] of kinds) for (let i = 0; i < count; i++) list.push(['spec', kind, name]);
    const gap = list.some(([kind]) => kind === 'spec') && list.some(([kind]) => kind === 'face') ? 5 : 0;
    const step = list.length > 1 ? Math.min(14, (FACES_WIDTH - FACE_SIZE - gap) / (list.length - 1)) : 0;
    const drawn = list.map(([kind, what, name], i) => {
      const extra = i > 0 && kind === 'spec' && list[i - 1][0] === 'face' ? gap : 0;
      const margin = i === 0 ? 0 : Math.round((step - FACE_SIZE + extra) * 10) / 10;
      return kind === 'face' ? face(what, FACE_SIZE, margin)
        : `<i class="spec" style="margin-left:${margin}px" title="${name}">${specialistIcon(what, FACE_SIZE, 2.2)}</i>`;
    });
    people = `<span class="faces">${drawn.join('')}</span>`;
  }
  const disorder = city.unhappy > city.happy;
  const mood = disorder || city.growth_disorder
    ? `<span class="${disorder ? 'bad' : 'warn'}" title="${disorder ? 'Civil disorder' : 'Disorder if it grows'}">${icon('unhappy', 14, 2)}</span>` : '';
  return `${people}<span class="mood">${mood}</span>`;
}

function militaryWidget(city, color) {
  const cards = unitsIn(city).map((unit) => {
    const definition = store.unitDefs[unit[U.TYPE]];
    const order = unit[U.ORDER];
    const classes = ['unit-card'];
    if (order === 'fortified' || order === 'fortify') classes.push('fortified');
    if (order === 'sentry') classes.push('sentry');
    return `<span class="${classes.join(' ')}" style="background:${color}" title="${definition.name}${unit[U.VETERAN] ? ', veteran' : ''}">
      ${unitImage(definition)}${unit[U.VETERAN] ? '<i class="vet"></i>' : ''}</span>`;
  });
  return `<span class="units">${cards.join('') || '<span class="faint">None</span>'}</span>`
    + fig(34, num(city.units_away, city.units_away ? 'soft' : 'faint', true));
}

// ── Sorting ─────────────────────────────────────────────────────────────────

function sortValue(key, city) {
  if (key.startsWith('b:')) {
    const column = shelvesOf(store.rules).columns[tab].find((c) => c.key === key.slice(2));
    if (!column) return 0;
    if (has(city, column)) return 3;
    if (making(city, column)) return 1 + city.shields / city.cost;
    return needs(city, column) ? -1 : 0;
  }
  switch (key) {
    case 'value':
      return { food: city.food_surplus, production: city.surplus, trade: city.trade, gold: city.tax,
        science: city.science }[tab];
    case 'growth': return growthRank(city);
    case 'made': return city.shields_made;
    case 'pollution': return city.pollution_risk;
    case 'corruption': return city.corruption;
    case 'upkeep': return city.building_upkeep;
    case 'net': return city.tax - city.building_upkeep;
    case 'share': return city.science;
    case 'citizens': return citizens(city);
    case 'mood': return (city.unhappy > city.happy ? 2 : city.growth_disorder ? 1 : 0) + city.unhappy / 100;
    case 'units': return unitsIn(city).length;
    case 'away': return city.units_away;
    case 'routes': return city.trade_routes;
    case 'wonders': return wondersOf(city).length;
    default: return 0;
  }
}

// Descending first, then ascending, then back to the order of founding.
function nextSort(key) {
  if (key === 'founding') return null;
  if (!sortBy || sortBy.key !== key) return { key, dir: -1 };
  return sortBy.dir === -1 ? { key, dir: 1 } : null;
}

// ── The panel ───────────────────────────────────────────────────────────────

// A column title: what it shows in the header, its sort key and the name its tooltip gives.
function title(key, html, name, classes, tips, width = null) {
  const sorted = sortBy && sortBy.key === key;
  if (name) tips.set(key, `<div class="tip-name">${name}</div>`);
  const arrow = sorted ? `<svg class="arrow" width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor"
    stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${sortBy.dir < 0 ? DOWN : UP}</svg>` : '';
  return `<button class="${classes}${sorted ? ' sorted' : ''}" data-sort="${key}"${name ? ` data-tip="${key}"` : ''}
    aria-label="${name || 'Cities'}"${width ? ` style="width:${width}px"` : ''}>${html}${arrow}</button>`;
}

export function renderCities(container) {
  const id = leader();
  const tips = new Map();
  if (id === null || !store.state.me) {
    container.innerHTML = '<p class="empty"><b>Nobody is playing</b>Start a new game and pick '
      + '"Play a civilization" to lead one yourself.</p>';
    setTips(container, tips);
    return;
  }
  const me = store.state.me;
  const color = player(id).color;
  const spec = TABS.find((t) => t.id === tab);
  const widget = WIDGETS[tab];
  const cities = store.state.cities.filter((city) => city.owner === id).sort((a, b) => a.id - b.id);

  // A building gets its column once its advance is known, or once a city has it anyway.
  const known = (column) => column.ids.some((b) => {
    const definition = store.buildingDefs[b];
    return !definition.requires || me.tech_list.includes(definition.requires);
  }) || cities.some((city) => has(city, column));
  const columns = shelvesOf(store.rules).columns[tab].filter(known);
  const wonders = cities.some((city) => wondersOf(city).length);

  const heads = columns.map((column) => title(`b:${column.key}`, column.header, column.name, 'b', tips));
  if (tab === 'trade') heads.push(title('routes', icon('route', 13, 2), 'Trade routes', 'b', tips));
  if (wonders) heads.push(title('wonders', '★', 'Wonders', 'b wonder', tips));
  const legend = (widget.legend || []).map(([text, swatch]) => `<span><i style="background:${swatch}"></i>${text}</span>`).join('');
  const label = widget.label ? title(widget.label[0], widget.label[1], widget.label[2] || '', 'l', tips) : '';
  const figs = widget.figs.map(([key, width, html, name]) => title(key, html, name, 'f', tips, width));

  const scale = Math.max(1, ...cities.map((city) => Math.max(city.tax, city.building_upkeep)));
  const best = Math.max(0, ...cities.map((city) => city.science));
  const total = cities.reduce((sum, city) => sum + city.science, 0);
  const draw = {
    food: foodWidget,
    production: productionWidget,
    trade: tradeWidget,
    gold: (city) => goldWidget(city, scale),
    science: (city) => scienceWidget(city, best, total),
    happiness: happinessWidget,
    military: (city) => militaryWidget(city, color),
  }[tab];

  let order = cities;
  if (sortBy) {
    order = cities.map((city, i) => ({ city, i, v: sortValue(sortBy.key, city) }))
      .sort((a, b) => (a.v - b.v) * sortBy.dir || a.i - b.i).map((entry) => entry.city);
  }
  const rows = order.map((city) => {
    const cells = columns.map((column) => buildingCell(city, column));
    if (tab === 'trade') cells.push(`<span class="bcell"><b class="${city.trade_routes ? 'soft' : 'faint'}">${city.trade_routes}</b></span>`);
    if (wonders) {
      const own = wondersOf(city);
      const names = own.map((w) => store.buildingDefs[w].name).join(', ');
      cells.push(`<span class="bcell"${names ? ` title="${names}"` : ''}><b class="gold">${own.length > 1 ? `★${own.length}` : own.length ? '★' : ''}</b></span>`);
    }
    return `<button class="city-row${city.id === store.selectedCity ? ' selected' : ''}" data-city="${city.id}">
      <span class="size" style="background:${color}">${city.size}</span>
      <span class="name"><span>${city.capital ? '★ ' : ''}${city.name}</span></span>
      ${cells.join('')}<span class="widget">${draw(city)}</span></button>`;
  });

  const tabs = TABS.map((t) => `<button data-tab-id="${t.id}" aria-pressed="${t.id === tab}" style="--tab:${t.color}">
    ${icon(t.icon, 16, 1.9)}<span>${t.label}</span></button>`).join('');
  const scroll = container.scrollTop;
  container.style.setProperty('--tab', spec.color);
  container.innerHTML = `
    <div class="panel-head"><div class="titles"><h1>Cities</h1></div></div>
    <div class="top">
      <div class="tabs" role="group" aria-label="What to show">${tabs}</div>
      <div class="cols">
        ${title('founding', `Cities<span>${cities.length}</span>`, '', 'city-label', tips)}
        ${heads.join('')}
        <span class="widget">
          ${widget.value ? title('value', icon(spec.icon, 15), widget.value, 'v', tips) : ''}
          <span class="legend">${label}${legend}</span>
          ${figs.join('')}
        </span>
      </div>
    </div>
    <div class="city-rows">${rows.join('') || '<span class="sub quiet">No city yet: found one with your Settlers (B).</span>'}</div>`;
  container.scrollTop = scroll;
  setTips(container, tips);

  container.querySelectorAll('[data-tab-id]').forEach((button) => {
    button.addEventListener('click', () => {
      tab = button.dataset.tabId;
      sortBy = null;
      renderCities(container);
    });
  });
  container.querySelectorAll('[data-sort]').forEach((button) => {
    button.addEventListener('click', () => {
      sortBy = nextSort(button.dataset.sort);
      renderCities(container);
    });
  });
  container.querySelectorAll('[data-city]').forEach((row) => {
    row.addEventListener('click', () => {
      const city = cities.find((c) => c.id === Number(row.dataset.city));
      emit('select-city', city.id);
      emit('center', { x: city.x, y: city.y });
    });
  });
}
