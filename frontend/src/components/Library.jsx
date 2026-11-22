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
  useEffect(() => { api.libraryStatus().then(setStatus).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    const t = setTimeout(() => { api.librarySearch(type, q, edition).then((r) => setResults(r?.results || [])).catch((e) => setError(e.message)); }, 200);
    return () => clearTimeout(t);
  }, [type, q, edition]);
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
              <button key={`${r.source}-${r.name}-${r.class || ""}`} type="button" className={`lib-item ${open && open.name === r.name && open.source === r.source ? "on" : ""}`} onClick={() => show(r)}>
                <div className="lib-name">{r.name}<span className="lib-src">{r.source}{r.srd ? " · SRD" : ""}</span></div>
                <div className="lib-meta">{[r.class, r.level !== undefined && r.level !== null ? `level ${r.level}` : "", r.race].filter(Boolean).join(" · ")}</div>
                <div className="lib-sum">{r.summary}</div>
              </button>
            ))}
          </div>
          <div className="library-entry">
            {open ? (
              <>
                <h3 className="lib-title">{open.title}</h3>
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
          <div>{"Contains material from the System Reference Document 5.1 and 5.2 by Wizards of the Coast (CC-BY-4.0). Everything else comes from your own files and stays on your PC."}</div>
        </div>
      </div>
    </Modal>
  );
}
