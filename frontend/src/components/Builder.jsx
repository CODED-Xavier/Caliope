import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import Modal from "./Modal.jsx";

const ABILS = [["str", "STR"], ["dex", "DEX"], ["con", "CON"], ["int", "INT"], ["wis", "WIS"], ["cha", "CHA"]];
const POINT_COST = { 8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9 };
const METHOD_LABELS = { standard: "Standard array", pointbuy: "Point buy (27)", roll: "Roll 4d6", manual: "Type them in" };
const SKILL_NAMES = { "animal handling": "Animal Handling", "sleight of hand": "Sleight of Hand" };
const skillName = (s) => SKILL_NAMES[s] || s.charAt(0).toUpperCase() + s.slice(1);
const roll4d6 = () => { const d = Array.from({ length: 4 }, () => 1 + Math.floor(Math.random() * 6)).sort((a, b) => a - b); return d[1] + d[2] + d[3]; };

const CLASS_EMBLEMS = ["artificer", "barbarian", "bard", "cleric", "druid", "fighter", "monk", "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard"];
// race slugs with an emblem in /emblems/race-<slug>.png (most specific first: "half-orc" before "orc")
const RACE_EMBLEMS = ["custom-lineage", "shadar-kai", "half-orc", "dragonborn", "tiefling", "aasimar", "warforged", "autognome", "lizardfolk", "shifter", "triton",
  "goblin", "gnome", "dwarf", "human", "fairy", "faerie", "drow", "eladrin", "goliath", "halfling", "minotaur", "boggart", "kobold", "kender", "lupin",
  "merfolk", "vampire", "dhampir", "satyr", "skeleton", "elf", "orc"];
const slug = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/** The emblem shown on a class (or race) card; classes without their own get the generic one. */
export function emblemFor(type, name) {
  const n = slug(name);
  if (type === "class") return `/emblems/${CLASS_EMBLEMS.includes(n) ? n : "class"}.png`;
  if (type === "race") { const r = RACE_EMBLEMS.find((x) => n === x || n.startsWith(`${x}-`) || n.endsWith(`-${x}`)); return r ? `/emblems/race-${r}.png` : ""; }
  return "";
}

const EQUIP_CATEGORIES = [["", "All"], ["weapon", "Weapons"], ["armor", "Armour & shields"], ["gear", "Adventuring gear"], ["tools", "Tools"],
  ["ammunition", "Ammunition"], ["mounts", "Mounts & vehicles"]];

/** What a class gives at each level, a race's traits, a background's skills, gear and feature. */
function Details({ type, entry }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.libraryDetails(type, entry.source, entry.name).then(setD).catch((e) => setError(e.message)); }, [type, entry.source, entry.name]);
  if (error) return <div className="error-text tiny">{error}</div>;
  if (!d) return <div className="muted tiny">Loading…</div>;
  const chips = (pairs) => <div className="chip-row tight">{pairs.filter(([, v]) => v && (!Array.isArray(v) || v.length)).map(([k, v]) => <span key={k} className="pill small"><strong>{k}</strong>&nbsp;{Array.isArray(v) ? v.join(", ") : v}</span>)}</div>;
  if (d.kind === "class") {
    return (
      <div className="details">
        {chips([["Hit die", d.hit_die], ["Saves", d.saves], ["Armour", d.armor], ["Weapons", d.weapons], ["Spellcasting", d.spellcasting]])}
        {d.skills && <div className="small">{`Skills: ${d.skills}`}</div>}
        {d.subclasses.length > 0 && <div className="small">{`${d.subclass_title} (level ${d.subclass_level}): ${d.subclasses.join(", ")}`}</div>}
        <table className="level-table">
          <thead><tr><th>Lv</th><th>Prof</th><th>Features</th>{d.levels.some((l) => l.slots || l.pact) && <th>Slots</th>}</tr></thead>
          <tbody>
            {d.levels.map((l) => (
              <tr key={l.level} className={l.features.length ? "" : "quiet"}>
                <td>{l.level}</td><td>{`+${l.prof}`}</td><td>{l.features.join(", ") || "–"}</td>
                {d.levels.some((x) => x.slots || x.pact) && <td>{l.pact ? `${l.pact.count} × ${l.pact.level}` : Object.entries(l.slots || {}).map(([k, v]) => `${v}×${k}`).join(" ") || "–"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (d.kind === "race") {
    return (
      <div className="details">
        {chips([["Ability scores", d.abilities], ["Speed", `${d.speed} ft`], ["Size", d.size], ["Darkvision", d.darkvision ? `${d.darkvision} ft` : ""], ["Subraces", d.subraces]])}
        {d.traits.map((t) => <div key={t.name} className="small"><strong>{t.name}.</strong> <span className="muted">{t.text}</span></div>)}
      </div>
    );
  }
  return (
    <div className="details">
      {chips([["Skills", d.skills], ["Tools", d.tools], ["Languages", d.languages]])}
      {d.equipment.length > 0 && <div className="small"><strong>Equipment.</strong> <span className="muted">{d.equipment.join("; ")}</span></div>}
      {d.feature && <div className="small"><strong>{d.feature.name}.</strong> <span className="muted">{d.feature.text}</span></div>}
    </div>
  );
}

/** Pick from the Library with big cards (class, race, background, equipment). The ▸ arrow shows what it gives. */
export const money = (cp) => { // copper pieces -> "15 gp 5 sp"
  const gp = Math.floor(cp / 100), sp = Math.floor((cp % 100) / 10), c = cp % 10;
  return [gp && `${gp} gp`, sp && `${sp} sp`, c && `${c} cp`].filter(Boolean).join(" ") || "0 gp";
};

function OptionCards({ type, edition, onPick, picked, busy, categories, cls = "", maxLevel = -1, buyLabel = "" }) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [open, setOpen] = useState("");
  const [results, setResults] = useState([]);
  useEffect(() => {
    const t = setTimeout(() => { api.librarySearch(type, q, edition, cat, false, cls, maxLevel).then((r) => setResults((r?.results || []).slice(0, 80))).catch(() => setResults([])); }, 200);
    return () => clearTimeout(t);
  }, [type, q, edition, cat, cls, maxLevel]);
  const detailed = ["class", "race", "background"].includes(type);
  return (
    <>
      <input className="field big-touch" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" aria-label="Search" />
      {categories && (
        <div className="chip-row tight">
          {EQUIP_CATEGORIES.map(([k, label]) => <button key={k || "all"} type="button" className={`pill small ${cat === k ? "on" : ""}`} onClick={() => setCat(k)}>{label}</button>)}
        </div>
      )}
      <div className="option-cards">
        {results.length === 0 && <div className="muted small pad">Nothing found.</div>}
        {results.map((r) => {
          const key = `${r.source}-${r.name}`;
          const img = emblemFor(r.type || type, r.name);
          const isOpen = open === key;
          return (
            <div key={key} className={`option-card ${img ? "with-emblem" : ""} ${picked && picked.name === r.name && picked.source === r.source ? "on" : ""} ${isOpen ? "open" : ""}`}>
              <button type="button" className="option-main" disabled={busy} onClick={() => onPick({ type: r.type || type, name: r.name, source: r.source })}>
                {img && <img className="option-emblem" src={img} alt="" />}
                <span className="option-text">
                  <span className="option-name">{r.name}</span>
                  <span className="option-src">{`${r.source}${r.srd ? " · SRD" : ""}${r.category ? ` · ${r.category}` : ""}${r.level !== undefined && type === "spell" ? (r.level ? ` · level ${r.level}` : " · cantrip") : ""}${buyLabel && r.value ? ` · ${money(r.value)}` : ""}`}</span>
                  {r.summary && !isOpen && <span className="option-sum">{r.summary}</span>}
                </span>
              </button>
              {detailed && (
                <button type="button" className="option-more" aria-expanded={isOpen} title={isOpen ? "Hide" : "See what it gives"} onClick={() => setOpen(isOpen ? "" : key)}>
                  {isOpen ? "▾" : "▸"}
                </button>
              )}
              {isOpen && <Details type={r.type || type} entry={r} />}
            </div>
          );
        })}
      </div>
    </>
  );
}

function Abilities({ scores, methods, onSave, busy }) {
  const [method, setMethod] = useState("standard");
  const [vals, setVals] = useState({ ...scores });
  const [pool, setPool] = useState(methods?.standard || [15, 14, 13, 12, 10, 8]);
  const usesPool = method === "standard" || method === "roll";
  useEffect(() => {
    if (method === "standard") { setPool(methods?.standard || [15, 14, 13, 12, 10, 8]); setVals(Object.fromEntries(ABILS.map(([k]) => [k, ""]))); }
    if (method === "roll") { setPool(Array.from({ length: 6 }, roll4d6).sort((a, b) => b - a)); setVals(Object.fromEntries(ABILS.map(([k]) => [k, ""]))); }
    if (method === "pointbuy") setVals(Object.fromEntries(ABILS.map(([k]) => [k, 8])));
    if (method === "manual") setVals({ ...scores });
  }, [method]); // eslint-disable-line react-hooks/exhaustive-deps
  const spent = method === "pointbuy" ? ABILS.reduce((n, [k]) => n + (POINT_COST[vals[k]] ?? 99), 0) : 0;
  // with a pool, each number is used once: what is still free for this ability
  const free = (k) => {
    const left = [...pool];
    for (const [o] of ABILS) if (o !== k && vals[o] !== "") { const i = left.indexOf(Number(vals[o])); if (i >= 0) left.splice(i, 1); }
    return left;
  };
  const complete = ABILS.every(([k]) => vals[k] !== "" && Number(vals[k]) >= 1) && (method !== "pointbuy" || spent <= 27);
  return (
    <div className="builder-abilities">
      <div className="chip-row">
        {Object.keys(METHOD_LABELS).filter((m) => m in (methods || METHOD_LABELS)).map((m) => (
          <button key={m} type="button" className={`pill ${method === m ? "on" : ""}`} onClick={() => setMethod(m)}>{METHOD_LABELS[m]}</button>
        ))}
        {method === "roll" && <button type="button" className="btn small" onClick={() => { setPool(Array.from({ length: 6 }, roll4d6).sort((a, b) => b - a)); setVals(Object.fromEntries(ABILS.map(([k]) => [k, ""]))); }}>🎲 Roll again</button>}
      </div>
      {usesPool && <div className="muted small">{`Your numbers: ${pool.join(", ")}. Give each ability one of them.`}</div>}
      {method === "pointbuy" && <div className={`small ${spent > 27 ? "error-text" : "muted"}`}>{`Points spent: ${spent} of 27`}</div>}
      <div className="s5-abilities">
        {ABILS.map(([k, label]) => (
          <div className="s5-ability edit" key={k}>
            <span className="s5-ab-label">{label}</span>
            {usesPool ? (
              <select className="field" value={vals[k]} onChange={(e) => setVals({ ...vals, [k]: e.target.value === "" ? "" : Number(e.target.value) })}>
                <option value="">–</option>
                {[...new Set([...(vals[k] !== "" ? [Number(vals[k])] : []), ...free(k)])].sort((a, b) => b - a).map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            ) : method === "pointbuy" ? (
              <div className="row gap tight center">
                <button type="button" className="icon-btn" disabled={vals[k] <= 8} onClick={() => setVals({ ...vals, [k]: vals[k] - 1 })}>−</button>
                <span className="s5-ab-mod">{vals[k]}</span>
                <button type="button" className="icon-btn" disabled={vals[k] >= 15} onClick={() => setVals({ ...vals, [k]: vals[k] + 1 })}>＋</button>
              </div>
            ) : (
              <input className="field" type="number" min="1" max="30" value={vals[k]} onChange={(e) => setVals({ ...vals, [k]: e.target.value === "" ? "" : Number(e.target.value) })} />
            )}
          </div>
        ))}
      </div>
      <div className="muted tiny">Bonuses from your race are added on the sheet.</div>
      <button type="button" className="btn primary" disabled={busy || !complete} onClick={() => onSave(Object.fromEntries(ABILS.map(([k]) => [k, Number(vals[k])])))}>Save the scores</button>
    </div>
  );
}

function Pick({ step, chosen, onSave, busy }) {
  const [sel, setSel] = useState(chosen || []);
  const toggle = (o) => setSel((s) => (s.includes(o) ? s.filter((x) => x !== o) : s.length < step.count ? [...s, o] : s));
  return (
    <>
      <div className="muted small">{`Choose ${step.count}.`}</div>
      <div className="option-cards">
        {step.options.map((o) => (
          <button key={o} type="button" className={`option-card small ${sel.includes(o) ? "on" : ""}`} onClick={() => toggle(o)}>
            <span className="option-name">{step.id === "skills" ? skillName(o) : o}</span>
          </button>
        ))}
      </div>
      <button type="button" className="btn primary" disabled={busy || sel.length !== step.count} onClick={() => onSave(sel)}>Save</button>
    </>
  );
}

/** Starting equipment: the class's and background's packages (pick a or b), or the class's gold instead. */
function StartGear({ convId, who, busy, onApply }) {
  const [opt, setOpt] = useState(null);
  const [mode, setMode] = useState("packages");
  const [picks, setPicks] = useState({ class: {}, background: {} });
  const [chosen, setChosen] = useState({ class: {}, background: {} });
  const [gold, setGold] = useState("");
  useEffect(() => { api.characterStarting(convId, who).then(setOpt).catch(() => setOpt({})); }, [convId, who]);
  if (!opt) return <div className="muted tiny">Loading…</div>;
  const g = opt.class?.gold;
  const part = (which) => {
    const o = opt[which];
    if (!o?.groups?.length) return null;
    return (
      <div className="gear-part">
        <div className="lbl">{which === "class" ? `From your class (${o.name})` : `From your background (${o.name})`}</div>
        {o.groups.map((grp) => {
          const key = picks[which][grp.id] || grp.choices[0]?.key;
          return (
            <div className="gear-group" key={grp.id}>
              {grp.fixed.length > 0 && <div className="small">{grp.fixed.map((f) => f.label).join(", ")}</div>}
              {grp.choices.length > 0 && (
                <div className="gear-choices">
                  {grp.choices.map((c) => (
                    <label key={c.key} className={`gear-choice ${key === c.key ? "on" : ""}`}>
                      <input type="radio" name={`${which}-${grp.id}`} checked={key === c.key} onChange={() => setPicks({ ...picks, [which]: { ...picks[which], [grp.id]: c.key } })} />
                      <span><strong>{`(${c.key})`}</strong> {c.label}</span>
                    </label>
                  ))}
                  {(grp.choices.find((c) => c.key === key)?.items || []).map((it, n) => it.pick && (
                    <select key={n} className="field" value={chosen[which][`${grp.id}.${key}.${n}`] || ""}
                      onChange={(e) => setChosen({ ...chosen, [which]: { ...chosen[which], [`${grp.id}.${key}.${n}`]: e.target.value } })}>
                      <option value="">{`Choose ${it.label}…`}</option>
                      {it.candidates.map((cd) => <option key={`${cd.name}|${cd.source}`} value={`${cd.name}|${cd.source}`}>{cd.name}</option>)}
                    </select>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };
  const roll = () => { const [n, s] = g.dice.split("d").map(Number); let t = 0; for (let i = 0; i < n; i++) t += 1 + Math.floor(Math.random() * s); setGold(String(t * g.times)); };
  const apply = () => onApply({ op: "start_gear", choice: {
    ...(mode === "gold" ? { class_gold: Number(gold) } : { class: picks.class, class_picks: chosen.class }),
    background: picks.background, background_picks: chosen.background } });
  return (
    <div className="start-gear">
      {g && (
        <div className="chip-row tight">
          <button type="button" className={`pill ${mode === "packages" ? "on" : ""}`} onClick={() => setMode("packages")}>📦 Take the packages</button>
          <button type="button" className={`pill ${mode === "gold" ? "on" : ""}`} onClick={() => setMode("gold")}>{`💰 Take the gold instead (${g.dice} × ${g.times} gp)`}</button>
        </div>
      )}
      {mode === "gold" && g ? (
        <div className="row gap center wrap">
          <button type="button" className="btn small" onClick={roll}>{`🎲 Roll ${g.dice} × ${g.times}`}</button>
          <button type="button" className="btn small ghost" onClick={() => setGold(String(g.average))}>{`Take the average (${g.average} gp)`}</button>
          <input className="field num" value={gold} onChange={(e) => setGold(e.target.value.replace(/\D/g, ""))} aria-label="Gold" />
          <span className="muted small">gp, then buy what you want below</span>
        </div>
      ) : part("class")}
      {part("background")}
      <button type="button" className="btn primary" disabled={busy || (mode === "gold" && !gold)} onClick={apply}>Take this equipment</button>
    </div>
  );
}

/**
 * The 5e builder, like Roll20's Charactermancer: one step at a time with big cards. Every choice goes on the sheet
 * at once, so you can close it and come back.
 */
export default function Builder({ convId, onClose, onChanged, who = "" }) {
  const [steps, setSteps] = useState([]);
  const [methods, setMethods] = useState(null);
  const [data, setData] = useState(null);
  const [at, setAt] = useState("class");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async (next) => {
    try {
      const [b, c] = await Promise.all([api.builder5e(convId, who), api.character5e(convId, who)]);
      setSteps(b.steps || []); setMethods(b.methods); setData(c);
      if (next) setAt(next);
    } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, [convId, who]); // eslint-disable-line react-hooks/exhaustive-deps
  const nextAfter = (id) => { const i = steps.findIndex((s) => s.id === id); return steps[i + 1]?.id || id; };
  const apply = async (change, advance = true) => {
    setBusy(true); setError("");
    try {
      const r = await api.changeCharacter5e(convId, change, who);
      onChanged?.(r);
      await load(advance ? nextAfter(at) : null);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const ch = data?.character || {};
  const edition = ch.edition || "2014";
  const step = steps.find((s) => s.id === at) || steps[0];
  const current = step ? { class: ch.cls, race: ch.race, background: ch.background }[step.id] : null;

  return (
    <Modal title={who ? `5e builder · ${who}` : "5e character builder"} onClose={onClose} wide footer={<button type="button" className="btn primary" onClick={onClose}>Done</button>}>
      <div className="builder">
        <nav className="builder-steps" aria-label="Steps">
          {steps.map((s, i) => (
            <button key={s.id} type="button" className={`builder-step ${s.id === step?.id ? "on" : ""} ${s.done ? "done" : ""}`} onClick={() => setAt(s.id)}>
              <span className="builder-num">{s.done ? "✓" : i + 1}</span>{s.title}
            </button>
          ))}
        </nav>
        <div className="builder-body">
          {error && <div className="error-text small">{error}</div>}
          {!step && <div className="muted small pad">Loading…</div>}
          {step && <h3 className="builder-title">{step.title}{current ? <span className="muted small">{` · now: ${current.name}`}</span> : null}</h3>}
          {step && ["class", "race", "background"].includes(step.id) && (
            <OptionCards type={step.type} edition={edition} picked={current} busy={busy} onPick={(ref) => apply({ op: "add", ...ref })} />
          )}
          {step?.id === "abilities" && <Abilities scores={ch.scores || {}} methods={methods} busy={busy} onSave={(v) => apply({ op: "set", field: "scores", value: v })} />}
          {step?.id === "skills" && <Pick step={step} chosen={(ch.picks || {}).skills} busy={busy} onSave={(v) => apply({ op: "pick", kind: "skills", value: v })} />}
          {step?.id === "style" && (
            <div className="option-cards">
              {step.options.map((o) => {
                const has = (ch.options || []).some((x) => x.name === o);
                return (
                  <button key={o} type="button" disabled={busy || has} className={`option-card small ${has ? "on" : ""}`}
                    onClick={() => apply({ op: "add", type: "optionalfeature", name: o, source: (ch.cls || {}).source || "PHB" }, false)}>
                    <span className="option-name">{o}</span>
                  </button>
                );
              })}
            </div>
          )}
          {step?.id === "spells" && (
            <>
              <div className="muted small">{`Spells from the ${step.list} list${step.max_level ? `, up to level ${step.max_level}` : ": cantrips only for now"}. On your sheet: ${(ch.spells || []).map((x) => x.name).join(", ") || "none yet"}.`}</div>
              <OptionCards type="spell" edition={edition} busy={busy} cls={step.list} maxLevel={step.max_level} onPick={(ref) => apply({ op: "add", ...ref }, false)} />
            </>
          )}
          {step?.id === "equipment" && (
            <>
              <StartGear convId={convId} who={who} busy={busy} onApply={(change) => apply(change, false)} />
              <div className="section-title">{`🛒 Shop · you have ${money(ch.cp || 0)}`}</div>
              <div className="muted small">Prices from the Library. Bought things can be returned here for the full price.</div>
              {(ch.items || []).length > 0 && (
                <div className="gear-owned">
                  {(ch.items || []).map((it, i) => (
                    <span key={`${it.name}-${i}`} className="pill small">
                      {`${it.qty > 1 ? `${it.qty} × ` : ""}${it.name}`}
                      {it.bought ? <button type="button" className="link-btn" title={`Return it (${money(it.bought)} back)`} onClick={() => apply({ op: "refund", index: i }, false)}> ✕</button> : null}
                    </span>
                  ))}
                </div>
              )}
              <OptionCards type="baseitem" edition={edition} busy={busy} categories buyLabel="Buy" onPick={(ref) => apply({ op: "buy", ...ref }, false)} />
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
