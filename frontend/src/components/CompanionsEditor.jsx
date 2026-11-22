import React, { useState } from "react";
import { api } from "../api.js";
import { ask } from "../dialogs.jsx";
import HelpTip from "./HelpTip.jsx";
import MoodEditor from "./MoodEditor.jsx";

const ROLES = [["fighter", "⚔ Fighter"], ["archer", "🏹 Archer"], ["healer", "💚 Healer"], ["rogue", "🗡 Rogue"]];
// 5e level 1 numbers by role (same as backend/app/party.py)
const DEFAULTS = {
  fighter: { hp: 12, ac: 16, attack_bonus: 5, damage: "1d8+3", range: 1, speed: 6 },
  archer: { hp: 10, ac: 14, attack_bonus: 5, damage: "1d8+3", range: 16, speed: 6 },
  healer: { hp: 10, ac: 16, attack_bonus: 4, damage: "1d6+2", range: 1, speed: 5, heal: "1d8+3", heals: 2 },
  rogue: { hp: 9, ac: 14, attack_bonus: 5, damage: "1d6+3", range: 1, speed: 6 },
};
const MAX = 3;

/**
 * Up to 3 companions who travel with the player in "Play with companions" games: the Aedo voices them, Calíope plays
 * them in fights. They are card characters marked `companion`, with a small fight sheet.
 */
export default function CompanionsEditor({ cardId, npcs, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const team = npcs.map((n, i) => [n, i]).filter(([n]) => n.companion);
  const setAt = (i, patch) => onChange(npcs.map((n, j) => (j === i ? { ...n, ...patch } : n)));
  const setSheet = (i, k, v) => setAt(i, { sheet: { ...(npcs[i].sheet || {}), [k]: v } });
  const add = () => onChange([...npcs, { name: "", companion: true, personality: "", speech_style: "", description: "", relationship: 10,
    appearance: {}, sheet: { class: "", role: "fighter", ...DEFAULTS.fighter } }]);
  const write = async () => {
    if (team.length && !await ask.confirm("Replace the companions with 3 new ones written by the AI?")) return;
    setBusy(true); setError("");
    try {
      const r = await api.draftCompanions(cardId);
      onChange([...npcs.filter((n) => !n.companion), ...r.companions.map((c) => ({ relationship: 10, appearance: {}, ...c }))]);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const num = (v) => parseInt(v, 10) || 0;

  return (
    <details className="companions" open={team.length > 0}>
      <summary className="section-title">👥 Companions <span className="muted tiny">({team.length}/{MAX})</span> <HelpTip id="companions" /></summary>
      <div className="muted small">{"They travel with the player in games started with “Play with companions”: the Aedo voices them, and Calíope plays them in fights. In “Play solo” they stay home, and an adventure's fights are scaled to one hero."}</div>
      {team.map(([n, i]) => {
        const sh = { ...DEFAULTS[n.sheet?.role || "fighter"], ...(n.sheet || {}) };
        return (
          <div className="card companion-card" key={i}>
            <div className="row gap center">
              <input className="field grow" placeholder="Name" value={n.name} onChange={(e) => setAt(i, { name: e.target.value })} />
              <input className="field" style={{ width: 120 }} placeholder="Class (Cleric…)" value={sh.class || ""} onChange={(e) => setSheet(i, "class", e.target.value)} />
              <select className="field" value={sh.role} onChange={(e) => setAt(i, { sheet: { ...sh, role: e.target.value, ...DEFAULTS[e.target.value], class: sh.class } })}>
                {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              <button className="icon-btn" title="Remove" onClick={() => onChange(npcs.filter((_, j) => j !== i))}>✕</button>
            </div>
            <div className="companion-stats">
              <label>HP <input className="field num" value={sh.hp} onChange={(e) => setSheet(i, "hp", num(e.target.value))} /></label>
              <label>AC <input className="field num" value={sh.ac} onChange={(e) => setSheet(i, "ac", num(e.target.value))} /></label>
              <label>Attack <input className="field num" value={sh.attack_bonus} onChange={(e) => setSheet(i, "attack_bonus", num(e.target.value))} /></label>
              <label>Damage <input className="field" style={{ width: 70 }} value={sh.damage} onChange={(e) => setSheet(i, "damage", e.target.value)} /></label>
              <label>Range <input className="field num" value={sh.range} onChange={(e) => setSheet(i, "range", num(e.target.value))} title="Squares (1 = melee)" /></label>
              <label>Speed <input className="field num" value={sh.speed} onChange={(e) => setSheet(i, "speed", num(e.target.value))} title="Squares per turn (6 = 30 ft)" /></label>
              {sh.role === "healer" && <>
                <label>Heal <input className="field" style={{ width: 70 }} value={sh.heal || "1d8+3"} onChange={(e) => setSheet(i, "heal", e.target.value)} /></label>
                <label>Heals per fight <input className="field num" value={sh.heals ?? 2} onChange={(e) => setSheet(i, "heals", num(e.target.value))} /></label>
              </>}
            </div>
            <textarea className="field" rows={2} placeholder="Who they are (history, looks)" value={n.description || ""} onChange={(e) => setAt(i, { description: e.target.value })} />
            <textarea className="field" rows={2} placeholder="Personality" value={n.personality || ""} onChange={(e) => setAt(i, { personality: e.target.value })} />
            <input className="field" placeholder="Speech style (how they talk)" value={n.speech_style || ""} onChange={(e) => setAt(i, { speech_style: e.target.value })} />
            <details className="npc-pics">
              <summary className="small">{`🖼 Pictures and moods (${(n.portraits?.moods || []).length})`}</summary>
              <MoodEditor portraits={n.portraits} compact onChange={(v) => setAt(i, { portraits: v })} />
            </details>
          </div>
        );
      })}
      <div className="row gap wrap">
        {team.length < MAX && <button className="btn small" onClick={add}>＋ Add companion</button>}
        <button className="btn small" disabled={busy || !cardId} onClick={write}
          title={cardId ? "The AI writes 3 companions who fit this card (you can edit everything)" : "Save the card first"}>
          {busy ? "Writing…" : "✨ Write companions"}</button>
        {error && <span className="error-text tiny">{error}</span>}
      </div>
    </details>
  );
}
