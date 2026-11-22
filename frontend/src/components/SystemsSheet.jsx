import React from "react";

const sign = (n) => (n > 0 ? `+${n}` : `${n}`);
const modsText = (mods) => Object.entries(mods || {}).map(([k, v]) => `${k} ${sign(v)}`).join(", ");

/** One part as a dropdown label: "Hand's mace · 3 PF · Heavy · Melee +1, Handling -1 · Lv4". */
function partLabel(item, points) {
  points = points.length > 8 ? points.split(/\s+/).map((w) => w[0]).join("").toUpperCase() : points; // Frame Points -> FP
  return [item.name, `${item.cost} ${points}`, item.weight, modsText(item.mods), item.level ? `Lv${item.level}` : ""].filter(Boolean).join(" · ");
}

/**
 * A card's own sheet kept by the app (Black Sheep: Pilot Level, XP, Credits, Tier, Integrity, and the mech loadout).
 * Stats are edited in place; each slot picks a part from the card's catalog; the app checks the budget and level
 * gates and works out the totals (points used, net modifiers, speed, maximums).
 */
export default function SystemsSheet({ systems, state, computed, onValue, onPart, error, busy }) {
  if (!systems || !state) return null;
  const lo = systems.loadout;
  const values = state.values || {};
  const got = computed || {};
  const level = lo?.level_stat ? Number(values[lo.level_stat] || 0) : 99;
  return (
    <div className="systems-sheet">
      {(systems.stats || []).length > 0 && (
        <div className="sys-stats">
          {systems.stats.map((s) => {
            const top = got.max?.[s.key];
            return (
              <label key={s.key} className="sys-stat" title={s.note || ""}>
                <span className="lbl">{s.key}{top != null ? <span className="muted tiny">{` / ${top}`}</span> : null}</span>
                {s.kind === "choice" ? (
                  <select className="field" value={values[s.key] ?? ""} disabled={busy} onChange={(e) => onValue(s.key, e.target.value)}>
                    {(s.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input className={`field ${s.kind === "number" ? "num" : ""}`} value={values[s.key] ?? ""} disabled={busy}
                    onChange={(e) => onValue(s.key, s.kind === "number" ? e.target.value.replace(/[^\d-]/g, "") : e.target.value)} />
                )}
              </label>
            );
          })}
        </div>
      )}
      {lo && (
        <div className="sys-loadout">
          <div className="row gap center wrap">
            <strong>{lo.name || "Loadout"}</strong>
            {got.budget != null && (
              <span className={`pill ${got.used > got.budget ? "bad" : "on"}`}>{`${lo.points} ${got.used}/${got.budget}`}</span>
            )}
            {got.speed && <span className="pill">{`Speed ${got.speed} (${got.heavy} ${lo.speed?.weight || ""})`}</span>}
          </div>
          {got.budget != null && <span className="tracker-bar wide sys-bar"><span style={{ width: `${Math.min(100, Math.round((got.used / Math.max(1, got.budget)) * 100))}%` }} /></span>}
          <div className="sys-net">
            {Object.entries(got.mods || {}).map(([k, v]) => (
              <span key={k} className={`sys-mod ${v > 0 ? "up" : v < 0 ? "down" : ""}`}><span className="muted tiny">{k}</span><strong>{sign(v)}</strong></span>
            ))}
          </div>
          {(lo.slots || []).map((sl) => {
            const current = state.loadout?.[sl.key] || "";
            const item = (lo.catalog || []).find((i) => i.name === current);
            const fits = (lo.catalog || []).filter((i) => !sl.accepts?.length || sl.accepts.includes(i.kind));
            return (
              <div className="sys-slot" key={sl.key}>
                <span className="lbl">{sl.key}</span>
                <select className="field" value={current} disabled={busy} onChange={(e) => onPart(sl.key, e.target.value)}>
                  {!item && <option value="">{current || "—"}</option>}
                  {fits.map((i) => (
                    <option key={i.name} value={i.name} disabled={!i.start && i.level > level}>
                      {partLabel(i, lo.points)}{!i.start && i.level > level ? " 🔒" : ""}
                    </option>
                  ))}
                </select>
                {item && (item.effect || item.source) && (
                  <div className="muted tiny">{[item.effect, item.range && `${item.range} range`, item.source, item.price].filter(Boolean).join(" · ")}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {error && <div className="error-text small">{error}</div>}
    </div>
  );
}
