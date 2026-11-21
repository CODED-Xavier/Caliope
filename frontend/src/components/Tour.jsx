import React, { useEffect, useLayoutEffect, useState } from "react";
import { PcAdvice } from "./ModelsModal.jsx";
import { api } from "../api.js";
import { UI_LANGUAGES, getUiLanguage, setUiLanguage } from "../i18n/index.js";

/** Pick the interface language right in the first step (also in Settings). */
function LangPick() {
  const [cur, setCur] = useState(getUiLanguage());
  // In the tour the story's language follows too (most people play in the language they read); Settings keeps them apart.
  const pick = (id) => { setUiLanguage(id); setCur(id); api.saveSettings({ ui_language: id, response_language: id }).catch(() => {}); };
  return (
    <>
      <div className="row gap no-tr">
        {UI_LANGUAGES.map((l) => (
          <button key={l.id} className={`btn small ${cur === l.id ? "primary" : ""}`} onClick={() => pick(l.id)}>{l.label}</button>
        ))}
      </div>
      <p className="muted tiny">The stories are written in this language too. Settings can set them apart.</p>
    </>
  );
}

/** The first-run tour: a few quick steps over the real interface, skippable at any moment. */
const STEPS = [
  {
    title: "Welcome to Calíope",
    body: (
      <>
        <p>Calíope plays roleplay and tabletop stories with you, entirely on this PC. The game master is <b>the Aedo</b>; you write what your character says and does.</p>
        <p>This tour takes about a minute. You can skip it now and open it again from Settings.</p>
        <LangPick />
      </>
    ),
  },
  {
    target: '[data-tour="models"]',
    title: "1 · Give it a brain: the AI model",
    body: (
      <>
        <p>Calíope needs an AI model on your PC. In <b>🧠 Models</b>:</p>
        <ol>
          <li><b>Download engine</b> (once, about 30 MB).</li>
          <li><b>Find more</b> → search a model → open it → pick the file size shown for your card → <b>Download</b>.</li>
          <li><b>My models</b> → <b>Load</b>. Already have a .gguf model? <b>Browse this PC</b> uses it without a new download.</li>
        </ol>
        <PcAdvice compact />
      </>
    ),
  },
  {
    target: '[data-tour="new"]',
    title: "2 · Start a game",
    body: (
      <>
        <p><b>＋ New game</b> → pick a card (a world to play). <b>👥</b> shows its characters, and some cards let you choose how the story starts.</p>
        <p>Then create your character, or load one of your <b>🎭 Personas</b>.</p>
      </>
    ),
  },
  {
    title: "3 · How to write",
    body: (
      <table className="tour-table"><tbody>
        <tr><td><code>"Hello."</code></td><td>you speak</td></tr>
        <tr><td><code>*I draw my sword*</code></td><td>you act</td></tr>
        <tr><td><code>'He is lying.'</code></td><td>you think (only the Aedo knows)</td></tr>
        <tr><td><code>/how much gold?</code></td><td>a question to the Aedo, outside the story</td></tr>
        <tr><td><code>/roll 1d20+3</code>, <code>/wait until morning</code></td><td>dice, and letting time pass</td></tr>
      </tbody></table>
    ),
  },
  {
    title: "4 · During a game",
    body: (
      <>
        <p>Under each reply: <b>Continue</b>, <b>↻</b> write it again, <b>⏪</b> rewind, <b>🔊</b> read aloud. At the top: <b>↶ Undo</b>, <b>📜 Recap</b>, <b>🎵 Music</b>, <b>Aa</b> for text size and colours.</p>
        <p>The right panel has your <b>Sheet</b>, <b>Bag</b>, <b>People</b> (relationships and notes) and <b>Journal</b> (Cantos, memories). The small <b>‹ ›</b> bubbles on the chat's edges hide the columns.</p>
      </>
    ),
  },
  {
    target: '[data-tour="muse"]',
    title: "5 · The Muse",
    body: <p>A writer's room with the same AI: brainstorm stories and characters, then turn the talk into a new card, or add its characters to one of your cards.</p>,
  },
  {
    target: '[data-tour="settings"]',
    title: "6 · Settings and help",
    body: <p>Every setting has a <b>?</b> that explains it: reply length, narration voice, scene pictures, backups and more.</p>,
  },
  {
    title: "Ready? Get your first model",
    final: true,
    body: (
      <>
        <p>We recommend <b>Stheno 8B</b> (L3-8B-Stheno-v3.2): a roleplay model with a great balance between quality and speed. On an 8 GB card pick the <code>Q4_K_M</code> file (about 5 GB).</p>
        <PcAdvice compact />
      </>
    ),
  },
];

/** `hidden`: a window opened from the tour (for example by clicking the highlighted Models button) is on top;
 * the tour waits on the same step and comes back when it closes. */
export default function Tour({ onDone, onGetModel, hidden = false }) {
  const [i, setI] = useState(0);
  const [box, setBox] = useState(null);
  const step = STEPS[i];

  useLayoutEffect(() => {
    const el = step.target && !hidden ? document.querySelector(step.target) : null;
    if (!el) { setBox(null); return undefined; }
    const place = () => { const r = el.getBoundingClientRect(); setBox({ top: r.top - 6, left: r.left - 6, width: r.width + 12, height: r.height + 12 }); };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [i, hidden]); // eslint-disable-line

  useEffect(() => {
    if (hidden) return undefined;
    const key = (e) => { if (e.key === "Escape") onDone(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onDone, hidden]);

  if (hidden) return null;
  const cardStyle = box
    ? { top: Math.min(Math.max(16, box.top), window.innerHeight - 380), left: Math.min(box.left + box.width + 18, window.innerWidth - 440) }
    : {};
  // Around the highlighted button the screen stays blocked; the button itself can be clicked to try it.
  const blockers = box ? [
    { top: 0, left: 0, right: 0, height: Math.max(0, box.top) },
    { top: box.top + box.height, left: 0, right: 0, bottom: 0 },
    { top: box.top, left: 0, width: Math.max(0, box.left), height: box.height },
    { top: box.top, left: box.left + box.width, right: 0, height: box.height },
  ] : [];
  return (
    <div className={`tour ${box ? "open-spot" : ""}`}>
      {box ? <><div className="tour-spot" style={box} />{blockers.map((b, k) => <div key={k} className="tour-block" style={b} />)}</> : <div className="tour-dim" />}
      <div className={`tour-card ${box ? "" : "center"}`} style={cardStyle}>
        <div className="row center"><b className="grow">{step.title}</b><span className="muted tiny">{i + 1} / {STEPS.length}</span></div>
        <div className="tour-body small">{step.body}</div>
        {box && <div className="muted tiny">Try it: click the highlighted button. The tour waits here.</div>}
        <div className="row gap center">
          <button className="btn small ghost" onClick={onDone}>Skip the tour</button>
          <span className="grow" />
          {i > 0 && <button className="btn small" onClick={() => setI(i - 1)}>‹ Back</button>}
          {step.final ? (
            <>
              <button className="btn small" onClick={onDone}>Later</button>
              <button className="btn small primary" onClick={() => { onDone(); onGetModel("Stheno-v3.2"); }}>⬇ Get Stheno 8B</button>
            </>
          ) : <button className="btn small primary" onClick={() => setI(i + 1)}>Next ›</button>}
        </div>
      </div>
    </div>
  );
}
