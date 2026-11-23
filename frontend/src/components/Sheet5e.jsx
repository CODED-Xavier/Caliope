import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { LibraryPicker, DRAG_TYPE } from "./Library.jsx";
import Builder, { emblemFor } from "./Builder.jsx";
import LevelUp, { LevelTable } from "./LevelUp.jsx";
import Modal from "./Modal.jsx";
import { portraitSrc } from "../portraits.js";

const ABILS = [["str", "STR"], ["dex", "DEX"], ["con", "CON"], ["int", "INT"], ["wis", "WIS"], ["cha", "CHA"]];
const sig = (n) => (n >= 0 ? `+${n}` : `${n}`);
const SKILL_NAMES = {
  acrobatics: "Acrobatics", "animal handling": "Animal Handling", arcana: "Arcana", athletics: "Athletics", deception: "Deception",
  history: "History", insight: "Insight", intimidation: "Intimidation", investigation: "Investigation", medicine: "Medicine",
  nature: "Nature", perception: "Perception", performance: "Performance", persuasion: "Persuasion", religion: "Religion",
  "sleight of hand": "Sleight of Hand", stealth: "Stealth", survival: "Survival",
};

/**
 * The D&D 5e sheet kept by the app: every number is worked out from the class, race, background, scores and items.
 * Things come from the Library (drag a row onto the sheet, or press ＋); the rules are checked before they go on.
 */
export default function Sheet5e({ convId, state, busy, onUse, onRest, onRoll, onState, openBuilder, onBuilderShown, who = "", npcs = [] }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null); // { text, change } — a refused change can be added anyway
  const [showLib, setShowLib] = useState(false);
  const [over, setOver] = useState(false);
  const [modal, setModal] = useState(openBuilder ? "builder" : null);
  const [openFeat, setOpenFeat] = useState(null);
  const [showSkills, setShowSkills] = useState(false);
  const [working, setWorking] = useState(false);
  const charKey = JSON.stringify((who ? (state.party5e || {})[who] : state.character5e) || null);
  const lastKey = useRef("");

  useEffect(() => { if (openBuilder) { setModal("builder"); onBuilderShown?.(); } }, [openBuilder]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (lastKey.current === charKey && data) return;
    lastKey.current = charKey;
    api.character5e(convId, who).then(setData).catch((e) => setError({ text: e.message }));
  }, [convId, charKey, who]); // eslint-disable-line react-hooks/exhaustive-deps

  const took = (r) => {
    setData(r);
    lastKey.current = JSON.stringify(r.character || null);
    onState?.(who
      ? { ...state, party5e: { ...(state.party5e || {}), [who]: r.character }, party: r.party || state.party, party5e_sheet: r.party5e_sheet || state.party5e_sheet }
      : { ...state, character5e: r.character, ...(r.player ? { player: r.player } : {}), ...(r.party5e_sheet ? { party5e_sheet: r.party5e_sheet, party: r.party } : {}) });
  };
  const change = async (c) => {
    setWorking(true); setError(null);
    try { took(await api.changeCharacter5e(convId, c, who)); } catch (e) { setError({ text: e.message, change: c.op === "add" && !c.homebrew ? c : null }); } finally { setWorking(false); }
  };
  const add = (ref) => change({ op: "add", ...ref });
  const drop = (e) => {
    e.preventDefault(); setOver(false);
    try { const ref = JSON.parse(e.dataTransfer.getData(DRAG_TYPE) || "null"); if (ref) add(ref); } catch { /* not a Library row */ }
  };

  if (!data) return <div className="tab-body muted small pad">{error ? error.text : "Loading the sheet…"}</div>;
  const ch = data.character || {};
  const sh = data.sheet;
  const p = state.player || {};
  const inFight = !!state.combat?.active;
  const disabled = busy || working;
  const xpPct = sh?.next_level_xp ? Math.min(100, Math.round((sh.xp / sh.next_level_xp) * 100)) : 100;
  const ready = sh?.next_level_xp && sh.xp >= sh.next_level_xp;
  const hpPct = sh ? Math.max(0, Math.min(100, (sh.hp / Math.max(1, sh.hp_max)) * 100)) : 0;
  const removable = (slot, name) => (ch[slot] || []).findIndex((x) => x.name === name);

  return (
    <div className={`tab-body sheet5e ${over ? "drop-over" : ""}`}
      onDragOver={(e) => { if (Array.from(e.dataTransfer.types || []).includes(DRAG_TYPE)) { e.preventDefault(); setOver(true); } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(false); }} onDrop={drop}>
      <div className="s5-head">
        {who && faceOf(npcs, who) && <img className="s5-face" src={portraitSrc(faceOf(npcs, who))} alt="" />}
        {sh?.class && <img className="s5-emblem" src={emblemFor("class", sh.class)} alt="" />}
        <div className="grow">
          <div className="s5-name">{who || p.name || "Your hero"}</div>
          <div className="muted small">{[sh?.race && `${sh.subrace ? `${sh.subrace} ` : ""}${sh.race}`, sh?.class && `${sh.class} ${sh.level}${sh.subclass ? ` (${sh.subclass})` : ""}`, sh?.background].filter(Boolean).join(" · ") || "Nothing chosen yet"}</div>
        </div>
        <button type="button" className="btn small ghost" onClick={() => setModal("builder")} title="Class, race, background, scores, skills, equipment">✎ Builder</button>
      </div>
      {sh && (
        <div className="s5-xp" title={`${sh.xp} XP${sh.next_level_xp ? ` · level ${sh.level + 1} at ${sh.next_level_xp}` : ""}`}>
          <span className="tiny muted">{sh.next_level_xp ? `${sh.xp} / ${sh.next_level_xp} XP` : `${sh.xp} XP · highest level`}</span>
          <span className="tracker-bar wide"><span style={{ width: `${xpPct}%` }} /></span>
          {sh.class && <button type="button" className="btn small ghost" onClick={() => setModal("levels")} title="What each level of your class gives">📜 Levels</button>}
          {sh.level < 20 && sh.class && <button type="button" className={`btn small ${ready ? "primary" : ""}`} disabled={disabled || inFight} onClick={() => setModal("levelup")}>⬆ Level up</button>}
        </div>
      )}
      {(sh?.warnings || []).map((w) => <div key={w} className="warn-text tiny">⚠ {w}</div>)}

      {sh && (
        <>
          <div className="s5-abilities">
            {ABILS.map(([k, label]) => (
              <button type="button" key={k} className="s5-ability" title={`${label} ${sh.abilities[k].score}${sh.abilities[k].how ? ` (${sh.abilities[k].how})` : ""} · click to roll a check`}
                onClick={() => onRoll?.(`1d20${sig(sh.abilities[k].mod)}`)} disabled={busy}>
                <span className="s5-ab-label">{label}</span>
                <span className="s5-ab-mod">{sig(sh.abilities[k].mod)}</span>
                <span className="s5-ab-score">{sh.abilities[k].score}</span>
                {sh.save_prof.includes(k) && <span className="s5-ab-save" title="Saving throw proficiency">●</span>}
              </button>
            ))}
          </div>
          <div className="s5-stats">
            <div className="s5-stat" title={sh.ac_how}><span className="s5-stat-num">{sh.ac}</span><span className="s5-stat-label">AC</span><span className="s5-stat-how">{sh.ac_how}</span></div>
            <div className="s5-stat hp">
              <span className="s5-stat-num">{`${sh.hp}/${sh.hp_max}`}</span><span className="s5-stat-label">{`HP · ${sh.hit_die}`}</span>
              <div className="hp-track thin"><div className="hp-fill" style={{ width: `${hpPct}%` }} /></div>
              <div className="row gap tight">
                <button type="button" className="icon-btn" disabled={disabled} onClick={() => change({ op: "set", field: "hp_current", value: Math.max(0, sh.hp - 1) })} title="Lose 1 HP">−</button>
                <button type="button" className="icon-btn" disabled={disabled} onClick={() => change({ op: "set", field: "hp_current", value: Math.min(sh.hp_max, sh.hp + 1) })} title="Heal 1 HP">＋</button>
              </div>
            </div>
            <div className="s5-stat"><span className="s5-stat-num">{sig(sh.prof)}</span><span className="s5-stat-label">Proficiency</span></div>
            <div className="s5-stat"><span className="s5-stat-num">{sig(sh.initiative)}</span><span className="s5-stat-label">Initiative</span></div>
            <div className="s5-stat"><span className="s5-stat-num">{sh.speed}</span><span className="s5-stat-label">Speed (ft)</span></div>
            <div className="s5-stat"><span className="s5-stat-num">{sh.passive_perception}</span><span className="s5-stat-label">Passive Perception</span></div>
          </div>

          <button type="button" className="section-title link-btn" onClick={() => setShowSkills((v) => !v)}>{showSkills ? "▾ Saves & skills" : "▸ Saves & skills"}</button>
          {showSkills && (
            <div className="s5-skills">
              {ABILS.map(([k, label]) => (
                <button type="button" key={k} className={`s5-skill ${sh.save_prof.includes(k) ? "prof" : ""}`} onClick={() => onRoll?.(`1d20${sig(sh.saves[k])}`)} disabled={busy}>
                  <span>{`${label} save`}</span><strong>{sig(sh.saves[k])}</strong>
                </button>
              ))}
              {Object.entries(sh.skills).map(([k, v]) => (
                <button type="button" key={k} className={`s5-skill ${v.proficient ? "prof" : ""} ${v.expertise ? "exp" : ""}`} onClick={() => onRoll?.(`1d20${sig(v.bonus)}`)} disabled={busy}>
                  <span>{SKILL_NAMES[k] || k}</span><strong>{sig(v.bonus)}</strong>
                </button>
              ))}
            </div>
          )}

          {sh.attacks.length > 0 && <div className="section-title">Attacks</div>}
          {sh.attacks.map((a, i) => (
            <div className="s5-row" key={`${a.name}-${i}`}>
              <div className="grow"><strong>{a.name}</strong> <span className="muted tiny">{[a.range, a.dtype, ...(a.properties || [])].filter(Boolean).join(" · ")}</span></div>
              <button type="button" className="btn small" disabled={busy} onClick={() => onRoll?.(`1d20${sig(a.bonus)}`)} title="Roll to hit">{sig(a.bonus)}</button>
              <button type="button" className="btn small" disabled={busy} onClick={() => onRoll?.(a.damage)} title="Roll damage">{a.damage}</button>
            </div>
          ))}

          <Resources sh={sh} who={who} disabled={disabled} onUse={onUse} change={change} />
          {((ch.spells || []).length > 0 || sh.spell_counts) && (
            <>
              <div className="section-title">Spells</div>
              {sh.spell_counts && <SpellCounts c={sh.spell_counts} />}
              {(ch.spells || []).map((s, i) => (
                <div className="s5-row" key={`${s.name}-${i}`}>
                  {sh.spell_counts?.mode === "spellbook" && (
                    <input type="checkbox" checked={s.prepared !== false} disabled={disabled} title="Prepared today (unticked: only in your spellbook)"
                      onChange={(e) => change({ op: "prepare", index: i, on: e.target.checked })} />
                  )}
                  <div className="grow">{s.name}{s.homebrew && <span className="pill small">house rule</span>}</div>
                  <button type="button" className="icon-btn" disabled={disabled} onClick={() => change({ op: "remove", slot: "spells", index: i })} title="Remove">✕</button>
                </div>
              ))}
            </>
          )}

          <div className="section-title">Features</div>
          {sh.features.length === 0 && <div className="muted tiny">Choose a class to get its features.</div>}
          {sh.features.map((f) => {
            const left = f.uses_max ? f.uses_max - f.used : 0;
            const fi = removable("feats", f.name);
            const oi = removable("options", f.name);
            const xi = (ch.extras || []).findIndex((x) => x.name === f.name);
            return (
              <div className="s5-feature" key={`${f.name}-${f.level}`}>
                <div className="row gap center">
                  <button type="button" className="link-btn grow s5-feature-name" onClick={() => setOpenFeat(openFeat === f.name ? null : f.name)}>
                    {f.name} <span className="muted tiny">{f.level ? `· level ${f.level}` : f.homebrew ? "· house rule" : ""}</span>
                  </button>
                  {f.uses_max ? <span className="muted tiny" title="Spent from the Resources section">{`${left}/${f.uses_max}`}</span> : null}
                  {(fi >= 0 || oi >= 0 || xi >= 0) && (
                    <button type="button" className="icon-btn" disabled={disabled} title="Remove"
                      onClick={() => change({ op: "remove", slot: fi >= 0 ? "feats" : oi >= 0 ? "options" : "extras", index: fi >= 0 ? fi : oi >= 0 ? oi : xi })}>✕</button>
                  )}
                </div>
                {openFeat === f.name && f.text && <div className="s5-feature-text small">{f.text}</div>}
              </div>
            );
          })}
        </>
      )}

      <div className="section-title">Equipment</div>
      {(ch.items || []).length === 0 && <div className="muted tiny">No items yet.</div>}
      {(ch.items || []).map((it, i) => (
        <div className="s5-row" key={`${it.name}-${i}`}>
          <label className="row gap center grow" title="Worn or held: armour counts for AC, weapons become attacks">
            <input type="checkbox" checked={!!it.equipped} disabled={disabled} onChange={(e) => change({ op: "equip", index: i, on: e.target.checked })} />
            <span>{it.name}{it.qty > 1 ? ` ×${it.qty}` : ""}</span>{it.homebrew && <span className="pill small">house rule</span>}
          </label>
          <button type="button" className="icon-btn" disabled={disabled} onClick={() => change({ op: "remove", slot: "items", index: i })} title="Remove">✕</button>
        </div>
      ))}

      {!who && (
        <div className="row gap">
          <button className="btn small grow" disabled={busy || inFight} onClick={() => onRest?.("short")} title="About an hour of rest">☕ Short rest</button>
          <button className="btn small grow" disabled={busy || inFight} onClick={() => onRest?.("long")} title="A night's sleep: refills more and heals">🛌 Long rest</button>
        </div>
      )}
      {!who && state.party_mode === "companions" && Object.keys(state.party || {}).length > 0 && (
        <Companions convId={convId} state={state} npcs={npcs} busy={disabled} heroReady={!!ch.cls} onState={onState} onRoll={onRoll} />
      )}

      {error && (
        <div className="error-text small s5-error">
          {error.text}
          {error.change && <button type="button" className="link-btn" onClick={() => change({ ...error.change, homebrew: true })}>Add anyway (house rule)</button>}
        </div>
      )}
      <div className={`s5-drop ${over ? "on" : ""}`}>
        <span className="small">{over ? "Drop it on the sheet" : "Drag spells, items and feats here from the Library, or press ＋."}</span>
        <button type="button" className="btn small" onClick={() => setShowLib((v) => !v)}>{showLib ? "Hide the Library" : "📚 Open the Library"}</button>
      </div>
      {showLib && <LibraryPicker edition={ch.edition || "2014"} onAdd={add} busy={disabled} />}

      {modal === "builder" && <Builder convId={convId} who={who} onClose={() => setModal(null)} onChanged={took} />}
      {modal === "levels" && <Modal title={`📜 ${sh?.class || "Class"}: what each level gives`} onClose={() => setModal(null)} wide><LevelTable convId={convId} who={who} /></Modal>}
      {modal === "levelup" && <LevelUp convId={convId} who={who} onClose={() => setModal(null)} onDone={(r) => { took(r); setModal(null); }} />}
    </div>
  );
}

const faceOf = (npcs, name) => ((npcs || []).find((n) => n.name === name)?.portraits?.default || "");

const ROLE_LABELS = { front: "front-liner", healer: "healer", caster: "spellcaster", support: "support" };

/**
 * The companions' 5e sheets: the system builds them around your hero (a balanced party has a front-liner, a healer,
 * a spellcaster and a support, though in D&D one class can do several), or you build one step by step.
 */
function Companions({ convId, state, npcs, busy, heroReady, onState, onRoll }) {
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");
  const [building, setBuilding] = useState("");
  const [viewing, setViewing] = useState("");
  const names = Object.keys(state.party || {});
  const sheets = state.party5e_sheet || {};
  const missing = names.filter((n) => !(state.party5e || {})[n]);
  const took = (r) => onState?.({ ...state, party: r.party || state.party, party5e_sheet: r.party5e_sheet || state.party5e_sheet,
    party5e: { ...(state.party5e || {}), ...Object.fromEntries(names.map((n) => [n, (state.party5e || {})[n]]).filter(([, v]) => v)) } });
  const auto = async (body, tag) => {
    setWorking(tag); setError("");
    try {
      await api.autoParty5e(convId, body);
      const full = await api.state(convId);
      onState?.(full);
    } catch (e) { setError(e.message); } finally { setWorking(""); }
  };
  const roles = new Set(Object.values(sheets).flatMap((x) => x.roles || []));
  return (
    <div className="companions5e">
      <div className="section-title">Your companions</div>
      <div className="chip-row tight" title="A balanced party: a front-liner, a healer, a spellcaster and a support. In D&D one class can cover several.">
        {Object.entries(ROLE_LABELS).map(([k, label]) => <span key={k} className={`pill small ${roles.has(k) ? "on" : ""}`}>{roles.has(k) ? "✓ " : ""}{label}</span>)}
      </div>
      {!heroReady && <div className="muted tiny">Build your own hero first: the system picks the companions around your class.</div>}
      {missing.length > 0 && heroReady && (
        <button type="button" className="btn small primary" disabled={busy || !!working} onClick={() => auto({}, "all")}>
          {working === "all" ? "Building…" : `🎲 Let the system build ${missing.length === 1 ? missing[0] : `all ${missing.length}`}`}
        </button>
      )}
      {error && <div className="error-text tiny">{error}</div>}
      {names.map((n) => {
        const sh = sheets[n];
        const hp = (state.party || {})[n] || {};
        return (
          <div key={n} className="s5-row companion-row">
            {faceOf(npcs, n) ? <img className="s5-face small" src={portraitSrc(faceOf(npcs, n))} alt="" />
              : sh && <img className="s5-emblem small" src={emblemFor("class", sh.class)} alt="" />}
            <div className="grow">
              <strong>{n}</strong>
              <div className="muted tiny">{sh ? `${sh.class} ${sh.level}${sh.subclass ? ` (${sh.subclass})` : ""} · AC ${sh.ac} · ${hp.hp}/${hp.max_hp} HP · ${(sh.roles || []).map((r) => ROLE_LABELS[r]).join(", ")}` : "No 5e sheet yet"}</div>
            </div>
            {sh && <button type="button" className="btn small" onClick={() => setViewing(n)}>Sheet</button>}
            <button type="button" className="btn small" disabled={busy || !heroReady || !!working} title="The system picks class, race, background and gear to fill a gap in the party"
              onClick={() => auto({ name: n }, n)}>{working === n ? "…" : "🎲"}</button>
            <button type="button" className="btn small" disabled={busy} title="Build step by step, like your own hero" onClick={() => setBuilding(n)}>✎</button>
          </div>
        );
      })}
      {building && <Builder convId={convId} who={building} onClose={() => { setBuilding(""); api.state(convId).then((s) => onState?.(s)).catch(() => {}); }} onChanged={took} />}
      {viewing && (
        <Modal title={viewing} onClose={() => setViewing("")} wide>
          <Sheet5e convId={convId} state={state} who={viewing} npcs={npcs} busy={busy} onRoll={onRoll} onState={onState} />
        </Modal>
      )}
    </div>
  );
}

const POOLS = ["lay on hands", "ki", "monk's focus", "font of magic", "sorcery points"];

/** Resources: what the hero spends and gets back on rests (features with uses, pools of points, spell slots). The
 * same things are spent when the player names them in the chat ("I use Lay on Hands for 5"). */
function Resources({ sh, who, disabled, onUse, change }) {
  const [amounts, setAmounts] = useState({});
  const feats = sh.features.filter((f) => f.uses_max);
  const levels = Object.entries(sh.slots || {});
  const smite = sh.class === "Paladin" && sh.level >= 2 && (levels.length > 0);
  if (!feats.length && !levels.length && !sh.pact) return null;
  const back = (f) => (f.per === "short" ? "back after a short rest" : "back after a long rest");
  return (
    <div className="s5-resources">
      <div className="section-title">Resources</div>
      {sh.spell_dc ? <div className="muted tiny">{`Spell save DC ${sh.spell_dc} · spell attack ${sig(sh.spell_attack || 0)}`}</div> : null}
      {feats.map((f) => {
        const left = f.uses_max - f.used;
        const pool = POOLS.includes(f.name.toLowerCase());
        return (
          <div className="s5-res-row" key={f.name}>
            <span className="grow"><strong>{f.name}</strong> <span className="muted tiny">{back(f)}</span></span>
            {pool || f.uses_max > 8
              ? <span className="s5-res-count" title={`${left} of ${f.uses_max} left`}>{`${left}/${f.uses_max}`}</span>
              : <span className="pips" title={`${left} of ${f.uses_max} left · ${back(f)}`}>{Array.from({ length: f.uses_max }).map((_, i) => <span key={i} className={`pip ${i < left ? "on" : ""}`} />)}</span>}
            {!who && pool && (
              <input type="number" className="s5-res-amount" min="1" max={left} value={amounts[f.name] || ""} placeholder={f.name === "Lay on Hands" ? "HP" : "1"}
                title={f.name === "Lay on Hands" ? "How many points to spend (empty: heal what you are missing)" : "How many points to spend"}
                onChange={(e) => setAmounts({ ...amounts, [f.name]: e.target.value })} />
            )}
            {!who && <button type="button" className="btn small primary" disabled={disabled || left <= 0}
              onClick={() => { onUse?.(f.name, Number(amounts[f.name]) || undefined); setAmounts({ ...amounts, [f.name]: "" }); }}
              title={left <= 0 ? `Used up: ${back(f)}` : "Use it: the app spends it and tells the Aedo"}>Use</button>}
          </div>
        );
      })}
      {levels.map(([lv, n]) => {
        const left = (sh.slots_left || {})[lv] ?? n;
        return (
          <div className="s5-res-row" key={lv}>
            <span className="grow"><strong>{`Level ${lv} slots`}</strong> <span className="muted tiny">back after a long rest</span></span>
            <span className="pips" title={`${left} of ${n} left`}>{Array.from({ length: n }).map((_, i) => <span key={i} className={`pip slot ${i < left ? "on" : ""}`} />)}</span>
            {!who && (
              <>
                <button type="button" className="icon-btn" disabled={disabled || left <= 0} title="Spend a slot (a spell cast in the story)" onClick={() => change({ op: "slot", level: lv, delta: 1 })}>−</button>
                <button type="button" className="icon-btn" disabled={disabled || left >= n} title="Give a slot back" onClick={() => change({ op: "slot", level: lv, delta: -1 })}>＋</button>
              </>
            )}
          </div>
        );
      })}
      {sh.pact && (
        <div className="s5-res-row">
          <span className="grow"><strong>{`Pact slots (level ${sh.pact.level})`}</strong> <span className="muted tiny">back after a short rest</span></span>
          <span className="pips" title={`${sh.pact_left ?? sh.pact.count} of ${sh.pact.count} left`}>{Array.from({ length: sh.pact.count }).map((_, i) => <span key={i} className={`pip slot ${i < (sh.pact_left ?? sh.pact.count) ? "on" : ""}`} />)}</span>
          {!who && (
            <>
              <button type="button" className="icon-btn" disabled={disabled || !(sh.pact_left ?? sh.pact.count)} title="Spend a slot (a spell cast in the story)" onClick={() => change({ op: "slot", level: "pact", delta: 1 })}>−</button>
              <button type="button" className="icon-btn" disabled={disabled || (sh.pact_left ?? sh.pact.count) >= sh.pact.count} title="Give a slot back" onClick={() => change({ op: "slot", level: "pact", delta: -1 })}>＋</button>
            </>
          )}
        </div>
      )}
      {smite && <div className="muted tiny">⚡ Divine Smite: after a melee hit, spend a slot for 2d8 radiant (+1d8 per level above 1st, +1d8 against undead and fiends). In fights it is one of your options.</div>}
      {!who && <div className="muted tiny">Say it in the chat too: “I use Lay on Hands for 5”, “I rage”, “I cast Cure Wounds at 2nd level”. The app spends it.</div>}
    </div>
  );
}

/** How many cantrips and spells this level has, against what the sheet holds. */
function SpellCounts({ c }) {
  const part = (label, have, max) => <span className={`pill ${have > max ? "warn" : ""}`}>{`${label} ${have}/${max}`}</span>;
  return (
    <div className="chip-row tight">
      {c.cantrips > 0 && part("Cantrips", c.have_cantrips, c.cantrips)}
      {c.mode === "known" && part("Spells known", c.have_spells, c.known || 0)}
      {c.mode === "spellbook" && <span className="pill">{`Spellbook ${c.have_spells}/${c.spellbook}`}</span>}
      {c.mode === "spellbook" && part("Prepared", c.have_prepared, c.prepared || 0)}
      {c.mode === "prepared" && part("Prepared", c.have_spells, c.prepared || 0)}
    </div>
  );
}
