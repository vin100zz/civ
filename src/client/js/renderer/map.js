// The main map: terrain, improvements, territory, cities and units on a canvas,
// with drag to pan and wheel to zoom. The world wraps horizontally.

import { F, U, store, tileIndex, player, emit } from '../state.js';
import { sprite } from './sprites.js';

const MIN_TILE = 10;
const MAX_TILE = 96;
const DIRS8 = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];
const DIRS4 = [[0, -1], [1, 0], [0, 1], [-1, 0]];
const ORDER_MARK = {
  fortified: 'F', fortify: 'F', sentry: 'S', road: 'R', railroad: 'R', irrigate: 'I', mine: 'M',
  fortress: 'O', clean: 'P',
};

export class MapView {
  constructor(canvas, tooltip) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.tooltip = tooltip;
    this.tile = 32;          // pixels per tile
    this.cx = 40;            // camera centre, in tiles
    this.cy = 25;
    this.dirty = false;
    this.hover = null;
    this.onViewChange = () => {};
    this._bind();
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
    this.resize();
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
    this.cx = x + 0.5;
    this.cy = y + 0.5;
    this._clamp();
    this.invalidate();
    this.onViewChange();
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

  screenX(tx) {
    return Math.round((tx - this.cx) * this.tile + this.width / 2);
  }

  screenY(ty) {
    return Math.round((ty - this.cy) * this.tile + this.height / 2);
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
      this.invalidate();
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
    if (!tile) return;
    const index = tileIndex(tile.x, tile.y);
    const city = store.cityAt.get(index);
    if (city) {
      emit('select-city', city.id);
      return;
    }
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
    if (changed) this.invalidate();
    const html = this._describe(tile);
    if (!html) {
      this.tooltip.hidden = true;
      return;
    }
    const rect = this.canvas.getBoundingClientRect();
    this.tooltip.innerHTML = html;
    this.tooltip.hidden = false;
    const x = e.clientX - rect.left + 16;
    const y = e.clientY - rect.top + 16;
    this.tooltip.style.left = `${Math.min(x, this.width - 290)}px`;
    this.tooltip.style.top = `${Math.min(y, this.height - 140)}px`;
  }

  _describe(tile) {
    const { map, state } = store;
    const index = tileIndex(tile.x, tile.y);
    if (state.explored && state.explored[index] === '0') return 'Unexplored';
    const terrain = store.terrains[map.terrain[index]];
    const flags = map.flags[index];
    const lines = [];
    let name = terrain.name;
    if ((flags & F.SPECIAL) && terrain.special) name += ` (${terrain.special.name})`;
    lines.push(`<b>${name}</b> <span class="muted">${tile.x}, ${tile.y}</span>`);
    const works = [];
    if (flags & F.RAILROAD) works.push('railroad');
    else if (flags & F.ROAD) works.push('road');
    if (flags & F.IRRIGATION) works.push('irrigation');
    if (flags & F.MINE) works.push('mine');
    if (flags & F.FORTRESS) works.push('fortress');
    if (flags & F.HUT) works.push('hut');
    if (flags & F.POLLUTION) works.push('<span class="bad">pollution</span>');
    if (works.length) lines.push(works.join(', '));
    const city = store.cityAt.get(index);
    if (city) {
      const owner = player(city.owner);
      lines.push(`<b>${city.name}</b> — ${owner.nation}, size ${city.size}`);
      if (city.production) lines.push(`Building: ${city.production}`);
      if (city.disorder) lines.push('<span class="bad">Civil disorder</span>');
    }
    const units = store.unitsAt.get(index);
    if (units && units.length) {
      const counts = new Map();
      for (const unit of units) {
        const key = `${player(unit[U.OWNER]).name} ${store.unitDefs[unit[U.TYPE]].name}`
          + (unit[U.ABOARD] ? ' (aboard)' : '');
        counts.set(key, (counts.get(key) || 0) + 1);
      }
      for (const [key, count] of counts) lines.push(count > 1 ? `${key} ×${count}` : key);
    }
    return lines.join('<br>');
  }

  // ── Drawing ─────────────────────────────────────────────────────────────

  render() {
    const ctx = this.ctx;
    ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, this.width, this.height);
    const { map, state } = store;
    if (!map || !state) return;
    const ts = this.tile;
    const range = this.visibleRange();
    const explored = state.explored || null;

    // Terrain and what lies on it.
    for (let ty = range.y0; ty <= range.y1; ty++) {
      for (let tx = range.x0; tx <= range.x1; tx++) {
        const index = tileIndex(tx, ty);
        if (explored && explored[index] === '0') continue;
        const px = this.screenX(tx);
        const py = this.screenY(ty);
        const size = this.screenX(tx + 1) - px;
        this._drawTerrain(ctx, index, tx, ty, px, py, size);
      }
    }
    // Territory, on top of the terrain but under cities and units.
    if (store.options.territory && store.owner) this._drawTerritory(ctx, range, explored);
    if (store.options.grid && ts >= 16) this._drawGrid(ctx, range);

    for (let ty = range.y0; ty <= range.y1; ty++) {
      for (let tx = range.x0; tx <= range.x1; tx++) {
        const index = tileIndex(tx, ty);
        if (explored && explored[index] === '0') continue;
        const px = this.screenX(tx);
        const py = this.screenY(ty);
        const size = this.screenX(tx + 1) - px;
        const city = store.cityAt.get(index);
        const units = store.unitsAt.get(index);
        if (city) this._drawCity(ctx, city, units, px, py, size);
        else if (units) this._drawUnits(ctx, units, px, py, size);
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
    if (store.options.missions) this._drawMissions(ctx);
    this._drawSelection(ctx);
  }

  _drawTerrain(ctx, index, tx, ty, px, py, size) {
    const { map } = store;
    const terrain = store.terrains[map.terrain[index]];
    const flags = map.flags[index];
    ctx.imageSmoothingEnabled = true;

    const base = terrain.base_sprite ? sprite('terrain', terrain.base_sprite) : null;
    const isRiver = terrain.id === 'river';
    const image = isRiver ? null : sprite('terrain', terrain.sprite);
    if (base) ctx.drawImage(base, px, py, size, size);
    if (image) ctx.drawImage(image, px, py, size, size);
    if (!base && !image) {
      ctx.fillStyle = terrain.color;
      ctx.fillRect(px, py, size, size);
    }
    if (isRiver) this._drawRiver(ctx, tx, ty, px, py, size);

    if (size < 14) return;        // too small for details
    if ((flags & F.SPECIAL) && terrain.special) {
      const icon = sprite('terrain', terrain.special.sprite);
      if (icon) ctx.drawImage(icon, px, py, size, size);
    } else if ((flags & F.PATTERN) && terrain.pattern_sprite) {
      const icon = sprite('terrain', terrain.pattern_sprite);
      if (icon) ctx.drawImage(icon, px, py, size, size);
    }
    if (flags & F.IRRIGATION) {
      const icon = sprite('terrain', 'irrigation');
      if (icon) {
        ctx.globalAlpha = 0.75;
        ctx.drawImage(icon, px, py, size, size);
        ctx.globalAlpha = 1;
      }
    }
    if (flags & F.MINE) {
      const icon = sprite('terrain', 'mine');
      if (icon) ctx.drawImage(icon, px, py, size, size);
    }
    if (flags & (F.ROAD | F.RAILROAD)) this._drawRoad(ctx, tx, ty, px, py, size, flags);
    if (flags & F.FORTRESS) {
      ctx.strokeStyle = '#f2d16b';
      ctx.lineWidth = Math.max(1.5, size / 16);
      ctx.strokeRect(px + size * 0.14, py + size * 0.14, size * 0.72, size * 0.72);
    }
    if (flags & F.POLLUTION) {
      const icon = sprite('terrain', 'pollution');
      if (icon) ctx.drawImage(icon, px, py, size, size);
    }
    if (flags & F.HUT) this._drawHut(ctx, px, py, size);
  }

  _terrainId(tx, ty) {
    const { map } = store;
    if (ty < 0 || ty >= map.height) return null;
    return store.terrains[map.terrain[tileIndex(tx, ty)]].id;
  }

  _drawRiver(ctx, tx, ty, px, py, size) {
    const cx = px + size / 2;
    const cy = py + size / 2;
    ctx.strokeStyle = '#3d8fd6';
    ctx.lineCap = 'round';
    ctx.lineWidth = Math.max(2, size * 0.22);
    let links = 0;
    ctx.beginPath();
    for (const [dx, dy] of DIRS4) {
      const other = this._terrainId(tx + dx, ty + dy);
      if (other === 'river' || other === 'ocean') {
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + dx * size / 2, cy + dy * size / 2);
        links++;
      }
    }
    if (links) ctx.stroke();
    ctx.fillStyle = '#3d8fd6';
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(1.5, size * (links ? 0.11 : 0.2)), 0, Math.PI * 2);
    ctx.fill();
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
        ctx.globalAlpha = 0.13;
        ctx.fillRect(px, py, size, size);
        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = color;
        ctx.lineWidth = Math.max(1, size / 16);
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
    const inset = Math.max(1, Math.round(size * 0.06));
    ctx.fillStyle = '#000';
    ctx.fillRect(px + inset - 1, py + inset - 1, size - 2 * inset + 2, size - 2 * inset + 2);
    ctx.fillStyle = color;
    ctx.fillRect(px + inset, py + inset, size - 2 * inset, size - 2 * inset);
    const image = sprite('city', 'city');
    if (image && size >= 16) {
      ctx.imageSmoothingEnabled = false;
      ctx.globalAlpha = 0.55;
      ctx.drawImage(image, px + inset, py + inset, size - 2 * inset, size - 2 * inset);
      ctx.globalAlpha = 1;
    }
    if (city.walls) {
      ctx.strokeStyle = '#111';
      ctx.lineWidth = Math.max(2, size * 0.09);
      ctx.strokeRect(px + inset, py + inset, size - 2 * inset, size - 2 * inset);
    }
    if (size >= 12) {
      ctx.font = `bold ${Math.round(size * 0.52)}px Georgia, serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.lineWidth = Math.max(2, size * 0.09);
      ctx.strokeStyle = '#000';
      ctx.fillStyle = city.disorder ? '#ff5a4a' : '#fff';
      ctx.strokeText(String(city.size), px + size / 2, py + size / 2 + 1);
      ctx.fillText(String(city.size), px + size / 2, py + size / 2 + 1);
    }
    if (size >= 22) {
      const garrison = units ? units.length : 0;
      if (garrison) this._badge(ctx, px + size - inset, py + inset, String(garrison), size);
      if (city.capital) {
        ctx.fillStyle = '#ffd94a';
        ctx.font = `${Math.round(size * 0.32)}px sans-serif`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText('★', px + inset + 1, py + inset);
      }
    }
  }

  _drawCityLabel(ctx, city, px, py, size) {
    const label = city.name;
    ctx.font = `${Math.max(10, Math.min(15, Math.round(size * 0.36)))}px "Segoe UI", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.85)';
    ctx.fillStyle = store.selectedCity === city.id ? '#ffd94a' : '#fff';
    ctx.strokeText(label, px + size / 2, py + size + 1);
    ctx.fillText(label, px + size / 2, py + size + 1);
  }

  _drawUnits(ctx, units, px, py, size) {
    // Show the unit that would defend the tile: never a passenger while its ship is there.
    const crew = units.filter((unit) => !unit[U.ABOARD]);
    const shown = crew.length ? crew : units;
    let top = shown[0];
    for (const unit of shown) {
      if (store.unitDefs[unit[U.TYPE]].defense > store.unitDefs[top[U.TYPE]].defense) top = unit;
    }
    const definition = store.unitDefs[top[U.TYPE]];
    const color = player(top[U.OWNER]).color;
    const inset = Math.max(1, Math.round(size * 0.12));
    const box = size - 2 * inset;
    if (units.length > 1) {
      ctx.fillStyle = '#000';
      ctx.fillRect(px + inset + 2, py + inset - 2, box, box);
    }
    ctx.fillStyle = '#000';
    ctx.fillRect(px + inset - 1, py + inset - 1, box + 2, box + 2);
    ctx.fillStyle = color;
    ctx.fillRect(px + inset, py + inset, box, box);
    const image = sprite('unit', definition.sprite);
    if (image && size >= 14) {
      ctx.imageSmoothingEnabled = false;
      const scale = Math.min(box / image.width, box / image.height);
      const w = image.width * scale;
      const h = image.height * scale;
      ctx.drawImage(image, px + inset + (box - w) / 2, py + inset + (box - h) / 2, w, h);
    }
    if (size >= 22) {
      if (units.length > 1) this._badge(ctx, px + size - inset, py + inset, String(units.length), size);
      const mark = ORDER_MARK[top[U.ORDER]];
      if (mark) {
        ctx.font = `bold ${Math.round(size * 0.28)}px sans-serif`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = '#000';
        ctx.fillStyle = '#fff';
        ctx.strokeText(mark, px + inset + 1, py + size - inset);
        ctx.fillText(mark, px + inset + 1, py + size - inset);
      }
      if (top[U.VETERAN]) {
        ctx.fillStyle = '#ffd94a';
        ctx.beginPath();
        ctx.arc(px + inset + size * 0.1, py + inset + size * 0.1, size * 0.06, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  _badge(ctx, right, top, text, size) {
    const h = Math.round(size * 0.3);
    ctx.font = `bold ${Math.round(h * 0.85)}px sans-serif`;
    const w = Math.max(h, ctx.measureText(text).width + 4);
    ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
    ctx.fillRect(right - w, top, w, h);
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, right - w / 2, top + h / 2 + 1);
  }

  _drawMissions(ctx) {
    const detail = store.playerDetail;
    if (!detail || !detail.ai || !detail.ai.missions) return;
    const colors = {
      found_city: '#7bdc6a', improve: '#c9a25b', defend: '#6ab0ff', attack_city: '#ff5a4a',
      attack_unit: '#ff9d4a', explore: '#d7d7d7', help_wonder: '#e58cff', trade: '#ffd94a',
      explore_sea: '#8fd3ff', embark: '#4ad9c8',
    };
    const ts = this.tile;
    for (const mission of detail.ai.missions) {
      for (const tx of this._wrapped(mission.x)) {
        const px = this.screenX(tx);
        const py = this.screenY(mission.y);
        ctx.strokeStyle = colors[mission.kind] || '#fff';
        ctx.lineWidth = 2;
        ctx.setLineDash(mission.units ? [] : [4, 3]);
        ctx.beginPath();
        ctx.arc(px + ts / 2, py + ts / 2, ts * 0.46, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        if (ts >= 22 && mission.kind !== 'defend') {
          ctx.font = '10px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.lineWidth = 3;
          ctx.strokeStyle = '#000';
          ctx.fillStyle = colors[mission.kind] || '#fff';
          const text = mission.kind.replace('_', ' ');
          ctx.strokeText(text, px + ts / 2, py - 1);
          ctx.fillText(text, px + ts / 2, py - 1);
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

  _drawSelection(ctx) {
    const ts = this.tile;
    const draw = (x, y, color) => {
      for (const tx of this._wrapped(x)) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.strokeRect(this.screenX(tx) + 1, this.screenY(y) + 1, ts - 2, ts - 2);
      }
    };
    if (this.hover) draw(this.hover.x, this.hover.y, 'rgba(255, 255, 255, 0.55)');
    const detail = store.cityDetail;
    if (detail && store.selectedCity === detail.id) {
      for (const tile of detail.tiles) {
        if (tile.worked) draw(tile.x, tile.y, 'rgba(255, 217, 74, 0.9)');
      }
    }
  }
}
