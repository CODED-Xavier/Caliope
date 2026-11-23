import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import Modal from "./Modal.jsx";

const ABILS = [["str", "STR"], ["dex", "DEX"], ["con", "CON"], ["int", "INT"], ["wis", "WIS"], ["cha", "CHA"]];

function FeatSearch({ edition, value, onPick }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  useEffect(() => {
    const t = setTimeout(() => { api.librarySearch("feat", q, edition).then((r) => setResults((r?.results || []).slice(0, 40))).catch(() => setResults([])); }, 200);
    return () => clearTimeout(t);
  }, [q, edition]);
  return (
    <>
      <input className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search feats…" aria-label="Search feats" />
      <div className="option-cards">
        {results.map((r) => (
          <button key={`${r.source}-${r.name}`} type="button" className={`option-card small ${value && value.name === r.name && value.source === r.source ? "on" : ""}`}
            onClick={() => onPick({ name: r.name, source: r.source })}>
            <span className="option-name">{r.name}</span><span className="option-src">{r.source}</span>
            {r.summary && <span className="option-sum">{r.summary}</span>}
          </button>
        ))}
      </div>
    </>
  );
}

/** New cantrips or spells at level-up, from the class's list (up to your highest slot). Optional: they can be added
 * later from the Library too. */
function SpellPick({ edition, choice, value, onChange }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  useEffect(() => {
    const t = setTimeout(() => {
      api.librarySearch("spell", q, edition, "", false, choice.list, choice.max_level)
        .then((r) => setResults((r?.results || []).filter((x) => (choice.kind === "cantrips" ? x.level === 0 : x.level >= 1 && (!choice.exact_level || x.level === choice.exact_level))).slice(0, 60)))
        .catch(() => setResults([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q, edition, choice.list, choice.max_level, choice.kind, choice.exact_level]);
  const sel = value || [];
  const has = (r) => sel.some((x) => x.name === r.name && x.source === r.source);
  const toggle = (r) => onChange(has(r) ? sel.filter((x) => !(x.name === r.name && x.source === r.source)) : sel.length < choice.count ? [...sel, { name: r.name, source: r.source }] : sel);
  const title = choice.kind === "cantrips" ? `New cantrips: choose ${choice.count}`
    : choice.exact_level ? `Mystic Arcanum: one level ${choice.exact_level} spell`
      : choice.spellbook ? `Add ${choice.count} spells to your spellbook` : `New spells: choose ${choice.count}`;
  return (
    <>
      <div className="section-title">{title}</div>
      <div className="muted tiny">{`${choice.list} list${choice.kind === "spells" && !choice.exact_level ? ` · up to level ${choice.max_level}` : ""} · ${sel.length}/${choice.count} chosen · optional: you can also add them later from the Library`}</div>
      <input className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search spells…" aria-label="Search spells" />
      <div className="option-cards">
        {results.map((r) => (
          <button key={`${r.source}-${r.name}`} type="button" className={`option-card small ${has(r) ? "on" : ""}`} onClick={() => toggle(r)}>
            <span className="option-name no-tr">{r.name}</span><span className="option-src">{r.level ? `Level ${r.level}` : "Cantrip"} · {r.source}</span>
            {r.summary && <span className="option-sum">{r.summary}</span>}
          </button>
        ))}
        {results.length === 0 && <div className="muted small">No spells found in your Library.</div>}
      </div>
    </>
  );
}

/** 📜 The 20 levels of your class: features, proficiency, the class's own columns (Rages, Sneak Attack, Ki…), spells,
 * slots and uses. Your level and the next one are marked. */
export function LevelTable({ convId, who = "" }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.characterLevels(convId, who).then(setData).catch((e) => setError(e.message)); }, [convId, who]);
  if (error) return <div className="error-text small">{error}</div>;
  if (!data) return <div className="muted small pad">Loading…</div>;
  const rows = data.levels;
  const hasSlots = rows.some((r) => r.slots || r.pact);
  const has = (k) => rows.some((r) => r[k]);
  const hasUses = rows.some((r) => Object.keys(r.uses || {}).length);
  return (
    <div className="level-table-wrap">
      <table className="level-table">
        <thead>
          <tr>
            <th>Lv</th><th>Prof</th><th>Features</th>
            {data.columns.map((c) => <th key={c}>{c}</th>)}
            {has("cantrips") && <th>Cantrips</th>}
            {has("known") && <th>Spells known</th>}
            {has("spellbook") && <th>Spellbook</th>}
            {has("prepared") && <th>Prepared</th>}
            {hasSlots && <th>Slots</th>}
            {hasUses && <th>Uses</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.level} className={r.level === data.current ? "current" : r.level === data.current + 1 ? "next" : ""}>
              <td>{r.level}</td><td>{`+${r.prof}`}</td><td>{r.features.join(", ") || "–"}</td>
              {r.columns.map((v, i) => <td key={i}>{v}</td>)}
              {has("cantrips") && <td>{r.cantrips || "–"}</td>}
              {has("known") && <td>{r.known || "–"}</td>}
              {has("spellbook") && <td>{r.spellbook || "–"}</td>}
              {has("prepared") && <td>{r.prepared || "–"}</td>}
              {hasSlots && <td>{r.pact ? `${r.pact.count} × L${r.pact.level}` : Object.entries(r.slots || {}).map(([k, v]) => `${v}×L${k}`).join(" ") || "–"}</td>}
              {hasUses && <td>{Object.entries(r.uses || {}).map(([k, v]) => `${k} ${v}`).join(", ") || "–"}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="muted tiny">{data.current < 20 ? `Your level (${data.current}) and the next one are marked.` : "You are at the highest level."}</div>
    </div>
  );
}

const SPELL_KINDS = ["spells", "cantrips"];

/**
 * Level up: the class table's new features are added by the app; you only choose what is really yours to choose
 * (hit points, a subclass, an Ability Score Improvement or a feat, a new option).
 */
export default function LevelUp({ convId, onClose, onDone, who = "" }) {
  const [plan, setPlan] = useState(null);
  const [edition, setEdition] = useState("2014");
  const [hpWay, setHpWay] = useState("average");
  const [roll, setRoll] = useState(null);
  const [answers, setAnswers] = useState({});
  const [asiWay, setAsiWay] = useState("asi");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showTable, setShowTable] = useState(false);
  useEffect(() => {
    api.levelUpPlan(convId, who).then(setPlan).catch((e) => setError(e.message));
    api.character5e(convId, who).then((c) => setEdition(c?.character?.edition || "2014")).catch(() => {});
  }, [convId, who]);
  const faces = plan ? Number(String(plan.hit_die).replace("d", "")) : 8;
  const set = (id, v) => setAnswers((a) => ({ ...a, [id]: v }));
  const asi = answers.asi_or_feat?.asi || {};
  const asiTotal = Object.values(asi).reduce((n, v) => n + v, 0);
  const bump = (k, d) => {
    const v = Math.max(0, Math.min(2, (asi[k] || 0) + d));
    if (d > 0 && asiTotal >= 2) return;
    set("asi_or_feat", { asi: { ...asi, [k]: v } });
  };
  const ready = plan && (hpWay === "average" || roll) && plan.choices.every((c) => {
    const a = answers[c.id];
    if (SPELL_KINDS.includes(c.kind)) return true; // spells can be added later from the Library
    if (c.kind === "asi_or_feat") return a && (a.feat || (a.asi && Object.values(a.asi).reduce((n, v) => n + v, 0) === 2));
    if (c.kind === "optionalfeature") return Array.isArray(a) && a.length === c.count;
    return !!a;
  });
  const confirm = async () => {
    setBusy(true); setError("");
    try { onDone(await api.levelUp(convId, { ...answers, hp: hpWay === "average" ? "average" : { roll } }, who)); } catch (e) { setError(e.message); setBusy(false); }
  };

  return (
    <Modal title={plan ? `Level up to ${plan.to_level}` : "Level up"} onClose={onClose} wide
      footer={<><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button type="button" className="btn primary" disabled={!ready || busy} onClick={confirm}>{`⬆ Become level ${plan?.to_level ?? ""}`}</button></>}>
      {error && <div className="error-text small">{error}</div>}
      {!plan && !error && <div className="muted small pad">Loading…</div>}
      {plan && (
        <div className="levelup">
          <div className="section-title">You gain</div>
          <div className="chip-row">
            {plan.gains.length ? plan.gains.map((g) => <span key={g} className="pill on">{g}</span>) : <span className="muted small">No new class features at this level.</span>}
          </div>

          {(plan.changes || []).length > 0 && (
            <>
              <div className="section-title">{`What changes at level ${plan.to_level}`}</div>
              <table className="level-changes">
                <tbody>
                  {plan.changes.map((c) => <tr key={c.label}><td>{c.label}</td><td className="muted">{c.before}</td><td>→</td><td><strong>{c.after}</strong></td></tr>)}
                </tbody>
              </table>
            </>
          )}
          {plan.spell_mode === "prepared" && <div className="muted tiny">You prepare your spells from your whole class list after a long rest: add or remove them on the sheet.</div>}
          {plan.spell_mode === "known" && <div className="muted tiny">You may also swap one spell you know for another: remove it on the sheet and add the new one from the Library.</div>}
          <button type="button" className="link-btn small" onClick={() => setShowTable((v) => !v)}>{showTable ? "▾ All 20 levels" : "▸ 📜 All 20 levels"}</button>
          {showTable && <LevelTable convId={convId} who={who} />}

          <div className="section-title">{`Hit points (${plan.hit_die})`}</div>
          <div className="way-pick">
            <label className={`way ${hpWay === "average" ? "active" : ""}`}>
              <input type="radio" checked={hpWay === "average"} onChange={() => setHpWay("average")} />
              <span><strong>{`Take the average: ${plan.hp_average}`}</strong><br /><span className="muted tiny">Plus your CON modifier.</span></span>
            </label>
            <label className={`way ${hpWay === "roll" ? "active" : ""}`}>
              <input type="radio" checked={hpWay === "roll"} onChange={() => setHpWay("roll")} />
              <span><strong>{roll ? `Rolled: ${roll}` : `Roll a ${plan.hit_die}`}</strong><br />
                <button type="button" className="btn small" onClick={(e) => { e.preventDefault(); setHpWay("roll"); setRoll(1 + Math.floor(Math.random() * faces)); }}>🎲 Roll</button></span>
            </label>
          </div>

          {plan.choices.map((c) => (
            <div key={c.id}>
              {c.kind === "subclass" && (
                <>
                  <div className="section-title">Choose your subclass</div>
                  {c.options.length === 0 && <div className="muted small">No subclass for this class is in your Library.</div>}
                  <div className="option-cards">
                    {c.options.map((o) => (
                      <button key={o} type="button" className={`option-card ${answers[c.id] === o ? "on" : ""}`} onClick={() => set(c.id, o)}><span className="option-name">{o}</span></button>
                    ))}
                  </div>
                </>
              )}
              {c.kind === "asi_or_feat" && (
                <>
                  <div className="section-title">Ability Score Improvement or a feat</div>
                  <div className="chip-row">
                    <button type="button" className={`pill ${asiWay === "asi" ? "on" : ""}`} onClick={() => { setAsiWay("asi"); set(c.id, { asi: {} }); }}>+2 to scores</button>
                    <button type="button" className={`pill ${asiWay === "feat" ? "on" : ""}`} onClick={() => { setAsiWay("feat"); set(c.id, null); }}>A feat</button>
                  </div>
                  {asiWay === "asi" ? (
                    <>
                      <div className="muted small">{`+2 to one score, or +1 to two. ${2 - asiTotal} left.`}</div>
                      <div className="s5-abilities">
                        {ABILS.map(([k, label]) => (
                          <div className="s5-ability edit" key={k}>
                            <span className="s5-ab-label">{label}</span>
                            <div className="row gap tight center">
                              <button type="button" className="icon-btn" disabled={!asi[k]} onClick={() => bump(k, -1)}>−</button>
                              <span className="s5-ab-mod">{`+${asi[k] || 0}`}</span>
                              <button type="button" className="icon-btn" disabled={asiTotal >= 2 || (asi[k] || 0) >= 2} onClick={() => bump(k, 1)}>＋</button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : <FeatSearch edition={edition} value={answers[c.id]?.feat} onPick={(f) => set(c.id, { feat: f })} />}
                </>
              )}
              {SPELL_KINDS.includes(c.kind) && <SpellPick edition={edition} choice={c} value={answers[c.id]} onChange={(v) => set(c.id, v)} />}
              {c.kind === "optionalfeature" && (
                <>
                  <div className="section-title">{`Choose ${c.count}`}</div>
                  <div className="option-cards">
                    {c.options.map((o) => {
                      const sel = answers[c.id] || [];
                      const on = sel.includes(o);
                      return (
                        <button key={o} type="button" className={`option-card small ${on ? "on" : ""}`}
                          onClick={() => set(c.id, on ? sel.filter((x) => x !== o) : sel.length < c.count ? [...sel, o] : sel)}>
                          <span className="option-name">{o}</span>
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
