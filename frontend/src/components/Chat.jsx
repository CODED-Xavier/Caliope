import React, { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Markdown } from "../markdown.jsx";

const Message = memo(function Message({ m, isLast, isLastAssistant, onRegenerate, canAct, lastContext, onEdit, onResend, onRewind }) {
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
      {canAct && !isLast && <button className="icon-btn" title="Rewind: delete everything after this message" onClick={() => onRewind(m.id, false)}>⏪</button>}
      {canAct && !isOpening && <button className="icon-btn" title="Delete this message and everything after it" onClick={() => onRewind(m.id, true)}>🗑</button>}
    </div>
  );

  if (isUser) {
    const isDice = m.content.startsWith("\u{1F3B2}");
    return (
      <div className="msg user">
        <div className="user-col">
          {editing ? editor : (
            <>
              <div className={`bubble ${isDice ? "dice" : ""}`}><Markdown text={m.content} /></div>
              {m.meta?.edited && <div className="muted tiny edited">edited</div>}
              {actions}
            </>
          )}
        </div>
      </div>
    );
  }

  const changes = m.meta?.changes || [];
  return (
    <div className="msg assistant">
      {isOpening && <div className="tag">Opening scene</div>}
      {editing ? editor : (
        <>
          <Markdown text={m.content} />
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
          {isLastAssistant && lastContext && lastContext.memories.length > 0 && (
            <div className="muted small ctx">🧠 {lastContext.memories.length} memor{lastContext.memories.length === 1 ? "y" : "ies"} recalled</div>
          )}
          {actions}
        </>
      )}
    </div>
  );
});

const PHASES = { thinking: "Thinking…", writing: "", saved: "", updating: "Updating sheet and memories…" };

export default function Chat({ game, stream, busy, error, lastContext, onSend, onStop, onRegenerate, onDismissError, onEdit, onResend, onRewind }) {
  const [text, setText] = useState("");
  const scrollRef = useRef(null);
  const nearBottom = useRef(true);
  const taRef = useRef(null);
  const messages = game.messages;
  const lastAssistantIdx = (() => { for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "assistant") return i; return -1; })();

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && nearBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages.length, stream?.text, stream?.phase]);

  useEffect(() => { nearBottom.current = true; }, [game.conversation.id]);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [text]);

  const submit = () => {
    const t = text.trim();
    if (!t || busy) return;
    setText("");
    nearBottom.current = true;
    onSend(t);
  };

  return (
    <div className="chat">
      <div className="chat-scroll" ref={scrollRef} onScroll={(e) => {
        const el = e.currentTarget;
        nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      }}>
        <div className="chat-inner">
          {messages.map((m, i) => (
            <Message key={m.id} m={m} isLast={i === messages.length - 1} isLastAssistant={i === lastAssistantIdx}
              onRegenerate={onRegenerate} canAct={!busy} lastContext={busy ? null : lastContext}
              onEdit={onEdit} onResend={onResend} onRewind={onRewind} />
          ))}
          {!busy && messages.length > 0 && messages[messages.length - 1].role === "user" && (
            <div className="retry">
              <button className="btn" onClick={onRegenerate}>↻ Generate reply</button>
              <span className="muted small"> The last message has no reply yet (the model may have been offline).</span>
            </div>
          )}
          {stream && (
            <div className="msg assistant streaming">
              {stream.text ? <Markdown text={stream.text} /> : null}
              {stream.phase === "writing" && <span className="cursor">▍</span>}
              {PHASES[stream.phase] && <div className="muted small phase"><span className="spinner" /> {PHASES[stream.phase]}</div>}
              {stream.context && stream.context.memories.length > 0 && (
                <div className="muted small ctx">🧠 {stream.context.memories.length} memories recalled</div>
              )}
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
      <div className="composer-wrap">
        <div className="composer">
          <textarea
            ref={taRef}
            rows={1}
            value={text}
            placeholder="What do you do?  (tip: /roll 1d20+3 rolls dice)"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
            }}
          />
          {busy ? (
            <button className="send stop" onClick={onStop} title="Stop">■</button>
          ) : (
            <button className="send" onClick={submit} disabled={!text.trim()} title="Send">↑</button>
          )}
        </div>
        <div className="composer-hint muted small">Enter to send · Shift+Enter for a new line</div>
      </div>
    </div>
  );
}
