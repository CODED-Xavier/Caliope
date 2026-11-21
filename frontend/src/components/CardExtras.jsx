import React, { useState } from "react";
import { api } from "../api.js";
import { moodUrl, portraitSrc } from "../portraits.js";
import HelpTip from "./HelpTip.jsx";

/** First sentence of a character's description: their role at a glance. */
const roleOf = (n) => {
  const t = String(n.description || n.personality || "").replace(/\s+/g, " ").trim();
  const first = t.split(/(?<=[.!?])\s/)[0] || "";
  return first.length > 110 ? `${first.slice(0, 107)}…` : first;
};

/** Every character of a card with their standard picture, name and role. */
export function CharacterPreview({ npcs, onClose }) {
  const [zoom, setZoom] = useState(null);
  const [q, setQ] = useState("");
  const list = (npcs || []).filter((n) => !q || n.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="cast-preview">
      <div className="row gap center">
        <input className="field grow" placeholder="Find a character…" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="muted small">{(npcs || []).length} characters</span>
        {onClose && <button className="btn small" onClick={onClose}>‹ Back</button>}
      </div>
      <div className="cast-grid">
        {list.map((n) => {
          const url = moodUrl(n.portraits, "");
          return (
            <div key={n.name} className="cast-card" onClick={() => url && setZoom({ url, name: n.name })}>
              {url ? <img src={portraitSrc(url)} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
                : <div className="cast-empty">{n.name.slice(0, 1)}</div>}
              <div className="cast-name">{n.name}</div>
              <div className="muted tiny cast-role">{roleOf(n)}</div>
            </div>
          );
        })}
      </div>
      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={portraitSrc(zoom.url)} alt={zoom.name} />
        </div>
      )}
    </div>
  );
}

/** Starts of a card, as the backend lists them (default, alternate openings, the card's own starts). */
export function startsOf(card) {
  const out = [{ id: "default", name: "Default start", description: "The card's own opening." }];
  (card.alternate_openings || []).forEach((t, i) => {
    const first = String(t).replace(/[*_#>[\]!()]/g, "").trim().split("\n")[0];
    out.push({ id: `alt-${i + 1}`, name: `Alternate opening ${i + 1}`, description: first.length > 140 ? `${first.slice(0, 137)}…` : first });
  });
  return out.concat(card.starts || []);
}

/** "Choose your start" on the new game screen (only shown when a card has more than one). */
export function StartPicker({ card, value, onChange }) {
  const starts = startsOf(card);
  if (starts.length < 2) return null;
  return (
    <>
      <div className="section-title">Choose your start <HelpTip id="card_starts" /></div>
      <div className="way-pick starts-pick">
        {starts.map((s) => (
          <label key={s.id} className={`way ${value === s.id ? "active" : ""}`}>
            <input type="radio" checked={value === s.id} onChange={() => onChange(s.id)} />
            <span><strong>{s.name}</strong><br /><span className="muted tiny">{s.description || "—"}</span></span>
          </label>
        ))}
      </div>
    </>
  );
}

const SCENE_SPLIT = /\n\s*---+\s*\n/;

/** Card editor: the card's own starts (routes). */
export function StartsEditor({ starts, npcs, onChange }) {
  const list = starts || [];
  const setAt = (i, k, v) => onChange(list.map((s, j) => (j === i ? { ...s, [k]: v } : s)));
  const names = (npcs || []).map((n) => n.name);
  return (
    <>
      <div className="section-title">Starts (routes) <HelpTip id="card_starts" /> <span className="muted tiny">({list.length}/8)</span></div>
      <div className="muted tiny">The card's opening message is the default start. Add other ways into the same world: their own opening, how the world differs on this route, who the story starts with, and scenes the Aedo plays in order.</div>
      {list.map((s, i) => (
        <div className="card" key={i}>
          <div className="row gap center">
            <input className="field grow" placeholder="Name (e.g. Cult member)" value={s.name || ""} onChange={(e) => setAt(i, "name", e.target.value)} />
            <button className="icon-btn" title="Remove this start" onClick={() => onChange(list.filter((_, j) => j !== i))}>✕</button>
          </div>
          <input className="field" placeholder="One line for the start screen" value={s.description || ""} onChange={(e) => setAt(i, "description", e.target.value)} />
          <label className="lbl">Opening message</label>
          <textarea className="field" rows={4} value={s.opening || ""} onChange={(e) => setAt(i, "opening", e.target.value)} placeholder="The first scene the player sees (leave empty to use the card's opening)" />
          <label className="lbl">How the world is on this route</label>
          <textarea className="field" rows={3} value={s.setting || ""} onChange={(e) => setAt(i, "setting", e.target.value)} placeholder="Sent to the Aedo every turn: what is different here, the tone, the goal…" />
          <label className="lbl">Starts with (characters known from the beginning)</label>
          <input className="field" list="start-npcs" value={(s.focus || []).join(", ")}
            onChange={(e) => setAt(i, "focus", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))}
            placeholder="Names, separated by commas. Everyone else is met in the story." />
          <datalist id="start-npcs">{names.map((n) => <option key={n} value={n} />)}</datalist>
          <label className="lbl">Fixed scenes, in order <span className="muted tiny">(separate scenes with a line of ---)</span></label>
          <textarea className="field" rows={5} value={(s.scenes || []).join("\n\n---\n\n")}
            onChange={(e) => setAt(i, "scenes", e.target.value.split(SCENE_SPLIT).map((x) => x.trim()).filter(Boolean))}
            placeholder={"The welcoming ceremony: …\n\n---\n\nThe first night in the dormitory: …"} />
        </div>
      ))}
      {list.length < 8 && <button className="btn small" onClick={() => onChange([...list, { name: "", description: "", opening: "", setting: "", focus: [], scenes: [] }])}>＋ Add a start</button>}
    </>
  );
}

/** Card editor: take every character's pictures from a folder on this PC (Character/1.png … 6.png). */
export function PicturesFolder({ cardId, npcs, onApplied }) {
  const [folder, setFolder] = useState("");
  const [scan, setScan] = useState(null);
  const [picks, setPicks] = useState({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const run = async (fn) => { setBusy(true); setErr(""); setNote(""); try { await fn(); } catch (e) { setErr(e.message); } finally { setBusy(false); } };

  const look = (f) => run(async () => { setScan(await api.cardPicturesScan(cardId, f)); setPicks({}); });
  const browse = () => run(async () => {
    const r = await api.cardPicturesBrowse(cardId);
    if (r.folder) { setFolder(r.folder); setScan(await api.cardPicturesScan(cardId, r.folder)); setPicks({}); }
  });
  const apply = () => run(async () => {
    const r = await api.cardPicturesApply(cardId, folder, picks);
    setNote(`Pictures set for ${r.characters} characters${r.new?.length ? ` (new: ${r.new.join(", ")})` : ""}${r.games ? `, also in ${r.games} game(s) using this card` : ""}.`);
    setScan(null);
    onApplied(r.card);
  });
  const toR2 = () => run(async () => {
    const r = await api.cardPicturesToR2(cardId);
    setNote(`${r.uploaded} pictures are now in your private R2 bucket.`);
    onApplied(r.card);
  });

  if (!cardId) return <div className="muted tiny">Save the card once to take its pictures from a folder.</div>;
  return (
    <div className="pics-folder">
      <div className="row gap center">
        <button className="btn small primary" disabled={busy} onClick={browse}>📂 Pick the pictures folder…</button>
        <input className="field grow" value={folder} placeholder="or paste its address, e.g. D:\Lumencia\pictures" onChange={(e) => setFolder(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && folder.trim() && look(folder)} />
        <button className="btn small" disabled={busy || !folder.trim()} onClick={() => look(folder)}>Look</button>
      </div>
      <div className="muted tiny">One folder per character with 1.png … 6.png (1 Standard, 2 Happy, 3 Sad, 4 Angry, 5 Disgusted, 6 Blushing), or a single Name.png. Missing moods use the closest one. Run it again whenever you finish more pictures.</div>
      {busy && <div className="muted small"><span className="spinner" /> Working…</div>}
      {scan && (
        <div className="card">
          <div className="small"><b>{scan.characters.length}</b> characters found{scan.missing.length ? `, ${scan.missing.length} without pictures` : ""}.</div>
          <div className="pics-found">
            {scan.characters.map((c) => (
              <span key={c.character} className="chip" title={c.folder || "single picture"}>{c.character} · {c.moods.join(",")}</span>
            ))}
          </div>
          {scan.unmatched.length > 0 && (
            <>
              <div className="small" style={{ marginTop: 8 }}>Not matched to a character: pick who they are, add them as new characters, or leave them out</div>
              {scan.unmatched.map((u) => (
                <div key={u.folder} className="row gap center">
                  <span className="small grow">{u.folder} <span className="muted tiny">({u.count})</span></span>
                  <select className="field" value={picks[u.folder] || ""} onChange={(e) => setPicks((p) => ({ ...p, [u.folder]: e.target.value }))}>
                    <option value="">(leave out)</option>
                    <option value="__new__">＋ Add as a new character ({u.folder.replace(/\.(png|jpe?g|webp|gif)$/i, "")})</option>
                    {(npcs || []).map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
                  </select>
                </div>
              ))}
            </>
          )}
          <div className="row gap end" style={{ marginTop: 8 }}>
            <button className="btn small" onClick={() => setScan(null)}>Cancel</button>
            <button className="btn small primary" disabled={busy} onClick={apply}>Apply</button>
          </div>
        </div>
      )}
      <div className="row gap center">
        <button className="btn small ghost" disabled={busy} onClick={toR2} title="Needs your R2 keys in Settings">☁ Upload this card's pictures to my private R2</button>
        <HelpTip id="r2" />
      </div>
      {note && <div className="ok-text small">{note}</div>}
      {err && <div className="error-text small">{err}</div>}
    </div>
  );
}
