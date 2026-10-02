// "Science" tab: the technology tree of the selected civilization.

import { store } from '../state.js';
import { swatch } from './civs.js';

const BOX_W = 118;
const BOX_H = 22;
const GAP_X = 34;
const GAP_Y = 6;

let layout = null;     // computed once per rule set

function computeLayout() {
  const techs = store.rules.techs;
  const depth = {};
  const depthOf = (id) => {
    if (depth[id] !== undefined) return depth[id];
    const tech = store.techDefs[id];
    depth[id] = tech.prerequisites.length
      ? 1 + Math.max(...tech.prerequisites.map(depthOf)) : 0;
    return depth[id];
  };
  techs.forEach((t) => depthOf(t.id));
  const columns = [];
  for (const tech of techs) {
    const d = depth[tech.id];
    (columns[d] = columns[d] || []).push(tech.id);
  }
  // Order each column by the average row of its prerequisites, to shorten the links.
  const row = {};
  columns.forEach((column, d) => {
    if (d > 0) {
      const weight = (id) => {
        const pre = store.techDefs[id].prerequisites;
        return pre.reduce((sum, p) => sum + row[p], 0) / pre.length;
      };
      column.sort((a, b) => weight(a) - weight(b));
    }
    column.forEach((id, i) => { row[id] = i; });
  });
  const position = {};
  columns.forEach((column, d) => {
    column.forEach((id, i) => {
      position[id] = { x: 6 + d * (BOX_W + GAP_X), y: 6 + i * (BOX_H + GAP_Y) };
    });
  });
  const rows = Math.max(...columns.map((c) => c.length));
  return {
    position,
    width: columns.length * (BOX_W + GAP_X),
    height: rows * (BOX_H + GAP_Y) + 12,
  };
}

export function resetTechLayout() {
  layout = null;
}

export function renderTech(container) {
  const detail = store.playerDetail;
  if (store.selectedPlayer === null || !detail || detail.id !== store.selectedPlayer) {
    container.innerHTML = '<p class="empty">Select a civilization to see its advances.</p>';
    return;
  }
  if (!layout) layout = computeLayout();
  const known = new Set(detail.tech_list);
  const available = new Set(detail.research_options);
  const scroll = container.querySelector('#tech-tree');
  const scrollLeft = scroll ? scroll.scrollLeft : 0;
  const scrollTop = scroll ? scroll.scrollTop : 0;

  const lines = [];
  const boxes = [];
  for (const tech of store.rules.techs) {
    const at = layout.position[tech.id];
    let cls = 'tech';
    let style = `left:${at.x}px;top:${at.y}px;`;
    if (known.has(tech.id)) {
      cls += ' known';
      style += `background:${detail.color};`;
    } else if (tech.id === detail.researching) cls += ' researching';
    else if (available.has(tech.id)) cls += ' available';
    boxes.push(`<div class="${cls}" style="${style}" title="${tech.name}">${tech.name}</div>`);
    for (const pre of tech.prerequisites) {
      const from = layout.position[pre];
      const color = known.has(pre) && known.has(tech.id) ? detail.color : '#4a505c';
      const x1 = from.x + BOX_W;
      const y1 = from.y + BOX_H / 2;
      const x2 = at.x;
      const y2 = at.y + BOX_H / 2;
      const mid = (x1 + x2) / 2;
      lines.push(`<path d="M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}"
        stroke="${color}" fill="none" stroke-width="1.2"/>`);
    }
  }
  container.innerHTML = `
    <h2>${swatch(detail.color)}${detail.nation} — ${detail.techs} advances</h2>
    <p class="muted">Filled: known. Gold outline: being researched. Bright: can be researched now.</p>
    <div id="tech-tree" style="height: calc(100% - 70px)">
      <div style="position:relative;width:${layout.width}px;height:${layout.height}px">
        <svg width="${layout.width}" height="${layout.height}">${lines.join('')}</svg>
        ${boxes.join('')}
      </div>
    </div>`;
  const fresh = container.querySelector('#tech-tree');
  fresh.scrollLeft = scrollLeft;
  fresh.scrollTop = scrollTop;
}
