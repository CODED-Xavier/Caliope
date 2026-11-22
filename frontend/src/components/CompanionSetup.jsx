import React, { useState } from "react";
import Modal from "./Modal.jsx";
import MoodEditor from "./MoodEditor.jsx";
import { portraitSrc } from "../portraits.js";

const LOOKS = [["race", "Race"], ["hair", "Hair"], ["eyes", "Eyes"], ["build", "Build"], ["outfit", "Clothes"]];

/** A companion's standard face: the Standard mood, else the main picture. */
export function companionFace(npc) {
  const pics = npc?.portraits || {};
  return (pics.moods || []).find((m) => m.n === 1 || /^standard$/i.test(m.label))?.url || pics.default || "";
}

/** The card's companion with the start screen's changes laid over it. */
export function withEdits(npc, edits) {
  const e = edits?.[npc.name];
  return e ? { ...npc, ...e, appearance: { ...(npc.appearance || {}), ...(e.appearance || {}) } } : npc;
}

/**
 * "Set up your companions", opened when you choose to play with companions: like "Create my character here", for
 * each companion: name, background, appearance, personality, and pictures with named moods (Standard, Happy, Sad,
 * Angry, Disgusted, Blushing, or your own). Their Standard picture shows on their first turn in a fight; the moods
 * show in the story, two pictures per reply at most.
 */
export default function CompanionSetup({ team, edits, keep, onDone, onClose }) {
  const [draft, setDraft] = useState(() => Object.fromEntries(team.map((n) => [n.name, {
    name: withEdits(n, edits).name, description: withEdits(n, edits).description || "", personality: withEdits(n, edits).personality || "",
    appearance: { ...(withEdits(n, edits).appearance || {}) }, portraits: withEdits(n, edits).portraits || { default: "", moods: [] },
  }])));
  const [keepOnCard, setKeepOnCard] = useState(keep);
  const set = (of, patch) => setDraft((d) => ({ ...d, [of]: { ...d[of], ...patch } }));
  const done = () => {
    const bad = Object.values(draft).find((e) => !String(e.name || "").trim());
    if (bad) return;
    onDone(draft, keepOnCard);
  };
  const footer = (
    <div className="row gap center wide-row">
      <label className="row gap center small grow"><input type="checkbox" checked={keepOnCard} onChange={(e) => setKeepOnCard(e.target.checked)} />
        Keep them on the card for next games</label>
      <button type="button" className="btn" onClick={onClose}>Cancel</button>
      <button type="button" className="btn primary" onClick={done}>Done</button>
    </div>
  );
  return (
    <Modal title="Set up your companions" wide onClose={onClose} footer={footer}>
      <div className="muted small">Who travels with you. Give each one a face for every mood: their Standard picture shows on their first turn in a fight, and the story shows the mood that fits (two pictures per reply at most).</div>
      {team.map((n) => {
        const e = draft[n.name];
        const face = companionFace(e);
        return (
          <section className="card companion-setup" key={n.name}>
            <div className="row gap center">
              <div className="companion-face">{face ? <img src={portraitSrc(face)} alt="" /> : <span>{(e.name || "?").slice(0, 1)}</span>}</div>
              <div className="grow">
                <label className="lbl">Name</label>
                <input className="field" value={e.name} onChange={(ev) => set(n.name, { name: ev.target.value })} />
                {!String(e.name || "").trim() && <div className="error-text tiny">A companion needs a name.</div>}
              </div>
              {n.sheet?.class && <span className="pill on">{n.sheet.class}</span>}
            </div>
            <label className="lbl">Background</label>
            <textarea className="field" rows={3} value={e.description} onChange={(ev) => set(n.name, { description: ev.target.value })} placeholder="Where they come from, why they travel with you" />
            <label className="lbl">Appearance</label>
            <div className="looks-grid">
              {LOOKS.map(([k, label]) => (
                <input key={k} className="field" placeholder={label} aria-label={label} value={e.appearance[k] || ""}
                  onChange={(ev) => set(n.name, { appearance: { ...e.appearance, [k]: ev.target.value } })} />
              ))}
            </div>
            <label className="lbl">Personality</label>
            <input className="field" value={e.personality} onChange={(ev) => set(n.name, { personality: ev.target.value })} placeholder="Two or three words are enough" />
            <label className="lbl">Pictures and moods</label>
            <MoodEditor portraits={e.portraits} onChange={(v) => set(n.name, { portraits: v })} />
          </section>
        );
      })}
    </Modal>
  );
}
