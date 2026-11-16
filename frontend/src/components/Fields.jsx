import React, { useEffect, useState } from "react";

/** Number input that commits on blur / Enter. */
export function NumberField({ value, onCommit, min, max, className = "", width }) {
  const [v, setV] = useState(String(value ?? 0));
  useEffect(() => setV(String(value ?? 0)), [value]);
  const commit = () => {
    let n = parseInt(v, 10);
    if (Number.isNaN(n)) { setV(String(value ?? 0)); return; }
    if (min !== undefined) n = Math.max(min, n);
    if (max !== undefined) n = Math.min(max, n);
    setV(String(n));
    if (n !== value) onCommit(n);
  };
  return (
    <input className={`field num ${className}`} style={width ? { width } : undefined} inputMode="numeric" value={v}
      onChange={(e) => setV(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
  );
}

/** Text input / textarea that commits on blur. */
export function TextField({ value, onCommit, multiline, placeholder, className = "", rows = 3 }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  const commit = () => { if (v !== (value ?? "")) onCommit(v); };
  if (multiline) {
    return <textarea className={`field ${className}`} rows={rows} value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={commit} />;
  }
  return (
    <input className={`field ${className}`} value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
  );
}
