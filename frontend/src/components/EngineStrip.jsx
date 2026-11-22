import React from "react";

const hpColor = (r) => (r < 0.3 ? "var(--bad)" : r < 0.6 ? "var(--warn)" : "var(--good)");
const SKIP = /^(relationships?|inventory|quests?|location|time|conditions?|spell slots|inspiration|hit dice)$/i;

/** "Tier: Expert | Body: C+ [40/100]" lines (the card's tracker, kept by the app) as chips. */
export function trackerChips(statusText) {
  const chips = [];
  for (const line of String(statusText || "").split("\n")) {
    for (const part of line.split("|")) {
      let m = part.match(/^\s*-?\s*([^:]{1,24}):\s*(.+?)\s*$/);
      if (m) { // "Combat Log: Battles Today: 1" -> the inner pair; "Attributes (1-10): Magic 3" -> Magic 3
        const inner = m[2].match(/^([A-Za-z][\w ]{0,20}):\s*(.+)$/) || (/[()]/.test(m[1]) && m[2].match(/^([A-Za-z][\w ]{0,16})\s+(\S+)$/));
        if (inner) m = [m[0], inner[1], inner[2]];
      } else { // "Martial 7", "Day 3/100": a short name and its value without a colon
        const bare = part.match(/^\s*-?\s*([A-Za-z][A-Za-z ]{0,16}?)\s+(\d[\w+\-/.]*)\s*$/);
        if (bare) m = [part, bare[1], bare[2]];
      }
      if (!m || SKIP.test(m[1].trim())) continue;
      const value = m[2].trim();
      if (!value || value === "?" || value === "-" || value.length > 40) continue;
      const bar = value.match(/\[(\d+)\s*\/\s*(\d+)\]/);
      chips.push({ label: m[1].trim(), value: value.replace(/\s*\[\d+\s*\/\s*\d+\]/, ""), bar: bar ? Number(bar[1]) / Math.max(1, Number(bar[2])) : null });
    }
  }
  return chips.slice(0, 10);
}

/**
 * Under the top bar. Adventure cards: the party (you and your companions) with HP bars.
 * Role-play cards: the card's own tracker as chips (Lumencia: Tier, Body C+ with its EXP bar; Black Sheep: Day, Rank, Credits).
 */
export default function EngineStrip({ game }) {
  const st = game.state || {};
  const adventure = game.features?.kind === "adventure";
  if (adventure) {
    const p = st.player || {};
    const hp = p.hp || { current: 0, max: 1 };
    const party = st.party_mode === "companions" ? Object.entries(st.party || {}) : [];
    const ratio = hp.max ? hp.current / hp.max : 0;
    return (
      <div className="engine-strip" aria-label="Party">
        <div className="party-card me">
          <div className="party-avatar">{(p.name || "?").slice(0, 1).toUpperCase()}</div>
          <div className="party-info">
            <div className="party-line"><strong>{p.name || "You"}</strong><span className="muted">{`${[p.class, p.level ? `Lv ${p.level}` : ""].filter(Boolean).join(" ")} · AC ${p.ac ?? "?"}`}</span></div>
            <div className="hp-track"><div className="hp-fill" style={{ width: `${Math.max(0, Math.min(1, ratio)) * 100}%`, background: hpColor(ratio) }} /></div>
            <div className="muted tiny">{`${hp.current} / ${hp.max} HP`}</div>
          </div>
        </div>
        {party.map(([name, v]) => {
          const r = v.max_hp ? v.hp / v.max_hp : 0;
          return (
            <div className="party-card" key={name}>
              <div className="party-avatar small">{name.slice(0, 1).toUpperCase()}</div>
              <div className="party-info">
                <div className="party-line"><strong>{name.split(" ")[0]}</strong><span className="muted tiny">{`${v.hp}/${v.max_hp}`}</span></div>
                <div className="hp-track thin"><div className="hp-fill" style={{ width: `${Math.max(0, Math.min(1, r)) * 100}%`, background: hpColor(r) }} /></div>
              </div>
            </div>
          );
        })}
      </div>
    );
  }
  const chips = trackerChips(game.status_now);
  if (!chips.length) return null;
  return (
    <div className="engine-strip" aria-label="Tracker">
      {chips.map((c) => (
        <div className="tracker-chip" key={c.label}>
          <span className="tracker-label">{c.label}</span>
          <span className="tracker-value">{c.value}</span>
          {c.bar !== null && <span className="tracker-bar"><span style={{ width: `${Math.round(c.bar * 100)}%` }} /></span>}
        </div>
      ))}
    </div>
  );
}
