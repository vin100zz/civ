// Messages of the turn, stacked in a corner of the map: alerts, news, what the units and
// cities left to themselves did. "Show" brings the map there.

import { emit } from './state.js';
import { icon } from './icons.js';

const MAX = 5;
const LOOK = {
  bad: 'alert', good: 'check', info: 'scroll',
};
let host = null;
let extra = 0;              // messages that did not fit

export function initToasts(element) {
  host = element;
  host.addEventListener('click', (e) => {
    const toast = e.target.closest('.toast');
    if (!toast) return;
    if (e.target.closest('[data-show]')) {
      emit('locate', { x: Number(toast.dataset.x), y: Number(toast.dataset.y) });
    } else if (e.target.closest('[data-dismiss]')) {
      toast.remove();
    } else if (e.target.closest('[data-more]')) {
      emit('show-tab', 'turn');
    }
  });
}

export function clearToasts() {
  if (host) host.innerHTML = '';
  extra = 0;
}

// tone: 'bad' (danger), 'good', or 'info'. `life` in seconds, 0 to stay until the next turn.
export function toast({ text, detail = '', tone = 'info', x, y, life = 0 }) {
  if (!host) return;
  const shown = host.querySelectorAll('.toast:not(.more)').length;
  if (shown >= MAX) {
    extra++;
    let more = host.querySelector('.toast.more');
    if (!more) {
      host.insertAdjacentHTML('beforeend', '<div class="toast more glass"><button data-more></button></div>');
      more = host.querySelector('.toast.more');
    }
    more.querySelector('button').textContent = `${extra} more in the Turn panel`;
    return;
  }
  const located = x !== undefined && x !== null;
  const element = document.createElement('div');
  element.className = `toast glass ${tone}`;
  if (located) {
    element.dataset.x = x;
    element.dataset.y = y;
  }
  element.innerHTML = `
    <span class="mark">${icon(LOOK[tone] || 'scroll', 19)}</span>
    <span class="body"><b>${text}</b>${detail ? `<span>${detail}</span>` : ''}</span>
    ${located ? '<button class="btn small" data-show>Show</button>' : ''}
    <button class="btn ghost icon small" data-dismiss aria-label="Dismiss">${icon('close', 15, 2)}</button>`;
  const more = host.querySelector('.toast.more');
  host.insertBefore(element, more);
  if (life) setTimeout(() => element.remove(), life * 1000);
}
