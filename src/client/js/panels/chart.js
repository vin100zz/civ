// "History" workspace: one line per civilization for a chosen figure, the ranking beside it,
// and the other figures as small charts underneath.

import { store, emit, yearLabel } from '../state.js';
import { governmentName } from './civs.js';

const LABELS = {
  cities: 'Cities', population: 'Population', techs: 'Advances', score: 'Score',
  gold: 'Gold', units: 'Units',
};
const RANGES = [[0, 'Whole game'], [100, 'Last 100 turns'], [50, 'Last 50']];
const MARKS = { war: ['#F2756A', 'War declared'], wonder: ['#E2B659', 'Wonder completed'],
  civ_destroyed: ['#FFFFFF', 'Civilization destroyed'] };
const MAX_POINTS = 300;
let metric = 'score';
let range = 0;               // turns shown, 0 for the whole game
let watcher = null;

function build(container) {
  const metrics = store.historyFields.map((f) =>
    `<button data-metric="${f}">${LABELS[f] || f}</button>`).join('');
  const ranges = RANGES.map(([turns, label]) => `<button data-range="${turns}">${label}</button>`).join('');
  const keys = Object.values(MARKS).map(([color, label]) =>
    `<span><i class="dot" style="background:${color}"></i>${label}</span>`).join('');
  container.innerHTML = `
    <div class="work">
      <div class="work-head">
        <h1>History</h1>
        <div class="seg" id="chart-metrics" role="group" aria-label="Figure">${metrics}</div>
        <div class="right">
          <span class="sub">Range</span>
          <div class="seg" id="chart-ranges" role="group" aria-label="Range">${ranges}</div>
          <button class="btn" data-back>Back to map</button>
        </div>
      </div>
      <div class="history-main">
        <section class="frame chart-card">
          <div class="chart-top">
            <div><h2 id="chart-title"></h2><span class="sub" id="chart-span"></span></div>
            <div class="keys">${keys}</div>
          </div>
          <div id="chart-main"></div>
        </section>
        <section class="frame rank-card">
          <div class="between"><h2>Ranking</h2><span class="sub">change over the last 50 turns</span></div>
          <div id="chart-rank" style="display:flex;flex-direction:column;flex:1"></div>
        </section>
      </div>
      <div class="history-small" id="chart-small"></div>
    </div>`;
  container.addEventListener('click', (e) => {
    const target = e.target.closest('[data-metric], [data-range], [data-back], [data-player]');
    if (!target) return;
    if (target.dataset.metric) metric = target.dataset.metric;
    else if (target.dataset.range !== undefined) range = Number(target.dataset.range);
    else if (target.dataset.player !== undefined) return emit('select-player', Number(target.dataset.player));
    else return emit('back-to-map');
    return renderChart(container);
  });
  if (watcher) watcher.disconnect();
  watcher = new ResizeObserver(() => renderChart(container));
  watcher.observe(container.querySelector('#chart-main'));
}

// The smallest "round" number of four equal steps that holds the value.
function niceMax(value) {
  let best = Infinity;
  for (let magnitude = 1; magnitude <= 1e6; magnitude *= 10) {
    for (const step of [1, 2, 2.5, 5]) {
      const top = step * magnitude * 4;
      if (top >= value && Number.isInteger(top / 4) && top < best) best = top;
    }
  }
  return best;
}

export function renderChart(container) {
  const state = store.state;
  if (!state || !store.history.length) return;
  if (!container.querySelector('#chart-main')) build(container);
  const all = store.history;
  const fields = store.historyFields;
  if (!fields.includes(metric)) metric = fields[0];
  const field = fields.indexOf(metric);
  const cities = fields.indexOf('cities');
  const players = state.players.filter((p) => !p.barbarian);

  container.querySelectorAll('[data-metric]').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.metric === metric)));
  container.querySelectorAll('[data-range]').forEach((b) =>
    b.setAttribute('aria-pressed', String(Number(b.dataset.range) === range)));

  // Where each destroyed civilization stops: the turn after its last city.
  const last = all.length - 1;
  const end = {};
  for (const p of players) {
    end[p.id] = last;
    if (!p.alive && cities >= 0) {
      let seen = -1;
      all.forEach((row, i) => {
        if (row.players[p.id] && row.players[p.id][cities] > 0) seen = i;
      });
      end[p.id] = Math.min(last, seen + 1);
    }
  }
  const first = range ? Math.max(0, last - range) : 0;
  const span = Math.max(1, last - first);
  const value = (p, i, f = field) => (all[i].players[p.id] ? all[i].players[p.id][f] : 0);
  const line = (p, f, x, y) => {
    const stop = end[p.id];
    if (stop < first) return '';
    const step = Math.max(1, Math.ceil((stop - first) / MAX_POINTS));
    const points = [];
    for (let i = first; i <= stop; i += step) points.push(`${x(i).toFixed(1)},${y(value(p, i, f)).toFixed(1)}`);
    if ((stop - first) % step) points.push(`${x(stop).toFixed(1)},${y(value(p, stop, f)).toFixed(1)}`);
    return points.join(' ');
  };
  const peak = (f) => {
    let max = 1;
    for (let i = first; i <= last; i++) {
      for (const p of players) max = Math.max(max, value(p, i, f));
    }
    return max;
  };

  container.querySelector('#chart-title').textContent = LABELS[metric] || metric;
  container.querySelector('#chart-span').textContent =
    `${yearLabel(all[first].year)} to ${yearLabel(all[last].year)} · ${last - first} turns`;

  // ── Main chart ──
  const holder = container.querySelector('#chart-main');
  const w = holder.clientWidth;
  const h = holder.clientHeight;
  if (w > 200 && h > 120) {
    const pad = { left: 52, right: 150, top: 16, bottom: 36 };
    const x1 = w - pad.right;
    const y1 = h - pad.bottom;
    const max = niceMax(peak(field));
    const x = (i) => pad.left + (x1 - pad.left) * (i - first) / span;
    const y = (v) => y1 - (y1 - pad.top) * v / max;
    const parts = [];
    for (let k = 0; k <= 4; k++) {
      const gy = y(max * k / 4).toFixed(1);
      parts.push(`<line x1="${pad.left}" x2="${x1}" y1="${gy}" y2="${gy}" stroke="${k ? '#1D2430' : '#3A4556'}"/>
        <text x="${pad.left - 12}" y="${gy}" dy="4" text-anchor="end" font-size="12" fill="#8A95A5">${max * k / 4}</text>`);
    }
    const every = [10, 20, 25, 50, 100, 200].find((n) => span / n <= 7) || 200;
    for (let i = Math.ceil(first / every) * every; i <= last; i += every) {
      if (i !== last && x1 - x(i) < 64) continue;       // too close to the last label
      parts.push(`<line x1="${x(i)}" x2="${x(i)}" y1="${y1}" y2="${y1 + 6}" stroke="#3A4556"/>
        <text x="${x(i)}" y="${y1 + 24}" text-anchor="middle" font-size="12" fill="#8A95A5">${yearLabel(all[i].year)}</text>`);
    }
    if (last % every) {
      parts.push(`<text x="${x1}" y="${y1 + 24}" text-anchor="middle" font-size="12" fill="#8A95A5">${yearLabel(all[last].year)}</text>`);
    }
    for (const p of players) {
      const emphasis = p.id === store.selectedPlayer ? 3.5 : p.alive ? 2.25 : 1.5;
      parts.push(`<polyline points="${line(p, field, x, y)}" fill="none" stroke="${p.color}" stroke-width="${emphasis}"
        stroke-linejoin="round" stroke-linecap="round" opacity="${p.alive ? 1 : 0.75}"/>`);
    }
    // Where a civilization was destroyed, with its name above; names step up to stay apart.
    const placed = [];
    for (const p of players.filter((other) => !other.alive && end[other.id] >= first)) {
      const cx = x(end[p.id]);
      const cy = y(value(p, end[p.id]));
      let ty = cy - 12;
      while (placed.some((other) => Math.abs(other.x - cx) < 190 && Math.abs(other.y - ty) < 15)) ty -= 15;
      placed.push({ x: cx, y: ty });
      const side = cx - pad.left < 170 ? ['start', 10] : ['end', -10];
      parts.push(`<circle cx="${cx}" cy="${cy}" r="5" fill="#0B0E13" stroke="${p.color}" stroke-width="2"/>
        <path d="M${cx - 2} ${cy - 2}l4 4m0 -4l-4 4" stroke="${p.color}" stroke-width="1.5" stroke-linecap="round"/>
        <text x="${cx + side[1]}" y="${ty}" text-anchor="${side[0]}" font-size="12" fill="#B7C0CD" stroke="#0B0E13"
          stroke-width="3" paint-order="stroke">${p.nation} destroyed · ${yearLabel(all[end[p.id]].year)}</text>`);
    }
    // Names at the end of the lines, spread so that they never overlap.
    const labels = players.filter((p) => p.alive)
      .map((p) => ({ p, v: value(p, last), y: y(value(p, last)) })).sort((a, b) => a.y - b.y);
    labels.forEach((label, i) => {
      label.at = i ? Math.max(label.y, labels[i - 1].at + 19) : Math.max(label.y, pad.top + 4);
    });
    const overflow = labels.length ? labels[labels.length - 1].at - y1 : 0;
    for (const label of labels) {
      const at = label.at - Math.max(0, overflow);
      parts.push(`<circle cx="${x1}" cy="${label.y}" r="4" fill="${label.p.color}" stroke="#0B0E13" stroke-width="2"/>
        <path d="M${x1 + 6} ${label.y} L${x1 + 14} ${at}" stroke="${label.p.color}" opacity="0.7"/>
        <text x="${x1 + 18}" y="${at + 4.5}" font-size="13" font-weight="600" fill="${label.p.color}">${label.p.nation}<tspan dx="7" font-weight="500" fill="#E9ECF1">${label.v}</tspan></text>`);
    }
    for (const event of store.log) {
      const mark = MARKS[event.type];
      if (!mark || event.turn < all[first].turn || event.turn > all[last].turn) continue;
      const i = first + (event.turn - all[first].turn);
      parts.push(`<circle cx="${x(i)}" cy="${y1}" r="4.5" fill="${mark[0]}" stroke="#0B0E13" stroke-width="2">
        <title>${yearLabel(event.year)} — ${event.text}</title></circle>`);
    }
    holder.innerHTML = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="${LABELS[metric] || metric} of every civilization over time">${parts.join('')}</svg>`;
  }

  // ── Ranking ──
  const ordered = [...players].sort((a, b) => value(b, last) - value(a, last));
  const best = Math.max(1, value(ordered[0], last));
  const before = Math.max(0, last - 50);
  container.querySelector('#chart-rank').innerHTML = ordered.map((p, i) => {
    const now = value(p, last);
    const delta = now - value(p, before);
    const tone = !p.alive || delta === 0 ? 'muted' : delta > 0 ? 'good' : 'bad';
    return `<button class="rank-row${p.alive ? '' : ' dead'}${p.id === store.selectedPlayer ? ' selected' : ''}" data-player="${p.id}">
      <span class="rank">${i + 1}</span>
      <span class="swatch" style="background:${p.color}"></span>
      <span class="who"><span><b>${p.nation}</b><small>${governmentName(p.government)}</small></span>
        <span class="bar thin"><span style="width:${100 * now / best}%;background:${p.color}"></span></span></span>
      <span class="delta ${tone}">${p.alive ? `${delta >= 0 ? '+' : ''}${delta}` : 'destroyed'}</span>
      <span class="value">${now}</span></button>`;
  }).join('');

  // ── The other figures ──
  container.querySelector('#chart-small').innerHTML = fields.filter((f) => f !== metric).map((name) => {
    const f = fields.indexOf(name);
    const max = peak(f);
    const x = (i) => 2 + 308 * (i - first) / span;
    const y = (v) => 120 - 112 * v / max;
    const lines = players.map((p) => `<polyline points="${line(p, f, x, y)}" fill="none" stroke="${p.color}"
      stroke-width="1.75" stroke-linejoin="round" opacity="${p.alive ? 1 : 0.6}" vector-effect="non-scaling-stroke"/>`).join('');
    const alive = players.filter((p) => p.alive);
    const leader = alive.length ? alive.reduce((a, b) => (value(b, last, f) > value(a, last, f) ? b : a)) : null;
    return `<button class="frame small-card" data-metric="${name}" title="Show ${LABELS[name] || name} in the main chart">
      <span class="top"><b>${LABELS[name] || name}</b>
        ${leader ? `<span><span class="swatch small" style="background:${leader.color}"></span>${leader.nation} <b>${value(leader, last, f)}</b></span>` : ''}</span>
      <svg viewBox="0 0 312 128" preserveAspectRatio="none" role="img" aria-label="${LABELS[name] || name} over time">
        <line x1="2" x2="310" y1="120" y2="120" stroke="#283040" vector-effect="non-scaling-stroke"/>
        <line x1="2" x2="310" y1="8" y2="8" stroke="#1D2430" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>${lines}</svg>
      <span class="axis"><span>${yearLabel(all[first].year)}</span><span>peak ${max}</span><span>${yearLabel(all[last].year)}</span></span>
    </button>`;
  }).join('');
}
