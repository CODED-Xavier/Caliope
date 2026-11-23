import React, { useEffect, useMemo, useState } from "react";
import { ask } from "../dialogs.jsx";
import { api } from "../api.js";
import HelpTip from "./HelpTip.jsx";
import BattleMap, { SIDE_COLOR, TILE_STYLE } from "./BattleMap.jsx";
import { AREA_PRESETS, areaCells, distanceFt } from "../gridgeom.js";
import MapEditor from "./MapEditor.jsx";
import Modal from "./Modal.jsx";
import { emblemFor } from "./Builder.jsx";

const MAP_TYPES = { field: "Open field", forest: "Forest", road: "Road through the woods", dungeon: "Dungeon", cave: "Cave", tavern: "Tavern", river: "River crossing", street: "Town street" };
const MAP_FEATURES = ["rocks", "trees", "bushes", "barrels", "water", "mud"];
const BLOCKING = "#~TRB";

const CONDITIONS = ["prone", "grappled", "restrained", "poisoned", "stunned", "blinded", "frightened", "invisible"];
const BLANK = {
  d20: { name: "", count: 1, hp: 7, ac: 13, attack_bonus: 4, damage: "1d6+2", init_bonus: 1 },
  pool: { name: "", count: 1, hp: 6, pool: 5, defense: 4, damage: 1 },
};
BLANK.d20.range = 1; BLANK.pool.range = 1;
const FIELDS = {
  d20: [["hp", "HP", 52], ["ac", "AC", 46], ["attack_bonus", "Atk", 46], ["damage", "Damage", 70], ["init_bonus", "Init", 46], ["range", "Range", 46]],
  pool: [["hp", "Health", 56], ["pool", "Attack dice", 56], ["defense", "Defense dice", 56], ["damage", "Dmg +", 46], ["range", "Range", 46]],
};

/* ---------------------------------------------------------------- start form */
function StartForm({ convId, kind, busy, onStart, sceneFight, hasScene }) {
  const [system, setSystem] = useState("d20");
  const [enemies, setEnemies] = useState([{ ...BLANK.d20, name: "", count: 1 }]);  // a name from the Bestiary fills the numbers
  const [me, setMe] = useState({});
  const [grid, setGrid] = useState({ w: 12, h: 8 });
  const [mapMode, setMapMode] = useState("gen");          // gen | saved | empty
  const [mapType, setMapType] = useState("field");
  const [features, setFeatures] = useState([]);
  const [preview, setPreview] = useState(null);           // {tiles, background, name}
  const [saved, setSaved] = useState([]);
  const [savedId, setSavedId] = useState("");
  const [editor, setEditor] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState("");
  const [battle, setBattle] = useState(null);             // the adventure scene's map: {background, name, w, h, near}

  useEffect(() => { api.combatDefaults(convId, system).then(setMe).catch(() => setMe({})); }, [convId, system]);
  const loadSaved = () => api.maps().then((r) => setSaved(r.maps)).catch(() => {});
  useEffect(() => { loadSaved(); }, []);
  const reroll = async (type = mapType, feats = features) => {
    try { const r = await api.generateMap({ type, w: grid.w, h: grid.h, features: feats }); setPreview({ tiles: r.tiles, name: MAP_TYPES[type], type }); } catch (e) { setError(e.message); }
  };
  useEffect(() => { if (mapMode === "gen") reroll(); }, [mapMode, mapType, features.join(","), grid.w, grid.h]); // eslint-disable-line
  useEffect(() => {
    if (mapMode !== "saved") return;
    const m = saved.find((x) => String(x.id) === String(savedId)) || saved[0];
    if (m) { setSavedId(String(m.id)); setPreview({ tiles: m.tiles, background: m.background, name: m.name }); } else setPreview(null);
  }, [mapMode, savedId, saved]);
  useEffect(() => { if (mapMode === "empty") setPreview(null); }, [mapMode]);
  useEffect(() => {
    if (mapMode === "scene" && battle) {
      setGrid({ w: battle.w, h: battle.h });
      setPreview({ tiles: battle.tiles || [], background: battle.background, name: battle.name, geom: battle.geom, fog: battle.fog, painted: !!battle.painted });
    }
  }, [mapMode, battle]);
  useEffect(() => { if (sceneFight) suggest(); }, [sceneFight]); // eslint-disable-line
  const switchSystem = (s) => { setSystem(s); setEnemies(enemies.map((e) => ({ ...BLANK[s], name: e.name, count: e.count }))); };
  const setEnemy = (i, k, v) => setEnemies(enemies.map((e, j) => (j === i ? { ...e, [k]: v } : e)));
  const [monsters, setMonsters] = useState([]);
  useEffect(() => { api.bestiary().then((r) => setMonsters(r.monsters || [])).catch(() => {}); }, []);
  const fromBestiary = async (i) => { // a monster from the Bestiary: its sheet's numbers
    if (system !== "d20" || !enemies[i]?.name?.trim()) return;
    try {
      const r = await api.bestiaryFind(enemies[i].name.trim());
      if (r.combat) setEnemies((list) => list.map((e, j) => (j === i ? { ...e, ...r.combat } : e)));
    } catch { /* no sheet: keep what is typed */ }
  };
  const suggest = async () => {
    setSuggesting(true); setError("");
    try {
      const r = await api.combatSuggest(convId, system);
      setEnemies(r.enemies);
      if (r.battle) { setBattle(r.battle); setMapMode("scene"); }
      else if (r.map) { setMapMode("gen"); setMapType(r.map.type); setFeatures(r.map.features || []); }
    } catch (e) { setError(e.message); } finally { setSuggesting(false); }
  };
  const [painting, setPainting] = useState(false);
  const [paintKind, setPaintKind] = useState("");
  const paintScene = async () => { // 🎨 a new painted map for this scene (kept in the card as the scene's map)
    setPainting(true); setError("");
    try { const r = await api.paintSceneMap(convId, paintKind); setBattle(r.battle); setMapMode("scene"); } catch (e) { setError(e.message); } finally { setPainting(false); }
  };
  const start = () => {
    const list = enemies.filter((e) => String(e.name).trim());
    if (!list.length) { setError("Add at least one enemy."); return; }
    onStart({ action: "start", system, enemies: list, player: me, grid, map: preview || undefined,
      near: mapMode === "scene" && battle?.near ? battle.near : undefined });
  };
  const myFields = system === "pool" ? [["pool", "Attack dice"], ["defense", "Defense dice"], ["damage", "Dmg +"]] : [["attack_bonus", "Attack +"], ["damage", "Damage"], ["ac", "AC"], ["init_bonus", "Init +"]];

  return (
    <div className="tab-body combat-start">
      <div className="section-title">Start a fight <HelpTip id="combat" /></div>
      <div className="row gap center">
        <span className="small">Rules</span>
        <select className="field" value={system} onChange={(e) => switchSystem(e.target.value)}>
          <option value="d20">d20 (D&D 5e)</option>
          <option value="pool">d10 dice pool (Vampire 5e)</option>
        </select>
      </div>
      <div className="row gap center">
        <div className="section-title grow">Enemies</div>
        <button className="btn small" onClick={suggest} disabled={suggesting || busy}>{suggesting ? "Reading the scene…" : "✨ Suggest from the scene"}</button>
      </div>
      {enemies.map((e, i) => (
        <div className="enemy-row" key={i}>
          <div className="row gap center">
            <input className="field grow" placeholder="Name" value={e.name} onChange={(ev) => setEnemy(i, "name", ev.target.value)}
              list="bestiary-names" onBlur={() => fromBestiary(i)} title="A name from the 🐉 Bestiary fills in its numbers" />
            <span className="tiny muted">×</span>
            <input className="field num" style={{ width: 40 }} value={e.count} onChange={(ev) => setEnemy(i, "count", ev.target.value)} title="How many" />
            <button className="icon-btn" title="Remove" onClick={() => setEnemies(enemies.filter((_, j) => j !== i))}>✕</button>
          </div>
          <div className="row gap enemy-stats">
            {FIELDS[system].map(([k, label, w]) => (
              <label key={k} className="tiny muted">{label}<input className="field num" style={{ width: w }} value={e[k] ?? ""} onChange={(ev) => setEnemy(i, k, ev.target.value)} /></label>
            ))}
          </div>
          {e.spell ? (
            <div className="row gap enemy-stats caster">
              <label className="tiny muted">Spell<input className="field" style={{ width: 96 }} value={e.spell.name || ""} onChange={(ev) => setEnemy(i, "spell", { ...e.spell, name: ev.target.value })} /></label>
              <label className="tiny muted">Cost<input className="field num" style={{ width: 40 }} value={e.spell.cost ?? ""} onChange={(ev) => setEnemy(i, "spell", { ...e.spell, cost: ev.target.value })} /></label>
              <label className="tiny muted">Damage<input className="field num" style={{ width: 60 }} value={e.spell.damage ?? ""} onChange={(ev) => setEnemy(i, "spell", { ...e.spell, damage: ev.target.value })} /></label>
              <label className="tiny muted">Range<input className="field num" style={{ width: 40 }} value={e.spell.range ?? ""} onChange={(ev) => setEnemy(i, "spell", { ...e.spell, range: ev.target.value })} /></label>
              <label className="tiny muted">{e.mp_name || "Mana"}<input className="field num" style={{ width: 44 }} value={e.mp ?? ""} onChange={(ev) => setEnemy(i, "mp", ev.target.value)} /></label>
              <button className="icon-btn" title="Not a caster" onClick={() => setEnemies(enemies.map((x, j) => { if (j !== i) return x; const { spell, mp, mp_name, ...rest } = x; return rest; }))}>✕</button>
            </div>
          ) : (
            <button className="link-btn tiny" onClick={() => setEnemies(enemies.map((x, j) => (j === i ? { ...x, mp: 10, mp_name: "Mana", spell: { name: "Spell", cost: 3, damage: system === "pool" ? 2 : "2d6", range: 12 } } : x)))}>＋ casts spells (uses a power pool)</button>
          )}
        </div>
      ))}
      <button className="btn small" onClick={() => setEnemies([...enemies, { ...BLANK[system] }])}>＋ Add enemy</button>
      <datalist id="bestiary-names">{monsters.map((m) => <option key={m.id} value={m.name} />)}</datalist>
      <div className="section-title">You <span className="muted tiny">(from your sheet; change for this fight)</span></div>
      <div className="row gap enemy-stats">
        {myFields.map(([k, label]) => (
          <label key={k} className="tiny muted">{label}<input className="field num" style={{ width: k === "damage" ? 70 : 50 }} value={me[k] ?? ""} onChange={(ev) => setMe({ ...me, [k]: ev.target.value })} /></label>
        ))}
      </div>
      <div className="row gap center">
        <div className="section-title grow">Map</div>
        <button className="btn small" onClick={() => setEditor(true)}>🗺 My maps / editor</button>
      </div>
      <div className="row gap center">
        <select className="field grow" value={mapMode} onChange={(e) => setMapMode(e.target.value)}>
          <option value="gen">Generate</option>
          <option value="saved" disabled={!saved.length}>One of my maps{saved.length ? "" : " (none yet)"}</option>
          <option value="empty">Empty grid</option>
          {battle && <option value="scene">{`The adventure's map (${battle.name})`}</option>}
          {mapMode === "gen-custom" && <option value="gen-custom">From the editor (not saved)</option>}
        </select>
        {mapMode === "gen" && (
          <select className="field grow" value={mapType} onChange={(e) => setMapType(e.target.value)}>
            {Object.entries(MAP_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        )}
        {mapMode === "saved" && (
          <select className="field grow" value={savedId} onChange={(e) => setSavedId(e.target.value)}>
            {saved.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        )}
      </div>
      {mapMode === "gen" && (
        <div className="conds">
          {MAP_FEATURES.map((f) => (
            <button key={f} className={`chip ${features.includes(f) ? "on" : ""}`} onClick={() => setFeatures(features.includes(f) ? features.filter((x) => x !== f) : [...features, f])}>+ {f}</button>
          ))}
          <button className="chip" onClick={() => reroll()} title="Another map of this type">🎲 reroll</button>
        </div>
      )}
      {(mapMode === "scene" || hasScene) && (
        <div className="row gap center">
          <select className="field grow" value={paintKind} onChange={(e) => setPaintKind(e.target.value)} title="What the painted map shows">
            <option value="">Fits the scene</option>
            {Object.entries(MAP_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="btn small" onClick={paintScene} disabled={painting || busy}
            title="Calíope paints a battle map for this scene, with the grid already lined up, and keeps it in the card">
            {painting ? "Painting…" : battle?.painted ? "🎲 Paint another" : "🎨 Paint a map"}</button>
        </div>
      )}
      {mapMode !== "scene" && mapMode !== "empty" && <div className="muted tiny">🎨 This map is painted as a picture when the fight starts.</div>}
      {mapMode !== "saved" && mapMode !== "scene" && (
        <div className="row gap center">
          <span className="small grow">Size</span>
          <input className="field num" style={{ width: 44 }} value={grid.w} onChange={(e) => setGrid({ ...grid, w: Math.max(6, Math.min(24, parseInt(e.target.value, 10) || 6)) })} />
          <span className="muted">×</span>
          <input className="field num" style={{ width: 44 }} value={grid.h} onChange={(e) => setGrid({ ...grid, h: Math.max(4, Math.min(24, parseInt(e.target.value, 10) || 4)) })} />
          <span className="muted tiny">squares (5 ft)</span>
        </div>
      )}
      {preview && <BattleMap w={preview.tiles[0]?.length || grid.w} h={preview.tiles.length || grid.h} tiles={preview.tiles} background={preview.background}
        geom={preview.geom} fog={preview.fog} painted={preview.painted}
        cell={mapMode === "scene" ? Math.max(8, Math.floor(360 / grid.w)) : 20} className="preview" />}
      {editor && <MapEditor onClose={() => { setEditor(false); loadSaved(); }}
        onPicked={(m) => { setEditor(false); loadSaved(); setPreview({ tiles: m.tiles, background: m.background, name: m.name }); setMapMode(m.id ? "saved" : "gen-custom"); if (m.id) setSavedId(String(m.id)); }} />}
      {error && <div className="error-text small">{error}</div>}
      <button className="btn primary" disabled={busy} onClick={start}>⚔ Start the fight</button>
      {kind === "roleplay" && <div className="muted tiny">Tip: roleplay cards can fight too; the Aedo narrates what the dice decide.</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- grid */
const DIFFICULT = ',"';
// squares the player can walk to with the movement left (around walls and creatures; mud and bushes cost 2)
function reachable(combat, me, left) {
  const { w, h, tiles = [] } = combat.grid;
  const taken = new Set(combat.combatants.filter((c) => c.hp > 0 && c.id !== me.id).map((c) => `${c.x},${c.y}`));
  const cost = new Map([[`${me.x},${me.y}`, 0]]);
  const queue = [[me.x, me.y]];
  while (queue.length) {
    const [x, y] = queue.shift();
    const c0 = cost.get(`${x},${y}`);
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]]) {
      const nx = x + dx, ny = y + dy, k = `${nx},${ny}`;
      if (nx < 0 || ny < 0 || nx >= w || ny >= h || taken.has(k) || BLOCKING.includes(tiles[ny]?.[nx] || ".")) continue;
      const nc = c0 + (DIFFICULT.includes(tiles[ny]?.[nx] || ".") ? 2 : 1);
      if (nc <= left && nc < (cost.get(k) ?? 99)) { cost.set(k, nc); queue.push([nx, ny]); }
    }
  }
  cost.delete(`${me.x},${me.y}`);
  return cost;
}

const TOOL_KEY = "caliope.diagonals";

/** The map's tools: 🏃 move (your turn), 📏 measure (5 ft per square) and 🔥 area of effect (spells' shapes). */
function MapTools({ tool, setTool, rule, setRule, area, setArea, spells, onBig, big }) {
  const presets = [...spells.map((o) => ({ name: o.name, ...o.area })), ...AREA_PRESETS.filter((p) => !spells.some((o) => o.name === p.name))];
  return (
    <div className="map-tools row gap center wrap">
      {[["move", "🏃 Move"], ["measure", "📏 Measure"], ["area", "🔥 Area"]].map(([k, label]) => (
        <button key={k} type="button" className={`btn small ${tool === k ? "primary" : "ghost"}`} onClick={() => setTool(k)}>{label}</button>
      ))}
      {tool === "measure" && (
        <select className="field small" value={rule} onChange={(e) => setRule(e.target.value)} title="How diagonals count">
          <option value="5e">Diagonals: 5 ft</option>
          <option value="variant">Diagonals: 5-10-5 ft</option>
        </select>
      )}
      {tool === "area" && (
        <>
          <select className="field small" value={area.name || ""} onChange={(e) => { const p = presets.find((x) => x.name === e.target.value); if (p) setArea({ width: 5, ...p }); }}>
            {!presets.some((p) => p.name === area.name) && <option value="">Custom</option>}
            {presets.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
          <select className="field small" value={`${area.shape}:${area.origin}`} onChange={(e) => { const [shape, origin] = e.target.value.split(":"); setArea({ ...area, name: "", shape, origin }); }}>
            <option value="sphere:point">Sphere / circle</option>
            <option value="sphere:self">Around you</option>
            <option value="cone:self">Cone</option>
            <option value="line:self">Line</option>
            <option value="cube:self">Cube from you</option>
            <option value="cube:point">Cube at a point</option>
          </select>
          <input className="field num small" value={area.size} onChange={(e) => setArea({ ...area, name: "", size: Math.max(5, Number(e.target.value.replace(/\D/g, "")) || 5) })}
            title={area.shape === "sphere" ? "Radius in feet" : "Size in feet"} aria-label="Size in feet" />
          <span className="muted tiny">ft</span>
        </>
      )}
      <button type="button" className="btn small ghost push-right" onClick={onBig}>{big ? "✕ Close the big map" : "🗺 Big map"}</button>
    </div>
  );
}

function Grid({ combat, selected, onSelect, convId, onState, busy, myTurn, current, faces = {} }) {
  const { w, h, tiles = [], background = "", name = "", geom = null, fog = null, painted = false } = combat.grid;
  const [spells, setSpells] = useState([]); // your sheet's spells with an area (Fireball, Burning Hands…) for the 🔥 tool
  useEffect(() => {
    if (!convId) return;
    api.combatOptions(convId).then((d) => setSpells(Object.values(d?.groups || {}).flat().filter((o) => o.area))).catch(() => setSpells([]));
  }, [convId, combat.round]); // eslint-disable-line react-hooks/exhaustive-deps
  const [painting, setPainting] = useState(false);
  const [paintError, setPaintError] = useState("");
  const [tool, setTool] = useState("move");
  const [rule, setRuleState] = useState(() => { try { return localStorage.getItem(TOOL_KEY) || "5e"; } catch { return "5e"; } });
  const setRule = (v) => { setRuleState(v); try { localStorage.setItem(TOOL_KEY, v); } catch { /* private window */ } };
  const [area, setArea] = useState({ ...AREA_PRESETS[0], width: 5 });
  const [anchor, setAnchor] = useState(null); // 📏 the start square (your token by default)
  const [pinned, setPinned] = useState(null); // 🔥 a placed area stays until clicked again
  const [big, setBig] = useState(false);
  const paint = async () => { // a plain grid gets a painted map; everyone is placed again
    setPainting(true); setPaintError("");
    try { const r = await api.combatPaintMap(convId); onState?.(r.state); } catch (e) { setPaintError(e.message); } finally { setPainting(false); }
  };
  // tokens: your portrait, your companions' portraits, and a race emblem for enemies ("Goblin 2" -> the goblin emblem)
  const people = combat.combatants.map((c) => ({ ...c, image: faces[c.name] || (c.side === "enemy" ? emblemFor("race", c.name.replace(/\s*\d+$/, "")) : "") }));
  const me = people.find((c) => c.side === "player");
  const [hover, setHover] = useState(null);
  const [walkError, setWalkError] = useState("");
  const left = me && myTurn && me.hp > 0 ? Math.max(0, (me.speed || 6) - (combat.moved || 0)) : 0;
  const reach = useMemo(() => (left > 0 ? reachable(combat, me, left) : new Map()), [combat, left]); // eslint-disable-line
  const hoverCost = hover ? reach.get(`${hover.x},${hover.y}`) : undefined;
  const hoverTile = hover ? TILE_STYLE[tiles[hover.y]?.[hover.x] || "."] : null;
  const walk = async (x, y) => { // your token walks there (your turn only, within your speed)
    setWalkError("");
    if (!myTurn) { setWalkError(`It is ${current?.name}'s turn. You can move on your turn.`); return; }
    if (!reach.has(`${x},${y}`)) { if (!(me.x === x && me.y === y)) setWalkError(left ? `Too far: you can move ${left} more squares (${left * 5} ft) this turn.` : "No movement left this turn."); return; }
    try { const r = await api.combatMove(convId, x, y); onState?.(r.state); } catch (e) { setWalkError(e.message); }
  };
  // 📏 measure: from the start square to the one under the mouse
  const start = anchor || (me ? { x: me.x, y: me.y } : null);
  const measureTo = tool === "measure" ? hover : null;
  const feet = start && measureTo ? distanceFt(start, measureTo, rule) : 0;
  const walkFt = measureTo && !anchor && reach.has(`${measureTo.x},${measureTo.y}`) ? reach.get(`${measureTo.x},${measureTo.y}`) * 5 : null;
  // 🔥 area: aimed at the square under the mouse, or a placed one
  const aim = tool === "area" ? (pinned || hover) : null;
  const marks = useMemo(() => (aim && me ? areaCells(area, me, aim, w, h) : null), [aim?.x, aim?.y, area, me?.x, me?.y, w, h]); // eslint-disable-line
  const inside = marks ? people.filter((c) => c.hp > 0 && marks.has(`${c.x},${c.y}`)) : [];
  const click = (x, y) => {
    if (tool === "measure") { setAnchor(anchor && anchor.x === x && anchor.y === y ? null : { x, y }); return; }
    if (tool === "area") { setPinned(pinned && pinned.x === x && pinned.y === y ? null : { x, y }); return; }
    if (!busy) walk(x, y);
  };
  const map = (cell) => (
    <BattleMap w={w} h={h} tiles={tiles} background={background} tokens={people} selected={selected} geom={geom} cell={cell} painted={painted}
      // fog of war: the places already visited stay clear, and your side sees around itself
      fog={fog ? [...fog, ...people.filter((c) => c.side !== "enemy" && c.hp > 0).map((c) => ({ x: c.x + 0.5, y: c.y + 0.5, r: 4 }))] : null}
      reach={busy || tool !== "move" ? null : new Set(reach.keys())}
      marks={marks}
      ruler={start && measureTo && (measureTo.x !== start.x || measureTo.y !== start.y)
        ? { from: start, to: measureTo, label: `${feet} ft (${(feet * 0.3).toFixed(1).replace(/\.0$/, "")} m)` } : null}
      onToken={(id) => { const c = people.find((p) => p.id === id); if (tool !== "move" && c) click(c.x, c.y); else onSelect(id); }}
      onLeave={() => setHover(null)} onCellEnter={(x, y) => setHover({ x, y })} onCell={click} />
  );
  const status = (
    <div className="muted tiny">
      {name && <>{name} · </>}
      {tool === "measure" && (measureTo
        ? `📏 ${feet} ft${walkFt != null && walkFt !== feet ? ` · walking there costs ${walkFt} ft (rough ground)` : ""}${me && myTurn && !anchor ? ` · ${Math.max(0, left * 5 - (walkFt ?? feet))} of your ${left * 5} ft left after` : ""}`
        : `📏 Point at a square to measure from ${anchor ? "the marked square" : "your token"} (click a square to measure from there).`)}
      {tool === "area" && (aim
        ? `🔥 ${area.name || `${area.size} ft ${area.shape}`}: ${inside.length ? inside.map((c) => `${c.name}${c.side !== "enemy" ? " ⚠" : ""}`).join(", ") : "nobody inside"}${pinned ? " · placed (click it again to lift it)" : " · click to place it"}`
        : "🔥 Point where the spell goes; cones, lines and cubes from you point toward the mouse.")}
      {tool === "move" && (myTurn
        ? `🏃 Your turn: click a lit square to move (${left} of ${me?.speed || 6} squares left). Click an enemy to target it.`
        : `⏳ ${current?.name}'s turn. You move on your turn.`)}
      {tool === "move" && myTurn && hoverCost ? ` · ${hoverCost} ${hoverCost === 1 ? "square" : "squares"}` : ""}
      {hoverTile && hoverTile.label !== "Floor / grass" && <> · {hoverTile.label}</>}
    </div>
  );
  const tools = <MapTools tool={tool} setTool={(t) => { setTool(t); setAnchor(null); setPinned(null); }} rule={rule} setRule={setRule} area={area} setArea={setArea}
    spells={spells} big={big} onBig={() => setBig((b) => !b)} />;
  return (
    <div className="grid-wrap">
      {!background && convId && (
        <div className="row gap center">
          <button className="btn small" onClick={paint} disabled={painting || busy}>{painting ? "Painting…" : "🎨 Paint a map for this fight"}</button>
          {paintError && <span className="error-text tiny">{paintError}</span>}
        </div>
      )}
      {tools}
      {map(geom ? 28 : 30)}
      {status}
      {walkError && <div className="error-text tiny">{walkError}</div>}
      {big && ( // the same map, big in the middle of the screen
        <div className="big-map-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setBig(false); }}>
          <div className="big-map-box">
            {tools}
            <div className="big-map-scroll">{map(geom ? 44 : 48)}</div>
            {status}
            {walkError && <div className="error-text tiny">{walkError}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- 5e options, by cost */
const COST_LABELS = [["action", "Action"], ["bonus", "Bonus action"], ["reaction", "Reaction"], ["free", "Free"]];
const NEEDS_TARGET = new Set(["attack", "bonus_attack", "grapple", "shove", "opportunity"]);

/** Everything you can do this turn, sorted by what it costs (read from the rules and your features' own text). */
function OptionsList({ convId, combat, target, adv, busy, onStep }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(true);
  const [tip, setTip] = useState("");
  useEffect(() => { api.combatOptions(convId).then(setData).catch(() => setData(null)); }, [convId, combat.round, combat.turn, JSON.stringify(combat.spent || {}), combat.extra_actions, combat.reaction_round]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data?.groups) return null;
  const spent = combat.spent || {};
  const used = { action: spent.action && !combat.extra_actions, bonus: spent.bonus, reaction: combat.reaction_round === combat.round, free: false };
  const use = (o) => (["attack", "dodge", "bonus_attack"].includes(o.kind)
    ? onStep({ move: o.kind, target, advantage: adv })
    : onStep({ move: "use", option: o.id, target, advantage: adv }));
  return (
    <div className="options5e">
      <button type="button" className="section-title link-btn" onClick={() => setOpen((v) => !v)}>{open ? "▾ Your options" : "▸ Your options"}</button>
      {open && COST_LABELS.map(([cost, label]) => (
        <div key={cost} className={`opt-group ${used[cost] ? "spent" : ""}`}>
          <div className="opt-head"><span>{label}</span>{used[cost] && <span className="tiny muted">{cost === "reaction" ? " · used this round" : " · used"}</span>}</div>
          <div className="opt-list">
            {data.groups[cost].map((o) => {
              const noTarget = NEEDS_TARGET.has(o.kind) && !target;
              const empty = o.uses_left === 0;
              return (
                <button key={o.id} type="button" className={`opt ${o.kind === "spell" ? "spell" : o.kind === "feature" ? "feature" : ""}`}
                  disabled={busy || used[cost] || noTarget || empty || (o.kind === "bonus_attack" && !spent.attacked)}
                  title={o.text} onMouseEnter={() => setTip(o.text)} onFocus={() => setTip(o.text)} onClick={() => use(o)}>
                  {o.name}{o.uses_left !== undefined ? ` (${o.uses_left})` : ""}{o.kind === "spell" ? (o.level ? ` · ${o.level}` : " · cantrip") : ""}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {open && tip && <div className="tiny muted opt-tip">{tip}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- active fight */
function FightView({ combat, busy, onAction, onEdit, pools, abilities, convId, onState, martialArts, is5e, faces }) {
  const people = useMemo(() => combat.order.map((id) => combat.combatants.find((c) => c.id === id)), [combat]);
  const enemies = people.filter((c) => c.side === "enemy" && c.hp > 0);
  const [target, setTarget] = useState(enemies[0]?.id || "");
  const [selected, setSelected] = useState(null);
  const [adv, setAdv] = useState("");
  const [other, setOther] = useState("");
  const [stepLine, setStepLine] = useState("");
  const [stepError, setStepError] = useState("");
  const [stepping, setStepping] = useState(false);
  const [describing, setDescribing] = useState(false);
  const [words, setWords] = useState("");
  // "Want to describe it?": your words go under that roll in the round card; no rule changes, no AI call
  const describe = async () => {
    const text = words.trim();
    setDescribing(false); setWords("");
    if (!text) return;
    try { const r = await api.combatDescribe(convId, text); onState(r.state); setStepLine((l) => { const [h, ...rest] = l.split("\n"); return [h, `💬 "${text}"`, ...rest].join("\n"); }); } catch (e) { setStepError(e.message); }
  };
  const spent = combat.spent || { action: false, bonus: false, attacked: false };
  // one part of your turn (attack, bonus strike, dodge): rolled at once, your turn goes on until you end it
  const step = async (body) => {
    setStepping(true); setStepError("");
    try { const r = await api.combatStep(convId, body); setStepLine(r.line); onState(r.state); setDescribing(true); } catch (e) { setStepError(e.message); } finally { setStepping(false); }
  };
  useEffect(() => { if (!enemies.some((e) => e.id === target)) setTarget(enemies[0]?.id || ""); }, [combat]); // eslint-disable-line
  const current = people[combat.turn % people.length];
  const myTurn = current?.side === "player" && current.hp > 0;
  useEffect(() => { if (!myTurn) setStepLine(""); }, [myTurn]);
  const me = people.find((c) => c.side === "player");
  const moveLeft = me ? Math.max(0, (me.speed || 6) - (combat.moved || 0)) : 0;
  const pending = (combat.turn_lines || []).length > 0;
  const select = (id) => {
    setSelected(id);
    const c = people.find((p) => p.id === id);
    if (c?.side === "enemy" && c.hp > 0) setTarget(id);
  };
  const toggleCond = (c, k) => onEdit(c.id, { conditions: c.conditions.includes(k) ? c.conditions.filter((x) => x !== k) : [...c.conditions, k] });

  return (
    <div className="tab-body combat-on">
      <div className="row gap center">
        <div className="section-title grow">Round {combat.round} · {current?.side === "player" ? "your turn" : `${current?.name}'s turn`}</div>
        <span className="tag">{combat.system === "pool" ? "d10 pool" : "d20"}</span>
      </div>
      <Grid combat={combat} selected={selected} onSelect={select} convId={convId} onState={onState} busy={busy}
        myTurn={current?.side === "player"} current={current} faces={faces} />
      {describing && (
        <Modal title="Want to describe it?" onClose={() => { setDescribing(false); setWords(""); }}
          footer={<><button type="button" className="btn ghost" onClick={() => { setDescribing(false); setWords(""); }}>Skip</button>
            <button type="button" className="btn primary" disabled={!words.trim()} onClick={describe}>Add it</button></>}>
          <div className="muted small">{stepLine.split("\n")[0].replace(/\*\*/g, "")}</div>
          <textarea className="field" rows={3} autoFocus value={words} onChange={(e) => setWords(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); describe(); } }}
            placeholder="I swing my sword, trying to cut the goblin's head clean off!" />
          <div className="muted tiny">A bit of roleplay for the round card, under this roll. It changes nothing in the rules.</div>
        </Modal>
      )}
      <div className="turn-order">
        {people.map((c) => (
          <div key={c.id} className={`fighter ${c.id === current?.id ? "current" : ""} ${c.hp <= 0 ? "down" : ""} ${c.id === target ? "targeted" : ""}`} onClick={() => select(c.id)}>
            <div className="row gap center">
              <span className="dot-side" style={{ background: SIDE_COLOR[c.side] }} />
              <span className="grow small"><strong>{c.name}</strong>{c.side === "enemy" && c.id === target && <span className="tiny muted"> · target</span>}
                {c.companion && <span className="tiny muted">{` · 👥 ${c.role}${c.heal ? `, ${c.heals_left} heals` : ""}`}</span>}
                {c.side === "player" && c.dying && <span className="tiny bad-text">{` · 💀 dying ✔${c.death?.ok || 0} ✖${c.death?.fail || 0}`}</span>}
                {c.side === "player" && c.stable && c.hp <= 0 && <span className="tiny muted"> · stable</span>}</span>
              <button className="icon-btn" title="−1 HP" onClick={(e) => { e.stopPropagation(); onEdit(c.id, { hp: c.hp - 1 }); }}>−</button>
              <span className="small hp-num">{c.hp}/{c.max_hp}</span>
              <button className="icon-btn" title="+1 HP" onClick={(e) => { e.stopPropagation(); onEdit(c.id, { hp: c.hp + 1 }); }}>＋</button>
            </div>
            {c.spell && <div className="tiny muted">🔮 {c.mp_name} {c.mp}/{c.mp_max} · {c.spell.name} costs {c.spell.cost}</div>}
            <div className="hpbar small-bar"><div className="hpfill" style={{ width: `${(c.hp / c.max_hp) * 100}%`, background: c.hp / c.max_hp < 0.3 ? "var(--bad)" : c.hp / c.max_hp < 0.6 ? "var(--warn)" : "var(--good)" }} /></div>
            {selected === c.id && (
              <div className="conds">
                {CONDITIONS.map((k) => (
                  <button key={k} className={`chip ${c.conditions.includes(k) ? "on" : ""}`} onClick={(e) => { e.stopPropagation(); toggleCond(c, k); }}>{k}</button>
                ))}
              </div>
            )}
            {selected !== c.id && c.conditions.length > 0 && <div className="tiny muted">{c.conditions.join(", ")}</div>}
          </div>
        ))}
      </div>

      {people.find((c) => c.side === "player")?.hp <= 0 && (
        <div className="muted small down-note">{"💀 You are down. Your death saves are rolled on your turns while your companions fight on: press “Others act” to play the round."}</div>
      )}
      <div className="action-bar">
        <div className="row gap center">
          <select className="field grow" value={target} onChange={(e) => setTarget(e.target.value)}>
            {enemies.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.hp} HP)</option>)}
          </select>
          {combat.system === "d20" && (
            <select className="field" value={adv} onChange={(e) => setAdv(e.target.value)} title="Advantage or disadvantage on this attack">
              <option value="">normal</option><option value="advantage">advantage</option><option value="disadvantage">disadvantage</option>
            </select>
          )}
        </div>
        {myTurn && (
          <div className="turn-budget" aria-label="What is left this turn">
            <span className={`pill small ${spent.action ? "" : "on"}`} title="Attack, Dodge, a spell, something else">{spent.action ? "✔ Action used" : "● Action"}</span>
            <span className={`pill small ${spent.bonus ? "" : "on"}`} title="A Martial Arts strike, Second Wind, a bonus-action spell…">{spent.bonus ? "✔ Bonus used" : "● Bonus action"}</span>
            <span className={`pill small ${moveLeft ? "on" : ""}`} title="Click a lit square on the map to move">{`🏃 ${moveLeft * 5} ft`}</span>
            <span className={`pill small ${combat.reaction_round === combat.round ? "" : "on"}`} title="One check or reaction per round">{combat.reaction_round === combat.round ? "✔ Reaction used" : "● Reaction"}</span>
          </div>
        )}
        <div className="row gap">
          <button className="btn primary grow" disabled={busy || stepping || !target || !myTurn || spent.action} onClick={() => step({ move: "attack", target, advantage: adv })}>⚔ Attack</button>
          <button className="btn" disabled={busy || stepping || !myTurn || spent.action} onClick={() => step({ move: "dodge" })} title="Attacks against you have disadvantage until your next turn">🛡 Dodge</button>
          {martialArts && (
            <button className="btn" disabled={busy || stepping || !target || !myTurn || spent.bonus || !spent.attacked} onClick={() => step({ move: "bonus_attack", target, advantage: adv })}
              title={spent.attacked ? "Martial Arts: an Unarmed Strike as your bonus action" : "Attack first, then strike again as a bonus action"}>👊 Bonus strike</button>
          )}
        </div>
        {myTurn && is5e && <OptionsList convId={convId} combat={combat} target={target} adv={adv} busy={busy || stepping} onStep={step} />}
        {stepLine && <div className="step-line small">{stepLine.split("\n").map((l, i) => <div key={i}>{l.replace(/\*\*/g, "")}</div>)}</div>}
        {stepError && <div className="error-text tiny">{stepError}</div>}
        {myTurn && (
          <button className="btn primary wide big-touch" disabled={busy || stepping} onClick={() => { setStepLine(""); onAction({ action: "act", move: "end" }); }}
            title="Your turn is over: the Aedo tells what you did, then everyone else acts">{pending ? "⏭ End turn (the Aedo tells it)" : "⏭ End turn"}</button>
        )}
        {abilities?.length > 0 && (
          <div className="ability-row">
            {abilities.map((a) => {
              const short = Object.entries(a.costs || {}).find(([k, v]) => (pools?.[k]?.current ?? 0) < v);
              return (
                <button key={a.id} className={`btn small ${a.kind === "attack" ? "primary" : ""}`} disabled={busy || !!short || (a.kind === "attack" && !target)}
                  title={short ? `Not enough ${short[0]}` : `${a.description || a.name}${a.dice ? ` (${a.dice})` : ""}`}
                  onClick={() => onAction({ action: "act", move: "ability", ability: a.id, target, advantage: adv })}>
                  {a.kind === "heal" ? "💚" : a.kind === "attack" ? "✨" : "🔮"} {a.name} · {Object.entries(a.costs || {}).map(([k, v]) => `${v} ${k}`).join(", ") || "free"}
                </button>
              );
            })}
          </div>
        )}
        <div className="row gap">
          <input className="field grow" placeholder="Something else (a spell, a trick, fleeing…)" value={other} onChange={(e) => setOther(e.target.value)} />
          <button className="btn" disabled={busy || !other.trim()} onClick={() => { onAction({ action: "act", move: "other", text: other.trim() }); setOther(""); }}>Do it</button>
        </div>
        <div className="row gap">
          <button className="btn small grow" disabled={busy} onClick={() => onAction({ action: "enemies" })} title="Let everyone else act now">Others act</button>
          <button className="btn small danger" disabled={busy} onClick={async () => { if (await ask.confirm("End the fight now?")) onAction({ action: "end", reason: "the fight was stopped" }); }}>End fight</button>
        </div>
        <div className="muted tiny">Your turn: an action, a bonus action, your movement and a reaction. The app rolls each part at once; press End turn and the Aedo tells it, then everyone else acts. Typing your turn in the chat does it all in one go.</div>
      </div>
    </div>
  );
}

function sceneHasFoes(game) {
  const adv = game.conversation.scenario?.adventure;
  const id = game.state.adventure?.scene;
  return !!(adv?.scenes || []).find((s) => s.id === id && s.enemies?.length);
}

export default function CombatTab({ game, busy, onCombat, onCombatEdit, onState }) {
  const combat = game.state.combat;
  if (combat?.active) return <FightView combat={combat} busy={busy} onAction={onCombat} onEdit={onCombatEdit} pools={game.state.resources} abilities={game.state.abilities}
    convId={game.conversation.id} onState={onState} martialArts={!!game.state.character5e_sheet?.martial_arts} is5e={!!game.state.character5e}
    faces={Object.fromEntries([...(game.npcs || []).filter((n) => n.portraits?.default).map((n) => [n.name, n.portraits.default]),
      ...(game.state.player?.portraits?.default ? [[game.state.player.name, game.state.player.portraits.default]] : [])])} />;
  return (
    <>
      {combat && !combat.active && combat.log?.length > 0 && (
        <div className="tab-body"><div className="muted tiny">Last fight: {combat.log.slice(-3).join(" ")}</div></div>
      )}
      <StartForm convId={game.conversation.id} kind={game.features?.kind} busy={busy} onStart={onCombat}
        sceneFight={sceneHasFoes(game)} hasScene={!!game.state.adventure?.scene && !!game.conversation.scenario?.adventure?.scenes?.length} />
    </>
  );
}
