"""Paints a battle map picture from terrain tiles (maps.py), in the style of the map sites (Watabou, 2-Minute Tabletop).

The tiles stay the rules (walls block, trees give cover); this only makes the picture the players see. The picture's
squares are exactly the tiles, so the grid lines up with no detection: one tile = PX pixels.
Same tiles + same seed = the same picture.
"""
from __future__ import annotations

import io
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

PX = 64  # pixels per 5-foot square

# ground colours per map type: (base, variation)
GROUND = {
    "field": ((104, 132, 66), 26), "forest": ((78, 108, 52), 22), "road": ((92, 122, 58), 24), "river": ((98, 128, 64), 24),
    "dungeon": ((132, 124, 112), 14), "cave": ((112, 98, 80), 18), "tavern": ((128, 88, 52), 14), "street": ((128, 120, 108), 14),
}
WALL = {"dungeon": (46, 42, 40), "cave": (58, 48, 40), "tavern": (70, 52, 36), "street": (60, 56, 54)}
INDOOR = ("dungeon", "cave", "tavern", "street")


def _noise(w: int, h: int, scale: int, rng: np.random.Generator) -> np.ndarray:
    """Smooth random blotches between 0 and 1."""
    small = (rng.random((h // scale + 3, w // scale + 3)) * 255).astype(np.uint8)
    big = Image.fromarray(small).resize(((w // scale + 3) * scale, (h // scale + 3) * scale), Image.BICUBIC)
    return np.asarray(big, dtype=np.float32)[:h, :w] / 255.0


def _mask(tiles: list[str], chars: str, blur: float) -> Image.Image:
    """An 'L' picture: white where the tiles are one of chars, with soft (organic) or square edges."""
    h, w = len(tiles), len(tiles[0])
    cells = np.array([[255 if ch in chars else 0 for ch in row] for row in tiles], dtype=np.uint8)
    m = Image.fromarray(cells).resize((w * PX, h * PX), Image.NEAREST)
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: 255 if v > 127 else 0)
    return m


def _ground(kind: str, w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    base, var = GROUND.get(kind, GROUND["field"])
    n = _noise(w, h, 90, rng) * 0.6 + _noise(w, h, 24, rng) * 0.3 + rng.random((h, w)).astype(np.float32) * 0.1
    img = np.empty((h, w, 3), dtype=np.float32)
    for i in range(3):
        img[..., i] = base[i] + (n - 0.5) * 2 * var * (1.0 if i != 2 else 0.6)
    if kind == "tavern":  # floor planks
        ys = np.arange(h)
        img[(ys % (PX // 2)) < 2, :, :] *= 0.72
        plank = (rng.random(h // (PX // 2) + 1) - 0.5) * 18
        img += plank[ys // (PX // 2)][:, None, None]
    elif kind in ("dungeon", "street"):  # flagstones / cobbles
        step = PX // 2 if kind == "dungeon" else PX // 4
        ys, xs = np.mgrid[0:h, 0:w]
        offset = ((ys // step) % 2) * (step // 2)
        joint = ((ys % step) < 2) | (((xs + offset) % step) < 2)
        img[joint] *= 0.7
        tone = (rng.random((h // step + 1, w // step + 2)) - 0.5) * 16
        img += tone[ys // step, (xs + offset) // step][..., None]
    return np.clip(img, 0, 255)


def _paste(canvas: Image.Image, color, mask: Image.Image, opacity: float = 1.0) -> None:
    layer = Image.new("RGBA", canvas.size, (*color, 0))
    layer.putalpha(mask.point(lambda v: int(v * opacity)))
    canvas.alpha_composite(layer)


def _shadow(canvas: Image.Image, mask: Image.Image, dx: int = 6, dy: int = 8, blur: float = 7, opacity: float = 0.45) -> None:
    sh = Image.new("L", canvas.size, 0)
    sh.paste(mask, (dx, dy))
    _paste(canvas, (0, 0, 0), sh.filter(ImageFilter.GaussianBlur(blur)), opacity)


def _shade(color, k: float):
    return tuple(max(0, min(255, int(c * k))) for c in color)


def _tree(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, rnd: random.Random, kind: str) -> None:
    green = (52 + rnd.randint(-10, 12), 92 + rnd.randint(-14, 16), 40 + rnd.randint(-8, 10)) if kind != "forest" else \
        (40 + rnd.randint(-8, 10), 80 + rnd.randint(-12, 14), 36 + rnd.randint(-8, 8))
    for i in range(7):  # the canopy: overlapping leaf clusters
        a = i * 2 * math.pi / 7 + rnd.random()
        rr = r * (0.42 + rnd.random() * 0.12)
        x, y = cx + math.cos(a) * r * 0.5, cy + math.sin(a) * r * 0.5
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=_shade(green, 0.82))
    d.ellipse([cx - r * 0.62, cy - r * 0.62, cx + r * 0.62, cy + r * 0.62], fill=green)
    hx, hy = cx - r * 0.22, cy - r * 0.26  # light from the top left
    d.ellipse([hx - r * 0.3, hy - r * 0.3, hx + r * 0.3, hy + r * 0.3], fill=_shade(green, 1.22))


def _rock(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, rnd: random.Random) -> None:
    pts = []
    for i in range(7):
        a = i * 2 * math.pi / 7 + rnd.uniform(-0.3, 0.3)
        rr = r * rnd.uniform(0.7, 1.0)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.85))
    grey = 128 + rnd.randint(-16, 16)
    d.polygon(pts, fill=(grey, grey - 4, grey - 10), outline=(60, 56, 52))
    top = [(x - (x - cx) * 0.35 - r * 0.12, y - (y - cy) * 0.35 - r * 0.15) for x, y in pts]
    d.polygon(top, fill=(grey + 28, grey + 24, grey + 18))


def _bush(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, rnd: random.Random) -> None:
    for _ in range(6):
        x, y = cx + rnd.uniform(-r * 0.55, r * 0.55), cy + rnd.uniform(-r * 0.45, r * 0.45)
        rr = r * rnd.uniform(0.28, 0.42)
        g = (70 + rnd.randint(-10, 10), 112 + rnd.randint(-12, 12), 48 + rnd.randint(-8, 8))
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=g, outline=_shade(g, 0.7))


def _prop(d: ImageDraw.ImageDraw, x0: float, y0: float, rnd: random.Random, kind: str) -> None:
    """A barrel, crate or table filling one square."""
    s = PX
    wood = (122 + rnd.randint(-12, 12), 84 + rnd.randint(-10, 10), 48)
    choice = rnd.random()
    if kind == "tavern" and choice < 0.7:  # a round table with stools
        cx, cy = x0 + s / 2, y0 + s / 2
        for a in range(4):
            sx, sy = cx + math.cos(a * math.pi / 2 + 0.6) * s * 0.42, cy + math.sin(a * math.pi / 2 + 0.6) * s * 0.42
            d.ellipse([sx - 6, sy - 6, sx + 6, sy + 6], fill=_shade(wood, 0.8), outline=(40, 28, 18))
        d.ellipse([cx - s * 0.32, cy - s * 0.32, cx + s * 0.32, cy + s * 0.32], fill=wood, outline=(40, 28, 18), width=2)
    elif choice < 0.55:  # a barrel
        cx, cy, r = x0 + s / 2, y0 + s / 2, s * 0.34
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=wood, outline=(40, 28, 18), width=2)
        d.ellipse([cx - r * 0.7, cy - r * 0.7, cx + r * 0.7, cy + r * 0.7], outline=(60, 60, 64), width=2)
        d.ellipse([cx - r * 0.25, cy - r * 0.25, cx + r * 0.25, cy + r * 0.25], fill=_shade(wood, 0.8))
    else:  # a crate
        m = s * 0.16
        d.rectangle([x0 + m, y0 + m, x0 + s - m, y0 + s - m], fill=wood, outline=(40, 28, 18), width=2)
        d.line([x0 + m, y0 + m, x0 + s - m, y0 + s - m], fill=_shade(wood, 0.7), width=3)
        d.line([x0 + s - m, y0 + m, x0 + m, y0 + s - m], fill=_shade(wood, 0.7), width=3)


def paint(tiles: list[str], kind: str = "field", seed: int = 0, grid: bool = True) -> bytes:
    """The map picture (WebP bytes) for these tiles."""
    kind = kind if kind in GROUND else "field"
    h, w = len(tiles), len(tiles[0])
    W, H = w * PX, h * PX
    nrng = np.random.default_rng(seed)
    rnd = random.Random(seed)
    canvas = Image.fromarray(_ground(kind, W, H, nrng).astype(np.uint8)).convert("RGBA")

    # roads and paths: packed dirt with soft edges
    if any(":" in r for r in tiles):
        road = _mask(tiles, ":", PX * 0.35)
        dirt = Image.fromarray(_ground("cave", W, H, nrng).astype(np.uint8))
        canvas.alpha_composite(Image.merge("RGBA", (*dirt.split(), road.filter(ImageFilter.GaussianBlur(5)))))
    # mud / shallow water, then deep water
    if any("," in r for r in tiles):
        _paste(canvas, (92, 110, 96), _mask(tiles, ",~", PX * 0.4).filter(ImageFilter.GaussianBlur(4)), 0.8)
    if any("~" in r for r in tiles):
        water = _mask(tiles, "~", PX * 0.4)
        _paste(canvas, (38, 84, 132), water.filter(ImageFilter.GaussianBlur(3)))
        deep = water.filter(ImageFilter.GaussianBlur(PX * 0.4)).point(lambda v: 255 if v > 200 else 0)
        _paste(canvas, (28, 64, 110), deep.filter(ImageFilter.GaussianBlur(6)), 0.8)
        ripple = Image.new("L", canvas.size, 0)
        rd = ImageDraw.Draw(ripple)
        for _ in range(w * h // 3):
            x, y = rnd.uniform(0, W), rnd.uniform(0, H)
            rd.arc([x - 14, y - 4, x + 14, y + 4], 200, 340, fill=255, width=2)
        _paste(canvas, (170, 200, 230), Image.fromarray(np.minimum(np.asarray(ripple), np.asarray(water))), 0.35)

    # walls (indoors) or houses (street); outdoors "#" is a cliff edge
    if any("#" in r for r in tiles):
        organic = kind == "cave" or kind not in INDOOR
        walls = _mask(tiles, "#", PX * 0.45 if organic else 0)
        if kind == "street":
            _shadow(canvas, walls, 8, 10, 8, 0.5)
            roof = np.asarray(Image.new("RGB", canvas.size, (122, 62, 48))).astype(np.float32)
            ys = np.arange(H)
            roof[(ys % 12) < 2] *= 0.75  # roof tiles
            roof *= (0.85 + 0.3 * _noise(W, H, 120, nrng))[..., None]
            canvas.alpha_composite(Image.merge("RGBA", (*Image.fromarray(np.clip(roof, 0, 255).astype(np.uint8)).split(), walls)))
            ridge = Image.new("L", canvas.size, 0)  # roof ridges along each house row
            rdraw = ImageDraw.Draw(ridge)
            for y in range(h):
                if tiles[y].count("#") > w // 2:
                    rdraw.line([0, y * PX + PX // 2, W, y * PX + PX // 2], fill=255, width=1)
            _paste(canvas, (70, 30, 24), Image.fromarray(np.minimum(np.asarray(ridge), np.asarray(walls))), 0.4)
        else:
            color = WALL.get(kind, (70, 66, 60))
            _shadow(canvas, walls, 0, 0, PX * 0.22, 0.75)  # the walls darken the floor next to them
            _paste(canvas, color, walls)
            edge = walls.filter(ImageFilter.MaxFilter(9))
            rim = Image.fromarray(np.clip(np.asarray(edge, dtype=np.int16) - np.asarray(walls, dtype=np.int16), 0, 255).astype(np.uint8))
            _paste(canvas, (20, 18, 16), rim, 0.9)  # a dark outline, like the map sites draw
            hatch = Image.new("L", canvas.size, 0)  # cross-hatching inside the rock
            hd = ImageDraw.Draw(hatch)
            for k in range(-H, W, 14):
                hd.line([k, 0, k + H, H], fill=255, width=1)
            inner = walls.filter(ImageFilter.MinFilter(9))
            _paste(canvas, _shade(color, 1.5), Image.fromarray(np.minimum(np.asarray(hatch), np.asarray(inner))), 0.35)

    # things standing on the ground, with shadows: bushes, rocks, props, trees (trees last: canopies overlap)
    layers = {"\"": [], "R": [], "B": [], "D": [], "T": []}
    for y, row in enumerate(tiles):
        for x, ch in enumerate(row):
            if ch in layers:
                layers[ch].append((x, y))
    for ch in ("\"", "R", "B", "D", "T"):
        if not layers[ch]:
            continue
        obj = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(obj)
        for x, y in layers[ch]:
            cx, cy = x * PX + PX / 2 + rnd.uniform(-5, 5), y * PX + PX / 2 + rnd.uniform(-5, 5)
            if ch == "T":
                _tree(d, cx, cy, PX * rnd.uniform(0.72, 0.95), rnd, kind)
            elif ch == "R":
                _rock(d, cx, cy, PX * rnd.uniform(0.32, 0.44), rnd)
            elif ch == "\"":
                _bush(d, cx, cy, PX * 0.48, rnd)
            elif ch == "B":
                _prop(d, x * PX, y * PX, rnd, kind)
            elif ch == "D":
                horizontal = 0 < x < w - 1 and tiles[y][x - 1] == "#" and tiles[y][x + 1] == "#"
                if horizontal:
                    d.rectangle([x * PX, y * PX + PX * 0.3, (x + 1) * PX, y * PX + PX * 0.7], fill=(120, 80, 44), outline=(40, 26, 14), width=2)
                else:
                    d.rectangle([x * PX + PX * 0.3, y * PX, x * PX + PX * 0.7, (y + 1) * PX], fill=(120, 80, 44), outline=(40, 26, 14), width=2)
        alpha = obj.split()[3]
        if ch != "D":
            _shadow(canvas, alpha, 7 if ch == "T" else 4, 9 if ch == "T" else 5, 6 if ch == "T" else 3, 0.5 if ch == "T" else 0.4)
        canvas.alpha_composite(obj)

    # soft light: a little darker at the edges
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = 1 - 0.28 * (((xx / W - 0.5) * 2) ** 2 + ((yy / H - 0.5) * 2) ** 2) / 2
    arr = np.asarray(canvas.convert("RGB"), dtype=np.float32) * vig[..., None]
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    if grid:
        gd = ImageDraw.Draw(out, "RGBA")
        for x in range(1, w):
            gd.line([x * PX, 0, x * PX, H], fill=(0, 0, 0, 55), width=1)
        for y in range(1, h):
            gd.line([0, y * PX, W, y * PX], fill=(0, 0, 0, 55), width=1)
    buf = io.BytesIO()
    out.save(buf, "WEBP", quality=84, method=4)
    return buf.getvalue()


def geometry(tiles: list[str]) -> dict:
    """The picture's squares for the battle grid (no detection needed: one tile is PX pixels)."""
    return {"size": float(PX), "ox": 0.0, "oy": 0.0, "nat_w": float(len(tiles[0]) * PX), "nat_h": float(len(tiles) * PX)}
