// "Chronicle": what happened, newest first. Click an entry to see where.

import { store, emit, player, yearLabel } from '../state.js';
import { icon } from '../icons.js';

export const GROUPS = {
  Cities: ['city_founded', 'city_captured', 'city_destroyed', 'famine', 'disorder', 'order'],
  War: ['combat', 'war', 'peace', 'contact', 'barbarians', 'civ_destroyed', 'disband',
        'unit_lost', 'nuclear'],
  Science: ['tech', 'wonder', 'government'],
  Economy: ['building', 'sold', 'trade_route', 'hut', 'spaceship_part'],
  World: ['pollution', 'global_warming', 'meltdown', 'spaceship_launched', 'spaceship_lost',
          'game_over'],
};
const ICON = { Cities: 'city', War: 'sword', Science: 'flask', Economy: 'coins', World: 'globe' };
const enabled = { Cities: true, War: true, Science: true, Economy: false, World: true };
const MAX_SHOWN = 250;
const NO_CIV = '#8A95A5';
let selected = null;        // the log entry pointed at on the map

export function groupOf(type) {
  for (const [group, types] of Object.entries(GROUPS)) {
    if (types.includes(type)) return group;
  }
  return 'War';
}

// The last events worth a glance (no routine economy), newest first.
export function latestEvents(count) {
  const events = [];
  for (let i = store.log.length - 1; i >= 0 && events.length < count; i--) {
    if (groupOf(store.log[i].type) !== 'Economy') events.push(store.log[i]);
  }
  return events;
}

function build(container) {
  const filters = Object.keys(GROUPS).map((group) => `
    <button class="filter" data-group="${group}" aria-pressed="${enabled[group]}">${group}<span></span></button>`)
    .join('');
  container.innerHTML = `
    <div class="panel-head">
      <div class="titles"><h1>Chronicle</h1><span class="sub" id="log-count"></span></div>
      <label class="switch"><input type="checkbox" id="log-only-selected"><i></i>Selected civ only</label>
    </div>
    <div class="log-tools">
      <label class="search">${icon('search', 16, 2)}
        <input type="text" id="log-search" aria-label="Search events" autocomplete="off"
          placeholder="Search a city, a unit, an advance…"></label>
      <div class="chips">${filters}</div>
    </div>
    <div id="log-entries"></div>
    <div class="panel-foot log-foot"><span>Icon color = civilization · click an entry to locate it</span>
      <span id="log-shown"></span></div>`;
  container.querySelectorAll('.filter').forEach((button) => {
    button.addEventListener('click', () => {
      enabled[button.dataset.group] = !enabled[button.dataset.group];
      renderLog(container);
    });
  });
  container.querySelector('#log-only-selected').addEventListener('change', () => renderLog(container));
  container.querySelector('#log-search').addEventListener('input', () => renderLog(container));
  container.querySelector('#log-entries').addEventListener('click', (e) => {
    const entry = e.target.closest('.located');
    if (!entry) return;
    selected = store.log[Number(entry.dataset.index)] || null;
    emit('locate', { x: Number(entry.dataset.x), y: Number(entry.dataset.y) });
    renderLog(container);
  });
}

export function renderLog(container) {
  if (!container.querySelector('#log-entries')) build(container);
  const counts = Object.fromEntries(Object.keys(GROUPS).map((group) => [group, 0]));
  for (const event of store.log) counts[groupOf(event.type)]++;
  container.querySelectorAll('.filter').forEach((button) => {
    button.setAttribute('aria-pressed', String(enabled[button.dataset.group]));
    button.querySelector('span').textContent = counts[button.dataset.group];
  });
  const first = store.log[0];
  container.querySelector('#log-count').textContent = store.log.length
    ? `${store.log.length} events since ${yearLabel(first.year)} · newest first` : 'Nothing yet';

  const onlySelected = container.querySelector('#log-only-selected').checked;
  const query = container.querySelector('#log-search').value.trim().toLowerCase();
  const entries = [];
  let matching = 0;
  let lastYear = null;
  for (let i = store.log.length - 1; i >= 0; i--) {
    const event = store.log[i];
    const group = groupOf(event.type);
    if (!enabled[group]) continue;
    if (onlySelected && store.selectedPlayer !== null
        && event.player !== store.selectedPlayer && event.other !== store.selectedPlayer) continue;
    if (query && !event.text.toLowerCase().includes(query)) continue;
    matching++;
    if (entries.length >= MAX_SHOWN) continue;
    const who = event.player !== undefined ? player(event.player) : null;
    const located = event.x !== undefined;
    const classes = ['log-entry'];
    if (located) classes.push('located');
    if (event === selected) classes.push('selected');
    entries.push(`<div class="${classes.join(' ')}" data-index="${i}"
      ${located ? `data-x="${event.x}" data-y="${event.y}"` : ''}>
      <span class="when">${event.year !== lastYear ? yearLabel(event.year) : ''}</span>
      <span class="kind" style="color:${who ? who.color : NO_CIV}" title="${group}">${icon(ICON[group], 14, 2)}</span>
      <span class="text">${event.text}</span>
      ${located ? `<span class="where">${icon('pin', 12, 2)}${event.x}, ${event.y}</span>` : ''}</div>`);
    lastYear = event.year;
  }
  const list = container.querySelector('#log-entries');
  const scroll = list.scrollTop;
  list.innerHTML = entries.join('') || '<p class="empty"><b>Nothing to show</b>No event matches these filters.</p>';
  list.scrollTop = scroll;
  container.querySelector('#log-shown').textContent = matching > entries.length
    ? `${entries.length} of ${matching}` : `${matching}`;
}
