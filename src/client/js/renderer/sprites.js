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

// A unit sprite cut down to what it shows: no empty margins and, for a ship, no waves under
// the hull (the map already shows the sea). The map can then draw the unit itself as big as
// its tile allows. Cut once per sprite; null until the image is loaded.
const trimmed = new Map();

export function trimmedSprite(folder, name, afloat) {
  const image = sprite(folder, name);
  if (!image) return null;
  const key = `${folder}/${name}`;
  if (!trimmed.has(key)) trimmed.set(key, trim(image, afloat));
  return trimmed.get(key);
}

// The same cut sprite for an <img> in the panels. Until it is ready this gives the image as
// it is, and the load handler runs once it is, so the panels can show it again.
const pictures = new Map();  // sprite name -> object URL, or null while it is being made

export function unitPicture(definition) {
  const name = definition.sprite;
  const url = pictures.get(name);
  if (url) return url;
  if (url === undefined) {
    const canvas = trimmedSprite('unit', name, definition.domain === 'sea');
    if (canvas) {
      pictures.set(name, null);
      canvas.toBlob((blob) => {
        if (!blob) return;
        pictures.set(name, URL.createObjectURL(blob));
        onLoad();
      });
    }
  }
  return `/resources/unit/${name}.png`;
}

const SOLID = 40;          // alpha above which a pixel counts as drawn
const KEEL = 3;            // rows of dark outline put back under a hull cut at the waterline

function trim(image, afloat) {
  const w = image.naturalWidth;
  const h = image.naturalHeight;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(image, 0, 0);
  const pixels = ctx.getImageData(0, 0, w, h);
  const data = pixels.data;
  const at = (x, y) => (y * w + x) * 4;

  if (afloat) {
    // The waves are the lowest rows where most drawn pixels are blue, white crests between
    // them included: go up from the bottom until a few rows in a row are not water.
    let cut = null;
    for (let y = h - 1; y >= 0; y--) {
      let drawn = 0;
      let blue = 0;
      for (let x = 0; x < w; x++) {
        const i = at(x, y);
        if (data[i + 3] <= SOLID) continue;
        drawn++;
        if (data[i + 2] > data[i] + 50 && data[i + 2] > 120) blue++;
      }
      if (!drawn) continue;
      if (blue / drawn > 0.5) cut = y;
      else if (cut !== null && y < cut - 3) break;
    }
    if (cut !== null) {
      for (let i = at(0, cut); i < data.length; i += 4) data[i + 3] = 0;
      for (let y = Math.max(0, cut - KEEL); y < cut; y++) {
        for (let x = 0; x < w; x++) {
          const i = at(x, y);
          if (data[i + 3] <= SOLID) continue;
          data[i] = 11;
          data[i + 1] = 14;
          data[i + 2] = 19;
          data[i + 3] = 255;
        }
      }
    }
  }

  let left = w;
  let right = -1;
  let top = h;
  let bottom = -1;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (data[at(x, y) + 3] <= SOLID) continue;
      if (x < left) left = x;
      if (x > right) right = x;
      if (y < top) top = y;
      if (y > bottom) bottom = y;
    }
  }
  if (right < 0) return canvas;
  const out = document.createElement('canvas');
  out.width = right - left + 1;
  out.height = bottom - top + 1;
  out.getContext('2d').putImageData(pixels, -left, -top, left, top, out.width, out.height);
  return out;
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
