import React, { useEffect, useRef, useState } from "react";
import { ask } from "../dialogs.jsx";
import Modal from "./Modal.jsx";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";

const SYSTEMS = { dnd5e: "D&D 5e", vtm5: "Vampire: the Masquerade 5e", other: "Other" };

function BookCard({ book, onChanged, onDelete }) {
  const [rules, setRules] = useState(book.house_rules);
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState("");
  useEffect(() => setRules(book.house_rules), [book.house_rules]);
  const save = async () => {
    try { await api.updateRulebook(book.id, { house_rules: rules }); setSaved("Saved"); setTimeout(() => setSaved(""), 1500); onChanged(); }
    catch (e) { setSaved(e.message); }
  };
  const info = book.info || {};
  return (
    <div className={`card book ${book.status}`}>
      <div className="row gap center">
        <div className="grow">
          <div className="book-name">📖 {book.name} <span className="tag">{SYSTEMS[book.system] || "Other"}</span></div>
          {book.status === "processing" && (
            <>
              <div className="progress"><div style={{ width: `${Math.round(book.progress * 100)}%` }} /></div>
              <div className="muted tiny">{book.message || "Reading…"}</div>
            </>
          )}
          {book.status === "ready" && <div className="muted tiny">{book.message}{info.ocr_pages ? ` · ${info.ocr_pages} pages read with OCR` : ""}</div>}
          {book.status === "error" && <div className="error-text tiny">{book.message}</div>}
        </div>
        {book.status === "ready" && <button className="btn small" onClick={() => setOpen(!open)}>House rules{book.house_rules ? " ✓" : ""}</button>}
        <button className="icon-btn" title="Delete this rulebook" onClick={async () => { if (await ask.confirm(`Delete "${book.name}"? Cards that use it simply stop using it.`)) onDelete(book.id); }}>🗑</button>
      </div>
      {open && (
        <div className="house-rules">
          <label className="lbl">House rules <HelpTip id="house_rules" /></label>
          <textarea className="field" rows={4} value={rules} onChange={(e) => setRules(e.target.value)}
            placeholder="e.g. Critical hits deal maximum damage. Potions of healing are a bonus action." />
          <div className="row gap center end"><span className="muted tiny">{saved}</span><button className="btn small primary" onClick={save}>Save</button></div>
        </div>
      )}
    </div>
  );
}

export default function RulebooksModal({ onClose }) {
  const [books, setBooks] = useState([]);
  const [ocr, setOcr] = useState(true);
  const [error, setError] = useState("");
  const [system, setSystem] = useState("dnd5e");
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const fileRef = useRef(null);

  const load = async () => {
    try { const r = await api.rulebooks(); setBooks(r.books); setOcr(r.ocr_available); } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, []);
  // While a book is being read, refresh its progress.
  useEffect(() => {
    if (!books.some((b) => b.status === "processing")) return undefined;
    const t = setTimeout(load, 1500);
    return () => clearTimeout(t);
  }, [books]);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true); setError("");
    try { await api.uploadRulebook(file, name.trim() || file.name.replace(/\.[^.]+$/, ""), system); setName(""); await load(); }
    catch (e) { setError(e.message); } finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const search = async (e) => {
    e.preventDefault();
    if (!q.trim()) return;
    try { setResults((await api.searchRulebooks(q.trim())).results); } catch (er) { setError(er.message); }
  };

  return (
    <Modal title="Rulebooks" onClose={onClose} wide>
      <p className="muted small">
        Import a rulebook once. During play, the Aedo gets only the one or two passages that fit the moment, so the book never fills the
        AI's memory. Attach books to a card in the card editor (✎ → Rulebooks). <HelpTip id="rulebooks" />
      </p>

      <div className="card">
        <div className="row gap center wrap">
          <input className="field grow" placeholder="Name (optional, e.g. D&D SRD 5.2)" value={name} onChange={(e) => setName(e.target.value)} />
          <select className="field" value={system} onChange={(e) => setSystem(e.target.value)}>
            {Object.entries(SYSTEMS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="btn primary" disabled={uploading} onClick={() => fileRef.current?.click()}>{uploading ? "Uploading…" : "⇪ Import PDF or text"}</button>
          <input ref={fileRef} type="file" hidden accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" onChange={(e) => upload(e.target.files?.[0])} />
        </div>
        <div className="muted tiny">
          PDF with selectable text works best. You can also paste the rules into a .txt or .md file (lines starting with # become headings).
          {!ocr && <> Scanned books (pages that are pictures) need the free <a href="https://github.com/UB-Mannheim/tesseract/wiki" target="_blank" rel="noreferrer">Tesseract OCR</a> installed; restart the app after installing.</>}
          {ocr && <> OCR is installed, so scanned pages are read too (slower: about 2 to 4 seconds per page).</>}
        </div>
      </div>

      {error && <div className="error-text small">{error}</div>}
      {books.length === 0 && <div className="muted small">No rulebooks yet. A good start: the free D&D System Reference Document 5.2 (search "SRD 5.2" on dndbeyond.com, it is a PDF under the Creative Commons license).</div>}
      {books.map((b) => <BookCard key={b.id} book={b} onChanged={load} onDelete={async (id) => { await api.deleteRulebook(id).catch((e) => setError(e.message)); load(); }} />)}

      {books.some((b) => b.status === "ready") && (
        <>
          <div className="section-title">Look something up</div>
          <form className="row gap" onSubmit={search}>
            <input className="field grow" placeholder="e.g. grapple, falling damage, frenzy" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn" type="submit">Search</button>
          </form>
          {results && results.length === 0 && <div className="muted small">Nothing found.</div>}
          {results && results.map((r) => (
            <div className="card rule-hit" key={r.id}>
              <div className="small"><strong>{r.heading || "(no heading)"}</strong> <span className="muted tiny">· {r.book}, page {r.page}</span></div>
              <div className="small rule-text">{r.text}</div>
            </div>
          ))}
        </>
      )}
    </Modal>
  );
}
