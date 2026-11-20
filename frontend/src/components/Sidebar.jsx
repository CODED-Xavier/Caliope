import React, { useState } from "react";
import { MODE_LABELS, timeAgo } from "../utils.js";

export default function Sidebar({ convs, activeId, onSelect, onNew, onRename, onDelete, onSkills, onRulebooks, onModels, onSettings, health, theme, onToggleTheme }) {
  const online = health?.llm?.ok;
  const [filter, setFilter] = useState("");
  const shown = filter.trim() ? convs.filter((c) => (c.title || "").toLowerCase().includes(filter.trim().toLowerCase())) : convs;
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-dice">🎲</span> Local RPG
        <button className="icon-btn theme-btn" onClick={onToggleTheme} title="Toggle light/dark">{theme === "dark" ? "☀" : "☾"}</button>
      </div>
      <button className="btn primary wide" onClick={onNew}>＋ New game</button>
      <div className="side-label">Your games</div>
      {convs.length > 6 && <input className="field side-search" placeholder="Find a game…" value={filter} onChange={(e) => setFilter(e.target.value)} />}
      <div className="conv-list">
        {convs.length === 0 && <div className="muted small pad">No games yet. Start one!</div>}
        {filter && shown.length === 0 && <div className="muted small pad">No game matches.</div>}
        {shown.map((c) => (
          <div key={c.id} className={`conv ${c.id === activeId ? "active" : ""}`} onClick={() => onSelect(c.id)} title={c.title}>
            <div className="conv-main">
              <div className="conv-title">{c.title || "Untitled"}</div>
              <div className="conv-sub">{MODE_LABELS[c.mode] || "Adventure"} · {timeAgo(c.updated_at)}</div>
            </div>
            <div className="conv-actions">
              <button className="icon-btn" title="Rename" onClick={(e) => { e.stopPropagation(); onRename(c); }}>✎</button>
              <button className="icon-btn" title="Delete" onClick={(e) => { e.stopPropagation(); onDelete(c); }}>✕</button>
            </div>
          </div>
        ))}
      </div>
      <div className="side-footer">
        <button className="status-pill" onClick={onSettings} title="Open settings">
          <span className={`dot ${online ? "on" : "off"}`} />
          {online ? "Model server online" : "Model server offline"}
        </button>
        <div className="side-tools">
          <button className="btn ghost grow" onClick={onSkills}>🧩 Skills</button>
          <button className="btn ghost grow" onClick={onRulebooks} title="Rulebooks">📚 Rules</button>
          <button className="btn ghost grow" onClick={onModels} title="Download and manage AI models">🧠 Models</button>
          <button className="btn ghost grow" onClick={onSettings}>⚙ Settings</button>
        </div>
      </div>
    </aside>
  );
}
