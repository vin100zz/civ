// "History" tab: one line per civilization for a chosen figure.

import { store, yearLabel } from '../state.js';
import { swatch } from './civs.js';

const LABELS = {
  cities: 'Cities', population: 'Population', techs: 'Advances', score: 'Score',
  gold: 'Gold', units: 'Units',
};
let metric = 'score';

export function renderChart(container) {
  const state = store.state;
  if (!state || !store.history.length) return;
  if (!container.querySelector('#chart-canvas')) {
    const options = store.historyFields.map((f) =>
      `<option value="${f}"${f === metric ? ' selected' : ''}>${LABELS[f] || f}</option>`).join('');
    container.innerHTML = `
      <label>Figure <select id="chart-metric">${options}</select></label>
      <canvas id="chart-canvas"></canvas>
      <div class="legend" id="chart-legend"></div>`;
    container.querySelector('#chart-metric').addEventListener('change', (e) => {
      metric = e.target.value;
      renderChart(container);
    });
  }
  const canvas = container.querySelector('#chart-canvas');
  const box = canvas.getBoundingClientRect();
  if (box.width < 10) return;                 // tab not visible
  const ratio = window.devicePixelRatio || 1;
  canvas.width = box.width * ratio;
  canvas.height = box.height * ratio;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const w = box.width;
  const h = box.height;
  const pad = { left: 34, right: 8, top: 10, bottom: 20 };
  const field = store.historyFields.indexOf(metric);
  const history = store.history;
  const players = state.players.filter((p) => !p.barbarian);

  let max = 1;
  for (const row of history) {
    for (const p of players) {
      const values = row.players[p.id];
      if (values) max = Math.max(max, values[field]);
    }
  }
  const x = (i) => pad.left + (w - pad.left - pad.right) * (history.length > 1 ? i / (history.length - 1) : 0);
  const y = (v) => h - pad.bottom - (h - pad.top - pad.bottom) * v / max;

  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = '#343944';
  ctx.fillStyle = '#8d93a0';
  ctx.font = '10px sans-serif';
  ctx.lineWidth = 1;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let step = 0; step <= 4; step++) {
    const value = Math.round(max * step / 4);
    ctx.beginPath();
    ctx.moveTo(pad.left, y(value) + 0.5);
    ctx.lineTo(w - pad.right, y(value) + 0.5);
    ctx.stroke();
    ctx.fillText(String(value), pad.left - 4, y(value));
  }
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText(yearLabel(history[0].year), pad.left, h - pad.bottom + 5);
  ctx.textAlign = 'right';
  ctx.fillText(yearLabel(history[history.length - 1].year), w - pad.right, h - pad.bottom + 5);

  for (const p of players) {
    ctx.strokeStyle = p.color;
    ctx.lineWidth = p.id === store.selectedPlayer ? 3 : 1.5;
    ctx.beginPath();
    let started = false;
    history.forEach((row, i) => {
      const values = row.players[p.id];
      if (!values) return;
      if (started) ctx.lineTo(x(i), y(values[field]));
      else ctx.moveTo(x(i), y(values[field]));
      started = true;
    });
    ctx.stroke();
  }
  const last = history[history.length - 1].players;
  container.querySelector('#chart-legend').innerHTML = players
    .map((p) => ({ p, value: last[p.id] ? last[p.id][field] : 0 }))
    .sort((a, b) => b.value - a.value)
    .map(({ p, value }) => `<span>${swatch(p.color)}${p.name} ${value}</span>`).join('');
}
