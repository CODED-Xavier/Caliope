// Helpers for imported cards: big portraits inside replies, the INFO status block, characters met.

/** Portraits are served by the backend, which keeps a copy on this PC after the first download. */
export const portraitSrc = (url) => (url ? `/api/portrait?url=${encodeURIComponent(url)}` : "");

const INFO_LINE = /^[ \t]*(?:\*\*|\[)?INFO(?:\*\*|\])?[ \t]*$/m;

/** Hide a status block while a reply is still being written (the backend removes it when the reply is saved). */
export function hideStatus(text) {
  const m = String(text || "").match(INFO_LINE);
  return m ? text.slice(0, m.index).trimEnd() : text;
}

const TAG = /\[\[\s*show\s*:\s*([^|\]\n]+?)\s*(?:\|\s*([^\]\n]*?)\s*)?\]\]|!\[([^\]\n]*)\]\(([^)\s]*)\)/gi;

const MOODS = {
  1: ["standard", "neutral", "default", "normal", "calm"],
  2: ["happy", "smile", "smiling", "joy", "cheerful"],
  3: ["sad", "upset", "crying", "worried"],
  4: ["angry", "annoyed", "mad"],
  5: ["disgusted", "very angry", "furious"],
  6: ["blushing", "blush", "embarrassed", "shy", "flustered"],
};

const norm = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, " ");

function findNpc(npcs, name) {
  const t = norm(name);
  if (!t) return null;
  const exact = npcs.find((n) => norm(n.name) === t);
  if (exact) return exact;
  const part = npcs.filter((n) => norm(n.name).split(" ").includes(t) || norm(n.name).startsWith(`${t} `));
  if (part.length === 1) return part[0];
  const first = t.split(" ")[0];
  const byFirst = npcs.filter((n) => norm(n.name).split(" ")[0] === first);
  return byFirst.length === 1 ? byFirst[0] : null;
}

function pickMood(portraits, mood) {
  const moods = portraits?.moods || [];
  const want = norm(mood);
  if (!moods.length) return portraits?.default ? { label: "Standard", url: portraits.default } : null;
  const byLabel = moods.find((m) => norm(m.label) === want || norm(m.label).split(/[/,]/).includes(want));
  if (byLabel) return byLabel;
  let n = /^\d$/.test(want) ? Number(want) : 1;
  for (const [k, words] of Object.entries(MOODS)) if (words.some((w) => want === w || (w.length > 3 && want.includes(w)))) n = Number(k);
  return moods.find((m) => m.n === n) || moods[0];
}

/**
 * Split a reply into pieces: text and portraits. `known` is the message's saved {"Name|Mood": url} map;
 * when it has no entry (while streaming, or after an edit) the picture is looked up in the character list.
 * At most two different characters get a picture, like the backend does.
 */
export function splitStory(text, npcs = [], known = {}) {
  const parts = [];
  const people = new Set();
  let last = 0;
  let m;
  TAG.lastIndex = 0;
  while ((m = TAG.exec(text))) {
    if (m.index > last) parts.push({ type: "text", text: text.slice(last, m.index) });
    last = TAG.lastIndex;
    let name = m[1];
    let mood = m[2] || "";
    if (name === undefined) { // markdown image: "Name - Mood"
      const bits = (m[3] || "").split(/\s+[-–—:|]\s+|\s*[–—|]\s*/);
      name = bits[0] || "";
      mood = bits[1] || "";
    }
    const npc = findNpc(npcs, name);
    const canonical = npc ? npc.name : name.trim();
    if (!people.has(canonical) && people.size >= 2) continue;
    const savedKey = Object.keys(known).find((k) => norm(k.split("|")[0]) === norm(canonical) && norm(k.split("|")[1]) === norm(mood));
    const picked = savedKey ? { label: savedKey.split("|")[1], url: known[savedKey] } : npc ? pickMood(npc.portraits, mood) : null;
    if (!picked?.url) continue;
    people.add(canonical);
    parts.push({ type: "portrait", name: canonical, mood: picked.label, url: picked.url });
  }
  if (last < text.length) parts.push({ type: "text", text: text.slice(last) });
  return parts;
}

/** The newest status block written by the AI (shown in the Status tab). */
export function latestStatus(messages = []) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const s = messages[i].meta?.status;
    if (s) return { text: s, messageId: messages[i].id };
  }
  return null;
}
