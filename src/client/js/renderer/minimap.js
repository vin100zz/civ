// The world at a glance: terrain colors, territory, cities and the main view's frame.

import { store, tileIndex, player } from '../state.js';

const WIDTH = 320;          // pixels on screen (css/style.css)
const OCEAN = [22, 44, 74];

function rgb(color) {
  const value = parseInt(color.slice(1), 16);
  return [value >> 16, (value >> 8) & 255, value & 255];
}

export class Minimap {
  constructor(canvas, mapView) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.mapView = mapView;
    canvas.addEventListener('mousedown', (e) => this._jump(e));
    canvas.addEventListener('mousemove', (e) => {
      if (e.buttons & 1) this._jump(e);
    });
  }

  _jump(e) {
    if (!store.map) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = Math.floor((e.clientX - rect.left) / rect.width * store.map.width);
    const y = Math.floor((e.clientY - rect.top) / rect.height * store.map.height);
    this.mapView.centerOn(x, y);
    e.stopPropagation();
  }

  render() {
    const { map, state } = store;
    if (!map || !state) return;
    const scale = Math.max(1, Math.floor(WIDTH / map.width));
    const canvas = this.canvas;
    if (canvas.width !== map.width * scale || canvas.height !== map.height * scale) {
      canvas.width = map.width * scale;
      canvas.height = map.height * scale;
    }
    const ctx = this.ctx;
    const explored = state.explored || null;
    // Dimmed terrain, so that the territories and the cities stand out.
    const ground = store.terrains.map((terrain) =>
      (terrain.land ? rgb(terrain.color).map((c) => c * 0.62) : OCEAN));
    const civ = state.players.map((p) => rgb(p.color));
    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) {
        const index = tileIndex(x, y);
        if (explored && explored[index] === '0') {
          ctx.fillStyle = '#06080B';
        } else {
          const owner = store.owner ? store.owner[index] : -1;
          let color = ground[map.terrain[index]];
          if (owner >= 0) color = color.map((c, i) => c * 0.3 + civ[owner][i] * 0.7);
          ctx.fillStyle = `rgb(${color[0] | 0}, ${color[1] | 0}, ${color[2] | 0})`;
        }
        ctx.fillRect(x * scale, y * scale, scale, scale);
      }
    }
    for (const city of state.cities) {
      ctx.fillStyle = '#0B0E13';
      ctx.fillRect(city.x * scale - 1, city.y * scale - 1, scale + 2, scale + 2);
      ctx.fillStyle = '#fff';
      ctx.fillRect(city.x * scale, city.y * scale, scale, scale);
    }
    // Frame of the main view (may wrap around the world).
    const view = this.mapView;
    const w = view.width / view.tile * scale;
    const h = Math.min(view.height / view.tile, map.height) * scale;
    const left = view.cx * scale - w / 2;
    const top = Math.max(0, view.cy * scale - h / 2);
    for (const shift of [-map.width * scale, 0, map.width * scale]) {
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)';
      ctx.lineWidth = 3;
      ctx.strokeRect(left + shift + 0.5, top + 0.5, w, h - 1);
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(left + shift + 0.5, top + 0.5, w, h - 1);
    }
  }
}
