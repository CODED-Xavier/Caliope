"""Battle maps: terrain tiles, generators for common scenes, and the rules terrain adds to a fight.

A map is a list of equal-length strings, one character per 5-foot square:

    .  floor / grass           ,  shallow water or mud (difficult)   "  bushes (difficult, light cover)
    #  wall (blocks)           ~  deep water (blocks)                 D  door (open floor)
    T  tree (blocks, cover)    R  rock (blocks, cover)                B  barrel / crate / table (blocks, cover)

Generators are plain code (always work, instant, repeatable with a seed). The AI only picks which
generator fits the scene and a few features; it never draws the map itself.
"""
from __future__ import annotations

import random
from collections import deque

TILES = {
    ".": {"name": "floor", "block": False, "cover": False, "difficult": False},
    ",": {"name": "shallow water / mud", "block": False, "cover": False, "difficult": True},
    '"': {"name": "bushes", "block": False, "cover": False, "difficult": True},
    "D": {"name": "door", "block": False, "cover": False, "difficult": False},
    "#": {"name": "wall", "block": True, "cover": True, "difficult": False},
    "~": {"name": "deep water", "block": True, "cover": False, "difficult": False},
    "T": {"name": "tree", "block": True, "cover": True, "difficult": False},
    "R": {"name": "rock", "block": True, "cover": True, "difficult": False},
    "B": {"name": "barrel / crate", "block": True, "cover": True, "difficult": False},
}
TYPES = ("field", "forest", "dungeon", "cave", "tavern", "river", "street")
FEATURES = ("rocks", "trees", "bushes", "barrels", "water", "mud")
MIN_W, MIN_H, MAX_SIDE = 6, 4, 24


class MapError(ValueError):
    pass


# ------------------------------------------------------------------ helpers
def clean_tiles(rows, w: int | None = None, h: int | None = None) -> list[str]:
    """Make any list of rows a valid rectangle of known tiles (unknown characters become floor)."""
    rows = [str(r) for r in (rows or []) if isinstance(r, (str, int))]
    if not rows and not (w and h):
        raise MapError("The map is empty.")
    h = max(MIN_H, min(MAX_SIDE, h or len(rows)))
    w = max(MIN_W, min(MAX_SIDE, w or max(len(r) for r in rows)))
    out = []
    for y in range(h):
        row = rows[y] if y < len(rows) else ""
        out.append("".join(row[x] if x < len(row) and row[x] in TILES else "." for x in range(w)))
    return out


def blocked(tiles: list[str], x: int, y: int) -> bool:
    if not tiles:
        return False
    if y < 0 or y >= len(tiles) or x < 0 or x >= len(tiles[0]):
        return True
    return TILES.get(tiles[y][x], TILES["."])["block"]


def tile_at(tiles: list[str], x: int, y: int) -> str:
    if not tiles or y < 0 or y >= len(tiles) or x < 0 or x >= len(tiles[0]):
        return "."
    return tiles[y][x]


def line_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Squares between two squares (Bresenham), without the two ends."""
    cells = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err, x, y = dx + dy, x0, y0
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
        if (x, y) != (x1, y1):
            cells.append((x, y))
    return cells


def has_cover(tiles: list[str], ax: int, ay: int, tx: int, ty: int) -> bool:
    """The target has cover when a wall, tree, rock or crate lies between, or it stands in bushes."""
    if not tiles:
        return False
    if tile_at(tiles, tx, ty) == '"':
        return True
    return any(TILES.get(tile_at(tiles, x, y), TILES["."])["cover"] for x, y in line_cells(ax, ay, tx, ty))


def distance(ax: int, ay: int, bx: int, by: int) -> int:
    """Squares between two squares (diagonals count as 1, as in 5e)."""
    return max(abs(ax - bx), abs(ay - by))


def path_step(tiles: list[str], start: tuple[int, int], goal: tuple[int, int], occupied: set, max_steps: int) -> tuple[int, int]:
    """Where a creature ends after walking up to `max_steps` squares toward `goal` (shortest path around obstacles).
    Difficult terrain costs 2 squares."""
    if not tiles:
        h = w = MAX_SIDE
    else:
        h, w = len(tiles), len(tiles[0])
    best, best_d = start, distance(*start, *goal)
    seen = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        cost = seen[(x, y)]
        d = distance(x, y, *goal)
        if d < best_d or (d == best_d and cost < seen.get(best, 99)):
            best, best_d = (x, y), d
        if d <= 1:
            continue
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1)):
            if not (0 <= nx < w and 0 <= ny < h) or blocked(tiles, nx, ny) or (nx, ny) in occupied:
                continue
            step = 2 if TILES.get(tile_at(tiles, nx, ny), TILES["."])["difficult"] else 1
            nc = cost + step
            if nc <= max_steps and nc < seen.get((nx, ny), 99):
                seen[(nx, ny)] = nc
                queue.append((nx, ny))
    return best


def largest_region(grid: list[list[str]]) -> set:
    h, w = len(grid), len(grid[0])
    seen, best = set(), set()
    for y in range(h):
        for x in range(w):
            if (x, y) in seen or TILES[grid[y][x]]["block"]:
                continue
            region, queue = set(), deque([(x, y)])
            seen.add((x, y))
            while queue:
                cx, cy = queue.popleft()
                region.add((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and not TILES[grid[ny][nx]]["block"]:
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            if len(region) > len(best):
                best = region
    return best


# ------------------------------------------------------------------ generators
def _scatter(g, rng, ch, amount, keep_lanes=True):
    h, w = len(g), len(g[0])
    for _ in range(amount):
        x, y = rng.randrange(w), rng.randrange(h)
        if keep_lanes and (x <= 2 or x >= w - 3):  # leave both starting edges open
            continue
        if g[y][x] == ".":
            g[y][x] = ch


def generate(kind: str, w: int = 12, h: int = 8, seed: int | None = None, features: list[str] | None = None) -> list[str]:
    kind = kind if kind in TYPES else "field"
    w, h = max(MIN_W, min(MAX_SIDE, int(w))), max(MIN_H, min(MAX_SIDE, int(h)))
    rng = random.Random(seed)
    g = [["." for _ in range(w)] for _ in range(h)]
    area = w * h

    if kind == "field":
        _scatter(g, rng, '"', area // 12)
        _scatter(g, rng, "R", area // 28)
        _scatter(g, rng, "T", area // 30)
    elif kind == "forest":
        _scatter(g, rng, "T", area // 4)
        _scatter(g, rng, '"', area // 8)
        cx, cy = w // 2, h // 2  # a clearing in the middle
        for y in range(h):
            for x in range(w):
                if (x - cx) ** 2 / max(1, (w / 4) ** 2) + (y - cy) ** 2 / max(1, (h / 3.2) ** 2) < 1:
                    g[y][x] = "."
    elif kind == "dungeon":
        g = [["#" for _ in range(w)] for _ in range(h)]
        rooms = []
        for _ in range(40):
            rw, rh = rng.randint(3, max(3, w // 3)), rng.randint(2, max(2, h // 2))
            rx, ry = rng.randint(1, max(1, w - rw - 1)), rng.randint(1, max(1, h - rh - 1))
            if any(rx < x2 + 1 and rx + rw + 1 > x1 and ry < y2 + 1 and ry + rh + 1 > y1 for x1, y1, x2, y2 in rooms):
                continue
            rooms.append((rx, ry, rx + rw, ry + rh))
            for y in range(ry, min(h - 1, ry + rh)):
                for x in range(rx, min(w - 1, rx + rw)):
                    g[y][x] = "."
        rooms.sort()
        for (a, b) in zip(rooms, rooms[1:]):  # corridors between neighbouring rooms
            x1, y1 = (a[0] + a[2]) // 2, (a[1] + a[3]) // 2
            x2, y2 = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
            for x in range(min(x1, x2), max(x1, x2) + 1):
                g[y1][x] = "." if g[y1][x] == "#" else g[y1][x]
            for y in range(min(y1, y2), max(y1, y2) + 1):
                g[y][x2] = "." if g[y][x2] == "#" else g[y][x2]
        _scatter(g, rng, "B", max(1, area // 40), keep_lanes=False)
    elif kind == "cave":
        g = [["#" if rng.random() < 0.42 else "." for _ in range(w)] for _ in range(h)]
        for _ in range(4):
            new = [row[:] for row in g]
            for y in range(h):
                for x in range(w):
                    walls = sum(1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                                if (dx or dy) and (not (0 <= x + dx < w and 0 <= y + dy < h) or g[y + dy][x + dx] == "#"))
                    new[y][x] = "#" if walls >= 5 else "."
            g = new
        _scatter(g, rng, "R", area // 30, keep_lanes=False)
    elif kind == "tavern":
        for y in range(h):
            for x in range(w):
                if x in (0, w - 1) or y in (0, h - 1):
                    g[y][x] = "#"
        g[h - 1][w // 2] = "D"
        for y in range(2, h - 2, 2):  # tables
            for x in range(3, w - 3, 3):
                if rng.random() < 0.7:
                    g[y][x] = "B"
        for x in range(1, min(w - 1, 1 + w // 3)):  # the bar counter
            g[1][x] = "B"
    elif kind == "river":
        _scatter(g, rng, '"', area // 14)
        _scatter(g, rng, "T", area // 24)
        x = w // 2 - 1
        bridge = rng.randrange(1, h - 1)
        for y in range(h):
            x = max(3, min(w - 5, x + rng.choice((-1, 0, 0, 1))))
            for dx in range(2):
                g[y][x + dx] = "~"
            g[y][x - 1] = "," if g[y][x - 1] in '."' else g[y][x - 1]
            g[y][x + 2] = "," if g[y][x + 2] in '."' else g[y][x + 2]
            if y == bridge:
                for dx in range(-1, 3):
                    g[y][x + dx] = "."
        _scatter(g, rng, ",", area // 30)
    elif kind == "street":
        top, bottom = h // 3, h - h // 3
        for y in range(h):
            for x in range(w):
                if y < top or y >= bottom:
                    g[y][x] = "#"
        for x in range(2, w - 2, 4):  # alleys and doors between the houses
            g[top - 1][x] = "D"
            g[bottom][x + 1] = "D"
        _scatter(g, rng, "B", area // 30, keep_lanes=False)

    for f in features or []:
        ch = {"rocks": "R", "trees": "T", "bushes": '"', "barrels": "B", "water": "~", "mud": ","}.get(f)
        if ch:
            _scatter(g, rng, ch, max(2, area // 30))

    # Everyone must be able to reach everyone: cut off pockets become wall, and both edges stay open.
    region = largest_region(g)
    for y in range(h):
        for x in range(w):
            if not TILES[g[y][x]]["block"] and (x, y) not in region:
                g[y][x] = "#" if kind in ("dungeon", "cave", "tavern", "street") else "T" if kind == "forest" else "R"
    return ["".join(row) for row in g]


def open_cells(tiles: list[str]) -> list[tuple[int, int]]:
    if not tiles:
        return []
    region = largest_region([list(r) for r in tiles])
    return sorted(region)


# ------------------------------------------------------------------ your saved maps
class MapRepository:
    def __init__(self, db):
        self.db = db

    def list(self) -> list[dict]:
        return [self._row(r) for r in self.db.query("SELECT * FROM maps ORDER BY name COLLATE NOCASE")]

    def get(self, map_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM maps WHERE id = ?", (map_id,))
        if not row:
            raise MapError(f"Map {map_id} not found.")
        return self._row(row)

    def save(self, data: dict, map_id: int | None = None) -> dict:
        import json
        from .util import now, truncate

        name = truncate(str(data.get("name") or "").strip(), 60) or "My map"
        tiles = clean_tiles(data.get("tiles"))
        background = str(data.get("background") or "").strip()
        if background and not background.startswith(("http://", "https://", "/api/uploads/")):
            background = ""
        if map_id:
            self.get(map_id)
            self.db.execute("UPDATE maps SET name=?, tiles=?, background=? WHERE id=?", (name, json.dumps(tiles), background[:600], map_id))
            return self.get(map_id)
        cur = self.db.execute("INSERT INTO maps(name, tiles, background, created_at) VALUES(?,?,?,?)",
                              (name, json.dumps(tiles), background[:600], now()))
        return self.get(cur.lastrowid)

    def delete(self, map_id: int) -> None:
        self.get(map_id)
        self.db.execute("DELETE FROM maps WHERE id = ?", (map_id,))

    @staticmethod
    def _row(r) -> dict:
        import json
        tiles = json.loads(r["tiles"] or "[]")
        return {"id": r["id"], "name": r["name"], "tiles": tiles, "background": r["background"],
                "w": len(tiles[0]) if tiles else 0, "h": len(tiles)}
