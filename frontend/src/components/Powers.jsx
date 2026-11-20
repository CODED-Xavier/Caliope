import React, { useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";

const REGEN = [["round", "per round"], ["short_rest", "short rest"], ["long_rest", "night"], ["day", "new day"]];
const KINDS = [["attack", "attack"], ["heal", "heal"], ["effect", "effect"]];
const num = (v, d = 0) => { const n = parseInt(v, 10); return Number.isNaN(n) ? d : n; };

/** Card editor: the card's resources (Mana, Aura...) and the powers that spend them. */
export default function PowersEditor({ card, onChange }) {
  const res = card.resources || [];
  const abilities = card.abilities || [];
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const setRes = (i, patch) => onChange({ resources: res.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const rename = (i, name) => {  // the powers' costs follow the new name
    const old = res[i].name;
    onChange({
      resources: res.map((r, j) => (j === i ? { ...r, name } : r)),
      abilities: abilities.map((a) => {
        if (!a.costs || !(old in a.costs)) return a;
        const { [old]: v, ...rest } = a.costs;
        return { ...a, costs: { ...rest, [name]: v } };
      }),
    });
  };
  const setAb = (i, patch) => onChange({ abilities: abilities.map((a, j) => (j === i ? { ...a, ...patch } : a)) });
  const suggest = async () => {
    setBusy(true); setErr("");
    try { const r = await api.suggestResources(card); onChange({ resources: r.resources, abilities: r.abilities }); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <details>
      <summary className="muted small">Resources and powers <HelpTip id="resources" /> {res.length > 0 && <span className="tiny">({res.map((r) => r.name).join(", ")})</span>}</summary>
      <div className="powers-editor">
        <div className="row gap center">
          <button className="btn small" onClick={suggest} disabled={busy}>{busy ? "Reading the card…" : "✨ Suggest from the card"}</button>
          <span className="muted tiny">Then change anything. Regeneration: a number, or −1 for "all of it".</span>
        </div>
        {res.map((r, i) => (
          <div className="card" key={`r${i}`}>
            <div className="row gap center">
              <input className="field grow" placeholder="Mana, Aura, Stamina…" value={r.name} onChange={(e) => rename(i, e.target.value)} />
              <label className="tiny muted">Max <input className="field num" style={{ width: 52 }} value={r.max} onChange={(e) => setRes(i, { max: num(e.target.value, 1) })} /></label>
              <input type="color" title="Bar colour" value={r.color || "#6b6bd6"} onChange={(e) => setRes(i, { color: e.target.value })} />
              <button className="icon-btn" title="Remove" onClick={() => onChange({ resources: res.filter((_, j) => j !== i) })}>✕</button>
            </div>
            <div className="row gap wrap">
              {REGEN.map(([k, label]) => (
                <label key={k} className="tiny muted">{label}<input className="field num" style={{ width: 46 }} value={(r.regen || {})[k] ?? 0}
                  onChange={(e) => setRes(i, { regen: { ...(r.regen || {}), [k]: num(e.target.value) } })} /></label>
              ))}
            </div>
          </div>
        ))}
        <button className="btn small" onClick={() => onChange({ resources: [...res, { name: "", max: 10, regen: { round: 0, short_rest: 0, long_rest: -1, day: -1 }, color: "" }] })} disabled={res.length >= 6}>＋ Resource</button>

        <div className="section-title">Powers</div>
        {abilities.map((a, i) => (
          <div className="card" key={`a${i}`}>
            <div className="row gap center">
              <input className="field grow" placeholder="Fire Bolt, Aura Shield…" value={a.name} onChange={(e) => setAb(i, { name: e.target.value })} />
              <select className="field" value={a.kind || "effect"} onChange={(e) => setAb(i, { kind: e.target.value })}>
                {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              <button className="icon-btn" title="Remove" onClick={() => onChange({ abilities: abilities.filter((_, j) => j !== i) })}>✕</button>
            </div>
            <div className="row gap wrap">
              {res.map((r) => (
                <label key={r.name} className="tiny muted">{r.name || "?"} cost<input className="field num" style={{ width: 46 }} value={(a.costs || {})[r.name] ?? ""}
                  onChange={(e) => setAb(i, { costs: { ...(a.costs || {}), [r.name]: num(e.target.value) } })} /></label>
              ))}
              {a.kind !== "effect" && <label className="tiny muted">{a.kind === "heal" ? "Healing" : "Damage"}<input className="field num" style={{ width: 66 }} value={a.dice || ""} onChange={(e) => setAb(i, { dice: e.target.value })} /></label>}
              {a.kind === "attack" && <label className="tiny muted">Range<input className="field num" style={{ width: 40 }} value={a.range ?? 1} onChange={(e) => setAb(i, { range: num(e.target.value, 1) })} /></label>}
              {a.kind === "attack" && <label className="tiny muted">Hit +<input className="field num" style={{ width: 40 }} value={a.bonus ?? ""} placeholder="sheet" onChange={(e) => setAb(i, { bonus: e.target.value === "" ? null : num(e.target.value) })} /></label>}
            </div>
            <input className="field" placeholder="What it does (one sentence)" value={a.description || ""} onChange={(e) => setAb(i, { description: e.target.value })} />
          </div>
        ))}
        <button className="btn small" onClick={() => onChange({ abilities: [...abilities, { name: "", kind: "attack", costs: {}, dice: "", range: 1, description: "" }] })}>＋ Power</button>
        {err && <div className="error-text small">{err}</div>}
      </div>
    </details>
  );
}
