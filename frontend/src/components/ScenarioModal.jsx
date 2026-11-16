import React, { useEffect, useState } from "react";
import Modal from "./Modal.jsx";
import { api } from "../api.js";
import { MODE_LABELS } from "../utils.js";

const BLANK = {
  name: "", mode: "gm_world", description: "", language: "", system_rules: "", world: "", tone: "", opening_message: "",
  player: { name: "Adventurer", class: "", race: "", level: 1, stats: { STR: 10, DEX: 10, CON: 10, INT: 10, WIS: 10, CHA: 10 }, hp: { current: 10, max: 10 }, ac: 10, gold: 0, inventory: [], location: "" },
  npcs: [], skills: { mode: "auto", allow: [], pinned: [] },
};

function Editor({ initial, id, onCancel, onSaved }) {
  const [d, setD] = useState({ ...BLANK, ...initial });
  const [playerJson, setPlayerJson] = useState(JSON.stringify(initial.player ?? BLANK.player, null, 2));
  const [idea, setIdea] = useState("");
  const [gen, setGen] = useState(false);
  const [error, setError] = useState("");
  const set = (k, v) => setD((p) => ({ ...p, [k]: v }));
  const setNpc = (i, k, v) => set("npcs", d.npcs.map((n, j) => (j === i ? { ...n, [k]: v } : n)));

  const generate = async () => {
    if (!idea.trim()) return;
    setGen(true); setError("");
    try {
      const r = await api.generateScenario({ idea, mode: d.mode, language: d.language || "en" });
      setD({ ...BLANK, ...r.data }); setPlayerJson(JSON.stringify(r.data.player ?? {}, null, 2));
    } catch (e) { setError(e.message); } finally { setGen(false); }
  };

  const save = async () => {
    setError("");
    let player;
    try { player = JSON.parse(playerJson || "{}"); } catch { setError("The player template is not valid JSON."); return; }
    if (!d.name.trim()) { setError("Give the scenario a name."); return; }
    const data = { ...d, player };
    try { const saved = id ? await api.updateScenario(id, data) : await api.createScenario(data); onSaved(saved); } catch (e) { setError(e.message); }
  };

  return (
    <>
      <div className="card">
        <div className="lbl">✨ Generate from an idea (the AI drafts everything; you can edit it below)</div>
        <textarea className="field" rows={2} value={idea} onChange={(e) => setIdea(e.target.value)} placeholder="e.g. A cyberpunk heist in a flooded city where I play a retired hacker" />
        <div className="row gap center">
          <button className="btn" onClick={generate} disabled={gen || !idea.trim()}>{gen ? "Generating… (can take a minute)" : "Generate"}</button>
          <span className="muted tiny">Uses the mode selected below.</span>
        </div>
      </div>

      <label className="lbl">Name</label>
      <input className="field" value={d.name} onChange={(e) => set("name", e.target.value)} />
      <div className="row gap">
        <div className="grow">
          <label className="lbl">Mode</label>
          <select className="field" value={d.mode} onChange={(e) => set("mode", e.target.value)}>
            {Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="grow">
          <label className="lbl">Language</label>
          <select className="field" value={d.language} onChange={(e) => set("language", e.target.value)}>
            <option value="">Use my settings</option>
            <option value="en">English</option>
            <option value="pt-BR">Português (Brasil)</option>
            <option value="auto">Same as I write</option>
          </select>
        </div>
        <div className="grow">
          <label className="lbl">Skills</label>
          <select className="field" value={d.skills?.mode || "auto"} onChange={(e) => set("skills", { ...(d.skills || {}), mode: e.target.value })}>
            <option value="auto">Automatic</option>
            <option value="manual">Only pinned</option>
            <option value="off">Off</option>
          </select>
        </div>
      </div>
      <p className="muted tiny">
        {d.mode === "gm_world" && "The AI is the Game Master and invents places and characters as you play."}
        {d.mode === "gm_cast" && "The AI is the Game Master and runs the cast you define below."}
        {d.mode === "character" && "The AI plays ONE character (the first one below). The story is about your relationship."}
      </p>
      <label className="lbl">Short description (shown in the picker)</label>
      <input className="field" value={d.description} onChange={(e) => set("description", e.target.value)} />
      <label className="lbl">World / setting</label>
      <textarea className="field" rows={4} value={d.world} onChange={(e) => set("world", e.target.value)} />
      {d.mode !== "character" && (<>
        <label className="lbl">Game rules</label>
        <textarea className="field" rows={5} value={d.system_rules} onChange={(e) => set("system_rules", e.target.value)} />
      </>)}
      <label className="lbl">Tone / style</label>
      <textarea className="field" rows={2} value={d.tone} onChange={(e) => set("tone", e.target.value)} />
      <label className="lbl">Opening message</label>
      <textarea className="field" rows={4} value={d.opening_message} onChange={(e) => set("opening_message", e.target.value)} />

      <div className="section-title">{d.mode === "character" ? "The character" : "Characters (NPCs)"}</div>
      {d.npcs.map((n, i) => (
        <div className="card" key={i}>
          <div className="row gap center">
            <input className="field grow" placeholder="Name" value={n.name} onChange={(e) => setNpc(i, "name", e.target.value)} />
            <label className="small">Relationship</label>
            <input className="field num" style={{ width: 64 }} value={n.relationship ?? 0} onChange={(e) => setNpc(i, "relationship", parseInt(e.target.value, 10) || 0)} />
            <button className="icon-btn" onClick={() => set("npcs", d.npcs.filter((_, j) => j !== i))}>✕</button>
          </div>
          <textarea className="field" rows={2} placeholder="Description / appearance / history" value={n.description || ""} onChange={(e) => setNpc(i, "description", e.target.value)} />
          <textarea className="field" rows={2} placeholder="Personality" value={n.personality || ""} onChange={(e) => setNpc(i, "personality", e.target.value)} />
          <input className="field" placeholder="Speech style (how they talk)" value={n.speech_style || ""} onChange={(e) => setNpc(i, "speech_style", e.target.value)} />
        </div>
      ))}
      <button className="btn small" onClick={() => set("npcs", [...d.npcs, { name: "", description: "", personality: "", speech_style: "", relationship: 0 }])}>＋ Add character</button>

      <details>
        <summary className="muted small">Starting character sheet (advanced, JSON)</summary>
        <textarea className="field mono" rows={10} value={playerJson} onChange={(e) => setPlayerJson(e.target.value)} />
      </details>

      {error && <div className="error-text small">{error}</div>}
      <div className="row gap end">
        <button className="btn" onClick={onCancel}>Back</button>
        <button className="btn primary" onClick={save}>Save scenario</button>
      </div>
    </>
  );
}

export default function ScenarioModal({ onClose, onStart }) {
  const [list, setList] = useState([]);
  const [selected, setSelected] = useState(null);
  const [playerName, setPlayerName] = useState("");
  const [view, setView] = useState("pick"); // pick | edit
  const [editing, setEditing] = useState(null); // {id, initial}
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  const load = async (selectId) => {
    try { const l = await api.scenarios(); setList(l); setSelected(selectId ?? ((cur) => cur ?? l[0]?.id)); } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, []);
  const sel = list.find((s) => s.id === selected);

  const edit = async (id) => {
    try { const full = await api.scenario(id); setEditing({ id, initial: full.data }); setView("edit"); } catch (e) { setError(e.message); }
  };
  const start = async () => {
    setStarting(true); setError("");
    try { await onStart(sel.id, playerName.trim() || undefined); } catch (e) { setError(e.message); setStarting(false); }
  };

  if (view === "edit") {
    return (
      <Modal title={editing?.id ? "Edit scenario" : "New scenario"} onClose={onClose} wide>
        <Editor initial={editing?.initial ?? BLANK} id={editing?.id} onCancel={() => setView("pick")} onSaved={(saved) => { setView("pick"); load(saved.id); }} />
      </Modal>
    );
  }

  return (
    <Modal title="New game" onClose={onClose} wide footer={
      <>
        {error && <span className="error-text small grow">{error}</span>}
        <input className="field" style={{ maxWidth: 220 }} placeholder="Your character's name (optional)" value={playerName} onChange={(e) => setPlayerName(e.target.value)} />
        <button className="btn primary" disabled={!sel || starting} onClick={start}>{starting ? "Starting…" : "Start game"}</button>
      </>
    }>
      <div className="scn-grid">
        {list.map((s) => (
          <div key={s.id} className={`scn ${s.id === selected ? "active" : ""}`} onClick={() => setSelected(s.id)}>
            <div className="row gap center">
              <div className="scn-name grow">{s.name}</div>
              <button className="icon-btn" title="Edit" onClick={(e) => { e.stopPropagation(); edit(s.id); }}>✎</button>
              <button className="icon-btn" title="Delete" onClick={(e) => { e.stopPropagation(); if (window.confirm(`Delete scenario "${s.name}"? Your saved games stay.`)) api.deleteScenario(s.id).then(() => load()).catch((er) => setError(er.message)); }}>🗑</button>
            </div>
            <div className="tag">{MODE_LABELS[s.mode]}</div>
            <div className="muted small">{s.description}</div>
          </div>
        ))}
        <div className="scn new" onClick={() => { setEditing({ id: null, initial: BLANK }); setView("edit"); }}>
          <div className="scn-plus">＋</div>
          <div>Create a scenario</div>
          <div className="muted small">Write your own or let the AI draft one from an idea</div>
        </div>
      </div>
    </Modal>
  );
}
