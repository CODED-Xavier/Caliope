import React, { useEffect, useState } from "react";
import { ask } from "../dialogs.jsx";
import Modal from "./Modal.jsx";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";
import { portraitSrc } from "../portraits.js";

const ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"];
const BLANK = { name: "", type: "", ac: 12, ac_note: "", hp: 7, hp_dice: "", speed: "30 ft.", init_bonus: 0,
  stats: { STR: 10, DEX: 10, CON: 10, INT: 10, WIS: 10, CHA: 10 }, skills: "", senses: "", languages: "", cr: "", xp: 0,
  traits: "", actions: [{ name: "Attack", attack_bonus: 3, damage: "1d6+1", range: 1, text: "" }], notes: "", picture: "" };
const mod = (v) => { const m = Math.floor((parseInt(v, 10) || 10) - 10) >> 1; return m >= 0 ? `+${m}` : `${m}`; };

/** 🐉 The Bestiary: monster sheets saved in a folder; fights take their numbers from here. */
export default function BestiaryModal({ onClose }) {
  const [list, setList] = useState([]);
  const [folder, setFolder] = useState("");
  const [books, setBooks] = useState([]);
  const [shelf, setShelf] = useState("all");      // all | "" (your own) | a book
  const [query, setQuery] = useState("");
  const [edit, setEdit] = useState(null);         // {monster, oldId}
  const [importing, setImporting] = useState(false);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const load = () => api.bestiary().then((r) => { setList(r.monsters || []); setBooks(r.books || []); setFolder(r.folder || ""); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const [bookName, setBookName] = useState("");
  const runImport = async (body, filename = "") => {
    setErr(""); setNote("");
    try {
      const book = bookName.trim() || filename.replace(/\.(md|txt|pdf)$/i, "");
      const r = await api.bestiaryImport(body, false, book);
      setNote(r.added.length ? `Added ${r.added.length}${r.book ? ` to the folder "${r.book}"` : ""}: ${r.added.join(", ")}.${r.kept.length ? ` Already here (kept): ${r.kept.join(", ")}.` : ""}`
        : r.kept.length ? `All already here: ${r.kept.join(", ")}.` : "No stat blocks were found in that text.");
      setImporting(false); setText(""); setBookName(""); if (r.book) setShelf(r.book); load();
    } catch (e) { setErr(e.message); }
  };

  if (edit) {
    return (
      <Modal title={edit.oldId ? `🐉 ${edit.monster.name}` : "🐉 Create monster"} onClose={onClose} wide>
        <datalist id="bestiary-books">{books.map((b) => <option key={b} value={b} />)}</datalist>
        <MonsterSheet initial={edit.monster} onCancel={() => setEdit(null)}
          onSave={async (m) => { try { await api.bestiarySave(m, edit.oldId); setEdit(null); setNote(`"${m.name}" saved.`); load(); } catch (e) { ask.alert(e.message); } }}
          onDelete={edit.oldId ? async () => {
            if (!await ask.confirm(`Delete "${edit.monster.name}" from the Bestiary?`)) return;
            await api.bestiaryDelete(edit.oldId); setEdit(null); load();
          } : null} />
      </Modal>
    );
  }
  const q = query.trim().toLowerCase();
  const shown = list.filter((m) => (shelf === "all" || m.book === shelf) && (!q || `${m.name} ${m.type}`.toLowerCase().includes(q)));
  const groups = [...new Set(shown.map((m) => m.book))];
  return (
    <Modal title="🐉 Bestiary" onClose={onClose} wide>
      <div className="bestiary">
        <div className="muted small"><HelpTip id="bestiary" /> Monster sheets for fights. An enemy with the same name (or its plural) gets these numbers: AC, HP, attack, damage, initiative and speed. Each monster is a file in <span className="mono no-tr">{folder}</span>, in a folder per book.</div>
        <div className="row gap center wrap">
          <button className="btn small primary" onClick={() => setEdit({ monster: { ...BLANK, book: shelf === "all" ? "" : shelf, stats: { ...BLANK.stats }, actions: [...BLANK.actions] }, oldId: "" })}>＋ Create monster</button>
          <button className="btn small" onClick={() => setImporting(!importing)}>⤒ Import stat blocks</button>
          <button className="btn small" onClick={() => api.bestiaryOpen(shelf === "all" ? "" : shelf).catch((e) => setErr(e.message))} title="Open the folder in Windows Explorer">📂 Open folder</button>
          <span className="grow" />
          <select className="field" style={{ maxWidth: 220 }} value={shelf} onChange={(e) => setShelf(e.target.value)}>
            <option value="all">{`All books (${list.length})`}</option>
            <option value="">{`My monsters (${list.filter((m) => !m.book).length})`}</option>
            {books.map((b) => <option key={b} value={b}>{`${b} (${list.filter((m) => m.book === b).length})`}</option>)}
          </select>
          <input className="field" style={{ maxWidth: 180 }} placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        {importing && (
          <div className="card">
            <div className="small">A book's monster appendix (or any text with stat blocks: "Armor Class 15", "Hit Points 7 (2d6)", the STR…CHA table, "+4 to hit… Hit: 5 (1d6 + 2)"). Monsters already here are kept.</div>
            <div className="row gap center wrap">
              <input className="field grow" placeholder="Book (folder) name: the file's name if empty" value={bookName} onChange={(e) => setBookName(e.target.value)} />
              <label className="btn small">⬆ File (.md, .txt, .pdf)<input type="file" accept=".md,.txt,.pdf" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) runImport(f, f.name); e.target.value = ""; }} /></label>
            </div>
            <textarea className="field" rows={6} placeholder="…or paste the stat blocks here" value={text} onChange={(e) => setText(e.target.value)} />
            <button className="btn small primary" disabled={!text.trim()} onClick={() => runImport(new Blob([text], { type: "text/plain" }))}>Read them</button>
          </div>
        )}
        {note && <div className="ok-text small">{note}</div>}
        {err && <div className="error-text small">{err}</div>}
        <div className="monster-list">
          {groups.map((g) => (
            <React.Fragment key={g || "own"}>
              <div className="book-title">{g ? `📖 ${g}` : "✍ My monsters"}</div>
              {shown.filter((m) => m.book === g).map((m) => (
                <button key={m.id} className="monster-row" onClick={() => setEdit({ monster: m, oldId: m.id })}>
                  {m.picture ? <img src={portraitSrc(m.picture)} alt="" /> : <span className="monster-dot">🐉</span>}
                  <span className="grow"><b>{m.name}</b> <span className="muted tiny">{m.type}</span></span>
                  <span className="tiny">{`AC ${m.ac} · HP ${m.hp}${m.cr ? ` · CR ${m.cr}` : ""}`}</span>
                </button>
              ))}
            </React.Fragment>
          ))}
          {!shown.length && <div className="muted small">{list.length ? "Nothing matches." : "No monsters yet: create one or import a book's appendix."}</div>}
        </div>
      </div>
    </Modal>
  );
}

function MonsterSheet({ initial, onSave, onCancel, onDelete }) {
  const [m, setM] = useState(() => JSON.parse(JSON.stringify(initial)));
  const set = (k, v) => setM((x) => ({ ...x, [k]: v }));
  const setStat = (k, v) => setM((x) => ({ ...x, stats: { ...x.stats, [k]: v } }));
  const setAct = (i, k, v) => setM((x) => ({ ...x, actions: x.actions.map((a, j) => (j === i ? { ...a, [k]: v } : a)) }));
  const upload = async (file) => { if (!file) return; try { const r = await api.uploadPicture(file); set("picture", r.url); } catch (e) { ask.alert(e.message); } };
  const num = (k, w = 56) => <input className="field num" style={{ width: w }} value={m[k] ?? ""} onChange={(e) => set(k, e.target.value)} />;
  return (
    <div className="monster-sheet">
      <div className="row gap">
        {m.picture ? <img className="monster-pic" src={portraitSrc(m.picture)} alt="" /> : null}
        <div className="grow">
          <label className="lbl">Name<input className="field" value={m.name} onChange={(e) => set("name", e.target.value)} placeholder="Goblin" /></label>
          <label className="lbl">Type<input className="field" value={m.type} onChange={(e) => set("type", e.target.value)} placeholder="Small Humanoid (Goblinoid), Neutral Evil" /></label>
          <label className="lbl">Book (folder)<input className="field" value={m.book || ""} onChange={(e) => set("book", e.target.value)} placeholder="empty = My monsters" list="bestiary-books" /></label>
          <label className="btn small">⬆ Picture<input type="file" accept="image/*" hidden onChange={(e) => upload(e.target.files?.[0])} /></label>
        </div>
      </div>
      <div className="row gap wrap center">
        <label className="lbl">Armor Class {num("ac")}</label>
        <input className="field grow" placeholder="(leather armor, shield)" value={m.ac_note} onChange={(e) => set("ac_note", e.target.value)} />
      </div>
      <div className="row gap wrap center">
        <label className="lbl">Hit Points {num("hp")}</label>
        <input className="field" style={{ width: 110 }} placeholder="2d6" value={m.hp_dice} onChange={(e) => set("hp_dice", e.target.value)} />
        <label className="lbl">Speed<input className="field" style={{ width: 120 }} value={m.speed} onChange={(e) => set("speed", e.target.value)} /></label>
        <label className="lbl">Initiative {num("init_bonus", 48)}</label>
      </div>
      <div className="stat-grid">
        {ABILITIES.map((k) => (
          <label key={k} className="stat-box"><span>{k}</span>
            <input className="field num" value={m.stats[k]} onChange={(e) => setStat(k, e.target.value)} />
            <span className="muted tiny">{mod(m.stats[k])}</span></label>
        ))}
      </div>
      {[["skills", "Skills", "Stealth +6"], ["senses", "Senses", "Darkvision 60 ft., Passive Perception 9"], ["languages", "Languages", "Common, Goblin"]].map(([k, label, ph]) => (
        <label key={k} className="lbl">{label}<input className="field" value={m[k]} placeholder={ph} onChange={(e) => set(k, e.target.value)} /></label>
      ))}
      <div className="row gap center">
        <label className="lbl">Challenge<input className="field" style={{ width: 70 }} value={m.cr} placeholder="1/4" onChange={(e) => set("cr", e.target.value)} /></label>
        <label className="lbl">XP {num("xp", 80)}</label>
      </div>
      <label className="lbl">Traits (one per line)</label>
      <textarea className="field" rows={3} value={m.traits} onChange={(e) => set("traits", e.target.value)} placeholder="Nimble Escape. The goblin can take the Disengage or Hide action as a bonus action." />
      <div className="lbl">Actions <span className="muted tiny">(fights use the first one with a to-hit bonus and damage)</span></div>
      {m.actions.map((a, i) => (
        <div key={i} className="action-row">
          <div className="row gap center wrap">
            <input className="field grow" style={{ minWidth: 110 }} value={a.name} onChange={(e) => setAct(i, "name", e.target.value)} placeholder="Scimitar" />
            <label className="tiny muted">To hit<input className="field num" style={{ width: 46 }} value={a.attack_bonus ?? ""} onChange={(e) => setAct(i, "attack_bonus", e.target.value)} /></label>
            <label className="tiny muted">Damage<input className="field num" style={{ width: 70 }} value={a.damage} onChange={(e) => setAct(i, "damage", e.target.value)} placeholder="1d6+2" /></label>
            <label className="tiny muted">Range (squares)<input className="field num" style={{ width: 44 }} value={a.range ?? 1} onChange={(e) => setAct(i, "range", e.target.value)} /></label>
            <button className="icon-btn" title="Remove" onClick={() => set("actions", m.actions.filter((_, j) => j !== i))}>✕</button>
          </div>
          <input className="field" value={a.text} onChange={(e) => setAct(i, "text", e.target.value)} placeholder="Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) slashing damage." />
        </div>
      ))}
      <button className="btn small" onClick={() => set("actions", [...m.actions, { name: "", attack_bonus: "", damage: "", range: 1, text: "" }])}>＋ Action</button>
      <label className="lbl">Notes (tactics, lore)</label>
      <textarea className="field" rows={2} value={m.notes} onChange={(e) => set("notes", e.target.value)} />
      <div className="row gap end">
        {onDelete && <button className="btn small danger" onClick={onDelete}>Delete</button>}
        <span className="grow" />
        <button className="btn small" onClick={onCancel}>Back</button>
        <button className="btn small primary" disabled={!m.name.trim()} onClick={() => onSave(m)}>💾 Save</button>
      </div>
    </div>
  );
}
