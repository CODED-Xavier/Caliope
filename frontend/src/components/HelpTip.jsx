import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { helpTexts } from "../helpTexts.js";

/** Small "?" button. Use <HelpTip id="reply_length" />; the text comes from helpTexts.js. */
export default function HelpTip({ id }) {
  const [hover, setHover] = useState(false);
  const [sticky, setSticky] = useState(false);
  const [pos, setPos] = useState({ left: 0, top: 0 });
  const ref = useRef(null);
  const btnRef = useRef(null);
  const info = helpTexts[id];
  const open = hover || sticky;

  // Place the popup with fixed coordinates so scrolling panels never clip it and it stays on screen.
  // Measured after it is drawn (texts differ in length, Portuguese is longer): below the "?", else above, else
  // as high as fits; it never runs off the window.
  const popRef = useRef(null);
  useLayoutEffect(() => {
    if (!open || !btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    const width = 270;
    const h = popRef.current?.offsetHeight || 150;
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    const below = r.bottom + 6;
    const above = r.top - 6 - h;
    const top = below + h <= window.innerHeight - 8 ? below : above >= 8 ? above : Math.max(8, window.innerHeight - 8 - h);
    setPos({ left, top });
  }, [open]);

  useEffect(() => {
    if (!sticky) return undefined;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setSticky(false); };
    const onKey = (e) => { if (e.key === "Escape") setSticky(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [sticky]);

  if (!info) return null;
  return (
    <span className="helptip" ref={ref} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button type="button" className="helptip-btn" ref={btnRef} aria-label={`Help: ${info.title}`} aria-expanded={open}
        onClick={(e) => { e.stopPropagation(); setSticky(!sticky); }}>?</button>
      {open && (
        <span className="helptip-pop" role="tooltip" ref={popRef} style={{ left: pos.left, top: pos.top }}>
          <strong>{info.title}</strong>
          <span><b>What it does:</b> {info.what}</span>
          <span><b>When to use it:</b> {info.when}</span>
          <span><b>Speed:</b> {info.cost}</span>
        </span>
      )}
    </span>
  );
}
