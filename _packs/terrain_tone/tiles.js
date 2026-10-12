// The terrain tiles of resources/terrain that are drawn in code: plains, desert, hills,
// forest and jungle (flat style, motif in the ground's own hue). export.py paints them in
// a headless Edge and saves the PNGs.
(function () {
  const TAU = Math.PI * 2;

  // ---- small parts -------------------------------------------------------------------

  function blade(ctx, x, y, lean, h, w) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(lean);
    ctx.beginPath();
    ctx.moveTo(-w / 2, 0);
    ctx.quadraticCurveTo(-w * 0.55, -h * 0.55, 0, -h);
    ctx.quadraticCurveTo(w * 0.55, -h * 0.55, w / 2, 0);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function tuft(ctx, x, y, s, color) {
    ctx.fillStyle = color;
    blade(ctx, x - s * 0.18, y, -0.42, s * 0.72, s * 0.26);
    blade(ctx, x + s * 0.18, y, 0.42, s * 0.72, s * 0.26);
    blade(ctx, x, y, 0, s, s * 0.3);
  }

  function ellipse(ctx, x, y, rx, ry, rot, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.ellipse(x, y, rx, ry, rot, 0, TAU);
    ctx.fill();
  }

  // A fir: two-tone crown in three tiers on a short trunk. `top` is the tip.
  function fir(ctx, x, top, h, dark, light, trunk) {
    const crown = h * 0.86;
    const w = h * 0.66;
    ctx.fillStyle = trunk;
    ctx.fillRect(x - w * 0.07, top + crown * 0.9, w * 0.14, h - crown * 0.9);
    const right = [[0.22, 0.34], [0.11, 0.30], [0.37, 0.66], [0.21, 0.61], [0.5, 1]];
    const path = new Path2D();
    path.moveTo(x, top);
    for (const [px, py] of right) path.lineTo(x + px * w, top + py * crown);
    for (const [px, py] of right.slice().reverse()) path.lineTo(x - px * w, top + py * crown);
    path.closePath();
    ctx.fillStyle = dark;
    ctx.fill(path);
    ctx.save();
    ctx.clip(path);
    ctx.fillStyle = light;
    ctx.fillRect(x - w, top - 1, w, crown + 2);
    ctx.restore();
  }

  // A saguaro cactus `h` tall standing at (x, base); `arms` = [[side, at, reach, rise]…]
  // with side -1 or 1, `at` and `rise` as fractions of h, reach in pixels.
  function saguaro(ctx, x, base, h, s, arms, c) {
    const trace = (dx, dy) => {
      ctx.beginPath();
      ctx.moveTo(x + dx, base + dy);
      ctx.lineTo(x + dx, base - h + s / 2 + dy);
      for (const [side, at, reach, rise] of arms) {
        const y = base - h * at + dy;
        ctx.moveTo(x + dx, y);
        ctx.arcTo(x + side * reach + dx, y, x + side * reach + dx, y - 10, s * 0.55);
        ctx.lineTo(x + side * reach + dx, y - h * rise);
      }
    };
    ellipse(ctx, x + s * 0.3, base + 1, s * 1.5, s * 0.36, 0, c.sand);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = c.shade;
    ctx.lineWidth = s;
    trace(0, 0);
    ctx.stroke();
    ctx.strokeStyle = c.body;
    ctx.lineWidth = s * 0.66;
    trace(-s * 0.15, -s * 0.06);
    ctx.stroke();
    ctx.strokeStyle = c.light;
    ctx.lineWidth = s * 0.16;
    trace(-s * 0.22, -s * 0.1);
    ctx.stroke();
  }

  // A frond from (x, y) towards `angle`, bending down by `droop` at the tip.
  function frond(ctx, x, y, angle, len, width, droop, color, rib) {
    const dx = Math.cos(angle);
    const dy = Math.sin(angle);
    const tx = x + dx * len;
    const ty = y + dy * len + droop;
    const mx = x + dx * len * 0.5;
    const my = y + dy * len * 0.5 + droop * 0.15;
    const nx = -dy * width;
    const ny = dx * width;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.quadraticCurveTo(mx + nx, my + ny, tx, ty);
    ctx.quadraticCurveTo(mx - nx, my - ny, x, y);
    ctx.fill();
    if (rib) {
      ctx.strokeStyle = rib;
      ctx.lineWidth = Math.max(1, width * 0.16);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.quadraticCurveTo(mx, my, tx, ty);
      ctx.stroke();
    }
  }

  function palm(ctx, foot, crown, size, c) {
    const [fx, fy] = foot;
    const [cx, cy] = crown;
    ctx.strokeStyle = c.trunk;
    ctx.lineCap = 'round';
    ctx.lineWidth = Math.max(5, size * 0.2);
    const bend = (cx - fx) * 0.5 - size * 0.25;
    ctx.beginPath();
    ctx.moveTo(fx, fy);
    ctx.quadraticCurveTo(fx + bend, (fy + cy) / 2, cx, cy);
    ctx.stroke();
    ctx.strokeStyle = c.ring;
    ctx.lineWidth = Math.max(1, size * 0.04);
    for (let t = 0.2; t < 0.9; t += 0.17) {
      const x = (1 - t) ** 2 * fx + 2 * (1 - t) * t * (fx + bend) + t * t * cx;
      const y = (1 - t) ** 2 * fy + 2 * (1 - t) * t * ((fy + cy) / 2) + t * t * cy;
      ctx.beginPath();
      ctx.moveTo(x - size * 0.08, y);
      ctx.lineTo(x + size * 0.08, y);
      ctx.stroke();
    }
    for (const [a, l, d] of [[-2.65, 0.75, 6], [-2.05, 0.7, 2], [-1.1, 0.72, 2], [-0.5, 0.75, 6]]) {
      frond(ctx, cx, cy, a, size * l, size * 0.2, d * size / 40, c.leaf2, null);
    }
    const fronds = [[-3.05, 1, 14], [-2.4, 1, 6], [-1.6, 0.8, -1], [-0.8, 1, 6], [-0.1, 1, 14], [2.6, 0.75, 6], [0.55, 0.75, 6]];
    for (const [a, l, d] of fronds) {
      frond(ctx, cx, cy, a, size * l, size * 0.24, d * size / 40, c.leaf, c.rib);
    }
    ellipse(ctx, cx, cy + 1, size * 0.09, size * 0.08, 0, c.trunk);
  }

  // A big split leaf (monstera) centred at (x, y).
  function monstera(ctx, x, y, r, rot, c) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(rot);
    ctx.fillStyle = c.leaf;
    ctx.beginPath();
    ctx.moveTo(0, r);
    ctx.bezierCurveTo(-r * 1.25, r * 0.6, -r * 1.05, -r * 0.95, 0, -r * 0.62);
    ctx.bezierCurveTo(r * 1.05, -r * 0.95, r * 1.25, r * 0.6, 0, r);
    ctx.fill();
    // The splits show the ground through the leaf.
    ctx.globalCompositeOperation = 'destination-out';
    ctx.lineCap = 'round';
    ctx.lineWidth = Math.max(1.5, r * 0.13);
    for (const side of [-1, 1]) {
      for (const t of [-0.25, 0.2]) {
        ctx.beginPath();
        ctx.moveTo(side * r * 0.95, t * r);
        ctx.lineTo(side * r * 0.42, t * r + r * 0.16);
        ctx.stroke();
      }
    }
    ctx.globalCompositeOperation = 'source-over';
    ctx.strokeStyle = c.rib;
    ctx.lineWidth = Math.max(1, r * 0.08);
    ctx.beginPath();
    ctx.moveTo(0, r * 1.25);
    ctx.lineTo(0, -r * 0.45);
    ctx.stroke();
    ctx.restore();
  }

  // A rounded hill standing on `base`, peak `h` above it.
  function dome(ctx, cx, base, w, h, c) {
    const k = h / 0.75;
    const p = new Path2D();
    p.moveTo(cx - w / 2, base);
    p.bezierCurveTo(cx - w * 0.36, base - k, cx + w * 0.36, base - k, cx + w / 2, base);
    p.closePath();
    ctx.fillStyle = c.body;
    ctx.fill(p);
    ctx.save();
    ctx.clip(p);
    ellipse(ctx, cx + w * 0.42, base + h * 0.1, w * 0.4, h * 1.25, 0, c.shade);
    ellipse(ctx, cx - w * 0.16, base - h * 0.7, w * 0.2, h * 0.2, -0.45, c.light);
    ctx.restore();
  }

  // ---- palettes ----------------------------------------------------------------------

  const CACTUS = { body: '#5FA84E', shade: '#3E8443', light: '#93CF6C', sand: '#E2BE68' };
  const JUNGLE = { leaf: '#86C94F', leaf2: '#5DAF46', rib: '#3E8A3A', trunk: '#8C6A3C', ring: '#6E5230' };
  const JUNGLE_LEAF_DARK = { leaf: '#1F6A3C', rib: '#2F8A4E' };

  // ---- the tiles ---------------------------------------------------------------------
  // Each has its ground colour and a motif drawn on a transparent layer, so the motif can
  // be toned down before it is laid on the ground.

  const tiles = {
    plains: {
      color: '#BFC25A',      // between grassland and desert, so neither is mistaken for it
      toned: false,          // its tufts are small and light enough as they are
      motif(ctx) {
        tuft(ctx, 36, 52, 30, '#DDAA42');
        tuft(ctx, 92, 44, 24, '#8BA340');
        tuft(ctx, 66, 92, 32, '#DDAA42');
        tuft(ctx, 30, 102, 22, '#8BA340');
        tuft(ctx, 100, 100, 24, '#DDAA42');
      },
    },
    desert: {
      color: '#F0D483',
      toned: true,
      motif(ctx) {
        ctx.fillStyle = '#D9B05C';
        ctx.beginPath();
        ctx.moveTo(14, 64);
        ctx.quadraticCurveTo(40, 34, 70, 58);
        ctx.quadraticCurveTo(44, 50, 14, 64);
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(40, 104);
        ctx.quadraticCurveTo(76, 70, 116, 96);
        ctx.quadraticCurveTo(80, 86, 40, 104);
        ctx.fill();
        saguaro(ctx, 84, 96, 74, 15, [[-1, 0.44, 19, 0.22], [1, 0.6, 18, 0.18]], CACTUS);
      },
    },
    hills: {
      color: '#9CBE5C',
      toned: true,
      motif(ctx) {
        const c = { body: '#80A646', shade: '#628A38', light: '#BAD879' };
        dome(ctx, 70, 66, 64, 34, c);
        dome(ctx, 40, 100, 62, 36, c);
        dome(ctx, 94, 106, 52, 30, c);
      },
    },
    forest: {
      color: '#5F984E',
      toned: true,
      motif(ctx) {
        const [dark, light, trunk] = ['#24582E', '#347039', '#5B3F24'];
        fir(ctx, 66, 16, 58, dark, light, trunk);
        fir(ctx, 38, 44, 62, dark, light, trunk);
        fir(ctx, 92, 46, 60, dark, light, trunk);
      },
    },
    jungle: {
      color: '#399057',
      toned: true,
      motif(ctx) {
        monstera(ctx, 96, 92, 17, 0.5, JUNGLE_LEAF_DARK);
        palm(ctx, [54, 108], [62, 46], 46, JUNGLE);
      },
    },
  };

  function luminance(r, g, b) {
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  function hex(color) {
    const v = parseInt(color.slice(1), 16);
    return [v >> 16, (v >> 8) & 255, v & 255];
  }

  // Paints the tile of `terrain` on a 128 × 128 canvas. The motif is laid "tone on tone":
  // in the ground's own hue, darker or lighter as the motif is, at `amount` opacity, so it
  // stays behind what the map draws over it (irrigation, roads, mines, cities).
  function paint(canvas, terrain, amount) {
    const spec = tiles[terrain];
    const size = 128;
    canvas.width = canvas.height = size;
    const layer = document.createElement('canvas');
    layer.width = layer.height = size;
    spec.motif(layer.getContext('2d'));
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = spec.color;
    ctx.fillRect(0, 0, size, size);
    if (!spec.toned) {
      ctx.drawImage(layer, 0, 0);
      return canvas;
    }
    const base = hex(spec.color);
    const baseL = luminance(...base);
    const motif = layer.getContext('2d').getImageData(0, 0, size, size).data;
    const image = ctx.getImageData(0, 0, size, size);
    const out = image.data;
    for (let i = 0; i < out.length; i += 4) {
      const a = motif[i + 3] / 255;
      if (!a) continue;
      const k = luminance(motif[i], motif[i + 1], motif[i + 2]) / baseL;
      const t = a * amount;
      for (let c = 0; c < 3; c++) out[i + c] = base[c] + (base[c] * k - base[c]) * t;
    }
    ctx.putImageData(image, 0, 0);
    return canvas;
  }

  window.TILES = { tiles, paint };
})();
