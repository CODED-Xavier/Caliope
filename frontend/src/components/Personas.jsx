import React, { useEffect, useState } from "react";
import { ask } from "../dialogs.jsx";
import { api } from "../api.js";
import HelpTip from "./HelpTip.jsx";

/** Start screen: load one of your saved characters, or save the one you are making. */
export default function PersonaBar({ player, lore, onLoad }) {
  const [list, setList] = useState([]);
  const [pick, setPick] = useState("");
  const [note, setNote] = useState("");
  const load = () => api.personas().then(setList).catch(() => {});
  useEffect(() => { load(); }, []);

  const use = (id) => {
    setPick(id);
    const found = list.find((x) => String(x.id) === String(id));
    if (found) { onLoad(found); setNote(`Loaded ${found.name}.`); }
  };
  const save = async () => {
    const name = (player?.name || "").trim();
    if (!name) { setNote("Give your character a name first."); return; }
    const same = list.find((x) => x.name.toLowerCase() === name.toLowerCase());
    if (same && !await ask.confirm(`Replace your saved persona "${same.name}"?`)) return;
    try {
      const body = { name, player, lore };
      const saved = same ? await api.updatePersona(same.id, body) : await api.createPersona(body);
      setNote(`Saved as "${saved.name}".`);
      load();
    } catch (e) { setNote(e.message); }
  };
  const remove = async () => {
    const found = list.find((x) => String(x.id) === String(pick));
    if (!found || !await ask.confirm(`Delete the persona "${found.name}"?`)) return;
    await api.deletePersona(found.id); setPick(""); load();
  };

  return (
    <div className="row gap center persona-bar">
      <span className="small">🎭 Personas <HelpTip id="personas" /></span>
      <select className="field grow" value={pick} onChange={(e) => use(e.target.value)}>
        <option value="">{list.length ? "Use a saved character…" : "No saved characters yet"}</option>
        {list.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
      </select>
      {pick && <button type="button" className="icon-btn" title="Delete this persona" onClick={remove}>🗑</button>}
      <button type="button" className="btn small" onClick={save} title="Keep this character (and your world additions) for other games">💾 Save as persona</button>
      {note && <span className="muted tiny">{note}</span>}
    </div>
  );
}
