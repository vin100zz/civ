// What the units did in the person's sight, shown before the server's news of it is taken
// in: the moves of the others when its turn begins, one after the other as in the original
// game, and the fights its own orders start.
//
// The message telling of them waits meanwhile, and those that follow queue behind it. The
// steps are played over the state still on screen: each one names the units now standing
// on the tiles it touched (state.js applyStep).

import { store, U, leader, emit, tileIndex, applyStep, handleMessage } from './state.js';

const STEP_MS = 200;          // one step of a unit
const GAP_MS = 50;            // a breath before the next one
const CAMERA_MS = 180;        // time to find one's bearings when the camera has moved
const LUNGE_MS = 220;         // an attacker strikes
const AFTERMATH_MS = 420;     // whoever lost goes up in a flash
const BUDGET_MS = 6000;       // a long replay speeds up to fit in this time...
const FASTEST = 0.5;          // ...but no step goes faster than this share of its time
const FIGHTS = ['attack_won', 'attack_lost'];

let map = null;               // the map view, which draws the moves (main.js)
let covered = () => false;    // true when nothing of the map shows
let showing = false;          // a message is waiting for its steps to be played
let watching = false;         // ...and they are the moves of the others, which can be skipped
let hurried = false;          // the person asked to skip what is left
let wake = null;              // ends the pause in progress
const backlog = [];           // the messages that came meanwhile

export function initReplay(mapView, isCovered) {
  map = mapView;
  covered = isCovered;
}

// True while the moves of the others are being shown.
export function replaying() {
  return watching;
}

// True while a message waits for its steps to be shown: the state on screen is about to change.
export function settling() {
  return showing;
}

export function skipReplay() {
  hurried = true;
  if (wake) wake();
}

function pause(ms) {
  if (hurried) return Promise.resolve();
  return new Promise((resolve) => {
    wake = resolve;
    setTimeout(resolve, ms);
  });
}

function standing([x, y]) {
  return store.unitsAt.get(tileIndex(x, y)) || [];
}

// The steps of a message to show before it is taken in: what the others did, at the start
// of the person's turn; the fight, after one of its orders. Its own moves need no waiting:
// the map slides its units once the message is in.
function stepsToShow(message) {
  const me = leader();
  const steps = message.steps || [];
  if (me === null || !steps.length || covered() || document.hidden) return [];
  if (message.type === 'turn') return steps.filter((step) => step.owner !== me);
  if (message.type === 'update') return steps.filter((step) => FIGHTS.includes(step.outcome));
  return [];
}

// One step: the camera goes there, the unit slides or strikes, the tiles get their units.
async function show(step, pace, follow) {
  const sees = ([x, y]) => store.state.explored[tileIndex(x, y)] === '2';
  const [x, y] = sees(step.to) ? step.to : step.from;
  if (follow && map.bring(x, y)) await pause(CAMERA_MS * pace);
  const leaving = standing(step.from);

  if (FIGHTS.includes(step.outcome)) {
    const fighting = [step.from, step.to].map((tile) => [tile, standing(tile)]);
    if (leaving.some((unit) => unit[U.ID] === step.unit)) {
      map.lunge(step.unit, step.from, step.to, LUNGE_MS * pace);
      await pause(LUNGE_MS * pace);
    }
    applyStep(step);
    // Whoever is no longer there has lost.
    const left = new Set(step.tiles.flatMap(([, , units]) => units.map((unit) => unit[U.ID])));
    for (const [tile, units] of fighting) {
      const lost = units.filter((unit) => !left.has(unit[U.ID]));
      if (lost.length) map.burst(tile[0], tile[1], lost);
    }
    // After the person's own order the news comes in at once, under the flash.
    if (follow) await pause(AFTERMATH_MS * pace);
    return;
  }

  applyStep(step);
  // Whoever went from the first tile to the second travelled along: those aboard a ship.
  const aboard = new Set(leaving.map((unit) => unit[U.ID]));
  const moved = standing(step.to)
    .filter((unit) => unit[U.ID] === step.unit || aboard.has(unit[U.ID]));
  map.slide(moved.map((unit) => [unit[U.ID], [step.from, step.to]]), STEP_MS * pace);
  map.invalidate();
  await pause((STEP_MS + GAP_MS) * pace);
}

async function play(steps, others) {
  hurried = false;
  watching = others;
  if (others) {
    emit('play');
    await map.settled();            // the person's own last move first
  }
  const pace = others
    ? Math.max(FASTEST, Math.min(1, BUDGET_MS / (steps.length * (STEP_MS + GAP_MS)))) : 1;
  for (const step of steps) {
    if (hurried || document.hidden) applyStep(step);
    else await show(step, pace, others);
  }
}

// Every message of the server comes through here.
export async function receive(message) {
  if (showing) {
    backlog.push(message);
    return;
  }
  const steps = stepsToShow(message);
  if (steps.length) {
    showing = true;
    try {
      await play(steps, message.type === 'turn');
    } catch (error) {
      console.error(error);         // the message itself still tells everything
    }
    showing = false;
    watching = false;
  }
  handleMessage(message);
  while (backlog.length && !showing) receive(backlog.shift());
}
