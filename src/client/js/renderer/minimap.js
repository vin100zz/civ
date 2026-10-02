// The world at a glance: terrain colors, territory, cities and the main view's frame.

import { store, tileIndex, player } from '../state.js';

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
    const scale = Math.max(1, Math.floor(240 / map.width));
    const canvas = this.canvas;
    if (canvas.width !== map.width * scale || canvas.height !== map.height * scale) {
      canvas.width = map.width * scale;
      canvas.height = map.height * scale;
    }
    const ctx = this.ctx;
    const explored = state.explored || null;
    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) {
        const index = tileIndex(x, y);
        if (explored && explored[index] === '0') {
          ctx.fillStyle = '#000';
        } else {
          const owner = store.owner ? store.owner[index] : -1;
          const terrain = store.terrains[map.terrain[index]];
          ctx.fillStyle = owner >= 0 && terrain.land ? player(owner).color : terrain.color;
        }
        ctx.fillRect(x * scale, y * scale, scale, scale);
      }
    }
    for (const city of state.cities) {
      ctx.fillStyle = '#000';
      ctx.fillRect(city.x * scale - 1, city.y * scale - 1, scale + 2, scale + 2);
      ctx.fillStyle = '#fff';
      ctx.fillRect(city.x * scale, city.y * scale, scale, scale);
    }
    // Frame of the main view (may wrap around the world).
    const view = this.mapView;
    const w = view.width / view.tile * scale;
    const h = view.height / view.tile * scale;
    const left = view.cx * scale - w / 2;
    const top = view.cy * scale - h / 2;
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1;
    for (const shift of [-map.width * scale, 0, map.width * scale]) {
      ctx.strokeRect(left + shift + 0.5, top + 0.5, w, h);
    }
  }
}
