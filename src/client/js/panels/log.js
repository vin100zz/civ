// "Log" tab: what happened, newest first. Click an entry to see where.

import { store, emit, player, yearLabel } from '../state.js';

const GROUPS = {
  Cities: ['city_founded', 'city_captured', 'city_destroyed', 'famine', 'disorder', 'order'],
  War: ['combat', 'war', 'peace', 'contact', 'barbarians', 'civ_destroyed', 'disband',
        'unit_lost', 'nuclear'],
  Science: ['tech', 'wonder', 'government'],
  Economy: ['building', 'sold', 'trade_route', 'hut', 'spaceship_part'],
  World: ['pollution', 'global_warming', 'meltdown', 'spaceship_launched', 'spaceship_lost',
          'game_over'],
};
const enabled = { Cities: true, War: true, Science: true, Economy: false, World: true };
const MAX_SHOWN = 250;

function groupOf(type) {
  for (const [group, types] of Object.entries(GROUPS)) {
    if (types.includes(type)) return group;
  }
  return 'War';
}

export function renderLog(container) {
  if (!container.querySelector('.log-filters')) {
    const filters = Object.keys(GROUPS).map((group) => `
      <label class="check"><input type="checkbox" data-group="${group}"
        ${enabled[group] ? 'checked' : ''}> ${group}</label>`).join('');
    container.innerHTML = `
      <div class="log-filters">${filters}
        <label class="check"><input type="checkbox" id="log-only-selected"> Selected civilization only</label>
      </div><div id="log-entries"></div>`;
    container.querySelectorAll('input[data-group]').forEach((input) => {
      input.addEventListener('change', () => {
        enabled[input.dataset.group] = input.checked;
        renderLog(container);
      });
    });
    container.querySelector('#log-only-selected').addEventListener('change', () => renderLog(container));
  }
  const onlySelected = container.querySelector('#log-only-selected').checked;
  const entries = [];
  for (let i = store.log.length - 1; i >= 0 && entries.length < MAX_SHOWN; i--) {
    const event = store.log[i];
    if (!enabled[groupOf(event.type)]) continue;
    if (onlySelected && store.selectedPlayer !== null
        && event.player !== store.selectedPlayer && event.other !== store.selectedPlayer) continue;
    const who = event.player !== undefined ? player(event.player) : null;
    const color = who ? who.color : '#343944';
    const located = event.x !== undefined;
    entries.push(`<div class="log-entry${located ? ' located' : ''}" style="border-left-color:${color}"
      ${located ? `data-x="${event.x}" data-y="${event.y}"` : ''}>
      <span class="when">${yearLabel(event.year)}</span>${event.text}</div>`);
  }
  const list = container.querySelector('#log-entries');
  list.innerHTML = entries.join('') || '<p class="empty">Nothing yet.</p>';
  list.querySelectorAll('.located').forEach((entry) => {
    entry.addEventListener('click', () =>
      emit('center', { x: Number(entry.dataset.x), y: Number(entry.dataset.y) }));
  });
}
