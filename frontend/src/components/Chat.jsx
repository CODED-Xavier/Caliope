import React, { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Markdown } from "../markdown.jsx";

const Message = memo(function Message({ m, isLast, isLastAssistant, onRegenerate, canAct, lastContext }) {
  const [copied, setCopied] = useState(false);
  if (m.role === "user") {
    const isDice = m.content.startsWith("\u{1F3B2}");
    return (
      <div className="msg user">
        <div className={`bubble ${isDice ? "dice" : ""}`}>
          <Markdown text={m.content} />
        </div>
      </div>
    );
  }
  const changes = m.meta?.changes || [];
  return (
    <div className="msg assistant">
      {m.meta?.opening && <div className="tag">Opening scene</div>}
      <Markdown text={m.content} />
      {m.meta?.interrupted && <div className="muted small">⏹ Stopped early</div>}
      {changes.length > 0 && (
        <div className="chips">
          {changes.map((c, i) => <span key={i} className="chip">{c}</span>)}
        </div>
      )}
      {isLastAssistant && lastContext && (lastContext.skills.length > 0 || lastContext.memories.length > 0) && (
        <div className="muted small ctx">
          {lastContext.skills.length > 0 && <>🧩 {lastContext.skills.join(", ")} </>}
          {lastContext.memories.length > 0 && <>🧠 {lastContext.memories.length} memor{lastContext.memories.length === 1 ? "y" : "ies"} recalled</>}
        </div>
      )}
      <div className="msg-actions">
        <button className="icon-btn" title="Copy" onClick={() => { navigator.clipboard?.writeText(m.content); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>
          {copied ? "✓" : "⧉"}
        </button>
        {isLast && canAct && !m.meta?.opening && (
          <button className="icon-btn" title="Regenerate this reply" onClick={onRegenerate}>↻</button>
        )}
      </div>
    </div>
  );
});

const PHASES = { thinking: "Thinking…", writing: "", saved: "", updating: "Updating sheet and memories…" };

export default function Chat({ game, stream, busy, error, lastContext, onSend, onStop, onRegenerate, onDismissError }) {
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
              onRegenerate={onRegenerate} canAct={!busy} lastContext={busy ? null : lastContext} />
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
              {stream.context && (stream.context.skills.length > 0 || stream.context.memories.length > 0) && (
                <div className="muted small ctx">
                  {stream.context.skills.length > 0 && <>🧩 {stream.context.skills.join(", ")} </>}
                  {stream.context.memories.length > 0 && <>🧠 {stream.context.memories.length} memories </>}
                </div>
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
