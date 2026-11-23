import React, { useState } from "react";
import { api } from "../api.js";
import { ask } from "../dialogs.jsx";

/** ✴ Arsenal: the named techniques and spells of the player and every character (app/arsenal.py).
 *  The player names a move in [brackets]; the Aedo names the characters' moves. Each one keeps its first look,
 *  the power its user had then, and how many times it was used. Edit, add or forget them here. */
export default function ArsenalTab({ convId, state, npcs, busy, onState }) {
  const book = state.arsenal || {};
  const player = state.player?.name || "";
  const [adding, setAdding] = useState(null);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState("");
  const owners = Object.keys(book).sort((a, b) => (a === player ? -1 : b === player ? 1 : a.localeCompare(b)));
  const send = async (change) => {
    try { onState(await api.editArsenal(convId, change)); setError(""); return true; } catch (e) { setError(e.message); return false; }
  };
  const everyone = [player, ...(npcs || []).map((n) => n.name)].filter(Boolean);
  return (
    <div className="tab-body arsenal">
      <div className="muted small">Named techniques and spells. Name yours in [brackets] in a message, like <em>[Chou no Mai - Manabiki]</em>; the characters' own moves are kept when the Aedo names them. Their strength follows each one's current power.</div>
      {error && <div className="error small">{error}</div>}
      {owners.length === 0 && <div className="card small muted">No techniques yet.</div>}
      {owners.map((owner) => (
        <div className="arsenal-owner" key={owner}>
          <div className="section-title">{owner}{owner === player && <span className="pill">you</span>}</div>
          {book[owner].map((mv) => {
            const key = `${owner}|${mv.name}`;
            return editing?.key === key ? (
              <form key={key} className="card arsenal-move" onSubmit={async (e) => {
                e.preventDefault();
                if (await send({ op: "edit", owner, name: mv.name, ...editing.values })) setEditing(null);
              }}>
                <input className="field" value={editing.values.name} onChange={(e) => setEditing({ ...editing, values: { ...editing.values, name: e.target.value } })} />
                <input className="field" placeholder="Power when learned (Expert (Low), 3-Circle…)" value={editing.values.tier}
                  onChange={(e) => setEditing({ ...editing, values: { ...editing.values, tier: e.target.value } })} />
                <textarea className="field" rows={3} placeholder="What it looks like, what it does" value={editing.values.desc}
                  onChange={(e) => setEditing({ ...editing, values: { ...editing.values, desc: e.target.value } })} />
                <div className="row gap"><button className="btn small" type="submit" disabled={busy}>Save</button>
                  <button className="btn small ghost" type="button" onClick={() => setEditing(null)}>Cancel</button></div>
              </form>
            ) : (
              <div className="card arsenal-move" key={key}>
                <div className="row gap">
                  <strong className="grow move-name">『{mv.name}』</strong>
                  {mv.tier && <span className="pill">{mv.tier}</span>}
                  <span className="muted tiny" title="Times used">{mv.uses}×</span>
                  <button className="icon-btn" title="Edit" disabled={busy}
                    onClick={() => setEditing({ key, values: { name: mv.name, tier: mv.tier || "", desc: mv.desc || "" } })}>✎</button>
                  <button className="icon-btn" title="Forget this technique" disabled={busy} onClick={async () => {
                    if (await ask.confirm(`Forget ${mv.name}?`, { ok: "Forget", danger: true })) send({ op: "delete", owner, name: mv.name });
                  }}>✕</button>
                </div>
                {mv.desc && <div className="small">{mv.desc}</div>}
              </div>
            );
          })}
        </div>
      ))}
      {adding ? (
        <form className="card arsenal-move" onSubmit={async (e) => {
          e.preventDefault();
          if (await send({ op: "add", ...adding })) setAdding(null);
        }}>
          <select className="field" value={adding.owner} onChange={(e) => setAdding({ ...adding, owner: e.target.value })}>
            {everyone.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <input className="field" placeholder="Technique or spell name" value={adding.name} onChange={(e) => setAdding({ ...adding, name: e.target.value })} />
          <input className="field" placeholder="Power when learned (Expert (Low), 3-Circle…)" value={adding.tier} onChange={(e) => setAdding({ ...adding, tier: e.target.value })} />
          <textarea className="field" rows={3} placeholder="What it looks like, what it does" value={adding.desc} onChange={(e) => setAdding({ ...adding, desc: e.target.value })} />
          <div className="row gap"><button className="btn small" type="submit" disabled={busy || !adding.name.trim()}>Add</button>
            <button className="btn small ghost" type="button" onClick={() => setAdding(null)}>Cancel</button></div>
        </form>
      ) : (
        <button className="btn small" disabled={busy || !everyone.length} onClick={() => setAdding({ owner: everyone[0], name: "", tier: "", desc: "" })}>＋ Add a technique</button>
      )}
    </div>
  );
}
