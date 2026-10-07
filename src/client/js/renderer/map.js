// The main map: terrain, improvements, territory, cities and units on a canvas,
// with drag to pan and wheel to zoom. The world wraps horizontally.

import { F, U, store, tileIndex, player, leader, emit, inkOn, swatch } from '../state.js';
import { sprite } from './sprites.js';
import { Ground } from './ground.js';

const MIN_TILE = 10;
const MAX_TILE = 96;
const PAINT_BUDGET = 12;     // milliseconds a frame may spend painting new ground
const DIRS8 = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];
const DIRS4 = [[0, -1], [1, 0], [0, 1], [-1, 0]];
const INK = '#0B0E13';
const GOLD = '#E2B659';
const RIVER = '#3D8FD6';
const FONT = 'Geist, "Segoe UI", system-ui, sans-serif';
export const MISSION_COLORS = {
  found_city: '#7bdc6a', improve: '#c9a25b', defend: '#6ab0ff', attack_city: '#ff5a4a',
  attack_unit: '#ff9d4a', explore: '#d7d7d7', help_wonder: '#e58cff', trade: '#ffd94a',
  explore_sea: '#8fd3ff', embark: '#4ad9c8',
};
const ORDER_MARK = {
  fortified: 'F', fortify: 'F', sentry: 'S', road: 'R', railroad: 'R', irrigate: 'I', mine: 'M',
  fortress: 'O', clean: 'P',
};
// What a unit of the person was left to do by itself.
const TASK_MARK = { goto: 'G', explore: 'X', work: 'A' };
const BAD = '#F2756A';
const SLIDE_MS = 160;         // a unit sliding to the next tile after an order
const LEG_MS = 120;           // the least each tile of a longer way takes...
const WAY_MS = 900;           // ...unless the whole way would then take more than this
const BURST_MS = 480;         // a destroyed unit going up in a flash
const LINGER_MS = 260;        // the camera stays this long on a move that has just ended
const BLINK_ON_MS = 520;      // the unit waiting for orders shows this long...
const BLINK_OFF_MS = 280;     // ...then hides this long, as in the original game

function roundRect(ctx, x, y, w, h, radius) {
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, w, h, radius);
  else ctx.rect(x, y, w, h);
}

export class MapView {
  constructor(canvas, tooltip) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.tooltip = tooltip;
    this.ratio = window.devicePixelRatio || 1;
    this.tile = 32;          // pixels per tile
    this.cx = 40;            // camera centre, in tiles
    this.cy = 25;
    this.dirty = false;
    this.hover = null;
    this.marker = null;      // a tile to point at, e.g. the event picked in the chronicle
    this.ground = new Ground();
    this.onViewChange = () => {};
    // Hooks for the person playing (main.js): each returns true when it handled the event.
    this.onTileClick = () => false;
    this.onTileContext = () => false;
    this.onTileHover = () => {};
    // Html about sending the active unit to a tile: null for the usual tooltip, '' for none.
    this.describeMove = () => null;
    this.slides = new Map();            // unit id -> {path: [[x, y], ...], start, leg}
    this.bursts = [];                   // units just destroyed: {x, y, units, start}
    this.busyUntil = 0;                 // something moves on screen until then
    this.wanted = null;                 // the tile to bring into view once that is over
    this.blink = { key: null, since: 0, timer: null };
    this.still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this._bind();
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
    this.resize();
  }

  // Pixels per tile, kept to a whole number of device pixels: with a fractional size,
  // rounding gives neighbouring tiles different sizes and leaves black gaps between them.
  get tile() {
    return this._tile;
  }

  set tile(value) {
    const clamped = Math.min(MAX_TILE, Math.max(MIN_TILE, value));
    this._tile = Math.round(clamped * this.ratio) / this.ratio;
  }

  // Asks for a redraw on the next animation frame (several calls give one redraw).
  invalidate() {
    if (this.dirty) return;
    this.dirty = true;
    requestAnimationFrame(() => {
      this.dirty = false;
      this.render();
    });
  }

  resize() {
    const box = this.canvas.parentElement.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    this.width = Math.max(100, Math.floor(box.width));
    this.height = Math.max(100, Math.floor(box.height));
    this.canvas.width = this.width * ratio;
    this.canvas.height = this.height * ratio;
    this.ratio = ratio;
    this.tile = this._tile;  // snap again, the ratio may have changed
    this._clamp();
    this.invalidate();
  }

  fitWorld() {
    if (!store.map) return;
    const fit = Math.max(this.width / store.map.width, this.height / store.map.height);
    this.tile = Math.min(MAX_TILE, Math.max(MIN_TILE, Math.floor(fit)));
    this.cx = store.map.width / 2;
    this.cy = store.map.height / 2;
    this._clamp();
    this.invalidate();
  }

  centerOn(x, y) {
    this.wanted = null;
    this.cx = x + 0.5;
    this.cy = y + 0.5;
    this._clamp();
    this.invalidate();
    this.onViewChange();
  }

  // True if a tile shows at least `margin` pixels away from the edges (the bottom edge
  // counts double: the unit bar lies over it).
  _inView(x, y, margin = Math.min(160, this.width / 5)) {
    const w = store.map.width;
    let dx = x + 0.5 - this.cx;
    if (dx > w / 2) dx -= w;
    if (dx < -w / 2) dx += w;
    const px = this.width / 2 + dx * this.tile;
    const py = this.height / 2 + (y + 0.5 - this.cy) * this.tile;
    return px >= margin && px <= this.width - margin && py >= margin && py <= this.height - 2 * margin;
  }

  // Brings a tile into view if it is off screen or too close to the edges. Returns true
  // if the camera had to move.
  bring(x, y) {
    this.wanted = null;
    if (!store.map || this._inView(x, y)) return false;
    this.centerOn(x, y);
    return true;
  }

  // The same, but not before the moves showing on screen are over: the camera never leaves
  // in the middle of one.
  reveal(x, y) {
    this.wanted = { x, y };
    this.invalidate();
  }

  // True while the camera has yet to go where `reveal` sent it.
  get lagging() {
    return this.wanted !== null && Boolean(store.map) && !this._inView(this.wanted.x, this.wanted.y);
  }

  // Resolves once the moves showing on screen have been seen.
  settled() {
    const wait = this.busyUntil - performance.now();
    if (wait <= 0) return Promise.resolve();
    return new Promise((resolve) => { setTimeout(resolve, wait); }).then(() => this.settled());
  }

  // Something moves on a tile until then: if it shows, the camera stays for it.
  _hold(x, y, until) {
    if (this._inView(x, y, 0)) this.busyUntil = Math.max(this.busyUntil, until + LINGER_MS);
  }

  // Goes where `reveal` asked, as soon as nothing moves on screen any more.
  _follow() {
    if (!this.wanted) return;
    clearTimeout(this.followTimer);
    const wait = this.busyUntil - performance.now();
    if (wait > 0) this.followTimer = setTimeout(() => this.invalidate(), wait + 1);
    else this.bring(this.wanted.x, this.wanted.y);
  }

  zoomBy(factor) {
    this.tile = this.tile * factor;
    this._clamp();
    this.invalidate();
    this.onViewChange();
  }

  setMarker(tile) {
    this.marker = tile;
    this.invalidate();
  }

  // One tile of terrain with its improvements, for views other than the map.
  drawTile(ctx, tx, ty, px, py, size) {
    if (!store.map || ty < 0 || ty >= store.map.height) return;
    this._drawTerrain(ctx, tileIndex(tx, ty), tx, ty, px, py, size);
  }

  // ── Geometry ────────────────────────────────────────────────────────────

  _clamp() {
    if (!store.map) return;
    const { width: w, height: h } = store.map;
    const halfH = this.height / this.tile / 2;
    if (h <= halfH * 2) this.cy = h / 2;
    else this.cy = Math.min(h - halfH, Math.max(halfH, this.cy));
    this.cx = ((this.cx % w) + w) % w;
  }

  // Screen position of a tile corner. Only the origin is rounded, then tiles are counted
  // in whole device pixels, so neighbouring tiles always touch exactly.
  _screen(t, centre, extent) {
    const step = Math.round(this.tile * this.ratio);
    const origin = Math.round((extent / 2 - centre * this.tile) * this.ratio);
    return (origin + t * step) / this.ratio;
  }

  screenX(tx) {
    return this._screen(tx, this.cx, this.width);
  }

  screenY(ty) {
    return this._screen(ty, this.cy, this.height);
  }

  tileAt(px, py) {
    if (!store.map) return null;
    const x = Math.floor((px - this.width / 2) / this.tile + this.cx);
    const y = Math.floor((py - this.height / 2) / this.tile + this.cy);
    if (y < 0 || y >= store.map.height) return null;
    const w = store.map.width;
    return { x: ((x % w) + w) % w, y };
  }

  visibleRange() {
    const halfW = this.width / this.tile / 2;
    const halfH = this.height / this.tile / 2;
    return {
      x0: Math.floor(this.cx - halfW) - 1,
      x1: Math.ceil(this.cx + halfW) + 1,
      y0: Math.max(0, Math.floor(this.cy - halfH) - 1),
      y1: Math.min(store.map.height - 1, Math.ceil(this.cy + halfH) + 1),
    };
  }

  // ── Input ───────────────────────────────────────────────────────────────

  _bind() {
    const canvas = this.canvas;
    let drag = null;
    canvas.addEventListener('mousedown', (e) => {
      drag = { x: e.clientX, y: e.clientY, moved: false };
      canvas.classList.add('dragging');
    });
    window.addEventListener('mousemove', (e) => {
      if (drag) {
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
        if (drag.moved) {
          this.cx -= dx / this.tile;
          this.cy -= dy / this.tile;
          drag.x = e.clientX;
          drag.y = e.clientY;
          this._clamp();
          this.invalidate();
          this.onViewChange();
          this.tooltip.hidden = true;
        }
      } else if (e.target === canvas) {
        this._hover(e);
      }
    });
    window.addEventListener('mouseup', (e) => {
      if (drag && !drag.moved && e.target === canvas) this._click(e);
      drag = null;
      canvas.classList.remove('dragging');
    });
    canvas.addEventListener('mouseleave', () => {
      this.tooltip.hidden = true;
      this.hover = null;
      this.onTileHover(null);
      this.invalidate();
    });
    canvas.addEventListener('contextmenu', (e) => {
      const tile = this._eventTile(e);
      if (tile && this.onTileContext(tile)) e.preventDefault();
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const worldX = (px - this.width / 2) / this.tile + this.cx;
      const worldY = (py - this.height / 2) / this.tile + this.cy;
      const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
      this.tile = Math.min(MAX_TILE, Math.max(MIN_TILE, this.tile * factor));
      this.cx = worldX - (px - this.width / 2) / this.tile;
      this.cy = worldY - (py - this.height / 2) / this.tile;
      this._clamp();
      this.invalidate();
      this.onViewChange();
    }, { passive: false });
  }

  _eventTile(e) {
    const rect = this.canvas.getBoundingClientRect();
    return this.tileAt(e.clientX - rect.left, e.clientY - rect.top);
  }

  _click(e) {
    const tile = this._eventTile(e);
    if (!tile || e.button !== 0) return;
    if (this.onTileClick(tile)) return;
    const index = tileIndex(tile.x, tile.y);
    const city = store.cityAt.get(index);
    if (city) {
      emit('select-city', city.id);
      return;
    }
    if (leader() !== null) return;              // a person playing has nothing else to pick
    const units = store.unitsAt.get(index);
    if (units && units.length) {
      emit('select-player', units[0][U.OWNER]);
      return;
    }
    const owner = store.owner ? store.owner[index] : -1;
    if (owner >= 0) emit('select-player', owner);
  }

  _hover(e) {
    const tile = this._eventTile(e);
    if (!tile || !store.map) {
      this.tooltip.hidden = true;
      return;
    }
    const changed = !this.hover || this.hover.x !== tile.x || this.hover.y !== tile.y;
    this.hover = tile;
    if (changed) {
      this.invalidate();
      this.onTileHover(tile);
    }
    this._showTip(e);
  }

  // Shows (or refreshes) the tooltip of the hovered tile at the pointer's last position.
  refreshTip() {
    if (this.hover && this._pointer) this._showTip(this._pointer);
  }

  _showTip(e) {
    this._pointer = { clientX: e.clientX, clientY: e.clientY };
    const tile = this.hover;
    const move = this.describeMove(tile);
    const html = move === null ? this._describe(tile) : move;
    if (!html) {
      this.tooltip.hidden = true;
      return;
    }
    const rect = this.canvas.getBoundingClientRect();
    this.tooltip.innerHTML = html;
    this.tooltip.hidden = false;
    const x = e.clientX - rect.left + 18;
    const y = e.clientY - rect.top + 18;
    const box = this.tooltip.getBoundingClientRect();
    this.tooltip.style.left = `${Math.max(8, Math.min(x, this.width - box.width - 12))}px`;
    this.tooltip.style.top = `${Math.max(8, Math.min(y, this.height - box.height - 12))}px`;
  }

  _describe(tile) {
    const { map, state } = store;
    const index = tileIndex(tile.x, tile.y);
    const where = `<span class="mono">${tile.x}, ${tile.y}</span>`;
    if (state.explored && state.explored[index] === '0') {
      return `<div class="tip-title"><span>Unexplored</span>${where}</div>`;
    }
    const terrain = store.terrains[map.terrain[index]];
    const flags = map.flags[index];
    let ground = terrain.name;
    if ((flags & F.SPECIAL) && terrain.special) ground += ` (${terrain.special.name})`;
    const works = [];
    if (flags & F.RAILROAD) works.push('railroad');
    else if (flags & F.ROAD) works.push('road');
    if (flags & F.IRRIGATION) works.push('irrigation');
    if (flags & F.MINE) works.push('mine');
    if (flags & F.FORTRESS) works.push('fortress');
    if (flags & F.HUT) works.push('hut');
    if (flags & F.POLLUTION) works.push('<span class="bad">pollution</span>');

    const city = store.cityAt.get(index);
    const units = store.unitsAt.get(index);
    const owner = store.owner ? store.owner[index] : -1;
    const rows = [];
    let title = `<span>${ground}</span>`;
    let hint = '';
    const me = leader();
    if (city) {
      const civ = player(city.owner);
      title = `${swatch(civ.color)}<span>${city.name}</span>`;
      rows.push(['Owner', `${civ.nation} · size ${city.size}${city.capital ? ' · capital' : ''}`]);
      rows.push(['Terrain', [ground, ...works].join(' · ')]);
      if (city.foreign) {
        // A person only knows of a foreign city what it saw last.
        rows.push(['Last seen', `turn ${city.seen}`]);
      } else {
        rows.push(['Building', city.production || '<span class="bad">nothing</span>']);
        if (city.disorder) rows.push(['Status', '<span class="bad">Civil disorder</span>']);
        else if (city.celebrating) rows.push(['Status', '<span class="good">Celebrating</span>']);
        hint = 'Click to open the city';
      }
    } else {
      if (works.length) rows.push(['Works', works.join(' · ')]);
      if (owner >= 0) rows.push(['Territory', player(owner).nation]);
    }
    if (units && units.length) {
      const counts = new Map();
      for (const unit of units) {
        const key = (city ? '' : `${player(unit[U.OWNER]).name} `) + store.unitDefs[unit[U.TYPE]].name
          + (unit[U.ABOARD] ? ' (aboard)' : '');
        counts.set(key, (counts.get(key) || 0) + 1);
      }
      const list = [...counts].map(([key, count]) => (count > 1 ? `${key} ×${count}` : key));
      rows.push([city ? 'Garrison' : 'Units', list.join(', ')]);
      if (!city && me === null) hint = 'Click to select its civilization';
      else if (!city && units.some((unit) => unit[U.OWNER] === me)) hint = 'Click to give orders';
    }
    const body = rows.length
      ? `<dl class="tip-rows">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>` : '';
    return `<div class="tip-title">${title}${where}</div>${body}`
      + (hint ? `<div class="tip-foot">${hint}</div>` : '');
  }

  // ── Drawing ─────────────────────────────────────────────────────────────

  render() {
    const ctx = this.ctx;
    ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    ctx.fillStyle = '#06080B';
    ctx.fillRect(0, 0, this.width, this.height);
    const { map, state } = store;
    if (!map || !state) return;
    this._follow();
    const ts = this.tile;
    const range = this.visibleRange();
    const explored = state.explored || null;

    // Terrain and what lies on it.
    const painted = this._drawGround(ctx, range);
    for (let ty = range.y0; ty <= range.y1; ty++) {
      for (let tx = range.x0; tx <= range.x1; tx++) {
        const index = tileIndex(tx, ty);
        const px = this.screenX(tx);
        const py = this.screenY(ty);
        const size = this.screenX(tx + 1) - px;
        if (explored && explored[index] === '0') {
          ctx.fillStyle = '#06080B';
          ctx.fillRect(px, py, size, size);
          continue;
        }
        if (!painted(tx, ty)) this._drawFlat(ctx, index, px, py, size);
        this._drawFeatures(ctx, index, tx, ty, px, py, size);
      }
    }
    // Territory, on top of the terrain but under cities and units.
    if (store.options.territory && store.owner) this._drawTerritory(ctx, range, explored);
    if (store.options.grid && ts >= 16) this._drawGrid(ctx, range);

    const sliding = this._advanceSlides();
    // The tile of the unit waiting for orders, while its blink hides it. Everything on the
    // tile goes with it (a ship and those aboard): nothing else flashes in its place.
    const active = store.hud.unit;
    const dark = this._blinkedOut() ? tileIndex(active[U.X], active[U.Y]) : -1;
    for (let ty = range.y0; ty <= range.y1; ty++) {
      for (let tx = range.x0; tx <= range.x1; tx++) {
        const index = tileIndex(tx, ty);
        if (explored && explored[index] === '0') continue;
        const px = this.screenX(tx);
        const py = this.screenY(ty);
        const size = this.screenX(tx + 1) - px;
        const city = store.cityAt.get(index);
        const all = store.unitsAt.get(index);
        const units = all && sliding ? all.filter((unit) => !this.slides.has(unit[U.ID])) : all;
        if (city) {
          this._drawCity(ctx, city, all, px, py, size);
          // In a city the unit waiting for orders shows over it, and blinks there.
          if (active && index !== dark && all && all.includes(active)
              && !this.slides.has(active[U.ID])) {
            this._drawUnits(ctx, [active], px, py, size);
          }
        } else if (units && units.length && index !== dark) {
          this._drawUnits(ctx, units, px, py, size);
        }
        if (explored && explored[index] === '1') {
          ctx.fillStyle = 'rgba(0, 0, 0, 0.42)';
          ctx.fillRect(px, py, size, size);
        }
      }
    }
    // City names last so nothing hides them.
    if (ts >= 18) {
      for (let ty = range.y0; ty <= range.y1; ty++) {
        for (let tx = range.x0; tx <= range.x1; tx++) {
          const city = store.cityAt.get(tileIndex(tx, ty));
          if (city) this._drawCityLabel(ctx, city, this.screenX(tx), this.screenY(ty), ts);
        }
      }
    }
    if (sliding) this._drawSlides(ctx, ts);
    const bursting = this._drawBursts(ctx, ts);
    if (store.options.missions) this._drawMissions(ctx);
    this._drawSelection(ctx);
    this._drawOrders(ctx);
    if (sliding || bursting) this.invalidate();
  }

  // ── Units on the move ───────────────────────────────────────────────────

  // Slides the units that changed tile along the way they went: [[id, [[x, y], ...]], ...].
  // One step takes `duration`, each step of a longer way a little less. Jumps (a journey
  // nobody told the steps of, several turns of an observed game) are not animated. With
  // `watched`, the camera waits for the slides that show before it goes anywhere else.
  slide(routes, duration = SLIDE_MS, watched = true) {
    for (const [id, tiles] of routes) {
      const path = this._unwrap(tiles);
      if (!path) continue;
      const legs = path.length - 1;
      this._start(id, path, Math.max(duration / legs, Math.min(LEG_MS, WAY_MS / legs)), watched);
    }
  }

  // A unit strikes at the tile next to it and comes back.
  lunge(id, from, to, duration) {
    const path = this._unwrap([from, to]);
    if (!path) return;
    const [[x0, y0], [x1, y1]] = path;
    const reach = [x0 + (x1 - x0) * 0.45, y0 + (y1 - y0) * 0.45];
    this._start(id, [[x0, y0], reach, [x0, y0]], duration / 2);
  }

  // The units a fight has just destroyed on a tile go up in a flash.
  burst(x, y, units) {
    const now = performance.now();
    this.bursts.push({ x, y, units, start: now });
    this._hold(x, y, now + BURST_MS);
    this.invalidate();
  }

  _start(id, path, leg, watched = true) {
    const now = performance.now();
    const [x, y] = path[path.length - 1];
    this.slides.set(id, { path, start: now, leg });
    if (watched) this._hold(Math.round(x), Math.round(y), now + leg * (path.length - 1));
    this.invalidate();
  }

  // The tiles of a way, in columns that never jump across the edge of the world (they may
  // leave it on either side). Null if two of them are too far apart for a slide.
  _unwrap(tiles) {
    const w = store.map.width;
    const path = [tiles[0]];
    for (let i = 1; i < tiles.length; i++) {
      let dx = tiles[i][0] - tiles[i - 1][0];
      if (dx > w / 2) dx -= w;
      if (dx < -w / 2) dx += w;
      if (Math.abs(dx) > 2 || Math.abs(tiles[i][1] - tiles[i - 1][1]) > 2) return null;
      path.push([path[i - 1][0] + dx, tiles[i][1]]);
    }
    return path;
  }

  // True while the blink of the active unit hides it. The blink starts over, unit showing,
  // each time the active unit changes or moves; a timer keeps it going.
  _blinkedOut() {
    const unit = store.hud.unit;
    const blink = this.blink;
    const key = unit ? `${unit[U.ID]}:${unit[U.X]}:${unit[U.Y]}` : null;
    if (key !== blink.key) {
      blink.key = key;
      blink.since = performance.now();
    }
    clearTimeout(blink.timer);
    if (!unit || this.still || this.slides.has(unit[U.ID])) return false;
    const phase = (performance.now() - blink.since) % (BLINK_ON_MS + BLINK_OFF_MS);
    const showing = phase < BLINK_ON_MS;
    blink.timer = setTimeout(() => this.invalidate(),
      (showing ? BLINK_ON_MS : BLINK_ON_MS + BLINK_OFF_MS) - phase + 1);
    return !showing;
  }

  // Drops the slides that are over. Returns true while some unit is still sliding.
  _advanceSlides() {
    const now = performance.now();
    for (const [id, slide] of this.slides) {
      if (now - slide.start >= slide.leg * (slide.path.length - 1)) this.slides.delete(id);
    }
    return this.slides.size > 0;
  }

  _drawSlides(ctx, ts) {
    const now = performance.now();
    const explored = store.state.explored || null;
    // Units going the same way show as the stack they are: a ship and those aboard.
    const stacks = new Map();
    for (const unit of store.state.units) {
      const slide = this.slides.get(unit[U.ID]);
      if (!slide) continue;
      const legs = slide.path.length - 1;
      const t = Math.min(legs, (now - slide.start) / slide.leg);
      const leg = Math.min(legs - 1, Math.floor(t));
      const [x0, y0] = slide.path[leg];
      const [x1, y1] = slide.path[leg + 1];
      // Someone watching through a civilization's eyes only sees the arrival tile.
      if (explored && explored[tileIndex(Math.round(x1), Math.round(y1))] !== '2') continue;
      const ease = (t - leg) * (2 - (t - leg));
      const x = x0 + (x1 - x0) * ease;
      const y = y0 + (y1 - y0) * ease;
      const key = `${x}:${y}`;
      if (!stacks.has(key)) stacks.set(key, { x, y, units: [] });
      stacks.get(key).units.push(unit);
    }
    for (const { x, y, units } of stacks.values()) {
      for (const tx of this._wrapped(Math.round(x))) {
        const px = this.screenX(tx) + (x - Math.round(x)) * ts;
        this._drawUnits(ctx, units, px, this.screenY(0) + y * ts, ts);
      }
    }
  }

  // Draws the destroyed units fading under a flash. Returns true while some are left.
  _drawBursts(ctx, ts) {
    const now = performance.now();
    this.bursts = this.bursts.filter((burst) => now - burst.start < BURST_MS);
    for (const burst of this.bursts) {
      const t = (now - burst.start) / BURST_MS;
      for (const tx of this._wrapped(burst.x)) {
        const px = this.screenX(tx);
        const py = this.screenY(burst.y);
        ctx.globalAlpha = 1 - t;
        this._drawUnits(ctx, burst.units, px, py, ts);
        ctx.globalAlpha = Math.max(0, 1 - 2.5 * t);
        ctx.fillStyle = '#FFE3B8';
        ctx.beginPath();
        ctx.arc(px + ts / 2, py + ts / 2, ts * (0.2 + 0.5 * t), 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1 - t;
        ctx.strokeStyle = BAD;
        ctx.lineWidth = Math.max(1.5, ts * 0.1 * (1 - t));
        ctx.beginPath();
        ctx.arc(px + ts / 2, py + ts / 2, ts * (0.3 + 0.45 * t), 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
    return this.bursts.length > 0;
  }

  // Pastes the painted ground over the visible tiles. Returns a test telling whether a
  // tile got its ground: chunks not painted within this frame's budget are left for the
  // next one, and their tiles are drawn flat meanwhile.
  _drawGround(ctx, range) {
    const ground = this.ground;
    const level = ground.levelFor(Math.round(this.tile * this.ratio));
    if (!ground.ready(level)) return () => false;
    ground.sync();
    const tiles = ground.tilesPerChunk(level);
    const deadline = performance.now() + PAINT_BUDGET;
    let paintedNow = 0;
    const mayPaint = () => paintedNow++ === 0 || performance.now() < deadline;
    const missing = new Set();
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    for (let cy = Math.floor(range.y0 / tiles); cy * tiles <= range.y1; cy++) {
      for (let cx = Math.floor(range.x0 / tiles); cx * tiles <= range.x1; cx++) {
        const canvas = ground.chunk(level, cx * tiles, cy * tiles, mayPaint);
        if (!canvas) {
          missing.add(`${cx}:${cy}`);
          continue;
        }
        const px = this.screenX(cx * tiles);
        const py = this.screenY(cy * tiles);
        ctx.drawImage(canvas, px, py, this.screenX((cx + 1) * tiles) - px, this.screenY((cy + 1) * tiles) - py);
      }
    }
    if (!missing.size) return () => true;
    this.invalidate();
    return (tx, ty) => !missing.has(`${Math.floor(tx / tiles)}:${Math.floor(ty / tiles)}`);
  }

  _drawTerrain(ctx, index, tx, ty, px, py, size) {
    this._drawFlat(ctx, index, px, py, size);
    this._drawFeatures(ctx, index, tx, ty, px, py, size);
  }

  // The plain square tile: what the map shows until its ground is painted.
  _drawFlat(ctx, index, px, py, size) {
    const terrain = store.terrains[store.map.terrain[index]];
    ctx.imageSmoothingEnabled = true;
    const base = terrain.base_sprite ? sprite('terrain', terrain.base_sprite) : null;
    const image = terrain.id === 'river' ? null : sprite('terrain', terrain.sprite);
    if (base) ctx.drawImage(base, px, py, size, size);
    if (image) ctx.drawImage(image, px, py, size, size);
    if (!base && !image) {
      ctx.fillStyle = terrain.color;
      ctx.fillRect(px, py, size, size);
    }
  }

  _drawFeatures(ctx, index, tx, ty, px, py, size) {
    const { map } = store;
    const terrain = store.terrains[map.terrain[index]];
    const flags = map.flags[index];
    ctx.imageSmoothingEnabled = true;
    if (terrain.id === 'river') this._drawRiver(ctx, tx, ty, px, py, size);

    if (size < 14) return;        // too small for details
    // Icons sit lightly on the ground: smaller and a little translucent so the terrain still reads.
    if ((flags & F.SPECIAL) && terrain.special) {
      this._overlay(ctx, sprite('terrain', terrain.special.sprite), px, py, size, 0.64, 0.82);
    } else if ((flags & F.PATTERN) && terrain.pattern_sprite) {
      this._overlay(ctx, sprite('terrain', terrain.pattern_sprite), px, py, size, 0.4, 0.8);
    }
    if (flags & F.IRRIGATION) this._overlay(ctx, sprite('terrain', 'irrigation'), px, py, size, 0.86, 0.3);
    if (flags & F.MINE) this._overlay(ctx, sprite('terrain', 'mine'), px, py, size, 0.64, 0.8);
    if (flags & (F.ROAD | F.RAILROAD)) this._drawRoad(ctx, tx, ty, px, py, size, flags);
    if (flags & F.FORTRESS) {
      ctx.strokeStyle = '#f2d16b';
      ctx.lineWidth = Math.max(1.5, size / 16);
      ctx.strokeRect(px + size * 0.14, py + size * 0.14, size * 0.72, size * 0.72);
    }
    if (flags & F.POLLUTION) this._overlay(ctx, sprite('terrain', 'pollution'), px, py, size, 0.64, 0.8);
    if (flags & F.HUT) this._drawHut(ctx, px, py, size);
  }

  /** Draws a centred icon at `scale` of the tile with the given opacity. */
  _overlay(ctx, icon, px, py, size, scale, alpha) {
    if (!icon) return;
    const w = size * scale;
    ctx.globalAlpha = alpha;
    ctx.drawImage(icon, px + (size - w) / 2, py + (size - w) / 2, w, w);
    ctx.globalAlpha = 1;
  }

  _terrainId(tx, ty) {
    const { map } = store;
    if (ty < 0 || ty >= map.height) return null;
    return store.terrains[(map.ground || map.terrain)[tileIndex(tx, ty)]].id;
  }

  // A river runs from edge to edge of its tile in a curve through the centre. Towards the
  // sea it fades out across the shore instead, since the rounded coast is not on the edge.
  _drawRiver(ctx, tx, ty, px, py, size) {
    const cx = px + size / 2;
    const cy = py + size / 2;
    const ends = [];
    const mouths = [];
    for (const [dx, dy] of DIRS4) {
      const other = this._terrainId(tx + dx, ty + dy);
      if (other === 'river') {
        ends.push([cx + dx * size / 2, cy + dy * size / 2]);
      } else if (other === 'ocean') {
        const start = [cx + dx * size * 0.25, cy + dy * size * 0.25];
        ends.push(start);
        mouths.push([start, [cx + dx * size * 0.8, cy + dy * size * 0.8]]);
      }
    }
    ctx.strokeStyle = RIVER;
    ctx.fillStyle = RIVER;
    ctx.lineWidth = Math.max(2, size * 0.22);
    if (!ends.length) {
      ctx.beginPath();
      ctx.arc(cx, cy, Math.max(1.5, size * 0.2), 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    ctx.lineCap = 'round';
    ctx.beginPath();
    if (ends.length === 1) {
      ctx.moveTo(ends[0][0], ends[0][1]);
      ctx.lineTo(cx, cy);
    }
    for (let i = 0; i < ends.length; i++) {
      for (let j = i + 1; j < ends.length; j++) {
        ctx.moveTo(ends[i][0], ends[i][1]);
        ctx.quadraticCurveTo(cx, cy, ends[j][0], ends[j][1]);
      }
    }
    ctx.stroke();
    ctx.lineCap = 'butt';
    for (const [from, to] of mouths) {
      const fade = ctx.createLinearGradient(from[0], from[1], to[0], to[1]);
      fade.addColorStop(0, RIVER);
      fade.addColorStop(1, 'rgba(61, 143, 214, 0)');
      ctx.strokeStyle = fade;
      ctx.beginPath();
      ctx.moveTo(from[0], from[1]);
      ctx.lineTo(to[0], to[1]);
      ctx.stroke();
    }
  }

  _drawRoad(ctx, tx, ty, px, py, size, flags) {
    const { map } = store;
    const rail = (flags & F.RAILROAD) !== 0;
    const cx = px + size / 2;
    const cy = py + size / 2;
    ctx.lineCap = 'round';
    ctx.strokeStyle = rail ? '#3b3b3b' : '#8a6a3a';
    ctx.lineWidth = Math.max(1.5, size * (rail ? 0.1 : 0.08));
    let links = 0;
    ctx.beginPath();
    for (const [dx, dy] of DIRS8) {
      const y = ty + dy;
      if (y < 0 || y >= map.height) continue;
      const other = map.flags[tileIndex(tx + dx, y)];
      if (other & (F.ROAD | F.RAILROAD)) {
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + dx * size / 2, cy + dy * size / 2);
        links++;
      }
    }
    if (links) ctx.stroke();
    else {
      ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath();
      ctx.arc(cx, cy, Math.max(1.5, size * 0.09), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  _drawHut(ctx, px, py, size) {
    const w = size * 0.36;
    const x = px + (size - w) / 2;
    const y = py + size * 0.5;
    ctx.fillStyle = '#c9a25b';
    ctx.fillRect(x, y, w, size * 0.22);
    ctx.fillStyle = '#7a4b1e';
    ctx.beginPath();
    ctx.moveTo(x - size * 0.05, y);
    ctx.lineTo(px + size / 2, py + size * 0.26);
    ctx.lineTo(x + w + size * 0.05, y);
    ctx.closePath();
    ctx.fill();
  }

  _drawTerritory(ctx, range, explored) {
    const { map } = store;
    const owner = store.owner;
    for (let ty = range.y0; ty <= range.y1; ty++) {
      for (let tx = range.x0; tx <= range.x1; tx++) {
        const index = tileIndex(tx, ty);
        const who = owner[index];
        if (who < 0 || (explored && explored[index] === '0')) continue;
        const color = player(who).color;
        const px = this.screenX(tx);
        const py = this.screenY(ty);
        const size = this.screenX(tx + 1) - px;
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.12;
        ctx.fillRect(px, py, size, size);
        ctx.globalAlpha = 0.92;
        ctx.strokeStyle = color;
        ctx.lineWidth = Math.max(1, Math.min(2, size / 16));
        ctx.beginPath();
        DIRS4.forEach(([dx, dy], i) => {
          const y = ty + dy;
          const other = y < 0 || y >= map.height ? -2 : owner[tileIndex(tx + dx, y)];
          if (other === who) return;
          const inset = ctx.lineWidth / 2;
          if (i === 0) { ctx.moveTo(px, py + inset); ctx.lineTo(px + size, py + inset); }
          if (i === 1) { ctx.moveTo(px + size - inset, py); ctx.lineTo(px + size - inset, py + size); }
          if (i === 2) { ctx.moveTo(px, py + size - inset); ctx.lineTo(px + size, py + size - inset); }
          if (i === 3) { ctx.moveTo(px + inset, py); ctx.lineTo(px + inset, py + size); }
        });
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
  }

  _drawGrid(ctx, range) {
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.25)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let tx = range.x0; tx <= range.x1; tx++) {
      const x = this.screenX(tx) + 0.5;
      ctx.moveTo(x, this.screenY(range.y0));
      ctx.lineTo(x, this.screenY(range.y1 + 1));
    }
    for (let ty = range.y0; ty <= range.y1 + 1; ty++) {
      const y = this.screenY(ty) + 0.5;
      ctx.moveTo(this.screenX(range.x0), y);
      ctx.lineTo(this.screenX(range.x1 + 1), y);
    }
    ctx.stroke();
  }

  _drawCity(ctx, city, units, px, py, size) {
    const color = player(city.owner).color;
    const inset = Math.max(1, Math.round(size * 0.08));
    const box = size - 2 * inset;
    roundRect(ctx, px + inset, py + inset, box, box, size * 0.2);
    ctx.fillStyle = color;
    ctx.fill();
    // Walls show as a heavier outline.
    ctx.lineWidth = Math.max(1.5, size * (city.walls ? 0.1 : 0.045));
    ctx.strokeStyle = INK;
    ctx.stroke();
    if (size >= 12) {
      const ink = inkOn(color);
      ctx.font = `700 ${Math.round(size * 0.5)}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      if (city.disorder) ctx.fillStyle = ink === INK ? '#9B1C1C' : '#FFC2B8';
      else ctx.fillStyle = ink;
      ctx.fillText(String(city.size), px + size / 2, py + size / 2 + 1);
    }
    if (size >= 22) {
      const garrison = units ? units.length : 0;
      if (garrison) this._badge(ctx, px + size - inset + 2, py + inset - 2, String(garrison), size);
    }
  }

  // The name under the city, in a dark pill: civilization dot, star for a capital.
  _drawCityLabel(ctx, city, px, py, size) {
    const fontSize = Math.max(10, Math.min(13, Math.round(size * 0.3)));
    ctx.font = `600 ${fontSize}px ${FONT}`;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    const star = city.capital ? '★ ' : '';
    const starWidth = star ? ctx.measureText(star).width : 0;
    const nameWidth = ctx.measureText(city.name).width;
    const h = fontSize + 8;
    const pad = Math.round(h * 0.42);
    const dot = Math.round(fontSize * 0.56);
    const w = pad + dot + 5 + starWidth + nameWidth + pad;
    const x = Math.round(px + size / 2 - w / 2);
    const y = Math.round(py + size + 1);
    const selected = store.selectedCity === city.id;
    roundRect(ctx, x, y, w, h, h / 2);
    ctx.fillStyle = 'rgba(11, 14, 19, 0.88)';
    ctx.fill();
    ctx.lineWidth = selected ? 1.5 : 1;
    ctx.strokeStyle = selected ? GOLD : 'rgba(255, 255, 255, 0.18)';
    ctx.stroke();
    const middle = y + h / 2 + 0.5;
    ctx.fillStyle = player(city.owner).color;
    ctx.beginPath();
    ctx.arc(x + pad + dot / 2, middle, dot / 2, 0, Math.PI * 2);
    ctx.fill();
    let tx = x + pad + dot + 5;
    if (star) {
      ctx.fillStyle = GOLD;
      ctx.fillText(star, tx, middle);
      tx += starWidth;
    }
    ctx.fillStyle = city.disorder ? '#FFAAA0' : '#F0F2F6';
    ctx.fillText(city.name, tx, middle);
  }

  _drawUnits(ctx, units, px, py, size) {
    // Show the unit that would defend the tile: never a passenger while its ship is there.
    // The unit the person is giving orders to comes first.
    const crew = units.filter((unit) => !unit[U.ABOARD]);
    const shown = crew.length ? crew : units;
    let top = shown[0];
    for (const unit of shown) {
      if (store.unitDefs[unit[U.TYPE]].defense > store.unitDefs[top[U.TYPE]].defense) top = unit;
    }
    const active = store.hud.unit;
    if (active) top = units.find((unit) => unit[U.ID] === active[U.ID]) || top;
    const definition = store.unitDefs[top[U.TYPE]];
    const color = player(top[U.OWNER]).color;
    const inset = Math.max(1, Math.round(size * 0.14));
    const box = size - 2 * inset;
    const radius = size * 0.16;
    const asleep = top[U.ORDER] === 'sentry';
    const dugIn = top[U.ORDER] === 'fortified' || top[U.ORDER] === 'fortify';
    ctx.lineWidth = Math.max(1, size * 0.04);
    ctx.strokeStyle = INK;
    if (units.length > 1) {
      // A second card behind the first: there is a stack here.
      const shift = Math.max(2, Math.round(size * 0.07));
      roundRect(ctx, px + inset + shift, py + inset - shift, box, box, radius);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.fillStyle = 'rgba(11, 14, 19, 0.45)';
      ctx.fill();
      ctx.stroke();
    }
    roundRect(ctx, px + inset, py + inset, box, box, radius);
    ctx.fillStyle = color;
    ctx.fill();
    const image = sprite('unit', definition.sprite);
    if (image && size >= 14) {
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      const room = box * 0.82;
      const scale = Math.min(room / image.width, room / image.height);
      const w = image.width * scale;
      const h = image.height * scale;
      ctx.drawImage(image, px + inset + (box - w) / 2, py + inset + (box - h) / 2, w, h);
    }
    if (asleep) {
      // A sentry is out of the game until something wakes it: greyed out and hatched.
      ctx.save();
      roundRect(ctx, px + inset, py + inset, box, box, radius);
      ctx.clip();
      ctx.fillStyle = 'rgba(92, 100, 112, 0.52)';
      ctx.fillRect(px + inset, py + inset, box, box);
      ctx.strokeStyle = 'rgba(11, 14, 19, 0.32)';
      ctx.lineWidth = Math.max(1, size * 0.035);
      ctx.beginPath();
      for (let d = -box; d < box; d += Math.max(4, size * 0.13)) {
        ctx.moveTo(px + inset + d, py + inset + box);
        ctx.lineTo(px + inset + d + box, py + inset);
      }
      ctx.stroke();
      ctx.restore();
    }
    // A fortified unit has a heavier outline with a pale line inside, like a rampart.
    roundRect(ctx, px + inset, py + inset, box, box, radius);
    if (dugIn) ctx.lineWidth = Math.max(1.5, size * 0.1);
    ctx.stroke();
    if (dugIn && size >= 22) {
      const edge = ctx.lineWidth / 2 + 0.75;
      roundRect(ctx, px + inset + edge, py + inset + edge, box - 2 * edge, box - 2 * edge, radius - edge);
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.stroke();
    }
    if (size >= 22) {
      if (units.length > 1) {
        this._badge(ctx, px + size - inset + size * 0.12, py + inset - size * 0.12, String(units.length), size);
      }
      const mark = TASK_MARK[top[U.TASK]] || ORDER_MARK[top[U.ORDER]];
      if (mark) {
        ctx.font = `700 ${Math.round(size * 0.26)}px ${FONT}`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = INK;
        ctx.fillStyle = '#fff';
        ctx.strokeText(mark, px + inset + 2, py + size - inset - 1);
        ctx.fillText(mark, px + inset + 2, py + size - inset - 1);
      }
      if (top[U.VETERAN]) {
        ctx.fillStyle = GOLD;
        ctx.strokeStyle = INK;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(px + inset + size * 0.03, py + inset + size * 0.03, size * 0.07, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }
  }

  _badge(ctx, right, top, text, size) {
    const h = Math.round(size * 0.3);
    ctx.font = `700 ${Math.round(h * 0.78)}px ${FONT}`;
    const w = Math.max(h, ctx.measureText(text).width + h * 0.5);
    roundRect(ctx, right - w, top, w, h, h / 2);
    ctx.fillStyle = INK;
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(233, 236, 241, 0.85)';
    ctx.stroke();
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, right - w / 2, top + h / 2 + 0.5);
  }

  _drawMissions(ctx) {
    const detail = store.playerDetail;
    if (!detail || !detail.ai || !detail.ai.missions) return;
    const ts = this.tile;
    for (const mission of detail.ai.missions) {
      const color = MISSION_COLORS[mission.kind] || '#fff';
      const defend = mission.kind === 'defend';
      for (const tx of this._wrapped(mission.x)) {
        const cx = this.screenX(tx) + ts / 2;
        const cy = this.screenY(mission.y) + ts / 2;
        ctx.setLineDash(mission.units ? [] : [4, 3]);
        ctx.beginPath();
        ctx.arc(cx, cy, ts * 0.52, 0, Math.PI * 2);
        if (!defend) {
          ctx.strokeStyle = INK;
          ctx.lineWidth = 4;
          ctx.stroke();
        }
        ctx.globalAlpha = defend ? 0.6 : 1;
        ctx.strokeStyle = color;
        ctx.lineWidth = defend ? 1.5 : 2;
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.setLineDash([]);
        if (ts >= 22 && !defend) {
          const text = mission.kind.replaceAll('_', ' ');
          ctx.font = `600 11px ${FONT}`;
          const w = ctx.measureText(text).width + 14;
          const h = 17;
          const y = cy - ts / 2 - h - 3;
          roundRect(ctx, cx - w / 2, y, w, h, h / 2);
          ctx.fillStyle = 'rgba(11, 14, 19, 0.92)';
          ctx.fill();
          ctx.lineWidth = 1;
          ctx.strokeStyle = color;
          ctx.stroke();
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = color;
          ctx.fillText(text, cx, y + h / 2 + 0.5);
        }
      }
    }
  }

  // Every on-screen column showing world column x (the world wraps).
  _wrapped(x) {
    const w = store.map.width;
    const range = this.visibleRange();
    const result = [];
    for (let tx = x + Math.ceil((range.x0 - x) / w) * w; tx <= range.x1; tx += w) result.push(tx);
    return result;
  }

  // What the person is doing: the active unit, the way a go-to would take, the enemy or the
  // destination pointed at.
  _drawOrders(ctx) {
    const { unit, route, target } = store.hud;
    if (!unit) return;
    const ts = this.tile;
    const ring = (x, y, color, halo) => {
      for (const tx of this._wrapped(x)) {
        const px = this.screenX(tx);
        const py = this.screenY(y);
        ctx.lineWidth = 6;
        ctx.strokeStyle = halo;
        roundRect(ctx, px - 2, py - 2, ts + 4, ts + 4, Math.min(10, ts * 0.2));
        ctx.stroke();
        ctx.lineWidth = 2;
        ctx.strokeStyle = color;
        roundRect(ctx, px + 1, py + 1, ts - 2, ts - 2, Math.min(8, ts * 0.16));
        ctx.stroke();
      }
    };
    if (route && route.length) {
      // Unwrap the columns so that the line never jumps across the world.
      const w = store.map.width;
      let column = this._wrapped(unit[U.X])[0];
      if (column === undefined) column = unit[U.X];
      const points = [[column, unit[U.Y], 0]];
      let last = unit[U.X];
      for (const [x, y, turn] of route) {
        let dx = x - last;
        if (dx > w / 2) dx -= w;
        if (dx < -w / 2) dx += w;
        column += dx;
        last = x;
        points.push([column, y, turn]);
      }
      const at = ([x, y]) => [this.screenX(x) + ts / 2, this.screenY(y) + ts / 2];
      const trace = () => {
        ctx.beginPath();
        points.forEach((point, i) => {
          const [px, py] = at(point);
          if (i) ctx.lineTo(px, py);
          else ctx.moveTo(px, py);
        });
        ctx.stroke();
      };
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = 'rgba(11, 14, 19, 0.75)';
      ctx.lineWidth = 7;
      trace();
      ctx.strokeStyle = GOLD;
      ctx.lineWidth = 3;
      ctx.setLineDash([2, 9]);
      trace();
      ctx.setLineDash([]);
      ctx.lineCap = 'butt';
      // Where each turn of the journey ends.
      ctx.font = `700 12px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      points.forEach((point, i) => {
        const final = i === points.length - 1;
        if (!i || (!final && points[i + 1][2] === point[2])) return;
        const [px, py] = at(point);
        const radius = final ? 13 : 11;
        ctx.beginPath();
        ctx.arc(px, final ? py - ts * 0.72 : py, radius, 0, Math.PI * 2);
        ctx.fillStyle = final ? GOLD : INK;
        ctx.fill();
        ctx.lineWidth = final ? 2 : 1.5;
        ctx.strokeStyle = final ? INK : GOLD;
        ctx.stroke();
        ctx.fillStyle = final ? '#1B1405' : GOLD;
        ctx.fillText(String(point[2]), px, (final ? py - ts * 0.72 : py) + 0.5);
      });
      const [gx, gy] = route[route.length - 1];
      ring(gx, gy, '#FFFFFF', 'rgba(255, 255, 255, 0.18)');
    }
    if (target) {
      if (target.goal) ring(target.x, target.y, '#FFFFFF', 'rgba(255, 255, 255, 0.18)');
      else ring(target.x, target.y, BAD, 'rgba(242, 117, 106, 0.28)');
    }
    if (!this.slides.has(unit[U.ID])) ring(unit[U.X], unit[U.Y], GOLD, 'rgba(226, 182, 89, 0.28)');
  }

  _drawSelection(ctx) {
    const ts = this.tile;
    const draw = (x, y, color) => {
      for (const tx of this._wrapped(x)) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        roundRect(ctx, this.screenX(tx) + 1, this.screenY(y) + 1, ts - 2, ts - 2, Math.min(6, ts * 0.14));
        ctx.stroke();
      }
    };
    const detail = store.cityDetail;
    if (detail && store.selectedCity === detail.id) {
      for (const tile of detail.tiles) {
        if (tile.worked) draw(tile.x, tile.y, GOLD);
      }
    }
    if (this.hover) draw(this.hover.x, this.hover.y, 'rgba(255, 255, 255, 0.85)');
    if (this.marker) {
      const rings = [[ts * 0.68, 6, 'rgba(11, 14, 19, 0.8)'], [ts * 0.68, 3, GOLD],
        [ts * 0.98, 2, 'rgba(226, 182, 89, 0.4)']];
      for (const tx of this._wrapped(this.marker.x)) {
        const cx = this.screenX(tx) + ts / 2;
        const cy = this.screenY(this.marker.y) + ts / 2;
        for (const [radius, width, color] of rings) {
          ctx.beginPath();
          ctx.arc(cx, cy, radius, 0, Math.PI * 2);
          ctx.strokeStyle = color;
          ctx.lineWidth = width;
          ctx.stroke();
        }
      }
    }
  }
}
