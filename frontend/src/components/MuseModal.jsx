import React, { useEffect, useRef, useState } from "react";
import { ask } from "../dialogs.jsx";
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
  const [chars, setChars] = useState(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [research, setResearch] = useState(false);
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

  const makeChars = async () => {
    if (busy || !talk) return;
    setBusy(true); setErr(""); setCard(null); setChars(null); setNote(""); setProgress("Starting…");
    try {
      await streamPost(`/api/muse/${talk.id}/characters`, {}, (ev) => {
        if (ev.type === "progress") setProgress(ev.step);
        else if (ev.type === "characters") setChars(ev.npcs);
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
    if (!await ask.confirm(`Delete the talk "${t.title}"?`)) return;
    await api.museDelete(t.id); if (talk?.id === t.id) setTalk(null); loadList();
  };

  return (
    <Modal title="🪶 The Muse" onClose={onClose} wide>
      <div className="muse">
        <div className="muse-list">
          <button className="btn primary small" onClick={fresh} disabled={busy}>＋ New talk</button>
          <button className="btn small" onClick={() => setResearch(true)} disabled={busy} title="Draft a card from a work's fan wiki">📚 Research a work</button>
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
          {research && (
            <ResearchPanel talkId={talk?.id} busy={busy} setBusy={setBusy}
              onClose={() => setResearch(false)} onError={setErr}
              onCard={async (c) => { setCard(c); setResearch(false); if (talk) setTalk(await api.museTalk(talk.id)); }}
              onChars={(npcs) => { setChars(npcs); setResearch(false); }} />
          )}
          {!talk && !research && card && <CardPreview card={card} onAdd={addCard} onSave={saveFile} onDiscard={() => setCard(null)} />}
          {!talk && chars && <CharactersPreview npcs={chars} onDone={(msg) => { setChars(null); setNote(msg); }} onError={setErr} onDiscard={() => setChars(null)} />}
          {!talk && (note || err) && <div className={`${err ? "error-text" : "ok-text"} small`}>{err || note}</div>}
          {research ? null : !talk ? (
            <div className="muted muse-empty">
              <p><HelpTip id="muse" /> Talk with the Muse like with a co-writer: worlds, characters, a new route for a card, a twist for your campaign.</p>
              <p>When the idea is ready, <b>✨ Make it a card</b> turns the talk into a card you can play.</p>
              <p><b>📚 Research a work</b> drafts a card from an existing anime, game or book series: its fan wiki's world, characters and lore.</p>
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
                {chars && <CharactersPreview npcs={chars} onDone={(msg) => { setChars(null); setNote(msg); }} onError={setErr} onDiscard={() => setChars(null)} />}
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
                <button className="btn small" disabled={busy || !talk.messages.length} onClick={makeChars} title="Write sheets for the characters of this talk and add them to one of your cards">👥 Add characters to a card</button>
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

function CharactersPreview({ npcs, onDone, onError, onDiscard }) {
  const [cards, setCards] = useState([]);
  const [target, setTarget] = useState("");
  const [pick, setPick] = useState(() => npcs.map(() => true));
  useEffect(() => { api.scenarios().then((l) => { setCards(l); if (l[0]) setTarget(String(l[0].id)); }).catch(() => {}); }, []);
  const add = async () => {
    try {
      const chosen = npcs.filter((_, i) => pick[i]);
      const r = await api.mergeCharacters(target, chosen);
      const name = cards.find((c) => String(c.id) === target)?.name || "the card";
      onDone(`${name}: ${r.added.length ? `added ${r.added.join(", ")}` : ""}${r.added.length && r.updated.length ? "; " : ""}${r.updated.length ? `filled in ${r.updated.join(", ")}` : ""}. Games using the card have them too.`);
    } catch (e) { onError(e.message); }
  };
  return (
    <div className="card muse-card">
      <strong>Characters from this talk</strong>
      {npcs.map((n, i) => (
        <label key={n.name} className="check small" style={{ alignItems: "flex-start" }}>
          <input type="checkbox" checked={pick[i]} onChange={(e) => setPick((p) => p.map((v, j) => (j === i ? e.target.checked : v)))} />
          <span><b>{n.name}</b>: {n.description}<br /><span className="muted">{n.personality}{n.speech_style ? ` · ${n.speech_style}` : ""}</span></span>
        </label>
      ))}
      <div className="muted tiny">A character with the same name already in the card (for example one added from your pictures folder) keeps its pictures and anything written; only its empty boxes are filled.</div>
      <div className="row gap center">
        <select className="field grow" value={target} onChange={(e) => setTarget(e.target.value)}>
          {cards.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <button className="btn small" onClick={onDiscard}>Discard</button>
        <button className="btn small primary" disabled={!target || !pick.some(Boolean)} onClick={add}>＋ Add to this card</button>
      </div>
    </div>
  );
}

/** 📚 Research a work: find its fan wiki, tick the pages, and draft a card from them. */
function ResearchPanel({ talkId, busy, setBusy, onClose, onError, onCard, onChars }) {
  const [query, setQuery] = useState("");
  const [wiki, setWiki] = useState(null);
  const [work, setWork] = useState("");
  const [pickC, setPickC] = useState({});
  const [pickL, setPickL] = useState({});
  const [step, setStep] = useState("");
  const [built, setBuilt] = useState(null);
  const [links, setLinks] = useState(""); // 🔗 any web pages, one per line
  const [linksName, setLinksName] = useState("");
  const fromLinks = async () => {
    setBusy(true); setStep("Starting…"); setBuilt(null); onError("");
    try {
      await streamPost("/api/research/links", { links, work: linksName.trim(), talk_id: talkId || null }, (ev) => {
        if (ev.type === "progress") setStep(ev.step);
        else if (ev.type === "card") setBuilt(ev.card);
        else if (ev.type === "error") onError(ev.message);
      });
    } catch (e) { onError(e.message); }
    setBusy(false); setStep("");
  };
  const find = async () => {
    if (!query.trim() || busy) return;
    setBusy(true); setStep("Looking for the wiki…"); setWiki(null); setBuilt(null); onError("");
    try {
      const r = await api.researchFind(query.trim());
      setWiki(r); setWork(r.work || "");
      setPickC(Object.fromEntries(r.characters.map((p, i) => [p.title, i < 12])));
      setPickL(Object.fromEntries(r.lore.map((p, i) => [p.title, i < 10])));
    } catch (e) { onError(e.message); }
    setBusy(false); setStep("");
  };
  const build = async () => {
    setBusy(true); setStep("Starting…"); onError("");
    try {
      await streamPost("/api/research/build", {
        api: wiki.api, sitename: wiki.sitename, work, talk_id: talkId || null,
        characters: Object.keys(pickC).filter((t) => pickC[t]), lore: Object.keys(pickL).filter((t) => pickL[t]),
      }, (ev) => {
        if (ev.type === "progress") setStep(ev.step);
        else if (ev.type === "card") setBuilt(ev.card);
        else if (ev.type === "error") onError(ev.message);
      });
    } catch (e) { onError(e.message); }
    setBusy(false); setStep("");
  };
  const list = (pages, pick, setPick) => (
    <div className="research-list">
      {pages.map((p) => (
        <label key={p.title} className="check small">
          <input type="checkbox" checked={!!pick[p.title]} onChange={(e) => setPick((x) => ({ ...x, [p.title]: e.target.checked }))} />
          <span>{p.title}</span>
        </label>
      ))}
      {!pages.length && <div className="muted tiny">None found.</div>}
    </div>
  );
  const count = (pick) => Object.values(pick).filter(Boolean).length;
  return (
    <div className="card research">
      <div className="row gap center"><strong className="grow">📚 Research a work</strong><button className="icon-btn" onClick={onClose} title="Close">✕</button></div>
      <div className="muted tiny">The Muse reads the work's fan wiki (Fandom or another MediaWiki wiki) and drafts a card: the world, the characters with their personality and looks, and a lorebook. Needs the internet. The wiki's text is shared by its authors (CC BY-SA); the card is for your own games.</div>
      <div className="row gap">
        <input className="field grow" value={query} placeholder="Jujutsu Kaisen, or the wiki's address" onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") find(); }} disabled={busy} />
        <button className="btn small primary" onClick={find} disabled={busy || !query.trim()}>Find the wiki</button>
      </div>
      {!wiki && !built && (
        <details className="research-links">
          <summary className="small">🔗 Or read the pages you choose (any site)</summary>
          <div className="muted tiny">One link per line. Start a line with <code>world:</code>, <code>character:</code> or <code>lore:</code> to say what it is; otherwise pages with Personality / Appearance / Abilities become characters, the first page the world, the rest lore. Up to 30 pages.</div>
          <input className="field" placeholder="Name of the work (optional)" value={linksName} onChange={(e) => setLinksName(e.target.value)} disabled={busy} />
          <textarea className="field" rows={5} value={links} onChange={(e) => setLinks(e.target.value)} disabled={busy}
            placeholder={"world: https://en.wikipedia.org/wiki/Jujutsu_Kaisen\ncharacter: https://jujutsu-kaisen.fandom.com/wiki/Satoru_Gojo\nlore: https://jujutsu-kaisen.fandom.com/wiki/Cursed_Energy"} />
          <button className="btn small primary" disabled={busy || !/https?:\/\//.test(links)} onClick={fromLinks}>✨ Draft the card from these pages</button>
        </details>
      )}
      {step && <div className="muted small"><span className="spinner" /> {step}</div>}
      {wiki && !built && (
        <>
          <div className="small">{`Found: ${wiki.sitename}`}</div>
          <label className="lbl">The work's own page (for the world)<input className="field" value={work} onChange={(e) => setWork(e.target.value)} /></label>
          <div className="row gap research-cols">
            <div className="grow"><div className="lbl">{`Characters (${count(pickC)})`}</div>{list(wiki.characters, pickC, setPickC)}</div>
            <div className="grow"><div className="lbl">{`Lore (${count(pickL)})`}</div>{list(wiki.lore, pickL, setPickL)}</div>
          </div>
          <div className="muted tiny">The biggest pages come first: usually the main characters and the key ideas. Up to 40 pages.</div>
          <button className="btn small primary" disabled={busy || !(count(pickC) + count(pickL))} onClick={build}>✨ Draft the card</button>
        </>
      )}
      {built && (
        <>
          <div className="ok-text small">{`Drafted "${built.name}": ${built.npcs.length} characters and ${built.lorebook.entries.length} lorebook entries.`}</div>
          <div className="row gap wrap">
            <button className="btn small primary" onClick={() => onCard(built)}>See the card</button>
            <button className="btn small" disabled={!built.npcs.length} onClick={() => onChars(built.npcs)}>👥 Add these characters to a card</button>
          </div>
          <div className="muted tiny">The card has no opening yet: write one in the card editor (✨ Draft), or ask the Muse. ✨ Fill can add speech styles.</div>
        </>
      )}
    </div>
  );
}
