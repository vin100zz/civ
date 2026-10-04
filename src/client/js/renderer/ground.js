// The ground of the map, painted ahead of time in square chunks: terrain colors melt into
// one another along slightly wavy borders, and the coast is rounded, with shallow water
// and a thin shoreline. The map view only has to paste the chunks.

import { store } from '../state.js';
import { sprite } from './sprites.js';

const LEVELS = [24, 48, 96];     // pixels per tile a chunk can be painted at
const CHUNK_PX = 384;            // side of a chunk, a multiple of every level
const MAX_CHUNKS = 120;
const REACH = 2;                 // a tile shows in the paint of tiles this far away

const BLEND_SIGMA = 0.12;        // softness of the borders between terrains, in tiles
const COAST_SIGMA = 0.30;        // how much the coastline is rounded
const BLEND_WARP = 0.22;         // how far the borders wander
const COAST_WARP = 0.15;
const SHALLOW = [108, 190, 226];
const SHALLOW_REACH = 0.55;
const FOAM = [240, 250, 255];
const FOAM_WIDTH = 0.045;
const SHORE = [60, 70, 40];
const SHORE_WIDTH = 0.05;

const STEPS = 256;

function normalCdf(z) {
  // Abramowitz & Stegun 7.1.26, good to 1e-7.
  const x = Math.abs(z) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * x);
  const erf = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592)
    * t * Math.exp(-x * x);
  return z < 0 ? (1 - erf) / 2 : (1 + erf) / 2;
}

// Share of a gaussian that lies beyond a point `t` tiles away, for t in [0, 1].
function tailTable(sigma) {
  const table = new Float32Array(STEPS + 2);
  for (let i = 0; i < table.length; i++) table[i] = normalCdf(-(i / STEPS) / sigma);
  return table;
}

const BLEND_TAIL = tailTable(BLEND_SIGMA);
const COAST_TAIL = tailTable(COAST_SIGMA);

// Distance to the coast (in tiles, positive inland) from the blurred share of land:
// exact along a straight coast, close enough around corners.
const COAST_DISTANCE = new Float32Array(1024);
for (let i = 0; i < 1024; i++) {
  const share = Math.min(0.9999, Math.max(0.0001, i / 1023));
  let low = -4;
  let high = 4;
  for (let n = 0; n < 30; n++) {
    const middle = (low + high) / 2;
    if (normalCdf(middle) < share) low = middle;
    else high = middle;
  }
  COAST_DISTANCE[i] = low * COAST_SIGMA;
}

function smoothstep(a, b, x) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

// A fixed random value in [-1, 1) for a tile corner.
function lattice(x, y, seed) {
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(seed, 1274126177);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 2147483648 - 1;
}

function median(histogram, count) {
  let seen = 0;
  for (let value = 0; value < 256; value++) {
    seen += histogram[value];
    if (seen * 2 >= count) return value;
  }
  return 255;
}

// What each terrain looks like at one level: its tile image, its ground color, and how
// much each pixel belongs to its motif (trees, dunes…) rather than to the ground.
// Null until every sprite is loaded.
function buildVisuals(level) {
  const visuals = [];
  const byKey = new Map();
  const kindOf = [];
  let sea = -1;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = level;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  const pixels = level * level;

  for (const terrain of store.terrains) {
    // Same layers as a flat tile: the base, then the terrain itself (rivers are drawn in code).
    const names = [terrain.base_sprite, terrain.id === 'river' ? null : terrain.sprite]
      .filter((name, i, all) => name && all.indexOf(name) === i);
    const key = `${terrain.land ? 'land' : 'sea'}:${names.join('+')}`;
    if (!byKey.has(key)) {
      ctx.fillStyle = terrain.color;
      ctx.fillRect(0, 0, level, level);
      for (const name of names) {
        const image = sprite('terrain', name);
        if (!image) return null;
        ctx.drawImage(image, 0, 0, level, level);
      }
      const rgba = ctx.getImageData(0, 0, level, level).data;
      const histograms = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
      for (let i = 0; i < pixels; i++) {
        for (let c = 0; c < 3; c++) histograms[c][rgba[i * 4 + c]]++;
      }
      const base = histograms.map((histogram) => median(histogram, pixels));
      const motif = new Float32Array(pixels);
      const tile = new Uint8ClampedArray(pixels * 4);
      for (let y = 0; y < level; y++) {
        for (let x = 0; x < level; x++) {
          const i = y * level + x;
          const gap = Math.abs(rgba[i * 4] - base[0]) + Math.abs(rgba[i * 4 + 1] - base[1])
            + Math.abs(rgba[i * 4 + 2] - base[2]);
          // Motifs fade out towards the edge of the tile, so wide ones are not cut sharply.
          const edge = Math.min(x, level - 1 - x, y, level - 1 - y) / (level * 0.16);
          const a = terrain.land
            ? Math.min(1, Math.max(0, (gap - 18) / 40)) * Math.min(1, edge) ** 1.2 : 1;
          motif[i] = a;
          for (let c = 0; c < 3; c++) tile[i * 4 + c] = base[c] + (rgba[i * 4 + c] - base[c]) * a;
          tile[i * 4 + 3] = 255;
        }
      }
      byKey.set(key, visuals.length);
      visuals.push({ land: terrain.land, rgba, base, motif, tile: new Uint32Array(tile.buffer) });
    }
    kindOf.push(byKey.get(key));
    if (!terrain.land && sea < 0) sea = byKey.get(key);
  }
  return { visuals, kindOf, sea };
}

// Paints the chunk of `tiles` × `tiles` tiles whose top-left tile is (startX, startY).
function paintChunk(level, look, startX, startY, tiles) {
  const { map } = store;
  const { visuals, kindOf, sea } = look;
  const side = tiles * level;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = side;
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(side, side);
  const out = image.data;
  const out32 = new Uint32Array(out.buffer);

  const kindAt = (x, y) => {
    const row = Math.min(map.height - 1, Math.max(0, y));
    const column = ((x % map.width) + map.width) % map.width;
    return kindOf[(map.ground || map.terrain)[row * map.width + column]];
  };
  const corner = (x, y, seed) => lattice(((x % map.width) + map.width) % map.width, y, seed);

  const around = new Int16Array(25);       // kinds of the 5 × 5 tiles around the current one
  const isLand = new Uint8Array(25);
  const weight = new Float32Array(visuals.length);
  const touched = new Int16Array(9);
  const ease = new Float32Array(level);    // smooth 0 → 1 across a tile, for the wander
  for (let i = 0; i < level; i++) {
    const t = (i + 0.5) / level;
    ease[i] = t * t * (3 - 2 * t);
  }

  for (let j = 0; j < tiles; j++) {
    const ty = startY + j;
    if (ty < 0 || ty >= map.height) continue;
    for (let i = 0; i < tiles; i++) {
      const tx = startX + i;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          const kind = kindAt(tx + dx, ty + dy);
          around[(dy + 2) * 5 + dx + 2] = kind;
          isLand[(dy + 2) * 5 + dx + 2] = visuals[kind].land ? 1 : 0;
        }
      }
      const own = around[12];
      const ownLook = visuals[own];
      const origin = j * level * side + i * level;

      // Nothing but the same terrain around: the tile as it is.
      let alone = true;
      for (let dy = 1; dy <= 3 && alone; dy++) {
        for (let dx = 1; dx <= 3; dx++) if (around[dy * 5 + dx] !== own) alone = false;
      }
      if (alone) {
        for (let y = 0; y < level; y++) {
          out32.set(ownLook.tile.subarray(y * level, (y + 1) * level), origin + y * side);
        }
        continue;
      }

      const seaLook = ownLook.land ? visuals[sea] : ownLook;
      const n00 = corner(tx, ty, 1), n10 = corner(tx + 1, ty, 1);
      const n01 = corner(tx, ty + 1, 1), n11 = corner(tx + 1, ty + 1, 1);
      const m00 = corner(tx, ty, 2), m10 = corner(tx + 1, ty, 2);
      const m01 = corner(tx, ty + 1, 2), m11 = corner(tx + 1, ty + 1, 2);

      for (let y = 0; y < level; y++) {
        const v = (y + 0.5) / level;
        const ev = ease[y];
        for (let x = 0; x < level; x++) {
          const u = (x + 0.5) / level;
          const eu = ease[x];
          const wanderX = (n00 + (n10 - n00) * eu) * (1 - ev) + (n01 + (n11 - n01) * eu) * ev;
          const wanderY = (m00 + (m10 - m00) * eu) * (1 - ev) + (m01 + (m11 - m01) * eu) * ev;
          const local = y * level + x;
          const at = (origin + y * side + x) * 4;

          // Share of land in the blurred neighbourhood, then the distance to the coast.
          let pu = u + COAST_WARP * wanderX;
          let pv = v + COAST_WARP * wanderY;
          let ox = pu < 0 ? -1 : pu >= 1 ? 1 : 0;
          let oy = pv < 0 ? -1 : pv >= 1 ? 1 : 0;
          pu -= ox;
          pv -= oy;
          let x0 = COAST_TAIL[(pu * STEPS + 0.5) | 0];
          let x2 = COAST_TAIL[((1 - pu) * STEPS + 0.5) | 0];
          let x1 = 1 - x0 - x2;
          let y0 = COAST_TAIL[(pv * STEPS + 0.5) | 0];
          let y2 = COAST_TAIL[((1 - pv) * STEPS + 0.5) | 0];
          let y1 = 1 - y0 - y2;
          let cell = (oy + 1) * 5 + ox + 1;
          const share = y0 * (x0 * isLand[cell] + x1 * isLand[cell + 1] + x2 * isLand[cell + 2])
            + y1 * (x0 * isLand[cell + 5] + x1 * isLand[cell + 6] + x2 * isLand[cell + 7])
            + y2 * (x0 * isLand[cell + 10] + x1 * isLand[cell + 11] + x2 * isLand[cell + 12]);
          const inland = COAST_DISTANCE[(Math.min(1, Math.max(0, share)) * 1023 + 0.5) | 0];
          let land = Math.min(1, Math.max(0, 0.5 + inland * level / 1.5));

          let r = 0;
          let g = 0;
          let b = 0;
          if (land > 0) {
            // Ground color: the land terrains around, each weighted by how close it is.
            pu = u + BLEND_WARP * wanderX;
            pv = v + BLEND_WARP * wanderY;
            ox = pu < 0 ? -1 : pu >= 1 ? 1 : 0;
            oy = pv < 0 ? -1 : pv >= 1 ? 1 : 0;
            pu -= ox;
            pv -= oy;
            x0 = BLEND_TAIL[(pu * STEPS + 0.5) | 0];
            x2 = BLEND_TAIL[((1 - pu) * STEPS + 0.5) | 0];
            x1 = 1 - x0 - x2;
            y0 = BLEND_TAIL[(pv * STEPS + 0.5) | 0];
            y2 = BLEND_TAIL[((1 - pv) * STEPS + 0.5) | 0];
            y1 = 1 - y0 - y2;
            cell = (oy + 1) * 5 + ox + 1;
            let count = 0;
            let total = 0;
            for (let dy = 0; dy < 3; dy++) {
              const wy = dy === 0 ? y0 : dy === 1 ? y1 : y2;
              for (let dx = 0; dx < 3; dx++) {
                const k = cell + dy * 5 + dx;
                if (!isLand[k]) continue;
                const w = wy * (dx === 0 ? x0 : dx === 1 ? x1 : x2);
                const kind = around[k];
                if (weight[kind] === 0 && w > 0) touched[count++] = kind;
                weight[kind] += w;
                total += w;
              }
            }
            if (total < 1e-4) {
              land = 0;
            } else {
              // Harden the weights around one half: a soft border, not a wide gradient.
              let sum = 0;
              for (let n = 0; n < count; n++) {
                const kind = touched[n];
                weight[kind] = smoothstep(0.3, 0.7, weight[kind] / total) + 1e-4;
                sum += weight[kind];
              }
              for (let n = 0; n < count; n++) {
                const w = weight[touched[n]] / sum;
                const base = visuals[touched[n]].base;
                r += w * base[0];
                g += w * base[1];
                b += w * base[2];
              }
              if (ownLook.land) {
                // The tile's own motif, fading where another terrain takes over.
                const a = ownLook.motif[local] * smoothstep(0.3, 0.62, weight[own] / sum);
                r += (ownLook.rgba[local * 4] - r) * a;
                g += (ownLook.rgba[local * 4 + 1] - g) * a;
                b += (ownLook.rgba[local * 4 + 2] - b) * a;
              }
              if (inland < SHORE_WIDTH) {
                const a = (1 - Math.max(0, inland) / SHORE_WIDTH) * 0.35;
                r += (SHORE[0] - r) * a;
                g += (SHORE[1] - g) * a;
                b += (SHORE[2] - b) * a;
              }
            }
            for (let n = 0; n < count; n++) weight[touched[n]] = 0;
          }
          if (land < 1) {
            let sr = seaLook.rgba[local * 4];
            let sg = seaLook.rgba[local * 4 + 1];
            let sb = seaLook.rgba[local * 4 + 2];
            const offshore = Math.max(0, -inland);
            if (offshore < SHALLOW_REACH) {
              const a = (1 - offshore / SHALLOW_REACH) ** 1.6 * 0.65;
              sr += (SHALLOW[0] - sr) * a;
              sg += (SHALLOW[1] - sg) * a;
              sb += (SHALLOW[2] - sb) * a;
            }
            if (offshore < FOAM_WIDTH) {
              const a = (1 - offshore / FOAM_WIDTH) * 0.63;
              sr += (FOAM[0] - sr) * a;
              sg += (FOAM[1] - sg) * a;
              sb += (FOAM[2] - sb) * a;
            }
            r = r * land + sr * (1 - land);
            g = g * land + sg * (1 - land);
            b = b * land + sb * (1 - land);
          }
          out[at] = r;
          out[at + 1] = g;
          out[at + 2] = b;
          out[at + 3] = 255;
        }
      }
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas;
}

export class Ground {
  constructor() {
    this.chunks = new Map();     // "level:x:y" → {canvas, x, y, tiles}, least recently used first
    this.looks = new Map();      // level → visuals
    this.terrain = null;         // the terrain the chunks were painted from
    this.width = 0;
  }

  // The level to paint at for tiles of `pixels` device pixels: the first one at least as fine.
  levelFor(pixels) {
    return LEVELS.find((level) => level >= pixels) || LEVELS[LEVELS.length - 1];
  }

  tilesPerChunk(level) {
    return CHUNK_PX / level;
  }

  // False while the sprites are still loading.
  ready(level) {
    if (!this.looks.has(level)) {
      const look = buildVisuals(level);
      if (!look || look.sea < 0) return false;
      this.looks.set(level, look);
    }
    return true;
  }

  // Forgets the chunks that show a tile whose terrain changed since they were painted.
  sync() {
    const { map } = store;
    const terrain = map.ground || map.terrain;       // see state.js groundTerrain
    const size = map.width * map.height;
    if (!this.terrain || this.terrain.length !== size || this.width !== map.width) {
      this.chunks.clear();
      this.terrain = Uint8Array.from(terrain);
      this.width = map.width;
      return;
    }
    for (let index = 0; index < size; index++) {
      if (this.terrain[index] === terrain[index]) continue;
      this.terrain[index] = terrain[index];
      const x = index % map.width;
      const y = (index - x) / map.width;
      for (const [key, chunk] of this.chunks) {
        const dx = (((x - chunk.x + REACH) % map.width) + map.width) % map.width;
        const dy = y - chunk.y + REACH;
        if (dx < chunk.tiles + 2 * REACH && dy >= 0 && dy < chunk.tiles + 2 * REACH) this.chunks.delete(key);
      }
    }
  }

  // The painted chunk starting at tile (x, y), or null when it is not painted yet and
  // `mayPaint` says there is no time left for it in this frame.
  chunk(level, x, y, mayPaint) {
    const { map } = store;
    const column = ((x % map.width) + map.width) % map.width;
    const key = `${level}:${column}:${y}`;
    let chunk = this.chunks.get(key);
    if (chunk) {
      this.chunks.delete(key);
    } else {
      if (!mayPaint()) return null;
      const tiles = this.tilesPerChunk(level);
      chunk = { canvas: paintChunk(level, this.looks.get(level), column, y, tiles), x: column, y, tiles };
      if (this.chunks.size >= MAX_CHUNKS) this.chunks.delete(this.chunks.keys().next().value);
    }
    this.chunks.set(key, chunk);
    return chunk.canvas;
  }
}
