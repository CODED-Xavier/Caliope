import React, { useEffect, useRef, useState } from "react";
import Modal from "./Modal.jsx";
import HelpTip from "./HelpTip.jsx";
import { api, streamPost } from "../api.js";
import { Markdown } from "../markdown.jsx";
import { MODE_LABELS } from "../utils.js";

/** The Muse: a writer's room with the model, and "Make it a card". */
export default function MuseModal({ onClose, onCardAdded }) {
  const [talks, setTalks] = useState([]);
  const [talk, setTalk] = useState(null);
  const [text, setText] = useState("");
  const [stream, setStream] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [card, setCard] = useState(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const bottom = useRef(null);

  const loadList = () => api.museTalks().then(setTalks).catch((e) => setErr(e.message));
  useEffect(() => { loadList(); }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [talk?.messages?.length, stream, progress]);

  const open = async (id) => { setCard(null); setNote(""); setErr(""); try { setTalk(await api.museTalk(id)); } catch (e) { setErr(e.message); } };
  const fresh = async () => { const t = await api.museCreate(); await loadList(); open(t.id); };

  const send = async () => {
    const content = text.trim();
    if (!content || busy || !talk) return;
    setBusy(true); setErr(""); setStream(""); setText("");
    try {
      await streamPost(`/api/muse/${talk.id}/message`, { content }, (ev) => {
        if (ev.type === "user_message") setTalk((t) => ({ ...t, messages: [...t.messages, ev.message] }));
        else if (ev.type === "token") setStream((s) => s + ev.text);
        else if (ev.type === "muse_message") { setStream(""); setTalk((t) => ({ ...t, messages: [...t.messages, ev.message] })); }
        else if (ev.type === "error") setErr(ev.message);
      });
    } catch (e) { setErr(e.message); }
    setBusy(false); setStream(""); loadList();
  };

  const makeCard = async () => {
    if (busy || !talk) return;
    setBusy(true); setErr(""); setCard(null); setNote(""); setProgress("Starting…");
    try {
      await streamPost(`/api/muse/${talk.id}/card`, {}, (ev) => {
        if (ev.type === "progress") setProgress(ev.step);
        else if (ev.type === "card") setCard(ev.card);
        else if (ev.type === "error") setErr(ev.message);
      });
    } catch (e) { setErr(e.message); }
    setBusy(false); setProgress("");
  };

  const addCard = async () => {
    try { const saved = await api.createScenario(card); setNote(`"${saved.name}" is in Calíope now: find it in New game (✎ to edit it).`); onCardAdded?.(); } catch (e) { setErr(e.message); }
  };
  const saveFile = async () => {
    try {
      const data = await api.cardFile(card);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${(card.name || "card").replace(/[^\w\- ]+/g, "").trim() || "card"}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      setNote("Saved as a card file (Character Card JSON). Import it any time with New game › Import a card.");
    } catch (e) { setErr(e.message); }
  };
  const undo = async () => { if (!busy && talk) setTalk(await api.museUndo(talk.id)); };
  const remove = async (t) => {
    if (!window.confirm(`Delete the talk "${t.title}"?`)) return;
    await api.museDelete(t.id); if (talk?.id === t.id) setTalk(null); loadList();
  };

  return (
    <Modal title="🪶 The Muse" onClose={onClose} wide>
      <div className="muse">
        <div className="muse-list">
          <button className="btn primary small" onClick={fresh} disabled={busy}>＋ New talk</button>
          {talks.map((t) => (
            <div key={t.id} className={`conv ${talk?.id === t.id ? "active" : ""}`} onClick={() => !busy && open(t.id)}>
              <div className="conv-title">{t.title}</div>
              <div className="row center"><span className="muted tiny grow">{t.messages} messages</span>
                <button className="icon-btn" title="Delete" onClick={(e) => { e.stopPropagation(); remove(t); }}>✕</button></div>
            </div>
          ))}
          {!talks.length && <div className="muted tiny">Your talks with the Muse are kept here.</div>}
        </div>
        <div className="muse-main">
          {!talk ? (
            <div className="muted muse-empty">
              <p><HelpTip id="muse" /> Talk with the Muse like with a co-writer: worlds, characters, a new route for a card, a twist for your campaign.</p>
              <p>When the idea is ready, <b>✨ Make it a card</b> turns the talk into a card you can play.</p>
              <button className="btn primary" onClick={fresh}>＋ Start a talk</button>
            </div>
          ) : (
            <>
              <div className="muse-msgs">
                {talk.summary && <details className="muted tiny"><summary>Earlier in this talk (summary)</summary><Markdown text={talk.summary} /></details>}
                {talk.messages.map((m) => (
                  <div key={m.id} className={`msg ${m.role === "user" ? "user" : "assistant"}`}>
                    <div className="bubble"><Markdown text={m.content} /></div>
                  </div>
                ))}
                {stream && <div className="msg assistant"><div className="bubble"><Markdown text={stream} /></div></div>}
                {busy && !stream && <div className="muted small"><span className="spinner" /> {progress || "The Muse is thinking…"}</div>}
                {card && <CardPreview card={card} onAdd={addCard} onSave={saveFile} onDiscard={() => setCard(null)} />}
                {note && <div className="ok-text small">{note}</div>}
                {err && <div className="error-text small">{err}</div>}
                <div ref={bottom} />
              </div>
              <div className="composer">
                <textarea rows={2} value={text} placeholder="Tell the Muse your idea, or ask her for one…" disabled={busy}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
                <button className="send" disabled={busy || !text.trim()} onClick={send}>↑</button>
              </div>
              <div className="row gap center muse-actions">
                <button className="btn small" disabled={busy || !talk.messages.length} onClick={undo} title="Remove her last answer (and your message) to ask differently">↶ Undo last</button>
                <span className="grow" />
                <button className="btn small primary" disabled={busy || !talk.messages.length} onClick={makeCard}>✨ Make it a card</button>
              </div>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}

function CardPreview({ card, onAdd, onSave, onDiscard }) {
  return (
    <div className="card muse-card">
      <div className="row gap center"><strong className="grow">{card.name}</strong><span className="tag">{MODE_LABELS[card.mode] || card.mode}</span></div>
      <div className="small">{card.description}</div>
      <details><summary className="small">World</summary><div className="small pre">{card.world}</div></details>
      {card.tone && <div className="muted tiny">Tone: {card.tone}</div>}
      <div className="small"><b>Characters:</b> {(card.npcs || []).map((n) => n.name).join(", ") || "none"}</div>
      {(card.npcs || []).length > 0 && (
        <details><summary className="small">Character sheets</summary>
          {card.npcs.map((n) => (
            <div key={n.name} className="small" style={{ margin: "6px 0" }}>
              <b>{n.name}</b>: {n.description}<br /><span className="muted">{n.personality}</span>
            </div>
          ))}
        </details>
      )}
      <details><summary className="small">Opening</summary><div className="small pre">{card.opening_message}</div></details>
      <div className="row gap end">
        <button className="btn small" onClick={onDiscard}>Discard</button>
        <button className="btn small" onClick={onSave}>⤓ Save file</button>
        <button className="btn small primary" onClick={onAdd}>＋ Add to Calíope</button>
      </div>
    </div>
  );
}
