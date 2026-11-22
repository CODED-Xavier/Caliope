export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const abilityMod = (score) => Math.floor((Number(score || 10) - 10) / 2);
export const fmtMod = (n) => (n >= 0 ? `+${n}` : `${n}`);

export function relationshipLabel(v) {
  if (v <= -80) return "mortal enemy";
  if (v <= -50) return "hostile";
  if (v <= -20) return "distrustful";
  if (v < 20) return "neutral";
  if (v < 50) return "friendly";
  if (v < 80) return "close";
  return "deeply bonded";
}

// What each level means for how a character treats the player (same table as backend/app/reputation.py).
export function relationshipEffect(v) {
  if (v <= -80) return "Wants you gone; works against you, never helps, never tells the truth.";
  if (v <= -50) return "Refuses help and favours, insults or threatens, shares nothing, may sabotage you.";
  if (v <= -20) return "Guarded and curt; helps only for a clear price or benefit, shares only what anyone knows.";
  if (v < 20) return "Polite and ordinary; normal prices and small help, keeps personal matters private.";
  if (v < 50) return "Warm; small favours, rumours and advice, a little discount, hears you out.";
  if (v < 80) return "Trusts you: shares personal worries and secrets when asked, takes risks for you.";
  return "Fiercely loyal: would sacrifice for you, reveals their deepest secrets, defends you anywhere.";
}

export function relationshipColor(v) {
  if (v <= -20) return "var(--bad)";
  if (v >= 20) return "var(--good)";
  return "var(--muted)";
}

export const MODE_LABELS = {
  gm_world: "Aedo · open world",
  gm_cast: "Aedo · preset cast",
  character: "Character card",
};

export function timeAgo(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export const KIND_LABELS = { roleplay: "Roleplay", adventure: "Adventure" };
export const SYSTEM_LABELS = { "dnd5e-2014": "D&D 5e", "dnd5e-2024": "D&D 5e (2024)" };
export const KIND_INFO = {
  roleplay: { icon: "🎭", title: "Roleplay", text: "Characters, relationships and conversation. Simple and fast." },
  adventure: { icon: "⚔️", title: "Adventure", text: "Rules, items, quests and map. More to track, slower." },
};
