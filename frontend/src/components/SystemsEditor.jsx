import React, { useState } from "react";
import { api } from "../api.js";

/**
 * Card editor: the card's own sheet kept by the app (stats, XP → level, a loadout with a catalog of parts).
 * 🔍 Find systems reads the card's text and lorebook and proposes it; check it here (as JSON) before saving the card.
 */
export default function SystemsEditor({ cardId, systems, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState(null); // the JSON being edited
  const has = systems && (systems.stats || systems.loadout);
  const find = async () => {
    setBusy(true); setError("");
    try { const r = await api.findSystems(cardId); setText(JSON.stringify(r.systems, null, 2)); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const apply = () => {
    try { onChange(text.trim() ? JSON.parse(text) : {}); setText(null); setError(""); } catch (e) { setError(`Not valid JSON: ${e.message}`); }
  };
  const lo = systems?.loadout;
  return (
    <details className="systems-editor" open={!!text}>
      <summary className="section-title">🧩 Card sheet <span className="muted tiny">{has ? `(${(systems.stats || []).length} stats${lo ? `, ${lo.slots.length} slots, ${lo.catalog.length} parts` : ""})` : "(none)"}</span></summary>
      <div className="muted small">The player's sheet kept by the app for this card: stats with ranges, XP that raises the level, and a loadout whose parts cost points from a budget. It shows on the start screen and the Sheet tab, and the Aedo sees its numbers.</div>
      <div className="row gap wrap">
        <button type="button" className="btn small" disabled={busy || !cardId} onClick={find} title={cardId ? "Read this card's text and lorebook" : "Save the card first"}>
          {busy ? "Reading the card…" : "🔍 Find systems"}</button>
        <button type="button" className="btn small ghost" onClick={() => setText(JSON.stringify(systems || {}, null, 2))}>✎ Edit as JSON</button>
        {has && <button type="button" className="btn small ghost" onClick={() => onChange({})}>Remove</button>}
      </div>
      {text !== null && (
        <>
          <div className="muted tiny">Check the numbers against the card (the reader never invents them; empty means the card didn't say). Then apply, and save the card.</div>
          <textarea className="field mono" rows={16} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row gap"><button type="button" className="btn small primary" onClick={apply}>Apply</button>
            <button type="button" className="btn small" onClick={() => setText(null)}>Cancel</button></div>
        </>
      )}
      {error && <div className="error-text small">{error}</div>}
    </details>
  );
}
