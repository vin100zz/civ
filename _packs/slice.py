"""Découpe les planches ChatGPT (fond magenta) en sprites individuels à fond transparent.

Usage : python slice.py <planche.png> <dossier_sortie> <nom1> <nom2> ... [--size 256] [--keep-bg]
Les sprites sont détectés par composantes connexes et nommés dans l'ordre de lecture
(lignes de haut en bas, gauche à droite).
"""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage


def magenta_alpha(rgb):
    """Alpha 0..255 : 0 sur le fond magenta, 255 ailleurs, bord adouci + décontamination."""
    r, g, b = [rgb[..., i].astype(np.int32) for i in range(3)]
    # distance au magenta pur
    d = np.sqrt((255 - r) ** 2 + g ** 2 + (255 - b) ** 2)
    alpha = np.clip((d - 60) / 90.0, 0, 1)
    return alpha


def despill(rgb, alpha):
    out = rgb.astype(np.float32)
    edge = (alpha > 0) & (alpha < 1)
    # retire la dominante magenta sur les pixels de bord
    m = np.minimum(out[..., 0], out[..., 2]) - out[..., 1]
    m = np.clip(m, 0, None)
    out[..., 0] -= np.where(edge, m * 0.8, 0)
    out[..., 2] -= np.where(edge, m * 0.8, 0)
    return np.clip(out, 0, 255).astype(np.uint8)


def components(mask, min_area):
    # relie les morceaux proches (reflets, lances détachées) : dilatation avant étiquetage
    grown = ndimage.binary_dilation(mask, iterations=14)
    labels, n = ndimage.label(grown)
    boxes = []
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        area = int((labels[sl] == i).sum())
        if area < min_area:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        boxes.append((y0, y1, x0, x1))
    return boxes


def reading_order(boxes):
    if not boxes:
        return boxes
    heights = [b[1] - b[0] for b in boxes]
    band = np.median(heights) * 0.6
    boxes = sorted(boxes, key=lambda b: (b[0] + b[1]) / 2)
    rows, current = [], [boxes[0]]
    for b in boxes[1:]:
        if abs((b[0] + b[1]) / 2 - np.mean([(c[0] + c[1]) / 2 for c in current])) < band:
            current.append(b)
        else:
            rows.append(current)
            current = [b]
    rows.append(current)
    out = []
    for row in rows:
        out.extend(sorted(row, key=lambda b: b[2]))
    return out


def grid_regions(mask, cols, rows):
    """Assigne chaque composante (sans dilatation) à la case de la grille où se trouve son centre."""
    h, w = mask.shape
    labels, n = ndimage.label(mask)
    regions = [np.zeros_like(mask) for _ in range(cols * rows)]
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        comp = labels == i
        if comp.sum() < 40:
            continue
        cy, cx = ndimage.center_of_mass(comp)
        c = min(cols - 1, int(cx / w * cols))
        r = min(rows - 1, int(cy / h * rows))
        regions[r * cols + c] |= comp
    boxes, masks = [], []
    for reg in regions:
        ys, xs = np.where(reg)
        if len(ys) == 0:
            continue
        boxes.append((ys.min(), ys.max() + 1, xs.min(), xs.max() + 1))
        masks.append(reg)
    return boxes, masks


def slice_tiles(path, outdir, names, size=256, grid=(3, 2), inset=0.06):
    """Tuiles opaques : recadre chaque tuile (retire coins arrondis/bords) et la met au carré."""
    img = Image.open(path).convert("RGB")
    rgb = np.array(img)
    mask = magenta_alpha(rgb) > 0.5
    boxes, masks = grid_regions(mask, *grid)
    if len(boxes) != len(names):
        print(f"ATTENTION {path}: {len(boxes)} tuiles pour {len(names)} noms")
    for name, (y0, y1, x0, x1) in zip(names, boxes):
        w, h = x1 - x0, y1 - y0
        dx, dy = int(w * inset), int(h * inset)
        tile = img.crop((x0 + dx, y0 + dy, x1 - dx, y1 - dy)).resize((size, size), Image.LANCZOS)
        tile.save(f"{outdir}/{name}.png")
    return len(boxes)


def slice_sheet(path, outdir, names, size=256, pad=0.06, grid=None):
    img = Image.open(path).convert("RGB")
    rgb = np.array(img)
    alpha = magenta_alpha(rgb)
    mask = alpha > 0.5
    masks = None
    if grid:
        boxes, masks = grid_regions(mask, *grid)
    else:
        boxes = reading_order(components(mask, min_area=int(rgb.shape[0] * rgb.shape[1] * 0.004)))
    if len(boxes) != len(names):
        print(f"ATTENTION {path}: {len(boxes)} sprites trouvés pour {len(names)} noms")
    clean = despill(rgb, alpha)
    rgba = np.dstack([clean, (alpha * 255).astype(np.uint8)])
    full = Image.fromarray(rgba, "RGBA")
    for k, (name, (y0, y1, x0, x1)) in enumerate(zip(names, boxes)):
        if masks is not None:
            own = ndimage.binary_dilation(masks[k], iterations=3)
            a = np.array(full)[..., 3] * own
            piece = np.array(full).copy()
            piece[..., 3] = a
            crop = Image.fromarray(piece, "RGBA").crop((x0, y0, x1, y1))
        else:
            crop = full.crop((x0, y0, x1, y1))
        bb = crop.getbbox()
        if bb:
            crop = crop.crop(bb)
        w, h = crop.size
        side = max(w, h)
        inner = int(size * (1 - 2 * pad))
        scale = inner / side
        crop = crop.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(crop, ((size - crop.width) // 2, (size - crop.height) // 2), crop)
        canvas.save(f"{outdir}/{name}.png")
    return len(boxes)


if __name__ == "__main__":
    args = sys.argv[1:]
    size = 256
    if "--size" in args:
        i = args.index("--size")
        size = int(args[i + 1])
        del args[i:i + 2]
    grid = None
    if "--grid" in args:
        i = args.index("--grid")
        c, r = args[i + 1].lower().split("x")
        grid = (int(c), int(r))
        del args[i:i + 2]
    tiles = "--tiles" in args
    if tiles:
        args.remove("--tiles")
    sheet, outdir, *names = args
    import os
    os.makedirs(outdir, exist_ok=True)
    if tiles:
        print(slice_tiles(sheet, outdir, names, size, grid=grid or (3, 2)))
    else:
        print(slice_sheet(sheet, outdir, names, size, grid=grid))
