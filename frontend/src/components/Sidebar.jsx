import React, { useState } from "react";
import { MODE_LABELS, timeAgo } from "../utils.js";

// Simple stroke icons (no emoji): one look in both themes.
const ICONS = {
  menu: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  games: "M5 4h11l3 3v13H5zM9 9h6M9 13h6M9 17h4",
  new: "M12 5v14M5 12h14",
  bestiary: "M4 18c3-1 4-4 4-7 0-3 2-6 5-6s5 3 5 6c0 3 1 6 2 7M10 11h.01M15 11h.01",
  library: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5",
  muse: "M4 20l6-6M14 4c3 0 6 3 6 6-4 0-6 2-6 6-3 0-6-3-6-6 4 0 6-2 6-6z",
  skills: "M9 3h6v4H9zM4 9h16v12H4zM9 13h6",
  rules: "M6 4h12v16H6zM9 8h6M9 12h6M9 16h3",
  models: "M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1 0 8v1a4 4 0 0 1-8 0v-1a4 4 0 0 1 0-8V7a4 4 0 0 1 4-4zM12 3v18",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z",
  sun: "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
};

export function Icon({ name, size = 20 }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={ICONS[name]} />
    </svg>
  );
}

function RailButton({ icon, label, onClick, on = false, tour, title }) {
  return (
    <button type="button" className={`rail-btn ${on ? "on" : ""}`} onClick={onClick} title={title || label} data-tour={tour}>
      <Icon name={icon} />
      <span className="rail-label">{label}</span>
    </button>
  );
}

/**
 * The slim icon rail on the left (always there) and, beside it, the drawer with your games
 * (opened with Games; it closes itself when you pick one on a narrow window).
 */
export default function Sidebar({ convs, activeId, onSelect, onNew, onHome, onRename, onRestart, onDelete, onSkills, onRulebooks, onBestiary,
  onLibrary, onModels, onMuse, onSettings, health, theme, onToggleTheme, collapsed, onCollapse }) {
  const online = health?.llm?.ok;
  const [filter, setFilter] = useState("");
  const shown = filter.trim() ? convs.filter((c) => (c.title || "").toLowerCase().includes(filter.trim().toLowerCase())) : convs;
  const pick = (id) => { onSelect(id); if (window.innerWidth < 1100) onCollapse(true); };
  return (
    <>
      <nav className="rail" aria-label="Main">
        <img className="rail-logo" src="/favicon.png" alt="Calíope" title="Calíope" />
        <RailButton icon="menu" label="Menu" onClick={onHome} on={!activeId} title="All your cards" />
        <RailButton icon="games" label="Games" onClick={() => onCollapse(!collapsed)} on={!collapsed} title="Your games" />
        <RailButton icon="new" label="New" onClick={onNew} tour="new" title="New game" />
        <div className="rail-gap" />
        <RailButton icon="library" label="Library" onClick={onLibrary} title="D&D 5e library: classes, spells, feats, items" />
        <RailButton icon="bestiary" label="Bestiary" onClick={onBestiary} title="Monster sheets for fights" />
        <RailButton icon="rules" label="Rules" onClick={onRulebooks} title="Rulebooks" />
        <RailButton icon="skills" label="Skills" onClick={onSkills} />
        <RailButton icon="muse" label="Muse" onClick={onMuse} tour="muse" title="Write stories and cards with the Muse" />
        <div className="rail-grow" />
        <RailButton icon="models" label="Models" onClick={onModels} tour="models" title="Download and manage AI models" />
        <RailButton icon={theme === "dark" ? "sun" : "moon"} label="Theme" onClick={onToggleTheme} title="Toggle light/dark" />
        <RailButton icon="settings" label="Settings" onClick={onSettings} tour="settings" />
        <button type="button" className="rail-status" onClick={onSettings} title={online ? "Model server online" : "Model server offline: open settings"}>
          <span className={`dot ${online ? "on" : "off"}`} />
        </button>
      </nav>
      {!collapsed && (
        <aside className="drawer" aria-label="Your games">
          <div className="drawer-head">
            <span className="drawer-title">Your games</span>
            <button type="button" className="icon-btn" onClick={() => onCollapse(true)} title="Close">✕</button>
          </div>
          <button type="button" className="btn primary wide big-touch" onClick={onNew}>＋ New game</button>
          {convs.length > 6 && <input className="field side-search" placeholder="Find a game…" value={filter} onChange={(e) => setFilter(e.target.value)} />}
          <div className="conv-list">
            {convs.length === 0 && <div className="muted small pad">No games yet. Start one!</div>}
            {filter && shown.length === 0 && <div className="muted small pad">No game matches.</div>}
            {shown.map((c) => (
              <div key={c.id} className={`conv ${c.id === activeId ? "active" : ""}`} onClick={() => pick(c.id)} title={c.title}>
                <div className="conv-main">
                  <div className="conv-title">{c.title || "Untitled"}</div>
                  <div className="conv-sub">{MODE_LABELS[c.mode] || "Adventure"} · {timeAgo(c.updated_at)}</div>
                </div>
                <div className="conv-actions">
                  <button className="icon-btn" title="Rename" onClick={(e) => { e.stopPropagation(); onRename(c); }}>✎</button>
                  <button className="icon-btn" title="Restart from the beginning" onClick={(e) => { e.stopPropagation(); onRestart(c); }}>↺</button>
                  <button className="icon-btn" title="Delete" onClick={(e) => { e.stopPropagation(); onDelete(c); }}>✕</button>
                </div>
              </div>
            ))}
          </div>
        </aside>
      )}
    </>
  );
}
