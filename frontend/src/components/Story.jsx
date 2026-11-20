import React, { memo, useState } from "react";
import { Markdown } from "../markdown.jsx";
import { portraitSrc, splitStory } from "../portraits.js";

function Portrait({ name, mood, url }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null; // no internet or a broken link: just the text
  return (
    <figure className="portrait-big">
      <img src={portraitSrc(url)} alt={`${name} (${mood})`} loading="lazy" onError={() => setFailed(true)} />
      <figcaption>{name}{mood && mood !== "Standard" ? <span className="muted"> · {mood}</span> : null}</figcaption>
    </figure>
  );
}

/** A reply with big character portraits above the part where each character speaks or acts. */
const Story = memo(function Story({ text, npcs, known }) {
  const parts = splitStory(String(text || ""), npcs || [], known || {});
  if (parts.length === 1 && parts[0].type === "text") return <Markdown text={parts[0].text} />;
  return (
    <>
      {parts.map((p, i) => (p.type === "portrait"
        ? <Portrait key={i} name={p.name} mood={p.mood} url={p.url} />
        : p.text.trim() ? <Markdown key={i} text={p.text} /> : null))}
    </>
  );
});

export default Story;
