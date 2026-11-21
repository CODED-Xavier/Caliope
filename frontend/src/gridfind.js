/**
 * Find the squares drawn on a map picture (like Foundry VTT and Roll20 line a map up with their grid).
 *
 * Grid lines are edges that repeat at the same distance across the whole picture. So: add up how strongly the
 * picture changes along each column (vertical lines) and each row (horizontal lines), look for the distance at
 * which those sums repeat best (autocorrelation), then slide a comb of that spacing to find where the first line is.
 * Returns {size, ox, oy, nat_w, nat_h} in the picture's own pixels, and a confidence from 0 to 1.
 */
export async function findGrid(src) {
  const img = await new Promise((ok, fail) => {
    const i = new Image();
    i.crossOrigin = "anonymous";
    i.onload = () => ok(i);
    i.onerror = () => fail(new Error("The map picture could not be read."));
    i.src = src;
  });
  const natW = img.naturalWidth, natH = img.naturalHeight;
  const k = Math.min(1, 1600 / Math.max(natW, natH));   // work on a copy at most 1600 px wide
  const W = Math.round(natW * k), H = Math.round(natH * k);
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, W, H);
  const px = ctx.getImageData(0, 0, W, H).data;
  const gray = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) gray[i] = 0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2];

  const cols = new Float32Array(W), rows = new Float32Array(H);
  for (let y = 1; y < H - 1; y++) {
    for (let x = 1; x < W - 1; x++) {
      const i = y * W + x;
      // a thin line is darker (or lighter) than both neighbours: second difference, not just any edge
      const lx = 2 * gray[i] - gray[i - 1] - gray[i + 1];
      const ly = 2 * gray[i] - gray[i - W] - gray[i + W];
      if (Math.abs(lx) > Math.abs(ly) * 1.5) cols[x] += Math.abs(lx);
      else if (Math.abs(ly) > Math.abs(lx) * 1.5) rows[y] += Math.abs(ly);
    }
  }
  const a = analyse(cols), b = analyse(rows);
  if (!a && !b) throw new Error("No grid was found on this picture. Set the square size by hand.");
  // the same spacing both ways (squares); trust the clearer direction when they disagree
  let period = a && b ? (Math.abs(a.period - b.period) / Math.max(a.period, b.period) < 0.08 ? (a.period * a.score + b.period * b.score) / (a.score + b.score) : (a.score >= b.score ? a.period : b.period)) : (a || b).period;
  const ox = a ? phase(a.s, period) : 0, oy = b ? phase(b.s, period) : 0;
  const confidence = Math.min(1, ((a?.score || 0) + (b?.score || 0)) / 2);
  return { size: +(period / k).toFixed(2), ox: +(ox / k).toFixed(2), oy: +(oy / k).toFixed(2), nat_w: natW, nat_h: natH, confidence };
}

function detrend(sig, win = 9) {
  const out = new Float32Array(sig.length);
  let sum = 0;
  const q = [];
  for (let i = 0; i < sig.length; i++) {
    q.push(sig[i]); sum += sig[i];
    if (q.length > win * 2 + 1) sum -= q.shift();
    const center = i - win;
    if (center >= 0) out[center] = Math.max(0, sig[center] - sum / q.length);
  }
  return out;
}

/** The spacing at which the signal repeats best (8 to 250 px), and how clearly (0 to 1). */
function analyse(raw) {
  const s = detrend(raw);
  const n = s.length;
  let zero = 0;
  for (let i = 0; i < n; i++) zero += s[i] * s[i];
  if (!zero) return null;
  const maxLag = Math.min(250, Math.floor(n / 3));
  const r = new Float32Array(maxLag + 2);
  for (let lag = 6; lag <= maxLag + 1; lag++) {
    let t = 0;
    for (let i = 0; i + lag < n; i++) t += s[i] * s[i + lag];
    r[lag] = t / zero;
  }
  let best = 0, bestLag = 0;
  for (let lag = 8; lag <= maxLag; lag++) {
    if (r[lag] > r[lag - 1] && r[lag] >= r[lag + 1] && r[lag] > best) { best = r[lag]; bestLag = lag; }
  }
  if (!bestLag || best < 0.05) return null;
  // the strongest repeat can be two or three squares: prefer the smallest spacing that repeats almost as well
  for (const div of [3, 2]) {
    const lag = Math.round(bestLag / div);
    if (lag >= 8) {
      let peak = 0;
      for (let d = -2; d <= 2; d++) peak = Math.max(peak, r[lag + d] || 0);
      if (peak > best * 0.7) { bestLag = lag; best = peak; break; }
    }
  }
  // sub-pixel spacing: the comb that collects the most line strength over the whole picture
  let period = bestLag, top = -1;
  for (let p = bestLag - 1; p <= bestLag + 1; p += 0.05) {
    const sc = combScore(s, p, phase(s, p));
    if (sc > top) { top = sc; period = p; }
  }
  return { period, score: Math.min(1, best * 2), s };
}

function combScore(s, period, off) {
  let t = 0;
  for (let x = off; x < s.length; x += period) {
    const i = Math.round(x);
    t += Math.max(s[i] || 0, s[i - 1] || 0, s[i + 1] || 0);
  }
  return t;
}

/** Where the first line is (0 to period). */
function phase(s, period) {
  let best = 0, bestOff = 0;
  for (let off = 0; off < period; off += 0.5) {
    const sc = combScore(s, period, off);
    if (sc > best) { best = sc; bestOff = off; }
  }
  return bestOff;
}

/** Squares across and down for a grid on a picture. */
export function gridSize(g) {
  if (!g?.size) return null;
  return { cols: Math.max(1, Math.floor((g.nat_w - g.ox) / g.size)), rows: Math.max(1, Math.floor((g.nat_h - g.oy) / g.size)) };
}
