// Inline icons on a 24 px grid, stroked with the current text color.

const PATHS = {
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  crown: '<path d="M4 19h16M4.5 16 3 7l5 4 4-7 4 7 5-4-1.5 9z"/>',
  city: '<path d="M3 21h18M5 21V8l7-4v17M19 21V12l-7-4M9 9v.01M9 13v.01M9 17v.01"/>',
  flask: '<path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3M7.5 15h9"/>',
  chart: '<path d="M3 3v18h18M7 15l4-5 3 3 5-7"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  step: '<path d="M6 5l9 7-9 7zM18 5v14"/>',
  save: '<path d="M5 3h11l4 4v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM8 3v5h7M8 21v-7h8v7"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  left: '<path d="M15 6l-6 6 6 6"/>',
  right: '<path d="M9 6l6 6-6 6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  pin: '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.4"/>',
  dice: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8.5 8.5v.01M15.5 8.5v.01M12 12v.01M8.5 15.5v.01M15.5 15.5v.01"/>',
  sword: '<path d="M14.5 17.5 3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2"/>',
  coins: '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18M7 6h1v4"/>',
  rocket: '<path d="M12 2.5c3 2.2 4.5 5.4 4.5 9.5v4h-9v-4c0-4.1 1.5-7.3 4.5-9.5zM7.5 13 4 16.5V19l3.5-1.2M16.5 13l3.5 3.5V19l-3.5-1.2M10 19.5c0 1 .8 2 2 2.5 1.2-.5 2-1.5 2-2.5"/><circle cx="12" cy="9.5" r="1.6"/>',
  trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3"/>',
};

export function icon(name, size = 18, stroke = 1.75) {
  return `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" `
    + `stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round" `
    + `aria-hidden="true">${PATHS[name] || ''}</svg>`;
}

// Fills every static element marked data-icon="name" (index.html) with its icon.
export function mountIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((element) => {
    const size = Number(element.dataset.size) || 18;
    const stroke = Number(element.dataset.stroke) || 1.75;
    element.insertAdjacentHTML('afterbegin', icon(element.dataset.icon, size, stroke));
  });
}
