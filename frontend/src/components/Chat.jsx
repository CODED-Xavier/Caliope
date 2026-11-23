import React, { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { companionFace } from "./CompanionSetup.jsx";
import { Markdown } from "../markdown.jsx";
import { firstMood, hideStatus, moodUrl, portraitSrc, stripTags } from "../portraits.js";
import Story from "./Story.jsx";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";
import { cantoStarts } from "./Cantos.jsx";

/** A picture of the scene, painted by Pollinations.ai the first time it is shown (can take up to a minute). */
/** The round card, with a companion's Standard picture on their first turn in the fight ("[[face: Name]]"). */
function CombatText({ text, npcs }) {
  const parts = String(text || "").split(/\n?\[\[face:\s*([^\]\n]+?)\s*\]\]\n?/);
  return parts.map((part, i) => {
    if (i % 2 === 0) return part.trim() ? <Markdown key={i} text={part} /> : null;
    const low = part.toLowerCase();
    const npc = (npcs || []).find((n) => n.name.toLowerCase() === low) || (npcs || []).find((n) => n.name.toLowerCase().split(" ")[0] === low.split(" ")[0]);
    const face = companionFace(npc);
    return face ? <img key={i} className="combat-face" src={portraitSrc(face)} alt={part} title={part} loading="lazy" /> : null;
  });
}

function ScenePicture({ pic, onReroll, canAct, kept, onKeep }) {
  const [state, setState] = useState("loading");
  const [tries, setTries] = useState(0);
  const [hidden, setHidden] = useState(false);
  useEffect(() => { setState("loading"); setTries(0); }, [pic.url]);
  useEffect(() => { // the free service paints one picture at a time: try again a little later
    if (state !== "error" || tries >= 2) return undefined;
    const t = setTimeout(() => { setTries((n) => n + 1); setState("loading"); }, 30000);
    return () => clearTimeout(t);
  }, [state, tries]);
  if (hidden) return <button className="link-btn tiny muted" onClick={() => setHidden(false)}>🖼 show scene picture</button>;
  return (
    <figure className={`scene-pic ${state}`}>
      {state !== "error" && (
        <img key={tries} src={`${portraitSrc(pic.url)}${tries ? `&try=${tries}` : ""}`} alt={pic.prompt} title={pic.prompt}
          onLoad={() => setState("ok")} onError={() => setState("error")} />
      )}
      {state === "loading" && <div className="scene-wait"><span className="spinner" /> Painting the scene… (up to a minute)</div>}
      {state === "error" && <div className="scene-wait">{tries >= 2 ? "The picture service did not answer. Try 🎲 later." : "The picture service is busy; trying again in 30 s…"}</div>}
      <figcaption>
        {!kept && state === "ok" && <button className="icon-btn" title="Keep it in the map bag (Map tab)" onClick={onKeep}>📌</button>}
        {kept && <span className="tiny muted" title="In the map bag (Map tab)">📌 kept</span>}
        {canAct && !pic.place && <button className="icon-btn" title="Another version of this picture" onClick={onReroll}>🎲</button>}
        <button className="icon-btn" title="Hide" onClick={() => setHidden(true)}>✕</button>
      </figcaption>
    </figure>
  );
}

/** A small round picture beside a message. Hidden when the picture cannot be loaded. */
function Avatar({ url, title, size }) {
  const [failed, setFailed] = useState(false);
  if (!url || failed) return null;
  return <img className={`msg-avatar ${size}`} src={portraitSrc(url)} alt={title} title={title} loading="lazy" onError={() => setFailed(true)} />;
}

/** Character cards: the character's picture beside each reply, in the mood of that reply. */
function speakerAvatar(text, speaker) {
  if (!speaker) return null;
  const mood = firstMood(text);
  return { url: moodUrl(speaker.portraits, mood || ""), mood: mood || "", text: stripTags(text) };
}

const CHECK_KIND = { save: "saving throw", check: "check" };

/** Buttons for the rolls the Aedo just asked for: the app adds the sheet's bonus and tells the Aedo the result. */
function CheckButtons({ checks, onCheck }) {
  return (
    <div className="check-row">
      {checks.map((c, i) => (
        <span key={i} className="check-btn">
          <button className="btn small primary" onClick={() => onCheck(i, "")} title="Roll with the bonus from your sheet; the result goes to the Aedo">
            🎲 {c.skill || c.ability} {CHECK_KIND[c.kind]}{c.dc ? ` (DC ${c.dc})` : ""}
          </button>
          <button className="btn small" title="Roll with advantage (two d20, keep the higher)" onClick={() => onCheck(i, "advantage")}>▲</button>
          <button className="btn small" title="Roll with disadvantage (two d20, keep the lower)" onClick={() => onCheck(i, "disadvantage")}>▼</button>
        </span>
      ))}
    </div>
  );
}

function FightOffer({ fight, onFight, onNoFight }) {
  const foes = fight.enemies.map((e) => (e.count > 1 ? `${e.count}× ${e.name}` : e.name)).join(", ");
  return (
    <div className="fight-offer">
      <span className="small"><b>⚔ A fight!</b> {foes}</span>
      <button className="btn small primary" onClick={() => onFight(fight)}>Start the fight</button>
      <button className="btn small" onClick={() => onNoFight(fight)} title="It isn't a fight (yet)">Not now</button>
    </div>
  );
}

const Message = memo(function Message({ m, npcs, speaker, playerPic, portraitStyle, scenePictures, onPaint, onCheck, onBuy, onFight, onNoFight, fightOpen, currency, isLast, isLastAssistant, onRegenerate, onContinue, canAct, lastContext, onEdit, onResend, onRewind, onFork, onSheet, hit, voiceOn, isSpeaking, onSpeak }) {
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const isUser = m.role === "user";
  const isOpening = !!m.meta?.opening;

  const startEdit = () => { setDraft(m.content); setEditing(true); };
  const save = async () => {
    if (!draft.trim() || saving) return;
    setSaving(true);
    const ok = await onEdit(m.id, draft);
    setSaving(false);
    if (ok) setEditing(false);
  };
  const saveAndResend = () => {
    if (!draft.trim()) return;
    setEditing(false);
    onResend(m.id, draft);
  };

  const editor = (
    <div className="edit-box">
      <textarea
        spellCheck
        className="field" autoFocus rows={Math.min(14, Math.max(3, draft.split("\n").length + 1))} value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setEditing(false);
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); save(); }
        }}
      />
      <div className="row gap end center">
        <span className="muted tiny grow">Ctrl+Enter saves · Esc cancels</span>
        <button className="btn small" onClick={() => setEditing(false)}>Cancel</button>
        <button className="btn small" onClick={save} disabled={saving || !draft.trim()}>Save</button>
        {isUser && <button className="btn small primary" onClick={saveAndResend} disabled={!draft.trim()}>Save and get a new reply</button>}
      </div>
      {isUser && <div className="muted tiny">"Save and get a new reply" removes everything after this message (the sheet goes back to how it was) and writes a new reply.</div>}
      {!isUser && <div className="muted tiny">Editing changes only the text. Sheet changes and memories made from the original reply stay as they are.</div>}
    </div>
  );

  const actions = (
    <div className="msg-actions">
      {!isUser && (
        <button className="icon-btn" title="Copy" onClick={() => { navigator.clipboard?.writeText(m.content); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>
          {copied ? "✓" : "⧉"}
        </button>
      )}
      {canAct && <button className="icon-btn" title="Edit this message" onClick={startEdit}>✎</button>}
      {canAct && !isUser && isLast && !isOpening && <button className="icon-btn" title="Regenerate this reply" onClick={onRegenerate}>↻</button>}
      {canAct && !isUser && isLast && !isOpening && !m.meta?.ooc && <button className="btn small continue-btn" title="Keep writing this reply from where it stopped" onClick={onContinue}>Continue ▸</button>}
      {canAct && !isLast && <button className="icon-btn" title="Rewind: delete everything after this message" onClick={() => onRewind(m.id, false)}>⏪</button>}
      {canAct && !isOpening && <button className="icon-btn" title="Delete this message and everything after it" onClick={() => onRewind(m.id, true)}>🗑</button>}
      {canAct && <button className="icon-btn" title="Save point: start a new game from this moment (this game stays as it is)" onClick={() => onFork(m.id)}>⑂</button>}
      {canAct && isUser && <button className="icon-btn" title="Use this message as my character sheet (fills the Sheet and Status tabs)" onClick={() => onSheet(m.id)}>📋</button>}
      {voiceOn && !isUser && <button className={`icon-btn ${isSpeaking ? "speaking" : ""}`} title={isSpeaking ? "Stop reading" : "Read aloud"} onClick={() => onSpeak(m.id)}>{isSpeaking ? "⏹" : "🔊"}</button>}
      {canAct && scenePictures && !isUser && !m.meta?.scene_picture && !m.meta?.ooc && <button className="icon-btn" title="Paint this scene (Pollinations.ai)" onClick={() => onPaint(m.id)}>🖼</button>}
    </div>
  );

  if (isUser) {
    const isDice = m.content.startsWith("\u{1F3B2}");
    const isCombat = !!m.meta?.combat || m.content.includes("\u2694\uFE0F");
    return (
      <div className={`msg user ${hit || ""}`} data-mid={m.id}>
        {playerPic && portraitStyle !== "off" && <Avatar url={playerPic} title="You" size="small" />}
        <div className="user-col">
          {editing ? editor : (
            <>
              <div className={`bubble ${isDice ? "dice" : ""} ${isCombat ? "combat-card" : ""} ${isCombat || isDice || m.meta?.app_line || (m.content.startsWith("\u2728") || m.content.startsWith("\u{1F4CC}")) ? "app-text" : ""}`}>
                {isCombat ? <CombatText text={m.content} npcs={npcs} /> : <Markdown text={showThoughts(m.content)} story={!isDice} />}
              </div>
              {(m.meta?.moves || []).length > 0 && (
                <div className="sheet-uses app-text">{moveLines(m.meta.moves).map((line, i) => <div key={i}>{line}</div>)}</div>
              )}
              {(m.meta?.fight_lines || []).length > 0 && (
                <div className="sheet-uses app-text">{m.meta.fight_lines.map((line, i) => <div key={i}>{line}</div>)}</div>
              )}
              {(m.meta?.sheet_uses || []).length > 0 && (
                <div className="sheet-uses app-text">{m.meta.sheet_uses.map((u, i) => <div key={i} className={u.ok ? "" : "warn-text"}>{u.line}</div>)}</div>
              )}
              {m.meta?.edited && <div className="muted tiny edited">edited</div>}
              {actions}
            </>
          )}
        </div>
      </div>
    );
  }

  if (m.meta?.ooc) {  // the Aedo's answer outside the story: not part of the story
    return (
      <div className={`msg assistant ooc ${hit || ""}`} data-mid={m.id}>
        <div className="msg-body">
          <div className="tag">{m.meta?.epilogue ? "📜 Epilogue" : "🗨 The Aedo, outside the story"}</div>
          <div className="bubble ooc-bubble"><Markdown text={m.content} /></div>
          {actions}
        </div>
      </div>
    );
  }

  const changes = [...(m.meta?.scene ? [`📍 Scene: ${m.meta.scene}`] : []), ...moveLines(m.meta?.moves), ...(m.meta?.fight_lines || []), ...(m.meta?.changes || [])];  // the adventure moved on
  const av = portraitStyle !== "off" ? speakerAvatar(m.content, speaker) : null;
  return (
    <div className={`msg assistant ${hit || ""} ${av?.url ? `with-avatar ${portraitStyle}` : ""}`} data-mid={m.id}>
      {av?.url && <Avatar url={av.url} title={`${speaker.name}${av.mood ? ` · ${av.mood}` : ""}`} size={portraitStyle === "small" ? "small" : "big"} />}
      <div className="msg-body">
      {isOpening && <div className="tag">Opening scene</div>}
      {editing ? editor : (
        <>
          {m.meta?.scene_picture && portraitStyle !== "off" && <ScenePicture pic={m.meta.scene_picture} canAct={canAct} onReroll={() => onPaint(m.id, true)} kept={!!m.meta.kept_picture} onKeep={() => onPaint(m.id, "keep")} />}
          <Story text={av ? av.text : m.content} npcs={npcs} known={m.meta?.portraits} portraitStyle={portraitStyle} />
          {m.meta?.edited && <span className="muted tiny edited"> (edited)</span>}
          {m.meta?.interrupted && <div className="muted small">⏹ Stopped early</div>}
          {changes.length > 0 && (
            <div className="chips">
              {changes.map((c, i) => <span key={i} className="chip">{c}</span>)}
            </div>
          )}
          {m.meta?.timing && (
            <div className="muted tiny timing" title="Time to first word, writing speed, sheet tracking and total time for this reply">
              ⏱ first word {m.meta.timing.first_word_s}s · writing {m.meta.timing.tokens_per_s} t/s
              {m.meta.timing.tracker_s !== undefined && <> · tracking {m.meta.timing.tracker_s}s</>}
              {m.meta.timing.summary_s !== undefined && <> · summary {m.meta.timing.summary_s}s</>}
              {m.meta.timing.total_s !== undefined && <> · total {m.meta.timing.total_s}s</>}
              {" "}· prompt ~{m.meta.timing.prompt_tokens} tokens
            </div>
          )}
          {isLast && canAct && m.meta?.checks?.length > 0 && <CheckButtons checks={m.meta.checks} onCheck={(i, mode) => onCheck(m.id, i, mode)} />}
          {isLast && canAct && m.meta?.fight && fightOpen && onFight && <FightOffer fight={m.meta.fight} onFight={onFight} onNoFight={onNoFight} />}
          {isLast && canAct && m.meta?.offers?.length > 0 && (
            <div className="check-row">
              {m.meta.offers.map((o, i) => (
                <button key={i} className="btn small" title="Buy one: the app takes the money and puts it in your bag" onClick={() => onBuy(m.id, i)}>
                  🛒 {o.item} · {o.price} {currency}
                </button>
              ))}
            </div>
          )}
          {isLastAssistant && lastContext && lastContext.memories.length > 0 && (
            <div className="muted small ctx">🧠 {lastContext.memories.length} memor{lastContext.memories.length === 1 ? "y" : "ies"} recalled</div>
          )}
          {isLastAssistant && lastContext && lastContext.rules?.length > 0 && (
            <div className="muted small ctx" title={lastContext.rules.join("\n")}>📖 Rules used: {lastContext.rules.join(" · ")}</div>
          )}
          {actions}
        </>
      )}
      </div>
    </div>
  );
});

const PHASES = { thinking: "Thinking…", writing: "", saved: "", updating: "Updating sheet and memories…" };

// In your own messages, thoughts are shown as 💭 in italics (they stay 'single-quoted' in the saved text).
const THOUGHT = /(?<![\w'])'(?=\S)((?:[^'\n]|(?<=\w)'(?=\w))*?[^\s'])'(?!\w)/g;
const showThoughts = (t) => (t.trimStart().startsWith("/") && !/^\s*\/roll/i.test(t)
  ? `🗨 *to the Aedo:* ${t.trimStart().slice(1)}`
  : t.split(/("[^"\n]*")/).map((part, i) => (i % 2 ? part : part.replace(THOUGHT, (_, x) => `*(💭 ${x})*`))).join(""));

// While a reply is being written: hide the status block and any half-written portrait tag at the end.
/** Named techniques the app kept this turn (app/arsenal.py): "✴ New technique: Lilia Valenheart · 『Crimson Fang』". */
const moveLines = (moves) => (moves || []).map((mv) => mv.new
  ? `✴ New technique: ${mv.owner} · 『${mv.name}』`
  : `✴ ${mv.owner} · 『${mv.name}』 (${mv.uses}×)`);

const liveText = (t) => hideStatus(t).replace(/\[\[\s*move\s*:\s*(?:[^|\]\n]*\|)?\s*([^\]\n]*?)\s*\]\]/gi, "**『$1』**")  // a technique being called out
  .replace(/\[\[\s*(?:fight|luta|duel|duelo|spar)\b[^\]\n]*\]\]\n?/gi, "")  // fight marks: counted by the app, not shown
  .replace(/(\[\[[^\]\n]*\]?|!\[[^\n]*)$/, "");

/** How a message is sent: free text (marks as you type them), or one mode for the whole message. */
const MODES = [
  { id: "free", label: "✍ Free", hint: `What do you do?   "speech"   *action*   'thought'   /to the Aedo`,
    who: "Mix as you like: \"speech\", *action*, 'thought', /question to the Aedo." },
  { id: "say", label: "🗣 Speak", hint: "What do you say?", who: "Your character says it aloud: everyone in the scene hears it." },
  { id: "act", label: "✋ Act", hint: "What do you do?", who: "Your character does it: everyone in the scene can see it." },
  { id: "think", label: "💭 Think", hint: "What do you think?", who: "Only the Aedo knows it; characters never hear thoughts." },
  { id: "ask", label: "🗨 Ask the Aedo", hint: "Ask the Aedo (outside the story)…", who: "Out of the story: the Aedo answers you plainly, the characters don't hear it." },
];

function withMode(t, mode) {
  if (!t || mode === "free" || t.startsWith("/")) return t;
  if (mode === "say") return /^["“]/.test(t) ? t : `"${t}"`;
  if (mode === "act") return t.startsWith("*") ? t : `*${t}*`;
  if (mode === "think") return t.startsWith("'") ? t : `'${t}'`;
  if (mode === "ask") return `/${t}`;
  return t;
}

export default function Chat({ game, stream, busy, error, lastContext, onSend, onStop, onRegenerate, onContinue, onDismissError, onEdit, onResend, onRewind, onFork, onSheet, onEpilogue, follow, searchOpen, onCloseSearch, portraitStyle = "big", scenePictures, onPaint, onCheck, onBuy, onFight, onNoFight, voiceOn, speaking, onSpeak }) {
  const [text, setText] = useState("");
  const [fixing, setFixing] = useState(false);
  const [beforeFix, setBeforeFix] = useState(null);
  const [atBottom, setAtBottom] = useState(true);
  const [query, setQuery] = useState("");
  const [hitIdx, setHitIdx] = useState(0);
  const scrollRef = useRef(null);
  const streamRef = useRef(null);
  const nearBottom = useRef(true);
  const anchored = useRef(false); // the start of the new reply was already brought into view
  const taRef = useRef(null);
  const messages = game.messages;
  const dividers = useMemo(() => cantoStarts(game.cantos, messages), [game.cantos, messages]);
  const mode = game.conversation.scenario?.mode;
  const main = game.npcs.find((n) => n.is_main);
  const speaker = mode === "character" && main && (main.portraits?.default || main.portraits?.moods?.length) ? main : null;
  const playerPic = game.state?.player?.portraits?.default || "";
  const streamAv = stream?.text && portraitStyle !== "off" ? speakerAvatar(liveText(stream.text), speaker) : null;
  const lastAssistantIdx = (() => { for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "assistant") return i; return -1; })();

  const toBottom = (smooth) => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  };

  // Opening a game: start at the end.
  useLayoutEffect(() => { nearBottom.current = true; toBottom(false); }, [game.conversation.id]);
  // A new message of yours: show it.
  const lastId = messages[messages.length - 1]?.id;
  const lastRole = messages[messages.length - 1]?.role;
  const waitingReply = useRef(false);
  useLayoutEffect(() => {
    if (lastRole === "user") { toBottom(false); waitingReply.current = true; return; }
    // The reply was saved before the view could stop at its start (a fast reply): show its start now.
    if (lastRole === "assistant" && waitingReply.current) {
      waitingReply.current = false;
      if (!follow && !anchored.current) {
        const el = scrollRef.current;
        const box = el?.querySelector(`[data-mid="${lastId}"]`);
        if (el && box && box.offsetTop - 12 > el.scrollTop) el.scrollTop = box.offsetTop - 12;
      }
      anchored.current = true;
    }
  }, [lastId, lastRole]); // eslint-disable-line
  useEffect(() => { if (!stream) anchored.current = false; }, [stream]);

  // While the AI writes: either follow the text, or stop at the start of the reply so you can read at your pace.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || !stream) return;
    if (follow) {
      if (nearBottom.current) el.scrollTop = el.scrollHeight;
      return;
    }
    const box = streamRef.current;
    if (!anchored.current && box && stream.text) {
      anchored.current = true;
      const top = box.offsetTop - 12;
      if (top > el.scrollTop) el.scrollTop = top;
    }
  }, [stream?.text, stream?.phase, follow]);

  // Chat search
  const q = query.trim().toLowerCase();
  const hits = q.length >= 2 ? messages.filter((m) => m.content.toLowerCase().includes(q)).map((m) => m.id) : [];
  const current = hits.length ? hits[Math.min(hitIdx, hits.length - 1)] : null;
  useEffect(() => { setHitIdx(hits.length ? hits.length - 1 : 0); }, [q]); // eslint-disable-line
  useEffect(() => {
    if (current == null) return;
    scrollRef.current?.querySelector(`[data-mid="${current}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [current]);
  useEffect(() => { if (!searchOpen) setQuery(""); }, [searchOpen]);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [text]);

  const regenerate = () => { waitingReply.current = true; anchored.current = false; onRegenerate(); };

  // The same function objects on every render, so the (memoized) messages do not all redraw on every new word.
  const live = useRef({});
  const check = (...args) => { waitingReply.current = true; anchored.current = false; onCheck?.(...args); };
  const buy = (...args) => { waitingReply.current = true; anchored.current = false; onBuy?.(...args); };
  live.current = { regenerate, onContinue, onFork, onSheet, onPaint, onEdit, onResend, onRewind, check, buy, onSpeak };
  const actions = useMemo(() => {
    const call = (name) => (...args) => live.current[name]?.(...args);
    return { regenerate: call("regenerate"), onContinue: call("onContinue"), onFork: call("onFork"), onSheet: call("onSheet"), onPaint: call("onPaint"),
      onEdit: call("onEdit"), onResend: call("onResend"), onRewind: call("onRewind"), check: call("check"), buy: call("buy"), speak: call("onSpeak") };
  }, []);

  const [epiloguing, setEpiloguing] = useState(false);
  const [sendMode, setSendMode] = useState(() => { try { return localStorage.getItem("caliope.mode") || "free"; } catch { return "free"; } });
  const pickMode = (m) => { setSendMode(m); try { localStorage.setItem("caliope.mode", m); } catch { /* ignore */ } taRef.current?.focus(); };
  const submit = () => {
    const t = withMode(text.trim(), sendMode);
    if (!t || busy) return;
    setText("");
    nearBottom.current = true;
    anchored.current = false;
    waitingReply.current = true;
    onSend(t);
  };

  return (
    <div className="chat">
      {searchOpen && (
        <div className="search-bar">
          <input className="field grow" autoFocus placeholder="Search this story…" value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") onCloseSearch();
              if (e.key === "Enter" && hits.length) setHitIdx((i) => (e.shiftKey ? (i - 1 + hits.length) % hits.length : (i + 1) % hits.length));
            }} />
          <span className="muted small">{q.length >= 2 ? (hits.length ? `${Math.min(hitIdx, hits.length - 1) + 1} / ${hits.length}` : "no match") : ""}</span>
          <button className="icon-btn" title="Previous (Shift+Enter)" disabled={!hits.length} onClick={() => setHitIdx((i) => (i - 1 + hits.length) % hits.length)}>▲</button>
          <button className="icon-btn" title="Next (Enter)" disabled={!hits.length} onClick={() => setHitIdx((i) => (i + 1) % hits.length)}>▼</button>
          <button className="icon-btn" title="Close" onClick={onCloseSearch}>✕</button>
        </div>
      )}
      <div className="chat-scroll" ref={scrollRef} onScroll={(e) => {
        const el = e.currentTarget;
        nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
        if (nearBottom.current !== atBottom) setAtBottom(nearBottom.current);
      }}>
        <div className="chat-inner">
          {messages.map((m, i) => (
            <React.Fragment key={m.id}>
            {dividers[m.id] && <div className="canto-divider"><span>{dividers[m.id].label}{dividers[m.id].title ? ` · ${dividers[m.id].title}` : ""}</span></div>}
            <Message key={m.id} m={m} npcs={game.npcs} speaker={speaker} playerPic={playerPic} portraitStyle={portraitStyle}
              scenePictures={scenePictures} onPaint={actions.onPaint} onCheck={actions.check} onBuy={actions.buy} onFight={onFight} onNoFight={onNoFight}
              fightOpen={!game.state?.combat?.active && !(game.state?.adventure?.fought || []).includes(m.meta?.fight?.scene)} currency={game.conversation.scenario?.currency || "gold"} isLast={i === messages.length - 1} isLastAssistant={i === lastAssistantIdx}
              onRegenerate={actions.regenerate} onContinue={actions.onContinue} onFork={actions.onFork} onSheet={actions.onSheet}
              hit={m.id === current ? "search-hit current" : hits.includes(m.id) ? "search-hit" : ""} canAct={!busy} lastContext={busy ? null : lastContext}
              onEdit={actions.onEdit} onResend={actions.onResend} onRewind={actions.onRewind}
              voiceOn={voiceOn} isSpeaking={speaking === m.id} onSpeak={actions.speak} />
            </React.Fragment>
          ))}
          {!busy && messages.length > 0 && messages[messages.length - 1].role === "user" && (
            <div className="retry">
              <button className="btn" onClick={regenerate}>↻ Generate reply</button>
              <span className="muted small"> The last message has no reply yet (the model may have been offline).</span>
            </div>
          )}
          {!busy && game.state?.finished && !messages.some((x) => x.meta?.epilogue) && (
            <div className="card story-end">
              <b>🏁 The story reached its end.</b>
              <div className="row gap center wrap">
                <button className="btn small primary" disabled={!onEpilogue || epiloguing} onClick={async () => { setEpiloguing(true); await onEpilogue(); setEpiloguing(false); }}>
                  {epiloguing ? "Writing…" : "📜 Write the epilogue"}</button>
                <span className="muted small">You can also keep playing: undo the last reply, or go on after the end.</span>
              </div>
            </div>
          )}
          {stream && (
            <div className={`msg assistant streaming ${streamAv?.url ? `with-avatar ${portraitStyle}` : ""}`} ref={streamRef}>
              {streamAv?.url && <Avatar url={streamAv.url} title={speaker.name} size={portraitStyle === "small" ? "small" : "big"} />}
              <div className="msg-body">
              {stream.continuing && <div className="muted tiny">continuing…</div>}
              {stream.text ? <Story text={streamAv ? streamAv.text : liveText(stream.text)} npcs={game.npcs} portraitStyle={portraitStyle} /> : null}
              {stream.phase === "writing" && <span className="cursor">▍</span>}
              {PHASES[stream.phase] && <div className="muted small phase">{stream.phase === "thinking" ? <span className="typing"><i /><i /><i /></span> : <span className="spinner" />} {PHASES[stream.phase]}</div>}
              {stream.context && stream.context.memories.length > 0 && (
                <div className="muted small ctx">🧠 {stream.context.memories.length} memories recalled</div>
              )}
              </div>
            </div>
          )}
          {error && (
            <div className="error-box">
              <span>⚠ {error}</span>
              <button className="icon-btn" onClick={onDismissError}>✕</button>
            </div>
          )}
        </div>
      </div>
      {!atBottom && (
        <button className="latest-btn" onClick={() => { nearBottom.current = true; toBottom(true); }} title="Go to the latest message">
          ↓ {busy ? "Writing…" : "Latest"}
        </button>
      )}
      <div className="composer-wrap">
        <div className="composer">
          <textarea
            ref={taRef}
            rows={1}
            spellCheck lang={chatLang(game)}
            value={text}
            placeholder={game.state?.combat?.active ? "⚔ In the fight: write your attack (\"I swing at Goblin 2's neck\") or /attack goblin 2. The app rolls it." : MODES.find((x) => x.id === sendMode)?.hint}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
            }}
          />
          {!busy && beforeFix != null && <button className="icon-btn fix-btn" title="Undo the correction" onClick={() => { setText(beforeFix); setBeforeFix(null); }}>↶</button>}
          {!busy && <button className="icon-btn fix-btn" disabled={!text.trim() || fixing} title="✨ Correct my text: spelling and grammar, keeping your words and marks"
            onClick={async () => {
              setFixing(true);
              try { const r = await api.correct(text, chatLang(game)); if (r.text !== text) { setBeforeFix(text); setText(r.text); } } catch (e) { /* keep the text */ }
              setFixing(false);
            }}>{fixing ? "…" : "✨"}</button>}
          {busy ? (
            <button className="send stop" onClick={onStop} title="Stop">■</button>
          ) : (
            <button className="send" onClick={submit} disabled={!text.trim()} title="Send">↑</button>
          )}
        </div>
        <div className="composer-hint muted small">
          <span className="modes">
            {MODES.map((x) => (
              <button key={x.id} className={`mode-chip ${sendMode === x.id ? "on" : ""}`} title={x.who} onClick={() => pickMode(x.id)}>{x.label}</button>
            ))}
          </span>
          <span className="mode-who">{MODES.find((x) => x.id === sendMode)?.who}</span>
          <HelpTip id="writing" /> · {game.state?.combat?.active ? <><span className="mark">/attack</span> · <span className="mark">/dodge</span></> : <span className="mark">/roll 1d20</span>} · Shift+Enter: new line
        </div>
      </div>
    </div>
  );
}


/** The language of this story, for the spell checker (red underline, suggestions on right-click). */
function chatLang(game) {
  const l = game?.conversation?.scenario?.language || game?.language || "";
  return /^pt/i.test(l) ? "pt-BR" : "en";
}
