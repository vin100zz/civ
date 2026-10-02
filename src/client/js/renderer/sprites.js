// Loads the sprites named in the rules. Drawing code asks for an image and gets null
// until it is ready, so the map can be drawn (with flat colors) before everything loads.

const cache = new Map();
let onLoad = () => {};

export function setOnLoad(handler) {
  onLoad = handler;
}

export function sprite(folder, name) {
  if (!name) return null;
  const key = `${folder}/${name}`;
  let entry = cache.get(key);
  if (!entry) {
    const image = new Image();
    entry = { image, ready: false };
    image.onload = () => {
      entry.ready = true;
      onLoad();
    };
    image.src = `/resources/${key}.png`;
    cache.set(key, entry);
  }
  return entry.ready ? entry.image : null;
}

export function preload(rules) {
  for (const terrain of rules.terrains) {
    sprite('terrain', terrain.sprite);
    sprite('terrain', terrain.base_sprite);
    if (terrain.special) sprite('terrain', terrain.special.sprite);
    sprite('terrain', terrain.pattern_sprite);
  }
  for (const name of ['irrigation', 'mine', 'pollution']) sprite('terrain', name);
  for (const unit of rules.units) sprite('unit', unit.sprite);
  sprite('city', 'city');
}
