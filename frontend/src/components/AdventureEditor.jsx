import React, { useState } from "react";
import { ask } from "../dialogs.jsx";
import { api } from "../api.js";
import HelpTip from "./HelpTip.jsx";
import { portraitSrc } from "../portraits.js";

const MUSIC = ["", "calm", "tavern", "exploration", "town", "forest", "dungeon", "mystery", "tension", "combat", "boss", "victory", "sad", "romantic", "horror", "epic"];
const ENEMY_FIELDS = [["count", "×", 34], ["hp", "HP", 44], ["ac", "AC", 40], ["attack_bonus", "Atk", 40], ["damage", "Damage", 62], ["init_bonus", "Init", 40]];

const checksToText = (list) => (list || []).map((c) => `${c.skill} DC ${c.dc}: ${c.what}`).join("\n");
function textToChecks(text) {
  return text.split("\n").map((ln) => {
    const m = ln.match(/^\s*(.*?)\s+DC\s*(\d{1,2})\s*:?\s*(.*)$/i);
    return m ? { skill: m[1].trim(), dc: parseInt(m[2], 10), what: (m[3] || m[1]).trim() } : null;
  }).filter(Boolean);
}

/** One scene of the adventure, opened to edit. */
function SceneEdit({ scene, scenes, maps, onChange, onRemove, onMerge }) {
  const set = (k, v) => onChange({ ...scene, [k]: v });
  const setEnemy = (i, k, v) => set("enemies", scene.enemies.map((e, j) => (j === i ? { ...e, [k]: v } : e)));
  const [checks, setChecks] = useState(checksToText(scene.checks));
  return (
    <div className="scene-edit">
      <div className="row gap">
        <label className="lbl grow">Name<input className="field" value={scene.name} onChange={(e) => set("name", e.target.value)} /></label>
        <label className="lbl grow">Location (group)<input className="field" value={scene.group || ""} onChange={(e) => set("group", e.target.value)} placeholder="e.g. Cragmaw Hideout" /></label>
      </div>
      <label className="lbl">Other names (commas)<input className="field" value={(scene.aliases || []).join(", ")}
        onChange={(e) => set("aliases", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} placeholder="Cave Mouth, area 1" /></label>
      <label className="lbl">Read-aloud text (narrated on the first visit)</label>
      <textarea className="field" rows={4} value={scene.read_aloud || ""} onChange={(e) => set("read_aloud", e.target.value)} />
      <label className="lbl">GM notes (hidden from the player)</label>
      <textarea className="field" rows={5} value={scene.notes || ""} onChange={(e) => set("notes", e.target.value)} />
      <label className="lbl">Checks and traps, one per line: <span className="mono">Wisdom (Perception) DC 12: spot the snare</span></label>
      <textarea className="field mono" rows={Math.min(6, Math.max(2, (scene.checks || []).length + 1))} value={checks}
        onChange={(e) => setChecks(e.target.value)} onBlur={() => set("checks", textToChecks(checks))} />
      <div className="lbl">Enemies here</div>
      {(scene.enemies || []).map((e, i) => (
        <div className="row gap center enemy-stats" key={i}>
          <input className="field grow" style={{ minWidth: 90 }} value={e.name} onChange={(ev) => setEnemy(i, "name", ev.target.value)} />
          {ENEMY_FIELDS.map(([k, label, w]) => (
            <label key={k} className="tiny muted">{label}<input className="field num" style={{ width: w }} value={e[k] ?? ""} onChange={(ev) => setEnemy(i, k, ev.target.value)} /></label>
          ))}
          <button className="icon-btn" title="Remove" onClick={() => set("enemies", scene.enemies.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <button className="btn small" onClick={() => set("enemies", [...(scene.enemies || []), { name: "Goblin", count: 1, hp: 7, ac: 15, attack_bonus: 4, damage: "1d6+2", init_bonus: 2 }])}>＋ Enemy</button>
      <label className="lbl">Treasure<input className="field" value={scene.treasure || ""} onChange={(e) => set("treasure", e.target.value)} /></label>
      <div className="row gap">
        <label className="lbl">XP award<input className="field num" style={{ width: 80 }} value={scene.xp || 0} onChange={(e) => set("xp", parseInt(e.target.value, 10) || 0)} /></label>
        <label className="lbl">Music<select className="field" value={scene.music || ""} onChange={(e) => set("music", e.target.value)}>
          {MUSIC.map((m) => <option key={m} value={m}>{m || "(keep)"}</option>)}</select></label>
        <label className="lbl grow">Map<select className="field" value={scene.map || ""} onChange={(e) => set("map", e.target.value)}>
          <option value="">(none)</option>{maps.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
      </div>
      <div className="lbl">Ways on from here</div>
      <div className="conds">
        {scenes.filter((x) => x.id !== scene.id && (!scene.group || x.group === scene.group || (scene.leads || []).includes(x.id))).map((x) => (
          <button key={x.id} className={`chip ${(scene.leads || []).includes(x.id) ? "on" : ""}`}
            onClick={() => set("leads", (scene.leads || []).includes(x.id) ? scene.leads.filter((y) => y !== x.id) : [...(scene.leads || []), x.id])}>{x.name}</button>
        ))}
      </div>
      <div className="row gap">
        <button className="btn small" onClick={onMerge}>⤴ Join to the scene above</button>
        <button className="btn small danger" onClick={onRemove}>✕ Remove this scene</button>
      </div>
    </div>
  );
}

/** A location's map: GM and player pictures, the grid size, and a marker per scene (click the picture to place it). */
function MapEdit({ map, scenes, onChange, onRemove }) {
  const [placing, setPlacing] = useState("");
  const [aspect, setAspect] = useState(0);  // picture height / width: the grid's rows follow it
  const set = (k, v) => onChange({ ...map, [k]: v });
  const rowsFor = (cols, a = aspect) => (a ? Math.max(4, Math.min(48, Math.round(cols * a))) : map.rows || 20);
  const setCols = (v) => { const cols = Math.max(6, Math.min(48, parseInt(v, 10) || 6)); onChange({ ...map, cols, rows: rowsFor(cols) }); };
  const upload = async (k, file) => {
    if (!file) return;
    try { const r = await api.uploadPicture(file); set(k, r.url); } catch (e) { ask.alert(e.message); }
  };
  const mine = scenes.filter((s) => s.map === map.id);
  const click = (e) => {
    if (!placing) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = Math.round(((e.clientX - box.left) / box.width) * 1000) / 1000, y = Math.round(((e.clientY - box.top) / box.height) * 1000) / 1000;
    onChange({ ...map, markers: { ...(map.markers || {}), [placing]: [x, y] } });
    const next = mine.find((s) => !(map.markers || {})[s.id] && s.id !== placing);
    setPlacing(next ? next.id : "");
  };
  const pic = map.picture || map.player_picture;
  return (
    <div className="card map-edit">
      <div className="row gap center">
        <input className="field grow" value={map.name} onChange={(e) => set("name", e.target.value)} />
        <button className="icon-btn" title="Remove the map" onClick={onRemove}>✕</button>
      </div>
      <div className="row gap center wrap">
        <label className="btn small">⬆ GM map<input type="file" accept="image/*" hidden onChange={(e) => upload("picture", e.target.files?.[0])} /></label>
        <label className="btn small">⬆ Player map<input type="file" accept="image/*" hidden onChange={(e) => upload("player_picture", e.target.files?.[0])} /></label>
        <span className="tiny muted">Squares</span>
        <input className="field num" style={{ width: 44 }} value={map.cols || 30} onChange={(e) => setCols(e.target.value)} />
        <span className="muted tiny">{`× ${map.rows || 20} (5-ft squares)`}</span>
      </div>
      {pic ? (
        <>
          <div className="row gap center">
            <span className="small">Place a marker for</span>
            <select className="field grow" value={placing} onChange={(e) => setPlacing(e.target.value)}>
              <option value="">(choose a scene, then click its spot)</option>
              {mine.map((s) => <option key={s.id} value={s.id}>{(map.markers || {})[s.id] ? "✓ " : ""}{s.name}</option>)}
            </select>
          </div>
          <div className={`adv-map ${placing ? "placing" : ""}`} onClick={click}>
            <img src={portraitSrc(pic)} alt="" onLoad={(e) => {
              const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
              if (!w || !h) return;
              setAspect(h / w);
              const rows = rowsFor(map.cols || 30, h / w);
              if (rows !== map.rows) onChange({ ...map, rows });
            }} />
            {mine.map((s) => (map.markers || {})[s.id] && (
              <span key={s.id} className={`adv-pin ${placing === s.id ? "on" : ""}`} style={{ left: `${map.markers[s.id][0] * 100}%`, top: `${map.markers[s.id][1] * 100}%` }}
                title={s.name}>{(s.name.match(/^[A-Z]?\d+[a-z]?/) || ["•"])[0]}</span>
            ))}
          </div>
          <div className="muted tiny">The player map (if you add one) is what the player sees in the Adventure tab and under fights; the GM map is used when there is no player map. Squares: how many 5-ft squares the picture is wide (the height follows the picture), so fights on this map line up with its grid.</div>
        </>
      ) : <div className="muted tiny">Add the map picture (the GM version, and the player version if the book has one).</div>}
    </div>
  );
}

/** Card editor: a published adventure split into parts and scenes, with maps. */
export default function AdventureEditor({ cardId, adventure, onChange, onImported }) {
  const adv = adventure || { title: "", background: "", parts: [], scenes: [], maps: [] };
  const [part, setPart] = useState("");
  const [paste, setPaste] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [open, setOpen] = useState("");
  const set = (k, v) => onChange({ ...adv, [k]: v });
  const run = async (body, filename) => {
    if (!cardId) { ask.alert("Save the card once first, then import the adventure."); return; }
    setBusy(true); setReport(null);
    try {
      const r = await api.importAdventure(cardId, body, part.trim(), filename || "");
      onImported(r.card); setReport(r.report); setText(""); setPaste(false);
    } catch (e) { ask.alert(e.message); } finally { setBusy(false); }
  };
  const setScene = (i, sc) => set("scenes", adv.scenes.map((x, j) => (j === i ? sc : x)));
  const removeScene = async (i) => { if (await ask.confirm(`Remove "${adv.scenes[i].name}"?`)) set("scenes", adv.scenes.filter((_, j) => j !== i)); };
  const mergeScene = (i) => {
    if (i === 0) return;
    const a = adv.scenes[i - 1], b = adv.scenes[i];
    const join = (x, y) => [x, y].filter((t) => t && t.trim()).join("\n\n");
    const merged = { ...a, read_aloud: join(a.read_aloud, b.read_aloud), notes: join(a.notes, `${b.name}: ${b.notes || ""}`),
      checks: [...a.checks, ...b.checks], enemies: [...a.enemies, ...b.enemies], treasure: join(a.treasure, b.treasure), xp: (a.xp || 0) + (b.xp || 0) };
    set("scenes", adv.scenes.flatMap((x, j) => (j === i - 1 ? [merged] : j === i ? [] : [x])));
  };
  const partName = (id) => (adv.parts.find((p) => p.id === id) || {}).title || "";
  let lastPart = null;
  return (
    <details className="story-frame adventure-edit" open={adv.scenes.length > 0 && adv.scenes.length < 3}>
      <summary className="lbl">Adventure: scenes, maps and fights <HelpTip id="adventure" /> {adv.scenes.length > 0 && <span className="muted tiny">{`(${adv.scenes.length} scenes)`}</span>}</summary>
      <div className="muted tiny">Import a published adventure (a PDF, or text copied from it) one part at a time. Calíope splits it into scenes with their read-aloud text, GM notes, checks, enemies, treasure and XP. Check each scene afterwards: the splitting is automatic. The book stays on this PC.</div>
      <div className="row gap center wrap">
        <input className="field grow" placeholder="Part name (e.g. Part 1: Goblin Arrows)" value={part} onChange={(e) => setPart(e.target.value)} />
        <label className={`btn small ${busy ? "disabled" : ""}`}>⬆ PDF or text file
          <input type="file" accept=".pdf,.txt,.md" hidden disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) run(f, f.name); e.target.value = ""; }} />
        </label>
        <button className="btn small" onClick={() => setPaste(!paste)}>📋 Paste text</button>
      </div>
      {paste && (
        <>
          <textarea className="field" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a chapter of the adventure here…" />
          <button className="btn small primary" disabled={busy || !text.trim()} onClick={() => run(new Blob([text], { type: "text/plain" }), "pasted.txt")}>{busy ? "Reading…" : "Import this text"}</button>
        </>
      )}
      {busy && <div className="muted small">Reading the adventure…</div>}
      {report && <div className="small">{`Found ${report.scenes} scenes (${report.read_aloud} with read-aloud text), ${report.checks} checks and ${report.enemies} enemy groups.`}{" "}
        {report.npcs.length > 0 && <span>{`New characters: ${report.npcs.join(", ")}.`} </span>}{report.background && <span>The background went to the Aedo's notes. </span>}<span>The card is saved.</span></div>}
      {adv.scenes.length > 0 && (
        <>
          <label className="lbl">Background for the Aedo (GM only)</label>
          <textarea className="field" rows={3} value={adv.background || ""} onChange={(e) => set("background", e.target.value)} />
          <div className="section-title">Maps <span className="muted tiny">({adv.maps.length})</span></div>
          {adv.maps.map((m, i) => (
            <MapEdit key={m.id || i} map={m} scenes={adv.scenes}
              onChange={(v) => set("maps", adv.maps.map((x, j) => (j === i ? v : x)))}
              onRemove={() => onChange({ ...adv, maps: adv.maps.filter((_, j) => j !== i), scenes: adv.scenes.map((s) => (s.map === m.id ? { ...s, map: "" } : s)) })} />
          ))}
          <button className="btn small" onClick={() => set("maps", [...adv.maps, { id: `map-${Date.now().toString(36)}`, name: "New map", picture: "", player_picture: "", cols: 30, rows: 20, markers: {} }])}>＋ Add a map</button>
          <div className="section-title">Scenes</div>
          {adv.scenes.map((sc, i) => {
            const header = sc.part !== lastPart ? <div className="part-title" key={`p-${sc.part}`}>{partName(sc.part) || "Part"}</div> : null;
            lastPart = sc.part;
            return (
              <React.Fragment key={sc.id || i}>
                {header}
                <div className={`scene-row ${open === sc.id ? "open" : ""}`}>
                  <button className="link-btn scene-head" onClick={() => setOpen(open === sc.id ? "" : sc.id)}>
                    <span>{sc.group ? <span className="muted">{sc.group} · </span> : null}{sc.name}</span>
                    <span className="muted tiny">{sc.read_aloud ? " 📖" : ""}{sc.checks?.length ? ` 🎲${sc.checks.length}` : ""}{sc.enemies?.length ? ` ⚔${sc.enemies.length}` : ""}{sc.xp ? ` 🏅${sc.xp}` : ""}</span>
                  </button>
                  {open === sc.id && <SceneEdit scene={sc} scenes={adv.scenes} maps={adv.maps} onChange={(v) => setScene(i, v)}
                    onRemove={() => removeScene(i)} onMerge={() => mergeScene(i)} />}
                </div>
              </React.Fragment>
            );
          })}
        </>
      )}
    </details>
  );
}
