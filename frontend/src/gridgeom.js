/**
 * Grid maths for the battle map's tools (1 square = 5 ft = 1.5 m).
 * - distance: 5e counts every square as 5 ft, diagonals too; the DMG variant alternates 5 and 10 ft on diagonals.
 * - areas: which squares a spell's shape covers (a square counts when its centre is inside).
 */
export const FT = 5;

export function distanceFt(a, b, rule = "5e") {
  const dx = Math.abs(a.x - b.x), dy = Math.abs(a.y - b.y);
  const long = Math.max(dx, dy), short = Math.min(dx, dy);
  return (rule === "variant" ? long + Math.floor(short / 2) : long) * FT;
}

const EPS = 0.01;

/** The squares an area covers: shape sphere/cube/cone/line, size in ft, origin "self" (from the caster) or "point". */
export function areaCells(area, caster, target, w, h) {
  const out = new Set();
  if (!area || !target) return out;
  const size = Math.max(5, Number(area.size) || 5) / FT; // in squares
  const put = (x, y) => { if (x >= 0 && y >= 0 && x < w && y < h) out.add(`${x},${y}`); };
  const from = area.origin === "self" ? caster : target;
  if (!from) return out;
  if (area.shape === "sphere") { // around a point (or around you): centres within the radius
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (Math.hypot(x - from.x, y - from.y) <= size + EPS) put(x, y);
    }
    return out;
  }
  const n = Math.max(1, Math.round(size));
  if (area.shape === "cube") {
    let x0, y0;
    if (area.origin === "self") { // its face on your square's edge, toward where you point
      const sx = Math.sign(target.x - caster.x), sy = Math.sign(target.y - caster.y);
      if (!sx && !sy) return out;
      x0 = sx > 0 ? caster.x + 1 : sx < 0 ? caster.x - n : caster.x - Math.floor((n - 1) / 2);
      y0 = sy > 0 ? caster.y + 1 : sy < 0 ? caster.y - n : caster.y - Math.floor((n - 1) / 2);
    } else { // a corner on the chosen square, spreading away from you
      x0 = !caster || target.x >= caster.x ? target.x : target.x - n + 1;
      y0 = !caster || target.y >= caster.y ? target.y : target.y - n + 1;
    }
    for (let y = y0; y < y0 + n; y++) for (let x = x0; x < x0 + n; x++) put(x, y);
    return out;
  }
  // cone and line start at the caster and point at the target square
  const dx = target.x - caster.x, dy = target.y - caster.y, len = Math.hypot(dx, dy);
  if (!len) return out;
  const ux = dx / len, uy = dy / len;
  const half = area.shape === "line" ? Math.max(5, Number(area.width) || 5) / FT / 2 : 0;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (x === caster.x && y === caster.y) continue;
    const vx = x - caster.x, vy = y - caster.y;
    const along = vx * ux + vy * uy;
    if (along <= 0 || along > size + EPS) continue;
    const across = Math.abs(vx * uy - vy * ux);
    if (area.shape === "line" ? across <= half + EPS : across <= along / 2 + EPS) put(x, y); // a cone is as wide as it is long
  }
  return out;
}

export const AREA_PRESETS = [
  { name: "Fireball", shape: "sphere", size: 20, origin: "point" },
  { name: "Burning Hands", shape: "cone", size: 15, origin: "self" },
  { name: "Lightning Bolt", shape: "line", size: 100, width: 5, origin: "self" },
  { name: "Thunderwave", shape: "cube", size: 15, origin: "self" },
  { name: "Shatter", shape: "sphere", size: 10, origin: "point" },
  { name: "Cone of Cold", shape: "cone", size: 60, origin: "self" },
  { name: "Spirit Guardians", shape: "sphere", size: 15, origin: "self" },
  { name: "Hypnotic Pattern", shape: "cube", size: 30, origin: "point" },
  { name: "Breath weapon (15 ft cone)", shape: "cone", size: 15, origin: "self" },
  { name: "Breath weapon (30 ft line)", shape: "line", size: 30, width: 5, origin: "self" },
];
