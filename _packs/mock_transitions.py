"""Mockup : transitions douces entre terrains et côtes arrondies, avec les vrais sprites du jeu."""
import numpy as np
from PIL import Image
from scipy import ndimage

R = r"C:\V\civ\resources\terrain"
OUT = r"C:\V\civ\_packs\mock"
S = 64          # pixels par case dans le mockup
rng = np.random.default_rng(11)

LEGEND = {"o": "ocean", "g": "grassland", "p": "plains", "d": "desert", "h": "hills", "m": "mountains",
          "f": "forest", "j": "jungle", "s": "swamp", "a": "arctic", "t": "tundra"}
GRID = """
ooooooooooooooooooo
oooooaaaaooooooooo
ooooaaaaaaooommooo
oooottaaattoommmoo
ooottttggggooommhoo
oootttgggpphhhhhho
ooogggggppphhhhgoo
ooogggffpppddhhgggo
oooggfffppdddgggggo
ooojjffffgdddgggjjo
oooojjjggggggssjjjo
ooooojjjggoooojjjoo
ooooooooooooooooooo
""".strip().split("\n")
GRID = [r.ljust(19, "o")[:19] for r in GRID]
terr = np.array([[LEGEND[c] for c in row] for row in GRID])
H, W = terr.shape
names = sorted(set(terr.flatten()))
LAND = [n for n in names if n != "ocean"]

SPRITES = {n: Image.open(f"{R}\\{n}.png").convert("RGB").resize((S, S), Image.LANCZOS) for n in names}
arr = {n: np.asarray(SPRITES[n]).astype(np.float32) for n in names}
base = {n: np.median(arr[n].reshape(-1, 3), axis=0) for n in names}
# motif = ce qui s'écarte de la couleur de fond
motif_a = {}
for n in names:
    d = np.abs(arr[n] - base[n]).sum(axis=2)
    m = np.clip((d - 18) / 40.0, 0, 1)
    # fondu vers les bords de la case : les motifs larges (collines, dunes) ne coupent plus net
    yy, xx = np.mgrid[0:S, 0:S]
    edge = np.minimum(np.minimum(xx, S - 1 - xx), np.minimum(yy, S - 1 - yy)) / (S * 0.16)
    motif_a[n] = m * np.clip(edge, 0, 1) ** 1.2


def tile_index():
    return np.kron(np.arange(H * W).reshape(H, W), np.ones((S, S), dtype=int))


def noise(scale, amp, seed):
    r = np.random.default_rng(seed)
    f = ndimage.gaussian_filter(r.standard_normal((H * S, W * S)), scale)
    return f / f.std() * amp


def warp_field(strength=0.10):
    return noise(S * 0.45, strength * S, 1), noise(S * 0.45, strength * S, 2)


def sample_nn(mask_tiles, wx, wy):
    """Indicateur par case, ré-échantillonné au pixel avec déformation organique."""
    ys, xs = np.mgrid[0:H * S, 0:W * S]
    xs = np.clip(xs + wx, 0, W * S - 1).astype(int)
    ys = np.clip(ys + wy, 0, H * S - 1).astype(int)
    big = np.kron(mask_tiles.astype(np.float32), np.ones((S, S), dtype=np.float32))
    return big[ys, xs]


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def flat_tiles():
    img = np.zeros((H * S, W * S, 3), np.float32)
    for y in range(H):
        for x in range(W):
            img[y * S:(y + 1) * S, x * S:(x + 1) * S] = arr[terr[y, x]]
    return img


def cell_terrain_px():
    ids = {n: i for i, n in enumerate(names)}
    t = np.vectorize(ids.get)(terr)
    return np.kron(t, np.ones((S, S), dtype=int)), ids


def blended(include_ocean, sigma=0.12, warp=0.10, sharp=True):
    wx, wy = warp_field(warp)
    kinds = names if include_ocean else LAND
    weights = {}
    for n in kinds:
        ind = sample_nn(terr == n, wx, wy)
        weights[n] = ndimage.gaussian_filter(ind, S * sigma)
    tot = sum(weights.values()) + 1e-6
    for n in kinds:
        weights[n] = weights[n] / tot
    if sharp:
        # frontière plus nette : on durcit les poids autour de 0.5 puis on renormalise
        for n in kinds:
            weights[n] = smoothstep(0.30, 0.70, weights[n])
        tot = sum(weights.values()) + 1e-6
        for n in kinds:
            weights[n] = weights[n] / tot
    img = np.zeros((H * S, W * S, 3), np.float32)
    for n in kinds:
        img += weights[n][..., None] * base[n]
    # motifs : on garde ceux de la case, atténués près des frontières
    cell, ids = cell_terrain_px()
    for n in names:
        if not include_ocean and n == "ocean":
            continue
        own = (cell == ids[n])
        w = smoothstep(0.30, 0.62, weights.get(n, np.zeros_like(img[..., 0])))
        tile_motif = np.zeros((H * S, W * S), np.float32)
        tile_rgb = np.zeros_like(img)
        for y in range(H):
            for x in range(W):
                if terr[y, x] == n:
                    sl = (slice(y * S, (y + 1) * S), slice(x * S, (x + 1) * S))
                    tile_motif[sl] = motif_a[n]
                    tile_rgb[sl] = arr[n]
        a = (tile_motif * w * own)[..., None]
        img = img * (1 - a) + tile_rgb * a
    return img, weights


def coast(land_img):
    """Côte arrondie : masque terre lissé (seuillage d'un flou), eaux peu profondes, liseré."""
    wx, wy = warp_field(0.07)
    land = sample_nn(terr != "ocean", wx, wy)
    soft = ndimage.gaussian_filter(land, S * 0.30)
    mask = soft > 0.5
    # eau : océan de base avec ses vagues
    sea = np.zeros((H * S, W * S, 3), np.float32)
    for y in range(H):
        for x in range(W):
            sea[y * S:(y + 1) * S, x * S:(x + 1) * S] = arr["ocean"]
    # distance à la terre (en cases) pour le dégradé d'eau peu profonde
    dist = ndimage.distance_transform_edt(~mask) / S
    shallow = np.clip(1 - dist / 0.55, 0, 1) ** 1.6
    shallow_col = np.array([108, 190, 226], np.float32)
    sea = sea * (1 - 0.65 * shallow[..., None]) + shallow_col * (0.65 * shallow[..., None])
    # liseré de rivage
    inner = ndimage.distance_transform_edt(mask) / S
    edge = np.clip(1 - np.abs(dist - 0.0) / 0.035, 0, 1)
    line_out = np.clip(1 - dist / 0.045, 0, 1) * (~mask)
    line_in = np.clip(1 - inner / 0.05, 0, 1) * mask
    m = ndimage.gaussian_filter(mask.astype(np.float32), 1.2)[..., None]
    img = land_img * m + sea * (1 - m)
    foam = np.clip(line_out * 0.9, 0, 1)[..., None]
    img = img * (1 - foam * 0.7) + np.array([240, 250, 255], np.float32) * foam * 0.7
    dark = np.clip(line_in * 0.35, 0, 1)[..., None]
    img = img * (1 - dark) + np.array([60, 70, 40], np.float32) * dark
    return img


def overlays(img):
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    spots = {(6, 5): "gold", (8, 6): "coal", (9, 10): "gems", (3, 13): "gold", (4, 6): "horse"}
    for (y, x), name in spots.items():
        if terr[y, x] == "ocean":
            continue
        ic = Image.open(f"{R}\\{name}.png").convert("RGBA")
        w = int(S * 0.64)
        ic = ic.resize((w, w), Image.LANCZOS)
        a = ic.getchannel("A").point(lambda v: int(v * 0.82))
        ic.putalpha(a)
        pil.alpha_composite(ic, (x * S + (S - w) // 2, y * S + (S - w) // 2))
    return pil.convert("RGB")


import os
os.makedirs(OUT, exist_ok=True)
a = overlays(flat_tiles())
a.save(f"{OUT}/A_current_b.png")
b_img, _ = blended(include_ocean=True)
b = overlays(b_img)
b.save(f"{OUT}/B2_smooth.png")
c_land, _ = blended(include_ocean=False)
c = overlays(coast(c_land))
c.save(f"{OUT}/C2_smooth_coast.png")
print(a.size)
