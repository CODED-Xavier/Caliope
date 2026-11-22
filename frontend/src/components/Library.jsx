import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import Modal from "./Modal.jsx";

const SECTIONS = [
  ["class", "Classes"], ["subclass", "Subclasses"], ["classFeature", "Class features"], ["race", "Races"], ["background", "Backgrounds"],
  ["feat", "Feats"], ["optionalfeature", "Options"], ["spell", "Spells"], ["baseitem", "Weapons & armour"], ["item", "Magic items"],
];

/** The D&D 5e library: the SRD built in plus your own 5e.tools files (data/compendium/dnd5e). */
export default function Library({ onClose }) {
  const [type, setType] = useState("spell");
  const [edition, setEdition] = useState("2014");
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [choices, setChoices] = useState(null);
  const [showHidden, setShowHidden] = useState(false);
  const [booksOpen, setBooksOpen] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => { api.libraryStatus().then(setStatus).catch((e) => setError(e.message)); api.libraryChoices().then(setChoices).catch(() => {}); }, []);
  useEffect(() => {
    const t = setTimeout(() => { api.librarySearch(type, q, edition, "", showHidden).then((r) => setResults(r?.results || [])).catch((e) => setError(e.message)); }, 200);
    return () => clearTimeout(t);
  }, [type, q, edition, showHidden, tick]);
  // your choices: an entry hidden from the builder and the lists (sheets that use it keep working), a book's rules list
  const saveChoices = async (next) => { try { setChoices(await api.saveLibraryChoices(next)); setTick((x) => x + 1); } catch (e) { setError(e.message); } };
  const keyOf = (r) => `${r.type || type}|${r.name}|${r.source}`;
  const isHidden = (r) => (choices?.hidden || []).includes(keyOf(r));
  const toggleHidden = (r) => saveChoices({ ...choices, hidden: isHidden(r) ? choices.hidden.filter((h) => h !== keyOf(r)) : [...(choices?.hidden || []), keyOf(r)] });
  const show = async (r) => { try { setOpen(await api.libraryEntry(r.type, r.source, r.name)); } catch (e) { setError(e.message); } };
  const reload = async () => { try { setStatus(await api.libraryReload()); setQ((x) => x); } catch (e) { setError(e.message); } };

  return (
    <Modal title="Library · D&D 5e" onClose={onClose} wide>
      <div className="library">
        <div className="library-bar">
          <label className="grow"><span className="lbl">Search</span>
            <input className="field big-touch" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Fireball, Second Wind, longsword…" /></label>
          <label><span className="lbl">Rules</span>
            <select className="field big-touch" value={edition} onChange={(e) => setEdition(e.target.value)}>
              <option value="2014">5e 2014</option><option value="2024">5e 2024</option>
            </select></label>
        </div>
        <div className="chip-row" role="tablist" aria-label="Sections">
          {SECTIONS.map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={type === k} className={`pill ${type === k ? "on" : ""}`} onClick={() => { setType(k); setOpen(null); }}>{label}</button>
          ))}
        </div>
        {error && <div className="error-text small">{error}</div>}
        <div className="library-body">
          <div className="library-list">
            {results.length === 0 && <div className="muted small pad">Nothing found.</div>}
            {results.map((r) => (
              <button key={`${r.source}-${r.name}-${r.class || ""}`} type="button" className={`lib-item ${open && open.name === r.name && open.source === r.source ? "on" : ""} ${r.hidden ? "is-hidden" : ""}`} onClick={() => show(r)}>
                <div className="lib-name">{r.name}<span className="lib-src">{r.source}{r.srd ? " · SRD" : ""}</span></div>
                <div className="lib-meta">{[r.class, r.level !== undefined && r.level !== null ? `level ${r.level}` : "", r.race].filter(Boolean).join(" · ")}</div>
                <div className="lib-sum">{r.summary}</div>
              </button>
            ))}
          </div>
          <div className="library-entry">
            {open ? (
              <>
                <div className="row gap center">
                  <h3 className="lib-title grow">{open.title}</h3>
                  {choices && <button type="button" className="btn small" onClick={() => toggleHidden({ ...open, type })}
                    title="Hidden entries leave the builder and the lists; a sheet that already uses one keeps it">{isHidden({ ...open, type }) ? "👁 Show it again" : "🙈 Hide from the lists"}</button>}
                </div>
                <div className="muted small">{`${open.source}${open.level !== undefined ? ` · level ${open.level}` : ""}`}</div>
                <div className="lib-text">{open.text}</div>
              </>
            ) : <div className="muted small pad">Pick an entry to read it.</div>}
          </div>
        </div>
        <div className="library-foot muted tiny">
          {status && `${status.entries} entries · ${status.files} files`}{status?.errors?.length ? ` · ${status.errors.length} files could not be read` : ""}
          {" · Your files: "}<span className="mono">{status?.folder}</span>
          {" "}<button type="button" className="link-btn" onClick={reload}>Reload</button>
          {" · "}<label className="tiny"><input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />{` Show hidden (${(choices?.hidden || []).length})`}</label>
          {" · "}<button type="button" className="link-btn" onClick={() => setBooksOpen((v) => !v)}>Books and rules</button>
          {booksOpen && choices && (
            <div className="lib-books">
              <div className="muted tiny">Which rules list each book's races, feats and items appear in. The 2014 and 2024 core books are fixed; the rest follows the book's own marks unless you choose.</div>
              {(choices.books || []).map((b) => (
                <label key={b} className="lib-book"><span className="mono">{b}</span>
                  <select className="field" value={(choices.editions || {})[b] || ""} onChange={(e) => {
                    const ed = { ...(choices.editions || {}) }; if (e.target.value) ed[b] = e.target.value; else delete ed[b];
                    saveChoices({ ...choices, editions: ed });
                  }}>
                    <option value="">as marked</option><option value="2014">5e 2014</option><option value="2024">5e 2024</option><option value="both">both</option>
                  </select>
                </label>
              ))}
            </div>
          )}
          <div>{"Contains material from the System Reference Document 5.1 and 5.2 by Wizards of the Coast (CC-BY-4.0). Everything else comes from your own files and stays on your PC."}</div>
        </div>
      </div>
    </Modal>
  );
}

export const DRAG_TYPE = "application/x-caliope-5e";
const PICK_SECTIONS = [["spell", "Spells"], ["baseitem", "Weapons & armour"], ["item", "Magic items"], ["feat", "Feats"], ["optionalfeature", "Options"],
  ["class", "Class"], ["race", "Race"], ["background", "Background"]];

/** The compact Library beside a 5e sheet: drag a row onto the sheet, or press ＋. */
export function LibraryPicker({ edition = "2014", onAdd, busy }) {
  const [type, setType] = useState("spell");
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const t = setTimeout(() => { api.librarySearch(type, q, edition).then((r) => { setResults((r?.results || []).slice(0, 40)); setError(""); }).catch((e) => setError(e.message)); }, 200);
    return () => clearTimeout(t);
  }, [type, q, edition]);
  const toggle = async (r) => {
    if (open && open.name === r.name && open.source === r.source) { setOpen(null); return; }
    try { setOpen(await api.libraryEntry(r.type || type, r.source, r.name)); } catch (e) { setError(e.message); }
  };
  return (
    <div className="lib-picker">
      <input className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the Library…" aria-label="Search the Library" />
      <div className="chip-row tight">
        {PICK_SECTIONS.map(([k, label]) => (
          <button key={k} type="button" className={`pill small ${type === k ? "on" : ""}`} onClick={() => { setType(k); setOpen(null); }}>{label}</button>
        ))}
      </div>
      {error && <div className="error-text tiny">{error}</div>}
      <div className="lib-picker-list">
        {results.length === 0 && <div className="muted tiny pad">Nothing found.</div>}
        {results.map((r) => {
          const ref = { type: r.type || type, name: r.name, source: r.source };
          const isOpen = open && open.name === r.name && open.source === r.source;
          return (
            <div key={`${r.source}-${r.name}-${r.class || ""}`} className="lib-row" draggable
              onDragStart={(e) => { e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(ref)); e.dataTransfer.effectAllowed = "copy"; }}
              title="Drag onto the sheet, or press ＋">
              <span className="lib-grip" aria-hidden="true">⠿</span>
              <button type="button" className="lib-row-main" onClick={() => toggle(r)}>
                <span className="lib-name">{r.name}</span>
                <span className="lib-src">{[r.level !== undefined && r.level !== null ? `lv ${r.level}` : "", r.source].filter(Boolean).join(" · ")}</span>
              </button>
              <button type="button" className="icon-btn add" disabled={busy} onClick={() => onAdd(ref)} title="Add to the sheet">＋</button>
              {isOpen && <div className="lib-row-text small">{open.text}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
