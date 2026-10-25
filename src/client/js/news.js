// The news of the person's turn. The great events (a wonder, a civilization destroyed, a city
// lost, a war declared on them, a nuclear strike, global warming, a spaceship) show in a
// banner over the map, kept from turn to turn until closed; every event worth a glance is
// listed in the Turn panel, "Since your last turn".

import { store, emit, leader, player, inkOn } from './state.js';
import { icon } from './icons.js';

// In the order they are shown when several arrive together.
const HEADLINES = {
  civ_destroyed: { kicker: 'Civilization destroyed', glyph: 'crown' },
  city_lost: { kicker: 'City lost', glyph: 'city' },
  war: { kicker: 'War declared', glyph: 'sword' },
  nuclear: { kicker: 'Nuclear attack', glyph: 'alert' },
  spaceship_lost: { kicker: 'Spaceship lost', glyph: 'rocket' },
  spaceship_launched: { kicker: 'Spaceship launched', glyph: 'rocket' },
  global_warming: { kicker: 'Global warming', glyph: 'thermo' },
  wonder: { kicker: 'Wonder of the world', glyph: 'wonder' },
};
const ORDER = Object.keys(HEADLINES);
const NO_CIV = '#8A95A5';

let host = null;
const banner = { items: [], index: 0 };
let heard = [];             // the events of the person's turn worth a glance, oldest first

export function initNews(element) {
  host = element;
  host.addEventListener('click', (e) => {
    const item = banner.items[banner.index];
    if (!item) return;
    if (e.target.closest('[data-show]')) {
      emit('locate', { x: item.x, y: item.y });
    } else if (e.target.closest('[data-step]')) {
      const count = banner.items.length;
      banner.index = (banner.index + Number(e.target.closest('[data-step]').dataset.step) + count) % count;
      render();
    } else if (e.target.closest('[data-close]')) {
      banner.items.splice(banner.index, 1);
      render();
    }
  });
}

// How an event reads for the person: 'bad', 'good' or 'info', or null to keep it quiet.
export function toneOf(event, me) {
  const mine = event.player === me;
  const against = event.other === me;
  switch (event.type) {
    case 'combat': return event.winner === me ? 'good' : mine || against ? 'bad' : 'info';
    case 'city_captured': return mine ? 'good' : against ? 'bad' : 'info';
    case 'disorder': case 'famine': case 'disband': case 'unit_lost': case 'pollution':
      return mine ? 'bad' : null;          // the misfortunes of others seen in passing
    case 'city_destroyed': case 'meltdown': return mine ? 'bad' : 'info';
    case 'barbarians': return 'bad';
    case 'war': return mine || against ? 'bad' : 'info';
    case 'peace': case 'order': return 'good';
    case 'celebration': return mine ? 'good' : null;
    case 'celebration_over': return mine ? 'info' : null;
    case 'wonder': return mine ? 'good' : 'info';
    case 'tech': return mine && event.how !== 'discover' ? 'good' : null;
    case 'sold': case 'hut': case 'contact': case 'government': case 'trade_route':
    case 'civ_destroyed': case 'nuclear': case 'global_warming': case 'spaceship_launched':
    case 'spaceship_lost': case 'spaceship_part':
      return 'info';
    default: return null;
  }
}

// Which headline an event makes, or null.
function headlineOf(event, me) {
  switch (event.type) {
    case 'city_captured': return event.other === me ? 'city_lost' : null;
    case 'city_destroyed': return event.player === me ? 'city_lost' : null;
    case 'war': return event.other === me ? 'war' : null;
    case 'civ_destroyed': case 'nuclear': case 'spaceship_lost': case 'spaceship_launched':
    case 'global_warming': case 'wonder':
      return event.type;
    default: return null;
  }
}

function detailOf(event) {
  if (event.type === 'wonder') return store.buildingDefs[event.wonder]?.description || '';
  if (event.type === 'civ_destroyed') {
    const left = store.state.players.filter((p) => p.alive && !p.barbarian).length;
    return left === 1 ? 'One civilization remains.' : `${left} civilizations remain.`;
  }
  return '';
}

function headline(events, me) {
  const fresh = [];
  for (const event of events) {
    const kind = headlineOf(event, me);
    if (!kind) continue;
    // A small city taken is also destroyed: one loss, told once.
    const located = event.x !== undefined;
    if (kind === 'city_lost' && located
        && [...banner.items, ...fresh].some((i) => i.kind === kind && i.x === event.x && i.y === event.y)) continue;
    const owner = event.player !== undefined ? player(event.player) : null;
    fresh.push({
      kind, ...HEADLINES[kind], text: event.text, detail: detailOf(event),
      color: owner ? owner.color : NO_CIV, x: located ? event.x : undefined, y: event.y,
    });
  }
  if (!fresh.length) return;
  fresh.sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
  banner.index = banner.items.length;          // the first of the new ones
  banner.items.push(...fresh);
  render();
}

function render() {
  if (!host) return;
  const items = banner.items;
  host.hidden = !items.length;
  if (!items.length) {
    host.innerHTML = '';
    banner.index = 0;
    return;
  }
  banner.index = Math.min(banner.index, items.length - 1);
  const item = items[banner.index];
  const pager = items.length < 2 ? '' : `
    <button class="btn ghost icon small" data-step="-1" aria-label="Previous news" data-hint="Previous">${icon('left', 16, 2)}</button>
    <span class="count mono">${banner.index + 1} / ${items.length}</span>
    <button class="btn ghost icon small" data-step="1" aria-label="Next news" data-hint="Next">${icon('right', 16, 2)}</button>`;
  host.innerHTML = `
    <span class="headline-mark" style="background:${item.color};color:${inkOn(item.color)}">${icon(item.glyph, 24, 1.8)}</span>
    <span class="body"><span class="kicker">${item.kicker}</span><b>${item.text}</b>${item.detail ? `<span>${item.detail}</span>` : ''}</span>
    ${item.x !== undefined ? '<button class="btn small" data-show>Show</button>' : ''}${pager}
    <button class="btn ghost icon small" data-close aria-label="Close this news" data-hint="Close">${icon('close', 15, 2)}</button>`;
}

// Another game: nothing of the last one is told.
export function resetNews() {
  heard = [];
  banner.items = [];
  render();
}

// The start of the person's turn: what happened while the others played, after what the order
// that ended the last turn brought (`carried`: its headlines are already in the banner).
export function openTurnNews(carried, events) {
  const me = leader();
  heard = [...carried, ...events].filter((event) => toneOf(event, me));
  headline(events, me);
}

// What one of the person's orders brought.
export function addNews(events) {
  const me = leader();
  heard.push(...events.filter((event) => toneOf(event, me)));
  headline(events, me);
}

export function turnNews() {
  return heard;
}
