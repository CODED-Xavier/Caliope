import React from "react";

/** "C- [40/100]" -> { grade: "C-", exp: 40, max: 100 } (the card's stats with an EXP bar). */
export function parseProgress(value) {
  const m = String(value || "").trim().match(/^(\S+)\s*\[\s*(-?\d+)\s*\/\s*(\d+)\s*\]$/);
  return m ? { grade: m[1], exp: Number(m[2]), max: Number(m[3]) || 100 } : null;
}

const empty = (v) => !String(v || "").trim() || /^[-?]$/.test(String(v).trim());

/** The values to start a form with: the card's opening values, with its blanks ("-") left empty to fill. */
export function startValues(groups) {
  const out = {};
  for (const g of groups || []) {
    for (const f of g.fields) {
      if (f.progress) out[f.key] = `${empty(f.grade) ? "" : f.grade} [${f.exp || 0}/${f.max || 100}]`.trim();
      else out[f.key] = empty(f.value) ? "" : f.value;
    }
  }
  return out;
}

/**
 * The card's own sheet (Lumencia: Tier, Affiliation, Attributes 1-10, Stats with grades and EXP), grouped like
 * the card's status block. Used on the start screen and in the Sheet tab.
 */
export default function CardSheetForm({ groups, values, onChange, hide }) {
  const set = (k, v) => onChange({ ...values, [k]: v });
  return (
    <div className="card-sheet-form">
      {(groups || []).map((g, gi) => (
        <fieldset className="card-sheet-group" key={`${g.title}-${gi}`}>
          {g.title && <legend>{g.title}</legend>}
          <div className="card-sheet-fields">
            {g.fields.filter((f) => !(hide && hide.test(f.key))).map((f) => {
              if (f.progress) {
                const p = parseProgress(values[f.key]) || { grade: "", exp: 0, max: f.max || 100 };
                const grade = p.grade.replace(/^-$/, "");
                const put = (gr, exp) => set(f.key, `${gr || "-"} [${Math.max(0, parseInt(exp, 10) || 0)}/${p.max}]`);
                return (
                  <div className="card-sheet-field with-exp" key={f.key}>
                    <span className="lbl">{f.key}</span>
                    <div className="row gap center">
                      <input className="field grade" value={grade} placeholder="Grade" aria-label={`${f.key} grade`}
                        onChange={(e) => put(e.target.value.trim(), p.exp)} />
                      <input className="field num exp" value={p.exp} aria-label={`${f.key} EXP`} onChange={(e) => put(grade, e.target.value)} />
                      <span className="muted tiny">{`/ ${p.max} EXP`}</span>
                    </div>
                    <span className="tracker-bar wide"><span style={{ width: `${Math.min(100, Math.round((p.exp / p.max) * 100))}%` }} /></span>
                  </div>
                );
              }
              return (
                <label className="card-sheet-field" key={f.key}>
                  <span className="lbl">{f.key}</span>
                  <input className="field" value={values[f.key] ?? ""} placeholder={f.hint && f.hint !== f.key ? f.hint : ""}
                    onChange={(e) => set(f.key, e.target.value)} />
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
