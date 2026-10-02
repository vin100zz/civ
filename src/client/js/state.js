// Client-side copy of what the server sends. No game rule lives here.

export const F = {
  SPECIAL: 1, PATTERN: 2, HUT: 4, ROAD: 8, RAILROAD: 16, IRRIGATION: 32, MINE: 64,
  FORTRESS: 128, POLLUTION: 256,
};

// Fields of a unit as sent by the server: [id, type, owner, x, y, order, veteran, aboard]
export const U = { ID: 0, TYPE: 1, OWNER: 2, X: 3, Y: 4, ORDER: 5, VETERAN: 6, ABOARD: 7 };

export const store = {
  rules: null,
  map: null,            // {width, height, terrain[], flags[], continent[]}
  state: null,          // {turn, year, players[], cities[], units[], explored?, pov}
  history: [],
  historyFields: [],
  log: [],
  playing: false,
  delay: 0.4,
  saves: [],            // names of the saved games on the server
  selectedPlayer: null, // player id
  selectedCity: null,   // city id
  cityDetail: null,
  playerDetail: null,
  options: { territory: true, grid: false, missions: false },
  // indexes rebuilt from the data above
  terrains: [],
  unitDefs: {},
  buildingDefs: {},
  techDefs: {},
  cityAt: new Map(),    // tile index -> city
  unitsAt: new Map(),   // tile index -> [unit, ...]
  owner: null,          // Int16Array: tile index -> player id owning the land, or -1
};

const listeners = new Map();

export function on(event, handler) {
  if (!listeners.has(event)) listeners.set(event, []);
  listeners.get(event).push(handler);
}

export function emit(event, data) {
  for (const handler of listeners.get(event) || []) handler(data);
}

export function tileIndex(x, y) {
  const w = store.map.width;
  return y * w + (((x % w) + w) % w);
}

export function player(id) {
  return store.state ? store.state.players[id] : null;
}

export function yearLabel(year) {
  return year < 0 ? `${-year} BC` : `${year} AD`;
}

const CITY_OFFSETS = [
  [0, 0], [0, -1], [1, 0], [0, 1], [-1, 0], [1, -1], [1, 1], [-1, 1], [-1, -1],
  [0, -2], [2, 0], [0, 2], [-2, 0], [-1, -2], [1, -2], [2, -1], [2, 1], [1, 2], [-1, 2],
  [-2, 1], [-2, -1],
];

function rebuildIndexes() {
  const { map, state } = store;
  store.cityAt = new Map();
  store.unitsAt = new Map();
  if (!map || !state) return;
  for (const city of state.cities) store.cityAt.set(tileIndex(city.x, city.y), city);
  for (const unit of state.units) {
    const index = tileIndex(unit[U.X], unit[U.Y]);
    if (!store.unitsAt.has(index)) store.unitsAt.set(index, []);
    store.unitsAt.get(index).push(unit);
  }
  // Land owned by each civilization: the tiles its cities can work. First city wins.
  const owner = new Int16Array(map.width * map.height).fill(-1);
  const cities = [...state.cities].sort((a, b) => a.id - b.id);
  for (const city of cities) {
    for (const [dx, dy] of CITY_OFFSETS) {
      const y = city.y + dy;
      if (y < 0 || y >= map.height) continue;
      const index = tileIndex(city.x + dx, y);
      if (owner[index] === -1) owner[index] = city.owner;
    }
  }
  store.owner = owner;
}

function setRules(rules) {
  store.rules = rules;
  store.terrains = rules.terrains;
  store.unitDefs = Object.fromEntries(rules.units.map((u) => [u.id, u]));
  store.buildingDefs = Object.fromEntries(rules.buildings.map((b) => [b.id, b]));
  store.techDefs = Object.fromEntries(rules.techs.map((t) => [t.id, t]));
}

export function handleMessage(message) {
  switch (message.type) {
    case 'init':
      setRules(message.rules);
      store.map = message.map;
      store.state = message.state;
      store.history = message.history;
      store.historyFields = message.history_fields;
      store.log = message.log;
      store.playing = message.playing;
      store.delay = message.delay;
      store.saves = message.saves || [];
      store.selectedCity = null;
      store.cityDetail = null;
      store.playerDetail = null;
      if (store.selectedPlayer !== null && !store.state.players[store.selectedPlayer]) {
        store.selectedPlayer = null;
      }
      rebuildIndexes();
      emit('init');
      emit('status');
      break;
    case 'turn':
      store.state = message.state;
      for (const [index, terrain, flags] of message.tile_changes) {
        store.map.terrain[index] = terrain;
        store.map.flags[index] = flags;
      }
      store.history.push(message.history);
      store.log.push(...message.events);
      if (store.log.length > 800) store.log.splice(0, store.log.length - 800);
      store.playing = message.playing;
      rebuildIndexes();
      emit('turn', message);
      emit('status');
      break;
    case 'state':
      store.state = message.state;
      rebuildIndexes();
      emit('state');
      break;
    case 'status':
      store.playing = message.playing;
      store.delay = message.delay;
      emit('status');
      break;
    case 'city':
      store.cityDetail = message.city;
      emit('city');
      break;
    case 'player':
      store.playerDetail = message.player;
      emit('player');
      break;
    case 'saves':
      store.saves = message.saves;
      emit('saves');
      break;
    case 'notice':
      emit('notice', message);
      break;
    default:
      break;
  }
}
