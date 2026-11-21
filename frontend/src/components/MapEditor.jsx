import React, { useEffect, useRef, useState } from "react";
import { ask } from "../dialogs.jsx";
import Modal from "./Modal.jsx";
import BattleMap, { TILE_STYLE } from "./BattleMap.jsx";
import { api } from "../api.js";

const blank = (w, h) => Array.from({ length: h }, () => ".".repeat(w));
const resize = (tiles, w, h) => Array.from({ length: h }, (_, y) => Array.from({ length: w }, (_, x) => tiles[y]?.[x] || ".").join(""));
const TYPE_LABEL = { field: "Open field", forest: "Forest", dungeon: "Dungeon", cave: "Cave", tavern: "Tavern", river: "River crossing", street: "Town street" };

/** Draw your own battle maps and keep them in a library you can pick from when a fight starts. */
export default function MapEditor({ onClose, onPicked }) {
  const [maps, setMaps] = useState([]);
  const [types, setTypes] = useState(Object.keys(TYPE_LABEL));
  const [current, setCurrent] = useState({ id: null, name: "My map", tiles: blank(12, 8), background: "" });
  const [brush, setBrush] = useState("#");
  const [genType, setGenType] = useState("dungeon");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const painting = useRef(false);
  const fileRef = useRef(null);

  const load = async () => {
    try { const r = await api.maps(); setMaps(r.maps); setTypes(r.types); } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const up = () => { painting.current = false; };
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  }, []);

  const w = current.tiles[0]?.length || 12, h = current.tiles.length || 8;
  const paint = (x, y) => setCurrent((c) => {
    const rows = [...c.tiles];
    rows[y] = rows[y].slice(0, x) + brush + rows[y].slice(x + 1);
    return { ...c, tiles: rows };
  });
  const setSize = (nw, nh) => setCurrent((c) => ({ ...c, tiles: resize(c.tiles, Math.max(6, Math.min(24, nw || 6)), Math.max(4, Math.min(24, nh || 4))) }));
  const generate = async () => {
    try { const r = await api.generateMap({ type: genType, w, h }); setCurrent((c) => ({ ...c, tiles: r.tiles })); } catch (e) { setError(e.message); }
  };
  const save = async () => {
    setError("");
    try {
      const saved = current.id ? await api.updateMap(current.id, current) : await api.createMap(current);
      setCurrent(saved); setNote("Saved"); setTimeout(() => setNote(""), 1500); load();
    } catch (e) { setError(e.message); }
  };
  const uploadBg = async (file) => {
    if (!file) return;
    try { const r = await api.uploadPicture(file); setCurrent((c) => ({ ...c, background: r.url })); } catch (e) { setError(e.message); }
  };

  return (
    <Modal title="Battle maps" onClose={onClose} wide>
      <div className="map-editor">
        <div className="map-lib">
          <div className="section-title">Your maps</div>
          {maps.length === 0 && <div className="muted tiny">None yet. Draw one and save it.</div>}
          {maps.map((m) => (
            <div key={m.id} className={`map-item ${current.id === m.id ? "active" : ""}`}>
              <button className="link-btn grow" onClick={() => setCurrent(m)}>{m.name} <span className="muted tiny">{m.w}×{m.h}</span></button>
              {onPicked && <button className="btn small" title="Use this map for the fight" onClick={() => onPicked(m)}>Use</button>}
              <button className="icon-btn" title="Delete" onClick={async () => { if (await ask.confirm(`Delete map "${m.name}"?`)) { await api.deleteMap(m.id).catch((e) => setError(e.message)); if (current.id === m.id) setCurrent({ ...current, id: null }); load(); } }}>🗑</button>
            </div>
          ))}
          <button className="btn small" onClick={() => setCurrent({ id: null, name: "My map", tiles: blank(12, 8), background: "" })}>＋ New map</button>
        </div>

        <div className="map-work">
          <div className="row gap center wrap">
            <input className="field grow" value={current.name} onChange={(e) => setCurrent({ ...current, name: e.target.value })} placeholder="Map name" />
            <input className="field num" style={{ width: 46 }} value={w} onChange={(e) => setSize(parseInt(e.target.value, 10), h)} title="Width" />
            <span className="muted">×</span>
            <input className="field num" style={{ width: 46 }} value={h} onChange={(e) => setSize(w, parseInt(e.target.value, 10))} title="Height" />
          </div>
          <div className="palette">
            {Object.entries(TILE_STYLE).map(([ch, st]) => (
              <button key={ch} className={`pal ${brush === ch ? "on" : ""}`} title={st.label} onClick={() => setBrush(ch)}>
                <span className="pal-swatch" style={{ background: st.fill === "transparent" ? "var(--panel)" : st.fill }}>{st.glyph || ""}</span>
                <span className="tiny">{st.label.split(" (")[0]}</span>
              </button>
            ))}
          </div>
          <BattleMap w={w} h={h} tiles={current.tiles} background={current.background} cell={34}
            onCell={(x, y) => { painting.current = true; paint(x, y); }}
            onCellEnter={(x, y) => { if (painting.current) paint(x, y); }} className="editing" />
          <div className="muted tiny">Click or drag to paint with the selected terrain. Walls, trees, rocks, crates and deep water block movement and give cover.</div>
          <div className="row gap center wrap">
            <select className="field" value={genType} onChange={(e) => setGenType(e.target.value)}>
              {types.map((t) => <option key={t} value={t}>{TYPE_LABEL[t] || t}</option>)}
            </select>
            <button className="btn small" onClick={generate}>🎲 Start from a generated map</button>
            <button className="btn small" onClick={() => setCurrent({ ...current, tiles: blank(w, h) })}>Clear</button>
            <span className="grow" />
            <button className="btn small" onClick={() => fileRef.current?.click()}>🖼 Picture underneath</button>
            {current.background && <button className="btn small" onClick={() => setCurrent({ ...current, background: "" })}>Remove picture</button>}
            <input ref={fileRef} type="file" hidden accept="image/png,image/jpeg,image/webp,image/gif" onChange={(e) => uploadBg(e.target.files?.[0])} />
          </div>
          {error && <div className="error-text small">{error}</div>}
          <div className="row gap end center">
            <span className="muted tiny">{note}</span>
            {onPicked && <button className="btn" onClick={() => onPicked(current)}>Use without saving</button>}
            <button className="btn primary" onClick={save}>{current.id ? "Save changes" : "Save map"}</button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
