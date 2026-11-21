import React, { useEffect, useMemo, useState } from "react";
import { ask } from "../dialogs.jsx";
import { api } from "../api.js";
import HelpTip from "./HelpTip.jsx";
import BattleMap, { SIDE_COLOR, TILE_STYLE } from "./BattleMap.jsx";
import MapEditor from "./MapEditor.jsx";

const MAP_TYPES = { field: "Open field", forest: "Forest", dungeon: "Dungeon", cave: "Cave", tavern: "Tavern", river: "River crossing", street: "Town street" };
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
function StartForm({ convId, kind, busy, onStart, sceneFight }) {
  const [system, setSystem] = useState("d20");
  const [enemies, setEnemies] = useState([{ ...BLANK.d20, name: "Bandit", count: 2 }]);
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
    try { const r = await api.generateMap({ type, w: grid.w, h: grid.h, features: feats }); setPreview({ tiles: r.tiles, name: MAP_TYPES[type] }); } catch (e) { setError(e.message); }
  };
  useEffect(() => { if (mapMode === "gen") reroll(); }, [mapMode, mapType, features.join(","), grid.w, grid.h]); // eslint-disable-line
  useEffect(() => {
    if (mapMode !== "saved") return;
    const m = saved.find((x) => String(x.id) === String(savedId)) || saved[0];
    if (m) { setSavedId(String(m.id)); setPreview({ tiles: m.tiles, background: m.background, name: m.name }); } else setPreview(null);
  }, [mapMode, savedId, saved]);
  useEffect(() => { if (mapMode === "empty") setPreview(null); }, [mapMode]);
  useEffect(() => {
    if (mapMode === "scene" && battle) { setGrid({ w: battle.w, h: battle.h }); setPreview({ tiles: [], background: battle.background, name: battle.name, geom: battle.geom, fog: battle.fog }); }
  }, [mapMode, battle]);
  useEffect(() => { if (sceneFight) suggest(); }, [sceneFight]); // eslint-disable-line
  const switchSystem = (s) => { setSystem(s); setEnemies(enemies.map((e) => ({ ...BLANK[s], name: e.name, count: e.count }))); };
  const setEnemy = (i, k, v) => setEnemies(enemies.map((e, j) => (j === i ? { ...e, [k]: v } : e)));
  const suggest = async () => {
    setSuggesting(true); setError("");
    try {
      const r = await api.combatSuggest(convId, system);
      setEnemies(r.enemies);
      if (r.battle) { setBattle(r.battle); setMapMode("scene"); }
      else if (r.map) { setMapMode("gen"); setMapType(r.map.type); setFeatures(r.map.features || []); }
    } catch (e) { setError(e.message); } finally { setSuggesting(false); }
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
            <input className="field grow" placeholder="Name" value={e.name} onChange={(ev) => setEnemy(i, "name", ev.target.value)} />
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
        geom={preview.geom} fog={preview.fog}
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
function Grid({ combat, selected, onSelect, onMove }) {
  const { w, h, tiles = [], background = "", name = "", geom = null, fog = null } = combat.grid;
  const people = combat.combatants;
  const sel = people.find((c) => c.id === selected);
  const [hover, setHover] = useState(null);
  const dist = sel && hover ? Math.max(Math.abs(hover.x - sel.x), Math.abs(hover.y - sel.y)) : 0;
  const occupied = (x, y) => people.some((c) => c.x === x && c.y === y && c.hp > 0);
  const blockedAt = (x, y) => BLOCKING.includes(tiles[y]?.[x] || ".");
  const hoverTile = hover ? TILE_STYLE[tiles[hover.y]?.[hover.x] || "."] : null;
  return (
    <div className="grid-wrap">
      <BattleMap w={w} h={h} tiles={tiles} background={background} tokens={people} selected={selected} geom={geom} cell={geom ? 28 : 30}
        // fog of war: the places already visited stay clear, and your side sees around itself
        fog={fog ? [...fog, ...people.filter((c) => c.side !== "enemy" && c.hp > 0).map((c) => ({ x: c.x + 0.5, y: c.y + 0.5, r: 4 }))] : null}
        onToken={onSelect} onLeave={() => setHover(null)} onCellEnter={(x, y) => setHover({ x, y })}
        onCell={(x, y) => { if (sel && !occupied(x, y) && !blockedAt(x, y)) onMove(sel.id, x, y); }} />
      <div className="muted tiny">
        {name && <>{name} · </>}
        {sel ? <>Selected: <strong>{sel.name}</strong>. Click an open square to move{hover && dist ? ` (${dist} squares, ${dist * 5} ft)` : ""}.</> : "Click a token to select it (enemies become your target)."}
        {hoverTile && hoverTile.label !== "Floor / grass" && <> · {hoverTile.label}</>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- active fight */
function FightView({ combat, busy, onAction, onEdit, pools, abilities }) {
  const people = useMemo(() => combat.order.map((id) => combat.combatants.find((c) => c.id === id)), [combat]);
  const enemies = people.filter((c) => c.side === "enemy" && c.hp > 0);
  const [target, setTarget] = useState(enemies[0]?.id || "");
  const [selected, setSelected] = useState(null);
  const [adv, setAdv] = useState("");
  const [other, setOther] = useState("");
  useEffect(() => { if (!enemies.some((e) => e.id === target)) setTarget(enemies[0]?.id || ""); }, [combat]); // eslint-disable-line
  const current = people[combat.turn % people.length];
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
      <Grid combat={combat} selected={selected} onSelect={select} onMove={(id, x, y) => onEdit(id, { x, y })} />
      <div className="turn-order">
        {people.map((c) => (
          <div key={c.id} className={`fighter ${c.id === current?.id ? "current" : ""} ${c.hp <= 0 ? "down" : ""} ${c.id === target ? "targeted" : ""}`} onClick={() => select(c.id)}>
            <div className="row gap center">
              <span className="dot-side" style={{ background: SIDE_COLOR[c.side] }} />
              <span className="grow small"><strong>{c.name}</strong>{c.side === "enemy" && c.id === target && <span className="tiny muted"> · target</span>}</span>
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
        <div className="row gap">
          <button className="btn primary grow" disabled={busy || !target} onClick={() => onAction({ action: "act", move: "attack", target, advantage: adv })}>⚔ Attack</button>
          <button className="btn" disabled={busy} onClick={() => onAction({ action: "act", move: "dodge" })} title="Attacks against you have disadvantage until your next turn">🛡 Dodge</button>
        </div>
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
        <div className="muted tiny">The app rolls everything and the Aedo narrates it. One reply per round: your action, then everyone else.</div>
      </div>
    </div>
  );
}

function sceneHasFoes(game) {
  const adv = game.conversation.scenario?.adventure;
  const id = game.state.adventure?.scene;
  return !!(adv?.scenes || []).find((s) => s.id === id && s.enemies?.length);
}

export default function CombatTab({ game, busy, onCombat, onCombatEdit }) {
  const combat = game.state.combat;
  if (combat?.active) return <FightView combat={combat} busy={busy} onAction={onCombat} onEdit={onCombatEdit} pools={game.state.resources} abilities={game.state.abilities} />;
  return (
    <>
      {combat && !combat.active && combat.log?.length > 0 && (
        <div className="tab-body"><div className="muted tiny">Last fight: {combat.log.slice(-3).join(" ")}</div></div>
      )}
      <StartForm convId={game.conversation.id} kind={game.features?.kind} busy={busy} onStart={onCombat}
        sceneFight={sceneHasFoes(game)} />
    </>
  );
}
