// "Science" workspace: the technology tree of the selected civilization, over the whole width.

import { store, emit } from '../state.js';
import { ranking } from './civs.js';

const BOX_W = 176;
const BOX_H = 52;
const PITCH_X = 214;
const PITCH_Y = 68;
const PAD = 28;
const MINI_ROW = 9;          // overview: pixels per row, in its own 72 px tall drawing

let layout = null;           // computed once per rule set
let centredOn = null;        // civilization whose frontier the view was last brought to

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
  const rows = Math.max(...columns.map((c) => c.length));
  const position = {};
  columns.forEach((column, d) => {
    const shift = (rows - column.length) / 2;      // short columns sit in the middle
    column.forEach((id, i) => {
      position[id] = { x: PAD + d * PITCH_X, y: PAD + Math.round((i + shift) * PITCH_Y), row: i + shift, column: d };
    });
  });
  // What each advance leads to and, when the rules say it, what it unlocks.
  const leads = {};
  const unlocks = {};
  for (const tech of techs) {
    for (const pre of tech.prerequisites) (leads[pre] = leads[pre] || []).push(tech.name);
  }
  for (const item of [...store.rules.units, ...store.rules.buildings]) {
    if (item.requires) (unlocks[item.requires] = unlocks[item.requires] || []).push(item.name);
  }
  return {
    position, leads, unlocks, rows,
    columns: columns.length,
    hasUnlocks: Object.keys(unlocks).length > 0,
    width: 2 * PAD + (columns.length - 1) * PITCH_X + BOX_W,
    height: 2 * PAD + (rows - 1) * PITCH_Y + BOX_H,
  };
}

export function resetTechLayout() {
  layout = null;
  centredOn = null;
}

function turnsLabel(count) {
  return `${count} turn${count === 1 ? '' : 's'}`;
}

function capital(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : '';
}

function civPicker(selected) {
  const buttons = ranking().map((p) => `
    <button data-player="${p.id}" aria-pressed="${p.id === selected}">
      <span class="swatch small" style="background:${p.color}"></span>${p.nation}<span class="muted">${p.techs}</span></button>`);
  return `<div class="seg" role="group" aria-label="Civilization">${buttons.join('')}</div>`;
}

function wire(container) {
  container.querySelectorAll('.work-head [data-player]').forEach((button) => {
    button.addEventListener('click', () => emit('select-player', Number(button.dataset.player)));
  });
  const back = container.querySelector('[data-back]');
  if (back) back.addEventListener('click', () => emit('back-to-map'));
}

// Keeps the overview's window on the part of the tree that is on screen, both ways.
function wireOverview(container) {
  const tree = container.querySelector('#tech-tree');
  const overview = container.querySelector('#tech-overview');
  const frame = container.querySelector('#tech-window');
  const sync = () => {
    const total = Math.max(1, tree.scrollWidth);
    frame.style.left = `${100 * tree.scrollLeft / total}%`;
    frame.style.width = `${Math.min(100, 100 * tree.clientWidth / total)}%`;
  };
  tree.addEventListener('scroll', sync);
  const jump = (e) => {
    const box = overview.getBoundingClientRect();
    const ratio = (e.clientX - box.left) / box.width;
    tree.scrollLeft = ratio * tree.scrollWidth - tree.clientWidth / 2;
  };
  overview.addEventListener('pointerdown', (e) => {
    overview.setPointerCapture(e.pointerId);
    jump(e);
  });
  overview.addEventListener('pointermove', (e) => {
    if (e.buttons & 1) jump(e);
  });
  // Drag the tree itself to pan it.
  let drag = null;
  tree.addEventListener('pointerdown', (e) => {
    drag = { x: e.clientX, y: e.clientY, left: tree.scrollLeft, top: tree.scrollTop };
    tree.classList.add('dragging');
  });
  tree.addEventListener('pointermove', (e) => {
    if (!drag || !(e.buttons & 1)) return;
    tree.scrollLeft = drag.left - (e.clientX - drag.x);
    tree.scrollTop = drag.top - (e.clientY - drag.y);
  });
  for (const type of ['pointerup', 'pointerleave']) {
    tree.addEventListener(type, () => {
      drag = null;
      tree.classList.remove('dragging');
    });
  }
  return sync;
}

export function renderTech(container) {
  const detail = store.playerDetail;
  const head = (selected) => `
    <div class="work-head">
      <h1>Science</h1>
      ${store.state ? civPicker(selected) : ''}
      <div class="right">
        <div class="keys"${selected !== null && detail ? ` style="--civ:${detail.color}"` : ''}>
          <span><i class="known"></i>Known</span><span><i class="researching"></i>Researching</span>
          <span><i class="available"></i>Available now</span><span><i></i>Locked</span>
        </div>
        <button class="btn" data-back>Back to map</button>
      </div>
    </div>`;
  if (store.selectedPlayer === null || !detail || detail.id !== store.selectedPlayer) {
    container.innerHTML = `<div class="work">${head(null)}
      <p class="empty"><b>No civilization selected</b>Pick one above to see its advances.</p></div>`;
    wire(container);
    return;
  }
  if (!layout) layout = computeLayout();
  const known = new Set(detail.tech_list);
  const available = new Set(detail.research_options);
  const current = detail.researching;
  const previous = container.querySelector('#tech-tree');
  const scrollLeft = previous ? previous.scrollLeft : 0;
  const scrollTop = previous ? previous.scrollTop : 0;

  const left = Math.max(0, detail.research_cost - detail.research_progress);
  const turns = detail.science > 0 && current ? Math.ceil(left / detail.science) : null;
  const progress = detail.research_cost
    ? Math.min(100, 100 * detail.research_progress / detail.research_cost) : 0;

  const links = { known: [], next: [], locked: [] };
  const boxes = [];
  const mini = [];
  for (const tech of store.rules.techs) {
    const at = layout.position[tech.id];
    let state = '';
    if (known.has(tech.id)) state = 'known';
    else if (tech.id === current) state = 'researching';
    else if (available.has(tech.id)) state = 'available';
    let sub = layout.hasUnlocks ? (layout.unlocks[tech.id] || []).join(', ') || '—' : `${capital(tech.era)} era`;
    if (state === 'researching') {
      sub = `${detail.research_progress} / ${detail.research_cost}${turns !== null ? ` · ${turnsLabel(turns)}` : ''}`;
    }
    boxes.push(`<div class="tech ${state}" style="left:${at.x}px;top:${at.y}px" title="${tech.name} — ${sub}">
      <b>${tech.name}</b><small>${sub}</small></div>`);
    const fill = state === 'known' ? detail.color : state === 'researching' ? '#E2B659'
      : state === 'available' ? '#8A95A5' : '#2F3948';
    mini.push(`<rect x="${at.column * 100 + 6}" y="${at.row * MINI_ROW}" width="88" height="6" rx="2" fill="${fill}"/>`);
    for (const pre of tech.prerequisites) {
      const from = layout.position[pre];
      const x1 = from.x + BOX_W;
      const y1 = from.y + BOX_H / 2;
      const y2 = at.y + BOX_H / 2;
      const mid = (x1 + at.x) / 2;
      const path = `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${at.x},${y2}`;
      if (known.has(pre) && known.has(tech.id)) links.known.push(path);
      else if (known.has(pre) && state) links.next.push(path);
      else links.locked.push(path);
    }
  }

  const info = current ? store.techDefs[current] : null;
  const requires = info ? info.prerequisites.map((id) => store.techDefs[id].name).join(', ') || '—' : '—';
  const ai = detail.ai && detail.ai.research ? detail.ai.research.slice(0, 5) : [];
  const bestScore = ai.length ? Math.max(0.001, ai[0][1]) : 1;
  const rankingCard = ai.length ? `
    <div class="card">
      <div class="ai-title"><span class="ai-badge">AI</span><span class="h2">Research ranking</span>
        <span class="sub">${available.size} advances available</span></div>
      <div class="ranking">${ai.map(([id, score]) => `
        <div><b>${store.techDefs[id] ? store.techDefs[id].name : id}</b>
          <span class="bar thin"><span style="width:${Math.max(3, 100 * score / bestScore)}%"></span></span>
          <span class="sub">${score}</span></div>`).join('')}</div>
    </div>` : `<div class="card"><span class="sub">${available.size} advances available</span></div>`;

  container.innerHTML = `
    <div class="work" style="--civ:${detail.color}">
      ${head(detail.id)}
      <div class="research">
        <div class="card">
          <div class="between"><span class="sub">Researching${info ? ` · ${capital(info.era)} era` : ''}</span>
            <span class="sub">${detail.techs} of ${store.rules.techs.length} advances known</span></div>
          <div class="between"><span class="big">${info ? info.name : 'Nothing'}</span>
            <span class="soft" style="font-size:13px"><b style="color:var(--text)">${detail.research_progress}</b> / ${detail.research_cost}
              · +${detail.science} per turn${turns !== null ? ` · <b style="color:var(--gold)">${turnsLabel(turns)}</b>` : ''}</span></div>
          <div class="bar"><span style="width:${progress}%"></span></div>
        </div>
        <dl class="card kv">
          <dt>Requires</dt><dd>${requires}</dd>
          <dt>Leads to</dt><dd>${info ? (layout.leads[current] || []).join(', ') || '—' : '—'}</dd>
          ${layout.hasUnlocks ? `<dt>Unlocks</dt><dd><b>${info ? (layout.unlocks[current] || []).join(', ') || '—' : '—'}</b></dd>` : ''}
        </dl>
        ${rankingCard}
      </div>
      <div class="tree">
        <div id="tech-tree">
          <div class="tree-canvas" style="width:${layout.width}px;height:${layout.height}px">
            <svg width="${layout.width}" height="${layout.height}" fill="none">
              <path d="${links.locked.join(' ')}" stroke="#2A3342" stroke-width="1.25"/>
              <path d="${links.next.join(' ')}" stroke="#8A95A5" stroke-width="1.5" stroke-dasharray="4 4"/>
              <path d="${links.known.join(' ')}" stroke="${detail.color}" stroke-width="1.5" opacity="0.75"/>
            </svg>
            ${boxes.join('')}
          </div>
        </div>
      </div>
      <div class="overview">
        <div class="titles"><b>Whole tree</b><span class="sub">Drag to scroll</span></div>
        <div id="tech-overview">
          <svg viewBox="0 0 ${layout.columns * 100} ${layout.rows * MINI_ROW}" preserveAspectRatio="none"
            role="img" aria-label="Overview of the whole technology tree">${mini.join('')}</svg>
          <div id="tech-window"></div>
        </div>
      </div>
    </div>`;
  wire(container);
  const sync = wireOverview(container);
  const tree = container.querySelector('#tech-tree');
  if (centredOn !== detail.id && tree.clientWidth > 0) {
    // First look at this civilization: bring its research front into view.
    const focus = layout.position[current] || layout.position[detail.tech_list[detail.tech_list.length - 1]];
    tree.scrollLeft = focus ? focus.x - tree.clientWidth * 0.42 : 0;
    tree.scrollTop = focus ? focus.y + BOX_H / 2 - tree.clientHeight / 2 : 0;
    centredOn = detail.id;
  } else {
    tree.scrollLeft = scrollLeft;
    tree.scrollTop = scrollTop;
  }
  sync();
}
