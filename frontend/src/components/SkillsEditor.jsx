import React from "react";

export const MAX_SKILLS = 8;

/**
 * Your character's skills (Soul Forge, Mana Sense Eyes…): a name, what it really does, and an optional cost from the
 * card's resources (Mana, Aura…). The Aedo always sees them; naming one in your message ("I use my soul forge") uses it.
 */
export default function SkillsEditor({ skills, onChange, resources = [] }) {
  const list = skills || [];
  const setAt = (i, patch) => onChange(list.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const costOf = (s) => Object.entries(s.costs || {})[0] || [resources[0] || "", 0];
  return (
    <div className="skills-editor">
      {list.map((s, i) => {
        const [res, amount] = costOf(s);
        return (
          <div className="card skill-card" key={s.id || i}>
            <div className="row gap center">
              <input className="field grow" placeholder="Skill name (Soul Forge…)" aria-label="Skill name" value={s.name || ""}
                onChange={(e) => setAt(i, { name: e.target.value })} />
              {resources.length > 0 && (
                <span className="row gap center skill-cost" title="What using it costs (0 = free)">
                  <input className="field num" aria-label="Cost" value={amount || 0}
                    onChange={(e) => { const n = Math.max(0, parseInt(e.target.value, 10) || 0); setAt(i, { costs: n ? { [res || resources[0]]: n } : {} }); }} />
                  <select className="field" aria-label="Paid with" value={res || resources[0]}
                    onChange={(e) => setAt(i, { costs: amount ? { [e.target.value]: amount } : {} })}>
                    {resources.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </span>
              )}
              <button type="button" className="icon-btn" title="Remove" onClick={() => onChange(list.filter((_, j) => j !== i))}>✕</button>
            </div>
            <textarea className="field" rows={2} maxLength={600} placeholder="What it does, and its limits (the Aedo follows this)"
              value={s.description || ""} onChange={(e) => setAt(i, { description: e.target.value })} />
          </div>
        );
      })}
      {list.length < MAX_SKILLS && (
        <button type="button" className="btn small" onClick={() => onChange([...list, { name: "", description: "", costs: {} }])}>＋ Add a skill</button>
      )}
    </div>
  );
}
