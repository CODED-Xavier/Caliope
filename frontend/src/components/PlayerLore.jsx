import React, { useEffect, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";

const blank = () => ({ id: Math.random().toString(36).slice(2, 12), name: "", keys: "", content: "", summary: "", enabled: true });
const toForm = (e) => ({ ...e, keys: Array.isArray(e.keys) ? e.keys.join(", ") : String(e.keys || "") }); // a saved persona may keep them as text

/**
 * The player's own lore entries (a new great house, a home village…). Canon in this game.
 * Without convId it only edits a list (the start screen); with convId it saves to the game and can ask the AI
 * for new facts the story established.
 */
export default function PlayerLore({ entries, onChange, convId, onSaved }) {
  const [list, setList] = useState(() => (entries || []).map(toForm));
  const [open, setOpen] = useState("");
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [ideas, setIdeas] = useState({}); // id -> suggestions
  const [asking, setAsking] = useState("");

  useEffect(() => { if (!dirty) setList((entries || []).map(toForm)); }, [entries]); // eslint-disable-line

  const update = (next) => { setList(next); setDirty(true); onChange?.(next); };
  const edit = (id, k, v) => update(list.map((e) => (e.id === id ? { ...e, [k]: v } : e)));
  const add = () => { const e = blank(); update([...list, e]); setOpen(e.id); };
  const remove = (id) => update(list.filter((e) => e.id !== id));

  const save = async () => {
    setError("");
    try {
      const conv = await api.setPlayerLore(convId, list);
      setDirty(false); setSaved(true); setTimeout(() => setSaved(false), 1500);
      onSaved?.(conv);
    } catch (e) { setError(e.message); }
  };
  const suggest = async (id) => {
    setAsking(id); setError("");
    try {
      if (dirty) await save();
      const r = await api.suggestPlayerLore(convId, id);
      setIdeas((x) => ({ ...x, [id]: r.suggestions.length ? r.suggestions : ["(nothing new in the story yet)"] }));
    } catch (e) { setError(e.message); } finally { setAsking(""); }
  };
  const accept = (id, line) => {
    edit(id, "content", ((list.find((e) => e.id === id)?.content || "").trim() + "\n- " + line).trim());
    setIdeas((x) => ({ ...x, [id]: x[id].filter((l) => l !== line) }));
  };

  return (
    <div className="player-lore">
      <div className="section-title">Your world additions <HelpTip id="player_lore" /></div>
      {!list.length && <p className="muted tiny">Add things your character brings to the world: a great house, a home town, an order. The Aedo treats them as true, even where the card's lore says otherwise.</p>}
      {list.map((e) => (
        <div key={e.id} className={`card lore-entry ${e.enabled ? "" : "off"}`}>
          <div className="row center gap">
            <button className="lore-head grow" onClick={() => setOpen(open === e.id ? "" : e.id)}>
              {open === e.id ? "▾" : "▸"} <b>{e.name || "(new entry)"}</b>
              {!e.enabled && <span className="muted tiny"> · off</span>}
            </button>
            <label className="tiny row center gap" title="Off: the Aedo ignores this entry">
              <input type="checkbox" checked={e.enabled} onChange={(ev) => edit(e.id, "enabled", ev.target.checked)} /> on
            </label>
          </div>
          {open === e.id && (
            <div className="lore-body">
              <input className="field" value={e.name} maxLength={80} onChange={(ev) => edit(e.id, "name", ev.target.value)} placeholder="Name, e.g. House Ardent" />
              <input className="field" value={e.keys} onChange={(ev) => edit(e.id, "keys", ev.target.value)} placeholder="Keywords that bring up the details (comma separated): Ardent, burning stag, Emberhold" />
              <textarea className="field" rows={5} maxLength={2000} value={e.content} onChange={(ev) => edit(e.id, "content", ev.target.value)}
                placeholder="Everything the Aedo should know: history, sigil, seat, members, allies and rivals among the card's houses…" />
              <input className="field" value={e.summary} maxLength={200} onChange={(ev) => edit(e.id, "summary", ev.target.value)} placeholder="One line the Aedo always sees (optional; the first sentence is used otherwise)" />
              <div className="row gap center">
                <span className="muted tiny grow">{e.content.length} / 2000</span>
                {convId && <button className="btn small" disabled={!!asking || !e.name} onClick={() => suggest(e.id)}>{asking === e.id ? "Reading the story…" : "✨ New facts from the story"}</button>}
                <button className="btn small ghost" onClick={() => remove(e.id)}>Remove</button>
              </div>
              {(ideas[e.id] || []).map((line) => (
                <div key={line} className="row gap center lore-idea">
                  <span className="small grow">{line}</span>
                  {!line.startsWith("(") && <button className="btn small" onClick={() => accept(e.id, line)}>Add</button>}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
      <div className="row gap center">
        <button className="btn small" onClick={add} disabled={list.length >= 30}>＋ Add an entry</button>
        <span className="grow" />
        {saved && <span className="ok-text small">✓ saved</span>}
        {convId && <button className="btn small primary" onClick={save} disabled={!dirty}>Save</button>}
      </div>
      {error && <div className="error-text small">{error}</div>}
    </div>
  );
}
