// "Cities" panel of the person playing: every city at a glance, one tab per concern. A tab
// shows the buildings that serve it (built, being built, missing) and what the city makes
// of it. The cities keep the order of their founding, unless a column title sorts them.

import { store, U, emit, leader, player, tileIndex, turnsFor } from '../state.js';
import { icon } from '../icons.js';
import { setTips } from '../tips.js';

// The tabs: their colour, the buildings that serve them [id, header] and their wonders.
// 'power' stands for the Power, Hydro and Nuclear Plants, which all do the same for a factory.
const TABS = [
  { id: 'food', label: 'Food', icon: 'food', color: 'var(--food)',
    buildings: [['granary', 'GRA'], ['aqueduct', 'AQU']], wonders: [] },
  { id: 'production', label: 'Production', icon: 'shield', color: 'var(--shield)',
    buildings: [['factory', 'FAC'], ['mfg_plant', 'MFG'], ['power', 'PWR'], ['mass_transit', 'MTR'], ['recycling_cntr', 'REC']],
    wonders: ['hoover_dam'] },
  { id: 'trade', label: 'Trade', icon: 'trade', color: 'var(--trade)',
    buildings: [['courthouse', 'CRT']], wonders: ['colossus'] },
  { id: 'gold', label: 'Gold', icon: 'coin', color: 'var(--gold)',
    buildings: [['marketplace', 'MKT'], ['bank', 'BNK']], wonders: [] },
  { id: 'science', label: 'Science', icon: 'flask', color: 'var(--sci)',
    buildings: [['library', 'LIB'], ['university', 'UNI']],
    wonders: ['copernicus_observatory', 'isaac_newtons_college', 'seti_program', 'great_library', 'darwins_voyage'] },
  { id: 'happiness', label: 'Happiness', icon: 'happy', color: 'var(--good)',
    buildings: [['temple', 'TMP'], ['colosseum', 'COL'], ['cathedral', 'CAT']],
    wonders: ['hanging_gardens', 'oracle', 'michelangelos_chapel', 'shakespeares_theatre', 'js_bachs_cathedral',
      'cure_for_cancer', 'womens_suffrage'] },
  { id: 'military', label: 'Military', icon: 'sword', color: '#D3D9E2',
    buildings: [['barracks', 'BAR'], ['city_walls', 'WAL'], ['sdi_defense', 'SDI']],
    wonders: ['great_wall', 'lighthouse', 'magellans_expedition', 'manhattan_project'] },
];
const POWER = ['power_plant', 'hydro_plant', 'nuclear_plant'];

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
const SPECIALISTS = [['entertainer', 'E', 'Entertainers'], ['taxman', 'T', 'Taxmen'], ['scientist', 'S', 'Scientists']];
const MAX_FACES = 17;       // beyond, the citizens are counted rather than drawn
const FACES_WIDTH = 144;    // pixels the faces may take in a row
const FACE_SIZE = 12;
const DOWN = '<path d="M1 1l4 4 4-4"/>';
const UP = '<path d="M1 5l4-4 4 4"/>';

let tab = 'food';
let sortBy = null;          // {key, dir: 1 ascending | -1 descending}, null: founding order

// ── The city ────────────────────────────────────────────────────────────────

const minus = (value) => (value < 0 ? `−${-value}` : String(value));
const ids = (id) => (id === 'power' ? POWER : [id]);
const has = (city, id) => ids(id).some((b) => city.buildings.includes(b));
const making = (city, id) => Boolean(city.item) && city.item[0] === 'building' && ids(id).includes(city.item[1]);
const blocked = (city) => city.max_size !== null && city.size >= city.max_size;
const specialists = (city) => SPECIALISTS.reduce((total, [kind]) => total + (city.specialists[kind] || 0), 0);
const citizens = (city) => city.happy + city.content + city.unhappy + specialists(city);
const wondersOf = (city, spec) => spec.wonders.filter((w) => city.buildings.includes(w));

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

// A building of the tab: built in the tab's colour, being built in grey, amber when the city
// needs it to grow.
function buildingCell(city, id) {
  if (has(city, id)) return `<span class="bcell"><i class="built">${icon('check', 10, 3.6)}</i></span>`;
  if (making(city, id)) {
    const done = Math.min(100, Math.round((100 * city.shields) / city.cost));
    return `<span class="bcell"><i class="making" style="--done:${done}%"></i></span>`;
  }
  if (id === 'aqueduct' && blocked(city)) return '<span class="bcell"><i class="needed"></i></span>';
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

// One face per citizen, then one disc per specialist, drawn closer together in a big city;
// beyond MAX_FACES, one face per mood and one disc per kind of specialist, each with its count.
function happinessWidget(city) {
  const moods = [['happy', city.happy], ['content', city.content], ['unhappy', city.unhappy]];
  const kinds = SPECIALISTS.map(([kind, letter, name]) => [letter, name, city.specialists[kind] || 0]);
  let people;
  if (citizens(city) > MAX_FACES) {
    const counts = moods.filter(([, count]) => count)
      .map(([mood, count]) => `<span style="color:${FACE[mood][0]}" title="${mood}">${count}${face(mood, FACE_SIZE)}</span>`);
    for (const [letter, name, count] of kinds) {
      if (count) counts.push(`<span class="specialist-count" title="${name}">${count}<i class="spec">${letter}</i></span>`);
    }
    people = `<span class="counts">${counts.join('')}</span>`;
  } else {
    const list = [];
    for (const [mood, count] of moods) for (let i = 0; i < count; i++) list.push(['face', mood]);
    for (const [letter, name, count] of kinds) for (let i = 0; i < count; i++) list.push(['spec', letter, name]);
    const gap = list.some(([kind]) => kind === 'spec') && list.some(([kind]) => kind === 'face') ? 5 : 0;
    const step = list.length > 1 ? Math.min(14, (FACES_WIDTH - FACE_SIZE - gap) / (list.length - 1)) : 0;
    const drawn = list.map(([kind, what, name], i) => {
      const extra = i > 0 && kind === 'spec' && list[i - 1][0] === 'face' ? gap : 0;
      const margin = i === 0 ? 0 : Math.round((step - FACE_SIZE + extra) * 10) / 10;
      return kind === 'face' ? face(what, FACE_SIZE, margin)
        : `<i class="spec" style="margin-left:${margin}px" title="${name}">${what}</i>`;
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
      <img src="/resources/unit/${definition.sprite}.png" alt="">${unit[U.VETERAN] ? '<i class="vet"></i>' : ''}</span>`;
  });
  return `<span class="units">${cards.join('') || '<span class="faint">None</span>'}</span>`
    + fig(34, num(city.units_away, city.units_away ? 'soft' : 'faint', true));
}

// ── Sorting ─────────────────────────────────────────────────────────────────

function sortValue(key, city, spec) {
  if (key.startsWith('b:')) {
    const id = key.slice(2);
    if (has(city, id)) return 3;
    if (making(city, id)) return 1 + city.shields / city.cost;
    return id === 'aqueduct' && blocked(city) ? -1 : 0;
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
    case 'wonders': return wondersOf(city, spec).length;
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
  const known = (building) => ids(building).some((b) => {
    const definition = store.buildingDefs[b];
    return definition && (!definition.requires || me.tech_list.includes(definition.requires));
  }) || cities.some((city) => has(city, building));
  const columns = spec.buildings.filter(([building]) => known(building));
  const wonders = cities.some((city) => wondersOf(city, spec).length);

  const named = (building) => (building === 'power' ? 'Power, Hydro or Nuclear Plant' : store.buildingDefs[building].name);
  const heads = columns.map(([building, header]) => title(`b:${building}`, header, named(building), 'b', tips));
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
    order = cities.map((city, i) => ({ city, i, v: sortValue(sortBy.key, city, spec) }))
      .sort((a, b) => (a.v - b.v) * sortBy.dir || a.i - b.i).map((entry) => entry.city);
  }
  const rows = order.map((city) => {
    const cells = columns.map(([building]) => buildingCell(city, building));
    if (tab === 'trade') cells.push(`<span class="bcell"><b class="${city.trade_routes ? 'soft' : 'faint'}">${city.trade_routes}</b></span>`);
    if (wonders) {
      const own = wondersOf(city, spec);
      const names = own.map((w) => store.buildingDefs[w].name).join(', ');
      cells.push(`<span class="bcell"${names ? ` title="${names}"` : ''}><b class="gold">${own.length > 1 ? `★${own.length}` : own.length ? '★' : ''}</b></span>`);
    }
    return `<button class="city-row" data-city="${city.id}">
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
