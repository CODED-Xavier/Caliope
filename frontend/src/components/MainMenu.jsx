import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { portraitSrc } from "../portraits.js";
import { KIND_LABELS, MODE_LABELS } from "../utils.js";

/** The main menu: every card as a tile (▶ Play, ✎ Edit) and ＋ New card. */
export default function MainMenu({ onPlay, onEdit, onCreate, onImport, refreshKey }) {
  const [cards, setCards] = useState(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api.scenarios().then(setCards).catch((e) => setError(e.message)); }, [refreshKey]);
  const q = query.trim().toLowerCase();
  const shown = (cards || []).filter((c) => !q || `${c.name} ${c.description}`.toLowerCase().includes(q));
  return (
    <div className="main-menu">
      <div className="row gap center menu-head">
        <h2 className="grow">Your cards</h2>
        {cards?.length > 6 && <input className="field" style={{ maxWidth: 220 }} placeholder="Search cards…" value={query} onChange={(e) => setQuery(e.target.value)} />}
        <button className="btn small" onClick={onImport}>⤒ Import a card</button>
      </div>
      {error && <div className="error-text small">{error}</div>}
      <div className="card-grid">
        <button className="card-tile new-tile" onClick={onCreate}>
          <span className="new-plus">＋</span><span>New card</span>
        </button>
        {shown.map((c) => (
          <div key={c.id} className="card-tile">
            <div className="tile-art" onClick={() => onPlay(c.id)} title="Play">
              {c.covers?.length ? c.covers.slice(0, 3).map((u, k) => <img key={k} src={portraitSrc(u)} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />)
                : <span className="tile-letter">{(c.name || "?").slice(0, 1)}</span>}
            </div>
            <div className="tile-body">
              <div className="tile-name">{c.name}</div>
              <div className="tiny muted">{MODE_LABELS[c.mode] || c.mode}{c.kind ? ` · ${KIND_LABELS[c.kind] || c.kind}` : ""}{c.npc_count ? ` · ${c.npc_count} characters` : ""}</div>
              <div className="small tile-desc">{c.description}</div>
            </div>
            <div className="row gap tile-actions">
              <button className="btn small primary grow" onClick={() => onPlay(c.id)}>▶ Play</button>
              <button className="btn small" onClick={() => onEdit(c.id)} title="Edit the card">✎ Edit</button>
            </div>
          </div>
        ))}
      </div>
      {cards && !cards.length && <div className="muted small">No cards yet: make one, import one, or ask the Muse.</div>}
    </div>
  );
}
