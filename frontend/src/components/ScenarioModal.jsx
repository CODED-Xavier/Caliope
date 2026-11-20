import React, { useEffect, useMemo, useState } from "react";
import Modal from "./Modal.jsx";
import HelpTip from "./HelpTip.jsx";
import KindPicker from "./KindPicker.jsx";
import { api } from "../api.js";
import { KIND_LABELS, MODE_LABELS } from "../utils.js";

const LOOKS = [["race", "Race / species"], ["hair", "Hair"], ["eyes", "Eyes"], ["build", "Build"], ["skin", "Skin"], ["outfit", "Style / outfit"], ["extra", "Other details"]];
const MAX_SKILLS = 3;

const BLANK = {
  name: "", mode: "gm_world", kind: "roleplay", features: {}, description: "", language: "", system_rules: "", world: "", tone: "", opening_message: "",
  species: [],
  player: { name: "Adventurer", class: "", race: "", level: 1, stats: { STR: 10, DEX: 10, CON: 10, INT: 10, WIS: 10, CHA: 10 }, hp: { current: 10, max: 10 }, ac: 10, gold: 0, inventory: [], location: "" },
  npcs: [], skills: { attached: [] },
};

function SkillPicker({ attached, onChange, cardText }) {
  const [skills, setSkills] = useState([]);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api.skills().then(setSkills).catch(() => {}); }, []);
  const shown = useMemo(() => {
    const f = filter.toLowerCase();
    return skills.filter((s) => s.enabled && (!f || s.name.toLowerCase().includes(f) || s.description.toLowerCase().includes(f))).slice(0, 40);
  }, [skills, filter]);
  const toggle = (name) => {
    if (attached.includes(name)) onChange(attached.filter((n) => n !== name));
    else if (attached.length < MAX_SKILLS) onChange([...attached, name]);
  };
  const suggest = async () => {
    setBusy(true); setError(""); setNote("");
    try {
      const got = await api.suggestSkills(cardText, MAX_SKILLS);
      if (got.length === 0) { setNote("No installed skill seems to fit this card."); }
      else { onChange(got.map((g) => g.name)); setNote(`Suggested by ${got[0].source === "ai" ? "the AI" : "keyword matching"}: ${got.map((g) => g.name).join(", ")}`); }
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <>
      <div className="section-title">Skills for this card <HelpTip id="card_skills" /> <span className="muted tiny">({attached.length}/{MAX_SKILLS})</span></div>
      <div className="row gap center">
        <input className="field grow" placeholder={`Search your ${skills.length} skills…`} value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button type="button" className="btn small" onClick={suggest} disabled={busy || skills.length === 0}>{busy ? "Asking…" : "✨ Suggest"}</button>
      </div>
      {note && <div className="muted small">{note}</div>}
      {error && <div className="error-text small">{error}</div>}
      {attached.length > 0 && (
        <div className="chips">{attached.map((n) => <button type="button" key={n} className="chip removable" onClick={() => toggle(n)} title="Remove">{n} ✕</button>)}</div>
      )}
      <div className="skill-pick">
        {skills.length === 0 && <div className="muted small">No skills installed. The card works fine without them.</div>}
        {shown.map((s) => (
          <label key={s.name} className={`skill-opt ${!attached.includes(s.name) && attached.length >= MAX_SKILLS ? "dim" : ""}`}>
            <input type="checkbox" checked={attached.includes(s.name)} onChange={() => toggle(s.name)} />
            <span><strong>{s.name}</strong> <span className="muted tiny">{s.description}</span></span>
          </label>
        ))}
      </div>
    </>
  );
}

/* ------------------------------------------------------------ card import */
function ImportView({ onCancel, onImported }) {
  const [card, setCard] = useState(null);
  const [preview, setPreview] = useState(null);
  const [name, setName] = useState("");
  const [skip, setSkip] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const readFile = async (file) => {
    setError(""); setPreview(null);
    if (!file) return;
    try {
      const obj = JSON.parse(await file.text());
      const r = await api.previewCard(obj);
      setCard(obj); setPreview(r); setName(r.scenario.name); setSkip([]);
    } catch (e) {
      setError(e instanceof SyntaxError ? "This file is not valid JSON. Character cards saved as PNG images are not supported yet: export the card as JSON." : e.message);
    }
  };
  const save = async () => {
    setBusy(true); setError("");
    try { onImported(await api.importCard(card, skip, name)); } catch (e) { setError(e.message); setBusy(false); }
  };
  const sc = preview?.scenario;
  const sm = preview?.summary;
  const toggle = (n) => setSkip(skip.includes(n) ? skip.filter((x) => x !== n) : [...skip, n]);

  return (
    <>
      <p className="muted small">Import a character card in JSON format (Character Card V2, the format used by SillyTavern and most card sites), or a card exported from this app.</p>
      <input type="file" accept=".json,application/json" onChange={(e) => readFile(e.target.files?.[0])} />
      {error && <div className="error-text small">{error}</div>}
      {preview && (
        <>
          <label className="lbl">Name</label>
          <input className="field" value={name} onChange={(e) => setName(e.target.value)} />
          <div className="import-facts">
            <span className="tag">{MODE_LABELS[sc.mode]}</span>
            <span className="tag">{sm.lorebook_entries} lorebook entries</span>
            <span className="tag">{sm.characters} characters</span>
            <span className="tag">{sm.characters_with_portraits} with portraits</span>
            <span className="tag" title="Description + reminders + examples, sent every turn">~{sm.fixed_tokens} fixed tokens</span>
          </div>
          {preview.warnings.length > 0 && <ul className="import-notes small">{preview.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
          {sc.npcs.length > 0 && (
            <>
              <div className="section-title">Characters to import <span className="muted tiny">(untick to leave out)</span></div>
              <div className="import-cast">
                {sc.npcs.map((n) => (
                  <label key={n.name} className="check small">
                    <input type="checkbox" checked={!skip.includes(n.name)} onChange={() => toggle(n.name)} />
                    {n.name}{n.portraits?.moods?.length ? <span className="muted tiny"> · {n.portraits.moods.length} portraits</span> : null}
                  </label>
                ))}
              </div>
            </>
          )}
          <div className="muted tiny">After importing you can edit everything with ✎, including the card texts and the lorebook.</div>
        </>
      )}
      <div className="row gap end">
        <button className="btn" onClick={onCancel}>Back</button>
        <button className="btn primary" onClick={save} disabled={!preview || busy || !name.trim()}>{busy ? "Importing…" : "Import card"}</button>
      </div>
    </>
  );
}

/* ---------------------------------------------------------- card texts / lorebook */
const INFO_FIELDS = [
  ["description", "Description", 6], ["scenario", "Scenario", 3], ["personality", "Personality", 3],
  ["system_prompt", "Extra instructions (system prompt)", 3], ["post_history", "Reminders (sent after the story; may contain the INFO template)", 6],
  ["example_messages", "Example messages (writing style)", 4],
];

function InformationEditor({ info, onChange }) {
  const i = info || {};
  const set = (k, v) => onChange({ ...i, [k]: v });
  const used = INFO_FIELDS.filter(([k]) => (i[k] || "").trim());
  return (
    <details>
      <summary className="muted small">Card texts <HelpTip id="card_information" /> {used.length > 0 && <span className="tiny">({used.length} filled)</span>}</summary>
      {INFO_FIELDS.map(([k, label, rows]) => (
        <React.Fragment key={k}>
          <label className="lbl">{label} <span className="muted tiny">~{Math.ceil((i[k] || "").length / 4)} tokens</span></label>
          <textarea className="field" rows={rows} value={i[k] || ""} onChange={(e) => set(k, e.target.value)} />
        </React.Fragment>
      ))}
      <div className="set-row">
        <div className="set-label">Status block every N replies <HelpTip id="status_every" /></div>
        <div className="set-control">
          <select className="field" value={i.status_every ?? 0} onChange={(e) => set("status_every", parseInt(e.target.value, 10))}>
            {[0, 1, 2, 3, 4, 5, 6, 8, 10].map((n) => <option key={n} value={n}>{n === 0 ? "Never" : n === 1 ? "Every reply" : `Every ${n} replies`}</option>)}
          </select>
        </div>
      </div>
    </details>
  );
}

const keysText = (keys) => (keys || []).join(", ");
const parseKeys = (t) => t.split(",").map((x) => x.trim()).filter(Boolean);

function LorebookEditor({ book, onChange }) {
  const b = { scan_depth: 4, token_budget: 800, entries: [], ...(book || {}) };
  const [filter, setFilter] = useState("");
  const setEntry = (idx, patch) => onChange({ ...b, entries: b.entries.map((e, j) => (j === idx ? { ...e, ...patch } : e)) });
  const add = () => onChange({ ...b, entries: [...b.entries, { id: Date.now(), name: "", keys: [], secondary_keys: [], content: "", enabled: true, constant: false, selective: false, case_sensitive: false, priority: 0, insertion_order: b.entries.length }] });
  const f = filter.toLowerCase();
  return (
    <details>
      <summary className="muted small">Lorebook <HelpTip id="lorebook" /> <span className="tiny">({b.entries.length} entries)</span></summary>
      <div className="row gap center">
        <input className="field grow" placeholder="Search entries…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <label className="small">Scan last <input className="field num" style={{ width: 48 }} value={b.scan_depth} onChange={(e) => onChange({ ...b, scan_depth: parseInt(e.target.value, 10) || 1 })} /> messages</label>
      </div>
      {b.entries.map((e, idx) => (!f || `${e.name} ${keysText(e.keys)} ${e.content}`.toLowerCase().includes(f)) && (
        <div className={`card lore-entry ${e.enabled ? "" : "dim"}`} key={e.id ?? idx}>
          <div className="row gap center">
            <input className="field grow" placeholder="Entry name" value={e.name || ""} onChange={(ev) => setEntry(idx, { name: ev.target.value })} />
            <label className="check small"><input type="checkbox" checked={e.enabled} onChange={(ev) => setEntry(idx, { enabled: ev.target.checked })} />On</label>
            <label className="check small" title="Always included, keywords or not"><input type="checkbox" checked={e.constant} onChange={(ev) => setEntry(idx, { constant: ev.target.checked })} />Always</label>
            <button className="icon-btn" title="Delete entry" onClick={() => onChange({ ...b, entries: b.entries.filter((_, j) => j !== idx) })}>✕</button>
          </div>
          <input className="field" placeholder="Keywords, separated by commas" defaultValue={keysText(e.keys)} onBlur={(ev) => setEntry(idx, { keys: parseKeys(ev.target.value) })} />
          <textarea className="field" rows={3} value={e.content} onChange={(ev) => setEntry(idx, { content: ev.target.value })} />
          <div className="muted tiny">~{Math.ceil((e.content || "").length / 4)} tokens when triggered</div>
        </div>
      ))}
      <button className="btn small" onClick={add}>＋ Add entry</button>
    </details>
  );
}

function Editor({ initial, id, onCancel, onSaved }) {
  const [d, setD] = useState({ ...BLANK, ...initial, features: initial.features || {}, skills: { attached: initial.skills?.attached || initial.skills?.pinned || [] } });
  const [playerJson, setPlayerJson] = useState(JSON.stringify(initial.player ?? BLANK.player, null, 2));
  const [speciesText, setSpeciesText] = useState((initial.species || []).join(", "));
  const [idea, setIdea] = useState("");
  const [npcFilter, setNpcFilter] = useState("");
  const [gen, setGen] = useState(false);
  const [error, setError] = useState("");
  const set = (k, v) => setD((p) => ({ ...p, [k]: v }));
  const setNpc = (i, k, v) => set("npcs", d.npcs.map((n, j) => (j === i ? { ...n, [k]: v } : n)));
  const setLook = (i, k, v) => set("npcs", d.npcs.map((n, j) => (j === i ? { ...n, appearance: { ...(n.appearance || {}), [k]: v } } : n)));
  const setFeature = (k, v) => {
    const f = { ...d.features };
    if (v === "" || v === undefined) delete f[k]; else f[k] = v;
    set("features", f);
  };
  const cardText = [d.name, d.description, d.world, d.tone, ...d.npcs.map((n) => `${n.name} ${n.personality || ""}`)].join(". ");

  const generate = async () => {
    if (!idea.trim()) return;
    setGen(true); setError("");
    try {
      const r = await api.generateScenario({ idea, mode: d.mode, kind: d.kind, language: d.language || "en" });
      setD({ ...BLANK, ...r.data, features: r.data.features || {}, skills: { attached: [] } });
      setPlayerJson(JSON.stringify(r.data.player ?? {}, null, 2));
      setSpeciesText((r.data.species || []).join(", "));
    } catch (e) { setError(e.message); } finally { setGen(false); }
  };

  const save = async () => {
    setError("");
    let player;
    try { player = JSON.parse(playerJson || "{}"); } catch { setError("The starting character sheet is not valid JSON."); return; }
    if (!d.name.trim()) { setError("Give the card a name."); return; }
    const species = speciesText.split(",").map((x) => x.trim()).filter(Boolean);
    const data = { ...d, player, species };
    try { const saved = id ? await api.updateScenario(id, data) : await api.createScenario(data); onSaved(saved); } catch (e) { setError(e.message); }
  };

  return (
    <>
      <div className="section-title">Card type <HelpTip id="card_kind" /></div>
      <KindPicker value={d.kind} onChange={(k) => set("kind", k)} />

      <div className="card">
        <div className="lbl">✨ Generate from an idea (the AI drafts everything; you can edit it below)</div>
        <textarea className="field" rows={2} value={idea} onChange={(e) => setIdea(e.target.value)} placeholder="e.g. A fantasy academy where four students keep a dangerous secret" />
        <div className="row gap center">
          <button className="btn" onClick={generate} disabled={gen || !idea.trim()}>{gen ? "Generating… (can take a minute)" : "Generate"}</button>
          <span className="muted tiny">Uses the card type and mode selected here.</span>
        </div>
      </div>

      <label className="lbl">Name</label>
      <input className="field" value={d.name} onChange={(e) => set("name", e.target.value)} />
      <div className="row gap">
        <div className="grow">
          <label className="lbl">Who the AI plays</label>
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
      <label className="lbl">Races or species in this world <HelpTip id="species" /></label>
      <input className="field" placeholder="Elf, Dwarf, Tiefling (empty = everyone is human)" value={speciesText} onChange={(e) => setSpeciesText(e.target.value)} />
      {d.mode !== "character" && (<>
        <label className="lbl">Game rules</label>
        <textarea className="field" rows={5} value={d.system_rules} onChange={(e) => set("system_rules", e.target.value)} />
      </>)}
      <label className="lbl">Tone / style</label>
      <textarea className="field" rows={2} value={d.tone} onChange={(e) => set("tone", e.target.value)} />
      <label className="lbl">Opening message</label>
      <textarea className="field" rows={4} value={d.opening_message} onChange={(e) => set("opening_message", e.target.value)} />

      <div className="section-title">{d.mode === "character" ? "The character" : "Characters (NPCs)"} <span className="muted tiny">({d.npcs.length})</span></div>
      {d.npcs.length > 8 && <div className="row gap center"><input className="field grow" placeholder="Find a character…" value={npcFilter} onChange={(e) => setNpcFilter(e.target.value)} /></div>}
      {d.npcs.map((n, i) => (npcFilter && !n.name.toLowerCase().includes(npcFilter.toLowerCase())) ? null : (
        <div className="card" key={i}>
          <div className="row gap center">
            <input className="field grow" placeholder="Name" value={n.name} onChange={(e) => setNpc(i, "name", e.target.value)} />
            <label className="small">Relationship</label>
            <input className="field num" style={{ width: 64 }} value={n.relationship ?? 0} onChange={(e) => setNpc(i, "relationship", parseInt(e.target.value, 10) || 0)} />
            <button className="icon-btn" onClick={() => set("npcs", d.npcs.filter((_, j) => j !== i))}>✕</button>
          </div>
          <textarea className="field" rows={2} placeholder="Description / history" value={n.description || ""} onChange={(e) => setNpc(i, "description", e.target.value)} />
          <textarea className="field" rows={2} placeholder="Personality" value={n.personality || ""} onChange={(e) => setNpc(i, "personality", e.target.value)} />
          <input className="field" placeholder="Speech style (how they talk)" value={n.speech_style || ""} onChange={(e) => setNpc(i, "speech_style", e.target.value)} />
          <div className="lbl">Looks <HelpTip id="appearance" /></div>
          <div className="looks-grid">
            {LOOKS.map(([key, label]) => (
              <input key={key} className="field" placeholder={label} value={(n.appearance || {})[key] || ""} onChange={(e) => setLook(i, key, e.target.value)} />
            ))}
          </div>
          <div className="row gap center">
            <input className="field grow" placeholder="Portrait link (https://…)" value={n.portraits?.default || ""}
              onChange={(e) => setNpc(i, "portraits", { moods: [], ...(n.portraits || {}), default: e.target.value })} />
            {n.portraits?.moods?.length > 0 && <span className="muted tiny">+{n.portraits.moods.length} moods</span>}
            <HelpTip id="portraits" />
          </div>
          <label className="check small"><input type="checkbox" checked={n.in_prompt !== false} onChange={(e) => setNpc(i, "in_prompt", e.target.checked)} />
            Profile always in the prompt <HelpTip id="in_prompt" /></label>
        </div>
      ))}
      <button className="btn small" onClick={() => set("npcs", [...d.npcs, { name: "", description: "", personality: "", speech_style: "", relationship: 0, appearance: {} }])}>＋ Add character</button>

      <InformationEditor info={d.information} onChange={(v) => set("information", v)} />
      <LorebookEditor book={d.lorebook} onChange={(v) => set("lorebook", v)} />

      <SkillPicker attached={d.skills.attached} onChange={(a) => set("skills", { attached: a })} cardText={cardText} />

      <details>
        <summary className="muted small">Advanced: what the AI tracks on this card</summary>
        <div className="set-row">
          <div className="set-label">What the AI tracks <HelpTip id="tracker" /><div className="muted tiny">Empty = the default of the card type</div></div>
          <div className="set-control">
            <select className="field" value={d.features.tracker || ""} onChange={(e) => setFeature("tracker", e.target.value)}>
              <option value="">Default for {KIND_LABELS[d.kind]}</option>
              <option value="off">Nothing</option>
              <option value="lite">Light (relationships, characters, memories)</option>
              <option value="full">Full (also HP, gold, items, quests)</option>
            </select>
          </div>
        </div>
        <div className="set-row">
          <div className="set-label">Track every N replies <HelpTip id="tracker_interval" /></div>
          <div className="set-control">
            <select className="field" value={d.features.tracker_interval || ""} onChange={(e) => setFeature("tracker_interval", e.target.value ? parseInt(e.target.value, 10) : "")}>
              <option value="">Default for {KIND_LABELS[d.kind]}</option>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n === 1 ? "Every reply" : `Every ${n} replies`}</option>)}
            </select>
          </div>
        </div>
      </details>

      <details>
        <summary className="muted small">Starting character sheet (advanced, JSON)</summary>
        <textarea className="field mono" rows={10} value={playerJson} onChange={(e) => setPlayerJson(e.target.value)} />
      </details>

      {error && <div className="error-text small">{error}</div>}
      <div className="row gap end">
        <button className="btn" onClick={onCancel}>Back</button>
        <button className="btn primary" onClick={save}>Save card</button>
      </div>
    </>
  );
}

export default function ScenarioModal({ onClose, onStart }) {
  const [list, setList] = useState([]);
  const [selected, setSelected] = useState(null);
  const [playerName, setPlayerName] = useState("");
  const [view, setView] = useState("pick"); // pick | edit | import
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
  const create = async () => {
    let kind = "roleplay";
    try { kind = (await api.settings()).default_card_kind || "roleplay"; } catch { /* keep default */ }
    setEditing({ id: null, initial: { ...BLANK, kind } });
    setView("edit");
  };
  const start = async () => {
    setStarting(true); setError("");
    try { await onStart(sel.id, playerName.trim() || undefined); } catch (e) { setError(e.message); setStarting(false); }
  };

  if (view === "import") {
    return (
      <Modal title="Import a card" onClose={onClose} wide>
        <ImportView onCancel={() => setView("pick")} onImported={(saved) => { setView("pick"); load(saved.id); }} />
      </Modal>
    );
  }

  if (view === "edit") {
    return (
      <Modal title={editing?.id ? "Edit card" : "New card"} onClose={onClose} wide>
        <Editor initial={editing?.initial ?? BLANK} id={editing?.id} onCancel={() => setView("pick")} onSaved={(saved) => { setView("pick"); load(saved.id); }} />
      </Modal>
    );
  }

  return (
    <Modal title="New game" onClose={onClose} wide footer={
      <>
        {error && <span className="error-text small grow">{error}</span>}
        <input className="field" style={{ maxWidth: 260 }} placeholder="Your character's name (optional)" value={playerName} onChange={(e) => setPlayerName(e.target.value)} />
        <button className="btn primary" disabled={!sel || starting} onClick={start}>{starting ? "Starting…" : "Start game"}</button>
      </>
    }>
      <div className="scn-grid">
        {list.map((s) => (
          <div key={s.id} className={`scn ${s.id === selected ? "active" : ""}`} onClick={() => setSelected(s.id)}>
            <div className="row gap center">
              <div className="scn-name grow">{s.name}</div>
              <a className="icon-btn" title="Export as a character card (JSON)" href={api.exportCardUrl(s.id)} download onClick={(e) => e.stopPropagation()}>⤓</a>
              <button className="icon-btn" title="Edit" onClick={(e) => { e.stopPropagation(); edit(s.id); }}>✎</button>
              <button className="icon-btn" title="Delete" onClick={(e) => { e.stopPropagation(); if (window.confirm(`Delete card "${s.name}"? Your saved games stay.`)) api.deleteScenario(s.id).then(() => load()).catch((er) => setError(er.message)); }}>🗑</button>
            </div>
            <div><span className={`tag kind-${s.kind}`}>{KIND_LABELS[s.kind] || "Adventure"}</span><span className="tag">{MODE_LABELS[s.mode]}</span></div>
            <div className="muted small">{s.description}</div>
          </div>
        ))}
        <div className="scn new" onClick={create}>
          <div className="scn-plus">＋</div>
          <div>Create a card</div>
          <div className="muted small">Write your own or let the AI draft one from an idea</div>
        </div>
        <div className="scn new" onClick={() => setView("import")}>
          <div className="scn-plus">⇪</div>
          <div>Import a card</div>
          <div className="muted small">Character Card JSON (SillyTavern format), with lorebook and portraits</div>
        </div>
      </div>
    </Modal>
  );
}
