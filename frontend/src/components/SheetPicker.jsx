import React, { useEffect, useState } from "react";
import { api } from "../api.js";

let cache = null;
export function useSheetTemplates() {
  const [list, setList] = useState(cache || []);
  useEffect(() => {
    if (cache) return;
    api.sheetTemplates().then((r) => { cache = r.templates || []; setList(cache); }).catch(() => {});
  }, []);
  return list;
}

/* Pick a ready sheet (D&D 5e, Tormenta20, Vampire…) and adjust its text. `value` is the sheet's text. */
export default function SheetPicker({ value, onChange, compact }) {
  const list = useSheetTemplates();
  const match = list.find((t) => t.text.trim() === (value || "").trim());
  const [custom, setCustom] = useState(false);
  const pick = (id) => {
    if (id === "") { setCustom(false); onChange(""); return; }
    if (id === "custom") { setCustom(true); if (!value) onChange("Location: [Location] | Time: [Time]\nHP: [HP]\n"); return; }
    setCustom(false);
    onChange(list.find((t) => t.id === id)?.text || "");
  };
  const selected = !value ? (custom ? "custom" : "") : match ? match.id : "custom";
  return (
    <div className="sheet-picker">
      <select className="field" value={selected} onChange={(e) => pick(e.target.value)}>
        <option value="">No sheet</option>
        {list.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        <option value="custom">My own…</option>
      </select>
      {(value || custom) && (
        <>
          <textarea className="field mono" rows={compact ? 5 : 7} value={value || ""} onChange={(e) => onChange(e.target.value)} />
          <div className="muted tiny">One row per line, cells separated by " | ". Write each value as [something]. Place, time, HP, level,
            attributes, items, money, quests and relationships come from the game by themselves; the other fields are kept by the app
            and changed when the story changes them.</div>
        </>
      )}
    </div>
  );
}
