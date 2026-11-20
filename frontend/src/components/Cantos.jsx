import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { portraitSrc } from "../portraits.js";
import HelpTip from "./HelpTip.jsx";

/** Journal: the Cantos (chapters) of this game, and closing the current one. */
export function CantosBox({ convId, cantos, onCantos, busy }) {
  const [title, setTitle] = useState("");
  const [working, setWorking] = useState(false);
  const [err, setErr] = useState("");
  const list = cantos || [];
  const open = list.find((c) => !c.closed_at);
  const close = async () => {
    if (!window.confirm("Close this Canto? The Aedo writes its chronicle and the next Canto begins.")) return;
    setWorking(true); setErr("");
    try { const r = await api.closeCanto(convId, title.trim()); onCantos(r.cantos); setTitle(""); } catch (e) { setErr(e.message); }
    setWorking(false);
  };
  const rename = async (c) => {
    const t = window.prompt(`New title for ${c.label}:`, c.title || "");
    if (t === null) return;
    try { await api.renameCanto(c.id, t); onCantos(await api.cantos(convId)); } catch (e) { setErr(e.message); }
  };
  return (
    <>
      <div className="section-title">Cantos <HelpTip id="cantos" /></div>
      {list.filter((c) => c.closed_at).map((c) => (
        <details key={c.id} className="card canto">
          <summary className="small"><b>{c.label}</b> · {c.title} <span className="muted tiny">({c.messages} messages)</span>
            <button className="icon-btn" title="Rename" onClick={(e) => { e.preventDefault(); rename(c); }}>✎</button></summary>
          <div className="small">{c.chronicle}</div>
        </details>
      ))}
      {open && (
        <div className="card canto open">
          <div className="small"><b>{open.label}</b> · in progress <span className="muted tiny">({open.messages} messages)</span></div>
          <div className="row gap center">
            <input className="field grow" placeholder="Title (optional: the Aedo names it)" value={title} onChange={(e) => setTitle(e.target.value)} />
            <button className="btn small primary" disabled={busy || working} onClick={close}>{working ? "Writing…" : "Close this Canto"}</button>
          </div>
        </div>
      )}
      {err && <div className="error-text small">{err}</div>}
    </>
  );
}

/** Map tab: the map bag, scene pictures you kept, with their place, date and Canto. */
export function MapBag({ convId, refreshKey }) {
  const [pics, setPics] = useState(null);
  const [zoom, setZoom] = useState(null);
  const load = () => api.gallery(convId).then(setPics).catch(() => setPics([]));
  useEffect(() => { load(); }, [convId, refreshKey]); // eslint-disable-line
  const rename = async (p) => {
    const t = window.prompt("Name this picture:", p.title);
    if (t !== null) { await api.renamePicture(p.id, t); load(); }
  };
  const remove = async (p) => { if (window.confirm(`Take "${p.title}" out of the map bag?`)) { await api.removePicture(p.id); load(); } };
  return (
    <>
      <div className="section-title">🎒 Map bag ({pics?.length || 0}) <HelpTip id="map_bag" /></div>
      {pics && !pics.length && <div className="muted small">Scene pictures you keep (📌 on a picture) are collected here. The first picture of every place is kept on its own.</div>}
      <div className="bag-grid">
        {(pics || []).map((p) => (
          <figure key={p.id} className="bag-pic">
            <img src={portraitSrc(p.url)} alt={p.prompt} title={p.prompt} loading="lazy" onClick={() => setZoom(p)} />
            <figcaption>
              <div className="small bag-title">{p.title}</div>
              <div className="muted tiny">{[p.location !== p.title ? p.location : "", p.date_label, p.canto_label].filter(Boolean).join(" · ")}</div>
              <div className="row gap">
                <button className="icon-btn" title="Rename" onClick={() => rename(p)}>✎</button>
                <button className="icon-btn" title="Take out of the bag" onClick={() => remove(p)}>✕</button>
              </div>
            </figcaption>
          </figure>
        ))}
      </div>
      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={portraitSrc(zoom.url)} alt={zoom.title} />
          <div className="lightbox-cap">{zoom.title}{zoom.date_label ? ` · ${zoom.date_label}` : ""}</div>
        </div>
      )}
    </>
  );
}

/** "Previously, in…": written only when asked, shown, and never added to the story. */
export function RecapView({ text, loading, onClose, onAgain }) {
  return (
    <div className="lightbox recap" onClick={onClose}>
      <div className="recap-card" onClick={(e) => e.stopPropagation()}>
        <div className="section-title">📜 Previously…</div>
        {loading ? <div className="muted"><span className="spinner" /> The Aedo remembers…</div> : <div className="recap-text">{text}</div>}
        <div className="row gap end">
          {!loading && <button className="btn small" onClick={onAgain}>↻ Again</button>}
          <button className="btn small primary" onClick={onClose}>Back to the story</button>
        </div>
      </div>
    </div>
  );
}

/** Message ids where a new Canto begins (for the dividers in the chat). */
export function cantoStarts(cantos, messages) {
  const out = {};
  for (const c of cantos || []) {
    if (c.number < 2) continue;
    const first = messages.find((m) => m.id >= c.first_message_id);
    if (first) out[first.id] = c;
  }
  return out;
}
