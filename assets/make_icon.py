"""32x32 pixel-art app icon: crossed sword and wand, violet -> orange."""
import math
import sys
from PIL import Image

N = 32
VIOLET = (138, 70, 255)
MAGENTA = (214, 72, 196)
ORANGE = (255, 140, 40)
OUT_C = (22, 10, 34, 255)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def grad(t):
    t = max(0.0, min(1.0, t))
    return lerp(VIOLET, MAGENTA, t * 2) if t < 0.5 else lerp(MAGENTA, ORANGE, (t - 0.5) * 2)


def light(c, k):
    return lerp(c, (255, 255, 255), k)


def dark(c, k):
    return lerp(c, (0, 0, 0), k)


def capsule(p0, p1, r0, r1):
    """{(x,y): s} pixels inside a tapered segment; s = side offset in -1..1 (negative = lit side)."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L  # perpendicular
    out = {}
    for y in range(N):
        for x in range(N):
            px, py = x + 0.5, y + 0.5
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (L * L)))
            cx, cy = x0 + dx * t, y0 + dy * t
            r = r0 + (r1 - r0) * t
            d = math.hypot(px - cx, py - cy)
            if d <= r:
                s = ((px - cx) * nx + (py - cy) * ny) / max(r, 0.01)
                out[(x, y)] = (s, t)
    return out


def outline(shape, canvas):
    for (x, y) in list(shape):
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + ox, y + oy)
            if q not in shape and 0 <= q[0] < N and 0 <= q[1] < N:
                canvas[q] = OUT_C


def paint(shape, canvas, colour_fn):
    for p, (s, t) in shape.items():
        canvas[p] = colour_fn(p, s, t) + (255,)


def gy(p):  # global gradient: top-left violet -> bottom-right orange
    return grad((p[1] - 4) / 22)


def shade(p, s, t, base=None):
    c = base or gy(p)
    if s < -0.35:
        return light(c, 0.35)
    if s > 0.45:
        return dark(c, 0.35)
    return c


def build():
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    px = img.load()
    # --- background: rounded tile, deep night with a soft glow
    for y in range(N):
        for x in range(N):
            cx, cy = min(max(x, 4), 27), min(max(y, 4), 27)
            if math.hypot(x - cx, y - cy) > 4.2:
                continue
            g = max(0.0, 1 - math.hypot(x - 15.5, y - 15.5) / 17)
            base = lerp((16, 9, 30), (64, 28, 92), g * g)
            edge = math.hypot(x - cx, y - cy) > 3.2 or x in (0, 31) or y in (0, 31)
            px[x, y] = (grad((x + y) / 62) if edge else base) + (255,)
    # dithered stars in the sky
    for (x, y) in ((22, 4), (27, 12), (4, 20), (12, 27), (19, 28), (3, 11)):
        px[x, y] = (200, 170, 255, 255)

    canvas = {}
    # --- wand (under): handle bottom-right, star top-left
    wand = capsule((25.5, 26.5), (9.5, 10.5), 1.6, 1.2)
    outline(wand, canvas)
    paint(wand, canvas, lambda p, s, t: shade(p, s, t, dark(gy(p), 0.15) if t > 0.25 else lerp((70, 34, 30), (110, 55, 40), 0.5)))
    # wand bands
    for p in ((20, 21), (21, 20), (21, 21), (20, 20), (22, 21), (21, 22)):
        if p in wand:
            canvas[p] = (255, 196, 90, 255)
    # star at the tip
    star = {(7, 8): 0}
    for i in range(1, 4):
        for q in ((7 + i, 8), (7 - i, 8), (7, 8 + i), (7, 8 - i)):
            star[q] = i
    for q in ((6, 7), (8, 7), (6, 9), (8, 9)):
        star[q] = 1
    outline(star, canvas)
    for q, i in star.items():
        canvas[q] = ((255, 255, 255) if i == 0 else (255, 230, 150) if i == 1 else (255, 160, 70) if i == 2 else (230, 90, 170)) + (255,)

    # --- sword (on top): hilt bottom-left, tip top-right
    blade = capsule((10.0, 22.0), (26.8, 5.2), 2.3, 0.5)
    guard = capsule((5.8, 17.8), (14.2, 26.2), 1.3, 1.3)
    grip = capsule((9.5, 22.5), (5.0, 27.0), 1.2, 1.2)
    pommel = {(x, y): (0, 0) for x in range(2, 7) for y in range(25, 30) if math.hypot(x + 0.5 - 4.0, y + 0.5 - 28.0) <= 1.9}
    hilt = {**guard, **grip, **pommel}
    outline({**blade, **hilt}, canvas)
    for p in canvas.copy():  # keep the sword's outline from eating the star
        pass
    paint(blade, canvas, lambda p, s, t: light(gy(p), 0.75) if abs(s) < 0.3 and t < 0.9 else shade(p, s, t))
    paint(grip, canvas, lambda p, s, t: shade(p, s, t, (92, 44, 120)))
    paint(guard, canvas, lambda p, s, t: shade(p, s, t, (250, 170, 50)))
    paint(pommel, canvas, lambda p, s, t: (255, 120, 60))
    canvas[(3, 27)] = (255, 220, 160, 255)  # gem glint

    for (x, y), c in canvas.items():
        px[x, y] = c
    # sparkles
    for (x, y), c in (((27, 21), (255, 200, 120)), ((16, 4), (190, 150, 255))):
        for q in ((x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            px[q] = (light(c, 0.6) if q == (x, y) else c) + (255,)
    return img


if __name__ == "__main__":
    out = sys.argv[1]
    img = build()
    img.save(f"{out}/icon-32.png")
    big = img.resize((256, 256), Image.NEAREST)
    big.save(f"{out}/icon.png")
    img.resize((512, 512), Image.NEAREST).save(f"{out}/icon-preview.png")
    frames = [img.resize((s, s), Image.NEAREST if s % 32 == 0 else Image.LANCZOS) for s in (16, 24, 48, 64, 128)]
    big.save(f"{out}/icon.ico", format="ICO", sizes=[(256, 256)], append_images=frames + [img])
    print("ok")
