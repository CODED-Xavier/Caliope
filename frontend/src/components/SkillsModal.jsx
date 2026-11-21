import React, { useEffect, useRef, useState } from "react";
import { ask } from "../dialogs.jsx";
import Modal from "./Modal.jsx";
import { api } from "../api.js";

export default function SkillsModal({ onClose }) {
  const [skills, setSkills] = useState([]);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  const load = () => api.skills().then(setSkills).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const run = async (fn, okText) => {
    setBusy(true); setError(""); setMsg("");
    try { const r = await fn(); if (r?.skills) setSkills(r.skills); setMsg(okText(r)); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <Modal title="Skills" onClose={onClose} wide>
      <p className="muted small">
        Skills are folders with a <code>SKILL.md</code>. Install them here, then attach up to 3 to a card in the card editor
        (there is a "Suggest" button that picks the best fit). The game works the same with none installed.
        Skill scripts are never run: only their text is used.
      </p>

      <h3>Installed ({skills.length})</h3>
      {skills.length === 0 && <div className="muted small">No skills installed.</div>}
      {skills.map((s) => (
        <div className="skill-row" key={s.name}>
          <input type="checkbox" checked={s.enabled} title="Enabled" onChange={(e) => api.toggleSkill(s.name, e.target.checked).then(setSkills).catch((er) => setError(er.message))} />
          <div className="grow">
            <div><strong>{s.name}</strong> <span className="muted tiny">{s.size} chars</span></div>
            <div className="muted small">{s.description || "(no description)"}</div>
          </div>
          <button className="icon-btn" title="Uninstall" onClick={async () => { if (await ask.confirm(`Uninstall ${s.name}?`)) api.deleteSkill(s.name).then(setSkills).catch((er) => setError(er.message)); }}>🗑</button>
        </div>
      ))}

      <h3>Install a skill</h3>
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); if (source.trim()) run(() => api.installSkill(source.trim()), (r) => `Installed: ${r.installed.join(", ")}`); }}>
        <input className="field grow" placeholder="GitHub link, .zip link, or a folder on this PC (C:\skills\my-skill)" value={source} onChange={(e) => setSource(e.target.value)} />
        <button className="btn primary" type="submit" disabled={busy}>{busy ? "Installing…" : "Install"}</button>
      </form>
      <div className="row gap center">
        <span className="muted small">or upload a .zip:</span>
        <input ref={fileRef} type="file" accept=".zip" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => api.uploadSkillZip(f), (r) => `Installed: ${r.installed.join(", ")}`); e.target.value = ""; }} />
      </div>
      {msg && <div className="ok-text small">✓ {msg}</div>}
      {error && <div className="error-text small">{error}</div>}
    </Modal>
  );
}
