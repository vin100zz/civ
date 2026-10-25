// "Replay" workspace: the whole game again on the map of the world, as the original game
// showed it at the end. The cities appear, change colour and go out, the land of each
// civilization grows and shrinks, the battles flare up, and the great events of the moment
// are told; the ranking and the chronicle of that moment are underneath the map.
//
// It shows every civilization, so the server only sends it once nothing is hidden: to the
// observer, or once the person's game is over. Each frame is a row of the History: the world
// as that turn begins (server/api/replay.py), after the turn before, whose year it bears and
// whose events it tells. The first row, before anybody has played, is left out.

import { store, emit, yearLabel, plural, territoryOf } from '../state.js';
import { send } from '../net.js';
import { icon } from '../icons.js';
import { rgb, OCEAN } from '../renderer/minimap.js';

const SPEEDS = [[3, 'Slow'], [8, 'Normal'], [24, 'Fast']];      // turns per second
const LAYERS = [['territory', 'Territory'], ['battles', 'Battles'], ['marks', 'Events']];
const CATEGORIES = [
  { id: 'conquest', label: 'Conquests', color: '#F59A3E', types: ['city_captured', 'city_destroyed', 'civ_destroyed'] },
  { id: 'war', label: 'War & peace', color: '#F2756A', types: ['war', 'peace', 'contact'] },
  { id: 'wonder', label: 'Wonders', color: '#E2B659', types: ['wonder'] },
  { id: 'government', label: 'Governments', color: '#6DB7F2', types: ['government'] },
  { id: 'founded', label: 'New cities', color: '#7C889A', types: ['city_founded'] },
];
const COLORS = {
  war: '#F2756A', peace: '#5FCB8B', contact: '#8A95A5', city_captured: '#F59A3E',
  city_destroyed: '#F59A3E', civ_destroyed: '#FFFFFF', wonder: '#E2B659', government: '#6DB7F2',
  city_founded: '#7C889A',
};
const WORLD_NEWS = '#E9ECF1';       // spaceships, nuclear strikes, warming, the end: always told
// What the replay stops on for a moment, at the slower speeds, and tells over the map.
const MAJOR = ['civ_destroyed', 'wonder', 'war', 'spaceship_launched', 'spaceship_lost', 'nuclear',
  'global_warming', 'game_over'];
const HOLD_MS = 1100;
const BATTLE_TURNS = 6;             // a battle fades out over these turns
const MARK_TURNS = 10;              // so do the wonders, the cities taken and razed
const CAPTION_TURNS = 12;           // the latest great event stays told over the map this long
const FEED = 10;                    // events of the chronicle under the map

const typeCategory = {};
for (const category of CATEGORIES) for (const type of category.types) typeCategory[type] = category.id;

let speed = 8;
const layers = { territory: true, battles: true, marks: true };
const shownCategories = { conquest: true, war: true, government: true, wonder: true, founded: false };
let world = null;           // the replay laid out frame by frame (prepare)
let frame = 0;              // the frame shown
let focus = null;           // {frame, x, y}: the place of the event picked in the chronicle
let playing = false;
let autoplay = false;       // play from the start once the replay is here
let asked = 0;              // when the replay was last asked for (ms), 0 once answered
let container = null;
let watcher = null;
let tiles = null;           // one pixel per tile, drawn to the size of the map

const timer = { last: 0, carry: 0, hold: 0 };

function told(event) {
  const category = typeCategory[event.type];
  return category === undefined || shownCategories[category];
}

function isMajor(event) {
  return MAJOR.includes(event.type)
    || (event.type === 'city_captured' && !(store.state.players[event.player] || {}).barbarian);
}

function colorOf(event) {
  return COLORS[event.type] || WORLD_NEWS;
}

// ── The replay, frame by frame ──────────────────────────────────────────────

// The frame where what happened during `turn` shows: that of the next turn (the last frame
// for what happened during the last turn).
function frameAfter(rows, turn) {
  let low = 0;
  let high = rows.length - 1;
  if (rows[high].turn <= turn) return high;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (rows[middle].turn > turn) high = middle;
    else low = middle + 1;
  }
  return low;
}

function prepare() {
  const data = store.replay;
  const rows = store.history.slice();       // the History goes on growing in an observed game
  const cities = [];
  const live = new Map();
  let next = 0;
  for (const row of rows) {
    while (next < data.cities.length && data.cities[next][1] <= row.turn) {
      const [kind, , id, value, x, y, name, size] = data.cities[next++];
      const city = live.get(id);
      if (kind === 'found') live.set(id, { id, owner: value, x, y, name, size });
      else if (kind === 'gone') live.delete(id);
      else if (city && kind === 'owner') city.owner = value;
      else if (city && kind === 'claims') city.claims = value;
      else if (city) city.size = value;
    }
    cities.push([...live.values()].map((city) => ({ ...city })));
  }
  const events = rows.map(() => []);
  data.events.forEach((event, index) => events[frameAfter(rows, event.turn)].push({ ...event, index }));
  const battles = rows.map(() => []);
  for (const [turn, x, y] of data.battles) battles[frameAfter(rows, turn)].push([x, y]);

  // Where a destroyed civilization leaves the ranking: the turn after its last city.
  const fields = store.historyFields;
  const cityField = fields.indexOf('cities');
  const end = {};
  for (const p of store.state.players) {
    if (p.barbarian || p.alive) continue;
    let seen = -1;
    rows.forEach((row, i) => {
      if (row.players[p.id] && row.players[p.id][cityField] > 0) seen = i;
    });
    end[p.id] = seen + 1;
  }
  // The turn a frame tells of: the one just played (the end of the game comes a turn later).
  const labels = rows.map((row, i) => {
    let { turn, year } = rows[Math.max(0, i - 1)];
    for (const event of events[i]) if (event.turn > turn) ({ turn, year } = event);
    return { turn, year };
  });
  // A game saved before replays were kept is only complete from the turn it was loaded.
  const since = data.since > rows[0].turn ? rows.find((row) => row.turn >= data.since) : null;
  const first = rows.length > 1 ? 1 : 0;
  world = {
    rows, labels, first, cities, events, battles, end,
    score: fields.indexOf('score'), cityField, since: since ? since.year : null,
    territory: new Map(),
  };
  frame = Math.max(first, Math.min(frame, rows.length - 1));
}

function territoryAt(i) {
  if (!world.territory.has(i)) {
    if (world.territory.size > 40) world.territory.clear();
    world.territory.set(i, territoryOf(world.cities[i]));
  }
  return world.territory.get(i);
}

// ── Drawing ─────────────────────────────────────────────────────────────────

// The world as the mini-map draws it: dimmed land, dark sea, the land of each civilization
// in its colour, and the cities as squares of their owner's colour, bigger for bigger ones.
export function paintWorld(canvas, { cities, owner, battles = [], marks = [], spot = null, small = false }) {
  const { map, state } = store;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(map.width, Math.round(canvas.clientWidth * dpr));
  const height = Math.round(width * map.height / map.width);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ground = store.terrains.map((t) => (t.land ? rgb(t.color).map((c) => c * 0.62) : OCEAN));
  const civ = state.players.map((p) => rgb(p.color));
  if (!tiles || tiles.width !== map.width || tiles.height !== map.height) {
    tiles = document.createElement('canvas');
    tiles.width = map.width;
    tiles.height = map.height;
  }
  const image = new ImageData(map.width, map.height);
  for (let i = 0; i < map.width * map.height; i++) {
    const terrain = store.terrains[map.terrain[i]];
    let color = ground[map.terrain[i]];
    if (owner && owner[i] >= 0) {
      const share = terrain.land ? 0.7 : 0.35;
      color = color.map((c, k) => c * (1 - share) + civ[owner[i]][k] * share);
    }
    image.data.set([color[0], color[1], color[2], 255], i * 4);
  }
  tiles.getContext('2d').putImageData(image, 0, 0);
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(tiles, 0, 0, width, height);

  const s = width / map.width;
  const at = (v) => (v + 0.5) * s;
  ctx.lineWidth = Math.max(1, 1.4 * dpr);
  for (const [x, y, age] of battles) {
    ctx.strokeStyle = `rgba(242, 117, 106, ${0.85 * (1 - age / BATTLE_TURNS)})`;
    ctx.beginPath();
    ctx.arc(at(x), at(y), s * (0.75 + age * 0.22), 0, Math.PI * 2);
    ctx.stroke();
  }
  for (const city of cities) {
    if (small) {
      const side = Math.max(1.5, s * 0.75);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
      ctx.fillRect(at(city.x) - side / 2, at(city.y) - side / 2, side, side);
      continue;
    }
    const side = Math.max(2.5, s * (0.55 + Math.min(city.size, 24) / 24 * 0.85));
    const pad = Math.max(1, dpr);
    ctx.fillStyle = '#0B0E13';
    ctx.fillRect(at(city.x) - side / 2 - pad, at(city.y) - side / 2 - pad, side + 2 * pad, side + 2 * pad);
    ctx.fillStyle = state.players[city.owner].color;
    ctx.fillRect(at(city.x) - side / 2, at(city.y) - side / 2, side, side);
  }
  for (const mark of marks) {
    const fade = 1 - mark.age / MARK_TURNS;
    ctx.globalAlpha = fade;
    if (mark.type === 'wonder') star(ctx, at(mark.x), at(mark.y) - s * 1.4, s * 1.15, dpr);
    else if (mark.type === 'city_destroyed') cross(ctx, at(mark.x), at(mark.y), s * 0.9, dpr);
    else ring(ctx, at(mark.x), at(mark.y), s * 1.5, state.players[mark.player].color, dpr);
    ctx.globalAlpha = 1;
  }
  if (spot) {
    ctx.strokeStyle = '#E2B659';
    ctx.lineWidth = 2 * dpr;
    ctx.beginPath();
    ctx.arc(at(spot.x), at(spot.y), s * 2.4, 0, Math.PI * 2);
    ctx.stroke();
  }
}

function ring(ctx, x, y, r, color, dpr) {
  for (const [style, width] of [['#0B0E13', 4], [color, 2]]) {
    ctx.strokeStyle = style;
    ctx.lineWidth = width * dpr;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.stroke();
  }
}

function star(ctx, x, y, r, dpr) {
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const angle = -Math.PI / 2 + i * Math.PI / 5;
    const reach = i % 2 ? r * 0.45 : r;
    ctx.lineTo(x + Math.cos(angle) * reach, y + Math.sin(angle) * reach);
  }
  ctx.closePath();
  ctx.fillStyle = '#E2B659';
  ctx.fill();
  ctx.strokeStyle = '#0B0E13';
  ctx.lineWidth = 1.2 * dpr;
  ctx.stroke();
}

function cross(ctx, x, y, r, dpr) {
  ctx.strokeStyle = '#F59A3E';
  ctx.lineWidth = 2.2 * dpr;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(x - r, y - r);
  ctx.lineTo(x + r, y + r);
  ctx.moveTo(x + r, y - r);
  ctx.lineTo(x - r, y + r);
  ctx.stroke();
  ctx.lineCap = 'butt';
}

// The world as it is now, small: the picture of the Replay button at the end of the game.
export function paintThumbnail(canvas) {
  if (!store.map || !store.state) return;
  paintWorld(canvas, { cities: store.state.cities, owner: store.owner, small: true });
}

function drawMap() {
  const battles = [];
  const marks = [];
  if (layers.battles) {
    for (let age = 0; age < BATTLE_TURNS && age <= frame; age++) {
      for (const [x, y] of world.battles[frame - age]) battles.push([x, y, age]);
    }
  }
  if (layers.marks) {
    for (let age = 0; age < MARK_TURNS && age <= frame; age++) {
      for (const event of world.events[frame - age]) {
        if (event.x === undefined || !['wonder', 'city_captured', 'city_destroyed'].includes(event.type)) continue;
        marks.push({ type: event.type, x: event.x, y: event.y, player: event.player, age });
      }
    }
  }
  paintWorld(container.querySelector('#replay-map'), {
    cities: world.cities[frame],
    owner: layers.territory ? territoryAt(frame) : null,
    battles, marks,
    spot: focus && focus.frame === frame ? focus : null,
  });
}

// ── The page ────────────────────────────────────────────────────────────────

function build() {
  const transport = [
    ['previous', 'step-back', 'Previous great event', 'Shift ←'],
    ['back', 'left', 'One turn back', '←'],
    ['play', 'play', 'Play', 'Space'],
    ['forward', 'right', 'One turn forward', '→'],
    ['next', 'step', 'Next great event', 'Shift →'],
  ].map(([id, name, hint, key]) => `<button class="btn icon${id === 'play' ? ' primary' : ''}" data-go="${id}"
      aria-label="${hint}" data-hint="${hint}" data-key="${key}">${icon(name, 18, 2)}</button>`).join('');
  container.innerHTML = `
    <div class="work replay-work">
      <div class="work-head">
        <h1>Replay</h1>
        <div class="seg" role="group" aria-label="Map layers">${LAYERS.map(([id, label]) =>
    `<button data-layer="${id}">${label}</button>`).join('')}</div>
        <span class="sub" id="replay-note"></span>
        <div class="right">
          <span class="sub">Speed</span>
          <div class="seg" role="group" aria-label="Speed">${SPEEDS.map(([value, label]) =>
    `<button data-speed="${value}">${label}</button>`).join('')}</div>
          <button class="btn" data-back>Back to map</button>
        </div>
      </div>
      <div class="replay-stage">
        <div class="replay-frame">
          <canvas id="replay-map" aria-label="The world as the turn shown begins"></canvas>
          <div class="replay-year glass"><b id="replay-year"></b><span id="replay-turn"></span></div>
          <div class="replay-caption glass" id="replay-caption" hidden></div>
          <p class="replay-wait" id="replay-wait">Loading the replay…</p>
        </div>
      </div>
      <div class="replay-bar">
        <div class="transport">${transport}</div>
        <input type="range" id="replay-range" min="0" max="0" value="0" aria-label="Turn">
      </div>
      <div class="replay-below">
        <section class="frame replay-section">
          <div class="between"><h2>Ranking</h2><span class="sub">cities · score</span></div>
          <div id="replay-rank"></div>
        </section>
        <section class="frame replay-section">
          <div class="between"><h2>Chronicle</h2><span class="sub" id="replay-count"></span></div>
          <div class="chips">${CATEGORIES.map((c) =>
    `<button class="filter" data-category="${c.id}"><i class="dot" style="background:${c.color}"></i>${c.label}</button>`).join('')}</div>
          <div id="replay-feed"></div>
        </section>
      </div>
    </div>`;
  container.addEventListener('click', (e) => {
    const target = e.target.closest('[data-layer], [data-speed], [data-category], [data-go], [data-event], [data-back]');
    if (!target) return;
    const data = target.dataset;
    if (data.layer) layers[data.layer] = !layers[data.layer];
    else if (data.speed) speed = Number(data.speed);
    else if (data.category) shownCategories[data.category] = !shownCategories[data.category];
    else if (data.go === 'play') toggle();
    else if (data.go) go(data.go);
    else if (data.event) pick(Number(data.event));
    else return emit('back-to-map');
    return show();
  });
  const range = container.querySelector('#replay-range');
  range.addEventListener('input', () => {
    pause();
    frame = Number(range.value);
    show();
  });
  range.addEventListener('change', () => range.blur());     // the keys go back to the replay
  if (watcher) watcher.disconnect();
  watcher = new ResizeObserver(() => world && show());
  watcher.observe(container.querySelector('.replay-stage'));
}

// The map as big as the workspace allows, the bar under it still in view.
function fit() {
  const stage = container.querySelector('.replay-stage');
  const work = container.querySelector('.replay-work');
  const top = stage.getBoundingClientRect().top - work.getBoundingClientRect().top + work.scrollTop;
  const room = work.clientHeight - top - container.querySelector('.replay-bar').offsetHeight - 36;
  const width = Math.max(240, Math.min(stage.clientWidth, room * store.map.width / store.map.height));
  const holder = container.querySelector('.replay-frame');
  holder.style.width = `${Math.floor(width)}px`;
  holder.style.aspectRatio = `${store.map.width} / ${store.map.height}`;
}

function show() {
  if (!world) return;
  const rows = world.rows;
  const row = rows[frame];
  fit();
  container.querySelectorAll('[data-layer]').forEach((b) => b.setAttribute('aria-pressed', String(layers[b.dataset.layer])));
  container.querySelectorAll('[data-speed]').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.speed) === speed)));
  container.querySelectorAll('[data-category]').forEach((b) => b.setAttribute('aria-pressed', String(shownCategories[b.dataset.category])));
  const play = container.querySelector('[data-go="play"]');
  play.innerHTML = icon(playing ? 'pause' : 'play', 18, 2);
  play.setAttribute('aria-label', playing ? 'Pause' : 'Play');
  play.dataset.hint = playing ? 'Pause' : 'Play';
  const range = container.querySelector('#replay-range');
  range.min = world.first;
  range.max = rows.length - 1;
  range.value = frame;
  const label = world.labels[frame];
  container.querySelector('#replay-year').textContent = yearLabel(label.year);
  container.querySelector('#replay-turn').textContent =
    `Turn ${label.turn} of ${world.labels[rows.length - 1].turn}`;
  container.querySelector('#replay-note').textContent = world.since !== null
    ? `Saved before replays were kept: complete from ${yearLabel(world.since)}` : '';
  drawMap();
  showCaption();
  showRanking(row);
  showChronicle();
}

function showCaption() {
  let latest = null;
  for (let i = frame; i >= Math.max(0, frame - CAPTION_TURNS) && !latest; i--) {
    const great = world.events[i].filter((event) => told(event) && (isMajor(event) || event.type === 'government'));
    latest = great[great.length - 1] || null;
  }
  const caption = container.querySelector('#replay-caption');
  caption.hidden = !latest;
  if (latest) {
    caption.innerHTML = `<i class="dot" style="background:${colorOf(latest)}"></i>
      <span class="when">${yearLabel(latest.year)}</span><span class="text">${latest.text}</span>`;
  }
}

function showRanking(row) {
  const players = store.state.players.filter((p) => !p.barbarian && row.players[p.id]);
  const value = (p, field) => row.players[p.id][field];
  players.sort((a, b) => value(b, world.score) - value(a, world.score));
  const best = Math.max(1, ...players.map((p) => value(p, world.score)));
  container.querySelector('#replay-rank').innerHTML = players.map((p, i) => {
    const gone = world.end[p.id] !== undefined && frame >= world.end[p.id];
    const cities = value(p, world.cityField);
    return `<div class="replay-rank${gone ? ' dead' : ''}">
      <span class="rank">${i + 1}</span><span class="swatch" style="background:${p.color}"></span>
      <span class="who"><b>${p.nation}</b><span class="bar thin"><span style="width:${100 * value(p, world.score) / best}%;background:${p.color}"></span></span></span>
      <span class="cities">${gone ? 'destroyed' : plural(cities, 'city')}</span>
      <span class="value">${value(p, world.score)}</span></div>`;
  }).join('');
}

function showChronicle() {
  const shown = [];
  let count = 0;
  for (let i = frame; i >= 0; i--) {
    const here = world.events[i].filter(told);
    count += here.length;
    for (let k = here.length - 1; k >= 0 && shown.length < FEED; k--) shown.push(here[k]);
  }
  container.querySelector('#replay-count').textContent = count ? `${plural(count, 'event')} so far` : '';
  container.querySelector('#replay-feed').innerHTML = shown.map((event) => `
    <button class="replay-event${world.events[frame].includes(event) ? ' now' : ''}" data-event="${event.index}">
      <span class="when">${yearLabel(event.year)}</span><i class="dot" style="background:${colorOf(event)}"></i>
      <span class="text">${event.text}</span></button>`).join('')
    || '<p class="sub replay-none">Nothing yet.</p>';
}

// ── Playing ─────────────────────────────────────────────────────────────────

function nextGreat(step) {
  for (let i = frame + step; i >= world.first && i < world.rows.length; i += step) {
    if (world.events[i].some((event) => told(event) && isMajor(event))) return i;
  }
  return step > 0 ? world.rows.length - 1 : world.first;
}

function go(where) {
  pause();
  focus = null;
  const last = world.rows.length - 1;
  if (where === 'previous') frame = nextGreat(-1);
  else if (where === 'next') frame = nextGreat(1);
  else if (where === 'back') frame = Math.max(world.first, frame - 1);
  else if (where === 'forward') frame = Math.min(last, frame + 1);
  else if (where === 'start') frame = world.first;
  else if (where === 'end') frame = last;
}

// An event of the chronicle: its turn, and where it happened.
function pick(index) {
  const i = world.events.findIndex((list) => list.some((event) => event.index === index));
  if (i < 0) return;
  const event = world.events[i].find((e) => e.index === index);
  pause();
  frame = i;
  focus = event.x !== undefined ? { frame: i, x: event.x, y: event.y } : null;
}

function play() {
  if (!world || playing) return;
  if (frame >= world.rows.length - 1) frame = world.first;
  playing = true;
  focus = null;
  Object.assign(timer, { last: performance.now(), carry: 0, hold: 0 });
  requestAnimationFrame(tick);
}

function pause() {
  playing = false;
}

function toggle() {
  if (playing) pause();
  else play();
}

function tick(now) {
  // Away from the workspace, the replay stops where it is.
  if (!playing || !container || container.offsetParent === null) {
    playing = false;
    if (container && container.offsetParent !== null) show();
    return;
  }
  const elapsed = Math.min(100, now - timer.last);
  timer.last = now;
  if (timer.hold > 0) {
    timer.hold -= elapsed;
  } else {
    timer.carry += elapsed * speed / 1000;
    let moved = false;
    while (timer.carry >= 1) {
      timer.carry -= 1;
      if (frame >= world.rows.length - 1) {
        playing = false;
        break;
      }
      frame += 1;
      moved = true;
      if (speed < 20 && world.events[frame].some((event) => told(event) && isMajor(event))) {
        timer.hold = HOLD_MS;
        timer.carry = 0;
        break;
      }
    }
    if (moved || !playing) show();
  }
  if (playing) requestAnimationFrame(tick);
}

// The keys of the workspace; true when the key was for it.
export function replayKey(e) {
  if (!world) return false;
  if (e.key === ' ') toggle();
  else if (e.key === 'ArrowLeft') go(e.shiftKey ? 'previous' : 'back');
  else if (e.key === 'ArrowRight') go(e.shiftKey ? 'next' : 'forward');
  else if (e.key === 'Home') go('start');
  else if (e.key === 'End') go('end');
  else return false;
  show();
  return true;
}

// From the game over window: the whole game from the start.
export function playFromStart() {
  focus = null;
  if (world) {
    frame = world.first;
    play();
  } else {
    autoplay = true;
  }
}

export function renderReplay(panel) {
  container = panel;
  if (!store.state || !store.map || !store.history.length) return;
  if (!panel.querySelector('#replay-map')) build();
  // Asked for again when turns were played since (an observed game goes on).
  const behind = !store.replay || !world || world.rows.length !== store.history.length;
  if (behind && performance.now() - asked > 1000) {
    asked = performance.now();
    send({ cmd: 'replay' });
  }
  panel.querySelector('#replay-wait').hidden = Boolean(world);
  if (world) show();
}

// The server's answer.
export function receiveReplay() {
  asked = 0;
  if (!store.history.length) return;
  const following = world && frame === world.rows.length - 1;
  prepare();
  if (following) frame = world.rows.length - 1;
  if (autoplay) {
    autoplay = false;
    frame = world.first;
    play();
  }
  if (container && container.offsetParent !== null) renderReplay(container);
}

// A new game, or another one loaded: nothing of the last replay holds.
export function resetReplay() {
  world = null;
  frame = 0;
  focus = null;
  playing = false;
  autoplay = false;
  asked = 0;
}
