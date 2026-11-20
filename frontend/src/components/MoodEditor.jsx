import React, { useRef, useState } from "react";
import { api } from "../api.js";
import { STANDARD_MOODS, portraitSrc } from "../portraits.js";

/**
 * Pictures of one character: a main picture plus one per mood (Standard, Happy, Sad, Angry, Disgusted, Blushing).
 * Each slot takes a link or a picture from this PC. Empty mood slots fall back to the main picture.
 */
export default function MoodEditor({ portraits, onChange, compact, mainOnly }) {
  const pics = { default: "", moods: [], ...(portraits || {}) };
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);
  const fileRef = useRef(null);
  const target = useRef(null);

  const urlFor = (n) => (n === 0 ? pics.default : (pics.moods.find((m) => m.n === n) || {}).url || "");
  const setSlot = (n, url) => {
    if (n === 0) return onChange({ ...pics, default: url });
    const label = (STANDARD_MOODS.find(([k]) => k === n) || [n, `Mood ${n}`])[1];
    const others = pics.moods.filter((m) => m.n !== n);
    const moods = url ? [...others, { n, label: (pics.moods.find((m) => m.n === n) || {}).label || label, url }] : others;
    onChange({ ...pics, moods: moods.sort((a, b) => (a.n ?? 99) - (b.n ?? 99)) });
  };
  const askLink = (n) => {
    const url = window.prompt("Paste the picture's link (https://…):", urlFor(n));
    if (url === null) return;
    if (url && !/^https?:\/\//i.test(url.trim())) { setError("The link must start with http:// or https://"); return; }
    setError(""); setSlot(n, url.trim());
  };
  const upload = async (file) => {
    const n = target.current;
    if (!file || n === null) return;
    setBusy(n); setError("");
    try { setSlot(n, (await api.uploadPicture(file)).url); } catch (e) { setError(e.message); } finally { setBusy(null); }
  };
  const pick = (n) => { target.current = n; fileRef.current.value = ""; fileRef.current.click(); };

  const slots = mainOnly ? [[0, "Picture"]] : [[0, "Main"], ...STANDARD_MOODS];
  return (
    <div className={`mood-editor ${compact ? "compact" : ""}`}>
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={(e) => upload(e.target.files?.[0])} />
      {slots.map(([n, label]) => {
        const url = urlFor(n);
        const shown = url || (n !== 0 ? pics.default : "");
        return (
          <div key={n} className={`mood-slot ${url ? "" : "empty"}`}>
            <div className="mood-pic" title={url || (n ? "Uses the main picture" : "No picture")}>
              {shown ? <img src={portraitSrc(shown)} alt={label} loading="lazy" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} /> : <span className="muted">?</span>}
              {busy === n && <span className="spinner mood-busy" />}
            </div>
            <div className="mood-label tiny">{label}</div>
            <div className="mood-btns">
              <button type="button" className="icon-btn" title="Choose a picture on this PC" onClick={() => pick(n)}>⬆</button>
              <button type="button" className="icon-btn" title="Paste a link" onClick={() => askLink(n)}>🔗</button>
              {url && <button type="button" className="icon-btn" title="Remove" onClick={() => setSlot(n, "")}>✕</button>}
            </div>
          </div>
        );
      })}
      {error && <div className="error-text tiny mood-error">{error}</div>}
    </div>
  );
}
