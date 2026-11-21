import React, { useEffect, useRef, useState } from "react";

/**
 * In-app dialogs instead of the browser's "127.0.0.1 says…" boxes.
 *   if (!(await ask.confirm("Delete it?"))) return;
 *   const name = await ask.prompt("New name:", old);   // null when cancelled
 *   ask.alert("Something went wrong");
 */
let push = null;
const open = (d) => new Promise((resolve) => (push ? push({ ...d, resolve }) : resolve(d.kind === "confirm" ? window.confirm(d.text) : null)));

export const ask = {
  confirm: (text, { ok = "OK", danger = false } = {}) => open({ kind: "confirm", text, ok, danger }),
  prompt: (text, value = "") => open({ kind: "prompt", text, value: value ?? "" }),
  alert: (text) => open({ kind: "alert", text }),
};

export function DialogHost() {
  const [queue, setQueue] = useState([]);
  const [value, setValue] = useState("");
  const input = useRef(null);
  useEffect(() => { push = (d) => setQueue((q) => [...q, d]); return () => { push = null; }; }, []);
  const d = queue[0];
  useEffect(() => { if (d) { setValue(d.value || ""); setTimeout(() => input.current?.focus(), 30); } }, [d]);
  const close = (result) => { d.resolve(result); setQueue((q) => q.slice(1)); };
  const cancel = () => close(d.kind === "confirm" ? false : null);
  const accept = () => close(d.kind === "confirm" ? true : d.kind === "prompt" ? value : null);
  const keys = useRef(null);
  keys.current = { cancel, accept };
  useEffect(() => {
    if (!d) return undefined;
    // Caught before anything else (a window behind would close on Escape too), wherever the focus is.
    const onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); keys.current.cancel(); }
      else if (e.key === "Enter" && !e.shiftKey) { e.stopPropagation(); e.preventDefault(); keys.current.accept(); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [d]);
  if (!d) return null;
  return (
    <div className="dialog-back" onMouseDown={(e) => { if (e.target === e.currentTarget) cancel(); }}>
      <div className="dialog" role="dialog" aria-modal="true">
        <div className="dialog-text">{d.text}</div>
        {d.kind === "prompt" && <input ref={input} className="field" value={value} onChange={(e) => setValue(e.target.value)} />}
        <div className="row gap end">
          {d.kind !== "alert" && <button className="btn small" onClick={cancel}>Cancel</button>}
          <button ref={d.kind === "prompt" ? null : input} className={`btn small ${d.danger ? "danger" : "primary"}`} onClick={accept}>{d.kind === "alert" ? "OK" : d.ok || "OK"}</button>
        </div>
      </div>
    </div>
  );
}
