// Tooltips of the panels. An element marked data-tip="key" shows, while the pointer is over
// it, the html its panel gave for that key. The map draws its own tooltip (renderer/map.js).

const given = new WeakMap();   // panel -> Map of key -> html
let box = null;                // the tooltip, made the first time one is needed
let shown = null;              // {panel, key, html} of the tip on screen
let pointer = null;            // where the pointer was last seen over a panel

function tipBox() {
  if (!box) {
    box = document.createElement('div');
    box.id = 'panel-tip';
    box.className = 'tip glass';
    box.setAttribute('role', 'tooltip');
    box.hidden = true;
    document.body.appendChild(box);
  }
  return box;
}

export function hideTips() {
  shown = null;
  if (box) box.hidden = true;
}

// Below and to the right of the pointer, flipped above it at the bottom of the window.
function place() {
  const rect = box.getBoundingClientRect();
  const x = Math.min(pointer.x + 16, window.innerWidth - rect.width - 12);
  let y = pointer.y + 18;
  if (y + rect.height > window.innerHeight - 12) y = pointer.y - rect.height - 12;
  box.style.left = `${Math.max(8, x)}px`;
  box.style.top = `${Math.max(8, y)}px`;
}

function show(panel, target) {
  const key = target.dataset.tip;
  const html = given.get(panel).get(key);
  if (!html) {
    hideTips();
    return;
  }
  const tip = tipBox();
  if (!shown || shown.html !== html) tip.innerHTML = html;
  shown = { panel, key, html };
  tip.hidden = false;
  place();
}

function under(panel, x, y) {
  const element = document.elementFromPoint(x, y);
  const target = element && element.closest('[data-tip]');
  return target && panel.contains(target) ? target : null;
}

// Gives a panel its tips, a Map of key -> html: to call each time the panel is drawn.
export function setTips(panel, tips) {
  const first = !given.has(panel);
  given.set(panel, tips);
  if (first) {
    panel.addEventListener('mousemove', (e) => {
      pointer = { x: e.clientX, y: e.clientY };
      const target = e.target.closest('[data-tip]');
      if (target && panel.contains(target)) show(panel, target);
      else if (shown && shown.panel === panel) hideTips();
    });
    panel.addEventListener('mouseleave', () => {
      if (shown && shown.panel === panel) hideTips();
    });
    panel.addEventListener('scroll', () => {
      if (shown && shown.panel === panel) hideTips();
    });
  } else if (shown && shown.panel === panel) {
    // The panel was drawn again under the pointer: the tip follows what stands there now.
    const target = under(panel, pointer.x, pointer.y);
    if (target) show(panel, target);
    else hideTips();
  }
}
