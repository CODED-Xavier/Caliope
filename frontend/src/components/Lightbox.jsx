import React, { useEffect, useState } from "react";

/**
 * Click any picture in the story (portraits, avatars, scene pictures) to see it big.
 * Esc, a click or the ✕ closes it. One listener for the whole app, so every picture gets it.
 */
export default function Lightbox() {
  const [pic, setPic] = useState(null);
  useEffect(() => {
    const onClick = (e) => {
      const img = e.target.closest?.("img");
      if (!img || !img.closest(".msg, .scene-pic") || img.closest("button, a")) return;
      if (!img.naturalWidth) return; // a picture that did not load
      e.preventDefault();
      setPic({ src: img.currentSrc || img.src, alt: img.alt || img.title || "" });
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);
  useEffect(() => {
    if (!pic) return undefined;
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); setPic(null); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [pic]);
  if (!pic) return null;
  return (
    <div className="lightbox" role="dialog" aria-modal="true" onClick={() => setPic(null)}>
      <img src={pic.src} alt={pic.alt} />
      {pic.alt && <div className="lightbox-caption">{pic.alt}</div>}
      <button className="icon-btn lightbox-close" title="Close (Esc)" onClick={() => setPic(null)}>✕</button>
    </div>
  );
}
