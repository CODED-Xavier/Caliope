/**
 * Interface language: English (the source text of every screen) or Português (Brasil).
 *
 * The screens are written in English. When PT-BR is on, a watcher swaps every English text on the page (and
 * placeholders, tooltips) for its translation as it appears, and puts the English back when you switch back.
 * Stories, chat messages and anything you type are never touched.
 * The translations live in pt-BR.json: "exact" texts, and "patterns" where {0}, {1}… stand for names and numbers.
 */
import PT from "./pt-BR.json";

export const UI_LANGUAGES = [
  { id: "en", label: "English" },
  { id: "pt-BR", label: "Português (Brasil)" },
];

const SKIP = ".bubble, .no-tr, .pre, .recap-text, textarea, input, code, pre, script, style, [contenteditable]";
const ATTRS = ["placeholder", "title", "aria-label", "alt"];

let lang = "en";
let observer = null;
const textOrig = new WeakMap();   // text node -> { en, shown }
const attrOrig = new WeakMap();   // element -> { attr: { en, shown } }

const exact = new Map(Object.entries(PT.exact || {}));
// The most specific first: "Not enough {0}: you have {1}." must win over "Not enough {0}".
const patterns = [...(PT.patterns || [])].sort((a, b) => b[0].replace(/\{\d\}/g, "").length - a[0].replace(/\{\d\}/g, "").length).map(([en, pt]) => {
  const parts = en.split(/(\{\d\})/);
  const order = [];
  const src = parts.map((p) => {
    const m = p.match(/^\{(\d)\}$/);
    if (m) { order.push(Number(m[1])); return "(.+?)"; }
    return p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("");
  return { re: new RegExp(`^${src}$`, "s"), order, pt };
});

/** The PT-BR text for an English text, or null when there is none. */
function lookup(text) {
  if (exact.has(text)) return exact.get(text);
  for (const p of patterns) {
    const m = text.match(p.re);
    if (m) {
      const vals = {};
      p.order.forEach((n, i) => { vals[n] = m[i + 1]; });
      return p.pt.replace(/\{(\d)\}/g, (_, n) => (vals[n] !== undefined ? (lookup(vals[n]) ?? vals[n]) : ""));
    }
  }
  return null;
}

/** Translate one piece of English (keeps the spaces around it). */
export function tr(text) {
  if (lang === "en" || !text) return text;
  const s = String(text);
  const core = s.replace(/\s+/g, " ").trim();
  if (!core || !/[A-Za-z]/.test(core)) return s;
  let out = lookup(core);
  if (out == null) {
    // "⚙ Settings", "Name:", "Saving…": try without leading symbols and trailing punctuation
    const m = core.match(/^([^A-Za-z"'(]*)(.*?)([\s:.…!?)]*)$/s);
    if (m && (m[1] || m[3])) {
      const mid = lookup(m[2]);
      if (mid != null) out = m[1] + mid + m[3];
    }
  }
  if (out == null) return s;
  const lead = s.match(/^\s*/)[0];
  const trail = s.match(/\s*$/)[0];
  return lead + out + trail;
}

const skipped = (el) => !el || el.closest(SKIP);

function doText(node) {
  const el = node.parentElement;
  if (skipped(el)) return;
  const rec = textOrig.get(node);
  const now = node.nodeValue;
  if (rec && now === rec.shown) return;               // already ours
  const en = now;                                      // new English text from the app
  const shown = tr(en);
  textOrig.set(node, { en, shown });
  if (shown !== now) node.nodeValue = shown;
}

function doAttrs(el) {
  if (el.closest(".bubble, .no-tr")) return;
  let recs = attrOrig.get(el);
  for (const a of ATTRS) {
    const now = el.getAttribute(a);
    if (now == null) continue;
    const rec = recs?.[a];
    if (rec && now === rec.shown) continue;
    const shown = tr(now);
    if (!recs) { recs = {}; attrOrig.set(el, recs); }
    recs[a] = { en: now, shown };
    if (shown !== now) el.setAttribute(a, shown);
  }
}

function walk(root) {
  if (root.nodeType === 3) { doText(root); return; }
  if (root.nodeType !== 1) return;
  if (root.matches?.(SKIP) && root.tagName !== "INPUT" && root.tagName !== "TEXTAREA") return;
  doAttrs(root);
  const tw = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.nodeType === 1 && n.matches(".bubble, .no-tr, .pre, .recap-text, code, pre, script, style")
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    if (n.nodeType === 3) doText(n); else doAttrs(n);
  }
}

function restore(root) {
  const tw = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  for (let n = tw.currentNode; n; n = tw.nextNode()) {
    if (n.nodeType === 3) {
      const rec = textOrig.get(n);
      if (rec && n.nodeValue === rec.shown) n.nodeValue = rec.en;
      textOrig.delete(n);
    } else {
      const recs = attrOrig.get(n);
      if (recs) for (const [a, rec] of Object.entries(recs)) if (n.getAttribute(a) === rec.shown) n.setAttribute(a, rec.en);
      attrOrig.delete(n);
    }
  }
}

function start() {
  if (observer) return;
  walk(document.body);
  observer = new MutationObserver((list) => {
    for (const m of list) {
      if (m.type === "characterData") doText(m.target);
      else if (m.type === "attributes") doAttrs(m.target);
      else m.addedNodes.forEach(walk);
    }
  });
  observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}

function stop() {
  observer?.disconnect();
  observer = null;
  restore(document.body);
}

export function getUiLanguage() { return lang; }

/** Switch the interface language ("en" or "pt-BR"). Remembered on this PC so the next start opens in it at once. */
export function setUiLanguage(next) {
  next = next === "pt-BR" ? "pt-BR" : "en";
  try { localStorage.setItem("caliope.ui_language", next); } catch { /* private window */ }
  document.documentElement.lang = next;
  if (next === lang) { if (next !== "en") start(); return; }
  lang = next;
  if (lang === "en") stop(); else start();
}

/** Called once before the first render: uses the language remembered on this PC. */
export function initUiLanguage() {
  let saved = "en";
  try { saved = localStorage.getItem("caliope.ui_language") || "en"; } catch { /* ignore */ }
  setUiLanguage(saved);
}
